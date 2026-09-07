"""An interpreter that reads and executes user-created routines."""

import os
import re
import threading
import time
import git
import cv2
from PIL import Image
from src.common import config, settings, utils
from src.detection.detection import ArrowPredictionClient, crop_to_640x640
from src.routine import components
from src.routine.routine import Routine
from src.command_book.command_book import CommandBook
from src.routine.components import Point
from src.common.vkeys import press, click, key_down, key_up
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
        'Feed pet': '9',
        'Item buff 1': 'b',
        'Item buff 2': 'n',
        'Item buff 3': 'm',
        'Item buff 4': ',',
        'Familiar pot': '.',
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
        # Item buffs 1-4: activate immediately (last_used=0). Familiar: wait full interval.
        last_item_buff = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        last_familiar_buff = time.time()
        while True:
            # Auto routine: resolve waypoints from minimap match once we have a live minimap
            if config.enabled and self.command_book is not None and getattr(config.routine, 'auto_mode', False) and len(config.routine) == 0:
                config.routine.resolve_auto_routine(
                    skill_rotation_duration=getattr(settings, 'skill_rotation_duration', 5.0),
                    move_tolerance=getattr(settings, 'move_tolerance', 0.075),
                )
                time.sleep(0.5)
                continue
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
                ib = getattr(getattr(getattr(config, 'gui', None), 'settings', None), 'item_buffs', None)
                ib = ib.settings if ib else None
                if ib:
                    for i in range(1, 5):
                        interval = ib.get(f'Item buff {i}')
                        if interval > 0 and (last_item_buff[i] == 0 or now - last_item_buff[i] >= interval):
                            press(self.config[f'Item buff {i}'], 1)
                            time.sleep(2)
                            last_item_buff[i] = now
                    fam_interval = ib.get('Familiar pot')
                    if fam_interval > 0 and now - last_familiar_buff >= fam_interval:
                        press(self.config['Familiar pot'], 1)
                        time.sleep(2)
                        last_familiar_buff = now

                # Rune interrupt: nearest waypoint replaces current index so we solve without waiting
                # on the next random step to match rune_closest_pos.
                if self.rune_active:
                    rune_i = self._routine_index_closest_to_rune()
                    if rune_i is not None:
                        config.routine.index = rune_i

                # Highlight the current Point
                config.gui.view.routine.select(config.routine.index)
                config.gui.view.details.display_info(config.routine.index)

                element = config.routine[config.routine.index]
                if self.rune_active and isinstance(element, Point):
                    self._solve_rune()
                    if not config.enabled:
                        continue
                element.execute()
                config.routine.step()
            else:
                time.sleep(0.01)

    def _routine_index_closest_to_rune(self):
        """Routine index of the Point nearest to rune minimap coords; None if none."""
        seq = getattr(config.routine, 'sequence', None) or []
        rp = self.rune_pos
        best_i = None
        best_d = float('inf')
        for i, comp in enumerate(seq):
            if isinstance(comp, Point):
                d = utils.distance(rp, comp.location)
                if d < best_d:
                    best_d = d
                    best_i = i
        return best_i

    def _rune_should_continue(self):
        return config.enabled and self.rune_active

    def abort_rune(self):
        """Stop rune alignment/solving immediately and release movement keys."""
        self.rune_active = False
        config.rune_aligning = False
        for key in ('left', 'right', 'up', 'down'):
            key_up(key)

    def _rune_interruptible_sleep(self, duration):
        """Sleep in short slices so Insert (pause) can abort rune logic promptly."""
        end = time.time() + duration
        while time.time() < end:
            if not self._rune_should_continue():
                return False
            time.sleep(min(0.05, max(0.0, end - time.time())))
        return True

    def _rune_rope_escape_jump_left(self):
        """Hold left and jump once (e.g. unstuck from rope) using this class's jump binding."""
        mod = getattr(self.command_book, 'module', None)
        jump_key = getattr(getattr(mod, 'Key', None), 'JUMP', 'space') if mod else 'space'
        key_down('left')
        time.sleep(0.05)
        press(jump_key, 1, down_time=0.08, up_time=0.12)
        key_up('left')
        time.sleep(0.25)

    def _rune_movement_keys(self):
        mod = getattr(self.command_book, 'module', None)
        key_cls = getattr(mod, 'Key', None) if mod else None
        jump_key = getattr(key_cls, 'JUMP', 'space') if key_cls else 'space'
        rope_key = getattr(key_cls, 'ROPE_LIFT', 'c') if key_cls else 'c'
        return jump_key, rope_key

    def _rune_fine_adjust(self, tol=0.04):
        """
        Fine-tune position at a rune without generic Adjust (which rope-lifts on any tiny Y error).
        Horizontal first; downward = down-jump; upward = rope lift only for large Y gaps.
        """
        if not self._rune_should_continue():
            return
        rx, ry = self.rune_pos
        px, py = config.player_pos
        dx = rx - px
        dy = ry - py
        jump_key, rope_key = self._rune_movement_keys()
        rope_min = config.RUNE_VERTICAL_ROPE_MIN

        if abs(dx) > tol:
            direction = 'left' if dx < 0 else 'right'
            print(f"[rune align] horizontal nudge {direction} (dx={dx:.4f})")
            key_down(direction)
            time.sleep(0.05)
            press(jump_key, 1, down_time=0.05, up_time=0.05)
            for _ in range(15):
                if not self._rune_should_continue():
                    break
                if abs(rx - config.player_pos[0]) <= tol:
                    break
                time.sleep(0.05)
            key_up(direction)
            time.sleep(0.1)
            return

        if abs(dy) <= tol:
            return

        if not self._rune_should_continue():
            return

        if dy > 0:
            print(f"[rune align] downward correction (dy={dy:.4f})")
            key_down('down')
            time.sleep(0.05)
            press(jump_key, 2, down_time=0.08, up_time=0.1)
            key_up('down')
            self._rune_interruptible_sleep(0.25)
            return

        if abs(dy) < rope_min:
            print(
                f"[rune align] skip rope lift (|dy|={abs(dy):.4f} < {rope_min}), jump only"
            )
            press(jump_key, 1, down_time=0.05, up_time=0.08)
            self._rune_interruptible_sleep(0.3)
            return

        print(f"[rune align] rope lift for large vertical gap (dy={dy:.4f})")
        press(rope_key, 1)
        self._rune_interruptible_sleep(2.0 if abs(dy) > 0.12 else 1.5)

    def _rune_align_until_stable(self):
        """
        Move/adjust until minimap position is within tolerance of the rune for several
        consecutive checks. Handles rope stuck via jump+left.
        """
        rune_align_tol = 0.04
        max_align_attempts = 20
        align_verify_need = 3
        align_verify_sleep = 0.4
        move = self.command_book['move']
        config.rune_aligning = True
        try:
            if not self._rune_should_continue():
                return
            move(*self.rune_pos).execute()
            if not self._rune_interruptible_sleep(align_verify_sleep):
                return
            align_attempt = 0
            consecutive_in_tol = 0
            stuck_pos_eps = 0.004
            stuck_same_need = 5
            prev_align_pos = None
            stuck_same_count = 0
            while align_attempt < max_align_attempts:
                if not self._rune_should_continue():
                    print("[rune align] aborted (bot paused)")
                    return
                px, py = config.player_pos
                rx, ry = self.rune_pos
                in_tol = abs(px - rx) <= rune_align_tol and abs(py - ry) <= rune_align_tol
                print(
                    f"[rune align] attempt {align_attempt + 1}/{max_align_attempts} "
                    f"player=({px:.4f},{py:.4f}) rune=({rx:.4f},{ry:.4f})"
                )
                if not in_tol:
                    if prev_align_pos is not None:
                        if (abs(px - prev_align_pos[0]) <= stuck_pos_eps
                                and abs(py - prev_align_pos[1]) <= stuck_pos_eps):
                            stuck_same_count += 1
                        else:
                            stuck_same_count = 0
                    prev_align_pos = (px, py)
                    if stuck_same_count >= stuck_same_need:
                        print(
                            f"[rune align] no movement {stuck_same_need}x "
                            f"(eps={stuck_pos_eps}), jump+left to escape rope"
                        )
                        self._rune_rope_escape_jump_left()
                        stuck_same_count = 0
                        prev_align_pos = None
                        consecutive_in_tol = 0
                        if not self._rune_interruptible_sleep(align_verify_sleep):
                            return
                        align_attempt += 1
                        continue
                else:
                    stuck_same_count = 0
                    prev_align_pos = None
                if in_tol:
                    consecutive_in_tol += 1
                    print(
                        f"[rune align] within tol={rune_align_tol} "
                        f"verify {consecutive_in_tol}/{align_verify_need}"
                    )
                    if consecutive_in_tol >= align_verify_need:
                        print(
                            f"[rune align] stable after {align_verify_need} verifies "
                            f"(loop attempt {align_attempt + 1})"
                        )
                        break
                    if not self._rune_interruptible_sleep(align_verify_sleep):
                        return
                else:
                    if consecutive_in_tol:
                        print("[rune align] left tolerance, resetting verify count")
                    consecutive_in_tol = 0
                    self._rune_fine_adjust(tol=rune_align_tol)
                    if not self._rune_interruptible_sleep(align_verify_sleep):
                        return
                align_attempt += 1
            else:
                print(f"[rune align] hit max attempts ({max_align_attempts}), proceeding to interact")
        finally:
            config.rune_aligning = False

    def _rune_try_climb_off_ladder_after_align(self):
        """
        Second-tier escape: if we verified near the rune but were on a ladder, holding up
        will move the minimap position. Hold up until position stops changing, then caller
        should re-align and re-verify.
        """
        if not self._rune_should_continue():
            return False
        stuck_pos_eps = 0.004
        hold_initial = 1.0
        stable_sleep = 0.15
        stable_need = 3
        max_extra_hold = 12.0

        def _moved(a, b):
            return max(abs(a[0] - b[0]), abs(a[1] - b[1])) > stuck_pos_eps

        p0 = config.player_pos
        key_down('up')
        try:
            if not self._rune_interruptible_sleep(hold_initial):
                return False
            p1 = config.player_pos
            if not _moved(p0, p1):
                return False
            print("[rune align] up-key moved player; holding up until climb stops")
            prev = p1
            stable = 0
            t0 = time.time()
            while time.time() - t0 < max_extra_hold:
                if not self._rune_should_continue():
                    return False
                if not self._rune_interruptible_sleep(stable_sleep):
                    return False
                cur = config.player_pos
                if _moved(prev, cur):
                    stable = 0
                    prev = cur
                else:
                    stable += 1
                    if stable >= stable_need:
                        break
            return True
        finally:
            key_up('up')
            time.sleep(0.2)

    @utils.run_if_enabled
    def _solve_rune(self):
        """
        Moves to the position of the rune and solves the arrow-key puzzle.
        Uses the Arrow Prediction API (env: ARROW_API_URL, PROXY_SECRET).
        :return:    None
        """
        global attempts
        if not self._rune_should_continue():
            return
        print("attempt: ", str(attempts))
        self._rune_align_until_stable()
        if not self._rune_should_continue():
            return
        if self._rune_try_climb_off_ladder_after_align():
            print("[rune align] re-aligning after ladder climb-off")
            self._rune_align_until_stable()
        if not self._rune_should_continue():
            return

        print('\nSolving rune:')
        solution_found = False
        frame = None
        rune_frame = None
        for i in range(3):
            if not self._rune_should_continue():
                return
            if not self._rune_interruptible_sleep(0.4):
                return
            press(self.config['Interact'], 1, down_time=0.2)        # Inherited from Configurable
            if not self._rune_interruptible_sleep(0.4):
                return
            rune_frame = config.capture.frame
            solution = self.prediction_client.predict_from_frame(rune_frame)

            print(f"Solution {i}: {solution}")
            if solution and len(solution) == 4:
                print(', '.join(solution))
                print('Solution found, entering result')
                for arrow in solution:
                    if not self._rune_should_continue():
                        return
                    press(arrow, 1, down_time=0.1)
                if not self._rune_interruptible_sleep(3):
                    return
                for _ in range(3):
                    if not self._rune_should_continue():
                        return
                    if not self._rune_interruptible_sleep(0.3):
                        return
                    frame = config.capture.frame
                    rune_buff = utils.multi_match(frame[:frame.shape[0] // 8, :],
                                                 RUNE_BUFF_TEMPLATE,
                                                 threshold=0.7)
                    if rune_buff:
                        rune_buff_pos = min(rune_buff, key=lambda p: p[0])
                        target = (
                            round(rune_buff_pos[0] + config.capture.window['left']),
                            round(rune_buff_pos[1] + config.capture.window['top'])
                        )
                        click(target, button='right')
                        attempts = 0
                        solution_found = True
                self.rune_active = False
                break
        if not self._rune_should_continue():
            return
        if not solution_found and frame is not None:
            self._save_failed_detection(frame)
        if not solution_found and rune_frame is not None:
            self._save_failed_detection(rune_frame)
            utils.enter_cash_shop()
            self.rune_active = False
            utils.exit_cash_shop()
        attempts += 1
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
            auto_path = config.routine.load_auto_for_command_book(self.command_book.name)
            from src.common import session
            session.save(
                command_book_path=os.path.abspath(file),
                routine_path=os.path.abspath(auto_path),
            )
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
