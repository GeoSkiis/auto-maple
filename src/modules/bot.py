"""An interpreter that reads and executes user-created routines."""

import os
import re
import threading
import time
import git
import cv2
from PIL import Image
from src.common import config, utils
from src.detection.detection import ArrowPredictionClient, crop_to_640x640
from src.routine import components
from src.routine.routine import Routine
from src.command_book.command_book import CommandBook
from src.routine.components import Point
from src.common.vkeys import press, click
from src.common.interfaces import Configurable


# The rune's buff icon
RUNE_BUFF_TEMPLATE = cv2.imread('assets/rune_buff_template.jpg', 0)

# Folder for saving frames when rune detection fails (project root)
FAILED_DETECTIONS_FOLDER = "failed_detections"
attempts = 0

class Bot(Configurable):
    """A class that interprets and executes user-defined routines."""

    DEFAULT_CONFIG = {
        'Interact': 'y',
        'Feed pet': '9'
    }

    def __init__(self):
        """Loads a user-defined routine on start up and initializes this Bot's main thread."""

        super().__init__('keybindings')
        config.bot = self

        self.rune_active = False
        self.rune_pos = (0, 0)
        self.rune_closest_pos = (0, 0)      # Location of the Point closest to rune
        self.submodules = []
        self.command_book = None            # CommandBook instance
        self.prediction_client = ArrowPredictionClient()

        config.routine = Routine()

        self.ready = False
        self.thread = threading.Thread(target=self._main)
        self.thread.daemon = True

    def start(self):
        """
        Starts this Bot object's thread.
        :return:    None
        """

        self.update_submodules()
        print('\n[~] Started main bot loop')
        self.thread.start()

    def _main(self):
        """
        The main body of Bot that executes the user's routine.
        :return:    None
        """

        print('\n[~] No detection algorithm onboard, offloaded to a server')

        self.ready = True
        config.listener.enabled = True
        last_fed = time.time()
        while True:
            if config.enabled and len(config.routine) > 0 and self.command_book is not None:
                # Buff and feed pets
                self.command_book.buff.main()
                pet_settings = config.gui.settings.pets
                auto_feed = pet_settings.auto_feed.get()
                num_pets = pet_settings.num_pets.get()
                now = time.time()
                if auto_feed and now - last_fed > 1200 / num_pets:
                    press(self.config['Feed pet'], 1)
                    last_fed = now

                # Highlight the current Point
                config.gui.view.routine.select(config.routine.index)
                config.gui.view.details.display_info(config.routine.index)

                # Execute next Point in the routine
                element = config.routine[config.routine.index]
                if self.rune_active and isinstance(element, Point) \
                        and element.location == self.rune_closest_pos:
                    self._solve_rune()
                element.execute()
                config.routine.step()
            else:
                time.sleep(0.01)

    @utils.run_if_enabled
    def _solve_rune(self):
        """
        Moves to the position of the rune and solves the arrow-key puzzle.
        Uses the Arrow Prediction API (env: ARROW_API_URL, PROXY_SECRET).
        :return:    None
        """
        global attempts
        print("attempt: ", str(attempts))
        move = self.command_book['move']
        move(*self.rune_pos).execute()
        adjust = self.command_book['adjust']
        adjust(*self.rune_pos).execute()
        time.sleep(0.4)
        adjust(*self.rune_pos).execute()
        time.sleep(0.4)
        press(self.config['Interact'], 1, down_time=0.2)        # Inherited from Configurable

        print('\nSolving rune:')
        solution_found = False
        frame = None
        for i in range(3):
            frame = config.capture.frame
            solution = self.prediction_client.predict_from_frame(frame)

            print(f"Solution {i}: {solution}")
            if solution and len(solution) == 4:
                print(', '.join(solution))
                print('Solution found, entering result')
                for arrow in solution:
                    press(arrow, 1, down_time=0.1)
                time.sleep(1)
                for _ in range(3):
                    time.sleep(0.3)
                    rune_buff = utils.multi_match(frame[:frame.shape[0] // 8, :],
                                                 RUNE_BUFF_TEMPLATE,
                                                 threshold=0.9)
                    if rune_buff:
                        rune_buff_pos = min(rune_buff, key=lambda p: p[0])
                        target = (
                            round(rune_buff_pos[0] + config.capture.window['left']),
                            round(rune_buff_pos[1] + config.capture.window['top'])
                        )
                        click(target, button='right')
                        self.rune_active = False
                        attempts = 0
                        solution_found = True
                        break
        if not solution_found and frame is not None:
            self._save_failed_detection(frame)
        attempts += 1
        if attempts % 3 == 0:
            utils.enter_cash_shop()
            utils.exit_cash_shop()
        if attempts > 9:
            self.rune_active = False
        if attempts > 20:
            os.system('taskkill /f /im "MapleStory.exe"')
            os.system(f'taskkill /f /pid {os.getpid()}')

    def _get_next_failed_image_number(self):
        """
        Return the next sequential number for failed detection images.
        Scans existing image_1.png, image_2.png, ... so numbering persists across restarts.
        """
        os.makedirs(FAILED_DETECTIONS_FOLDER, exist_ok=True)
        max_num = 0
        for name in os.listdir(FAILED_DETECTIONS_FOLDER):
            m = re.match(r'image_(\d+)\.png', name, re.IGNORECASE)
            if m:
                max_num = max(max_num, int(m.group(1)))
        return max_num + 1

    def _save_failed_detection(self, frame, vertical_offset: int = 50):
        """Save a frame to failed_detections/image_N.png when rune detection fails. Crops to 640x640 like detection."""
        try:
            os.makedirs(FAILED_DETECTIONS_FOLDER, exist_ok=True)
            next_num = self._get_next_failed_image_number()
            failed_image_path = os.path.join(FAILED_DETECTIONS_FOLDER, f'image_{next_num}.png')
            if frame.ndim == 3 and frame.shape[2] == 4:
                rgb = frame[..., :3][..., ::-1].copy()
            else:
                rgb = frame[..., ::-1].copy()
            img = Image.fromarray(rgb)
            img_cropped = crop_to_640x640(img, vertical_offset=vertical_offset)
            img_cropped.save(failed_image_path)
            print(f"Saved failed detection to {failed_image_path}")
        except Exception as e:
            print(f"Error saving failed detection: {e}")

    def load_commands(self, file):
        try:
            self.command_book = CommandBook(file)
            config.gui.settings.update_class_bindings()
        except ValueError:
            pass    # TODO: UI warning popup, say check cmd for errors

    def update_submodules(self, force=False):
        """
        Pulls updates from the submodule repositories. If FORCE is True,
        rebuilds submodules by overwriting all local changes.
        """

        utils.print_separator()
        print('[~] Retrieving latest submodules:')
        self.submodules = []
        repo = git.Repo.init()
        with open('.gitmodules', 'r') as file:
            lines = file.readlines()
            i = 0
            while i < len(lines):
                if lines[i].startswith('[') and i < len(lines) - 2:
                    path = lines[i + 1].split('=')[1].strip()
                    url = lines[i + 2].split('=')[1].strip()
                    self.submodules.append(path)
                    try:
                        repo.git.clone(url, path)       # First time loading submodule
                        print(f" -  Initialized submodule '{path}'")
                    except git.exc.GitCommandError:
                        sub_repo = git.Repo(path)
                        if not force:
                            sub_repo.git.stash()        # Save modified content
                        sub_repo.git.fetch('origin', 'main')
                        sub_repo.git.reset('--hard', 'FETCH_HEAD')
                        if not force:
                            try:                # Restore modified content
                                sub_repo.git.checkout('stash', '--', '.')
                                print(f" -  Updated submodule '{path}', restored local changes")
                            except git.exc.GitCommandError:
                                print(f" -  Updated submodule '{path}'")
                        else:
                            print(f" -  Rebuilt submodule '{path}'")
                        sub_repo.git.stash('clear')
                    i += 3
                else:
                    i += 1
