"""An interpreter that reads and executes user-created routines."""

import os
import re
import threading
import time
import random
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
        
        # Position monitoring variables
        self.last_position = (0, 0)
        self.position_time = time.time()

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
        gc_counter = 0  # Counter for periodic garbage collection
        
        while True:
            try:
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
                    try:
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
                    except Exception as e:
                        print(f'[!] Error in buff/feed logic: {e}')
                        time.sleep(1)

                    # Position monitoring: jump if player hasn't moved for 10 seconds
                    try:
                        current_pos = config.player_pos
                        if current_pos != (0, 0):  # Only if position is valid
                            distance = utils.distance(current_pos, self.last_position)
                            if distance > settings.move_tolerance:
                                # Player has moved, update last position and time
                                self.last_position = current_pos
                                self.position_time = now
                            elif now - self.position_time > 5:
                                # Player hasn't moved for 5 seconds, perform jump
                                print('[~] Player hasn\'t moved for 5 seconds, performing jump')
                                # Randomly choose left or right direction
                                direction = random.choice(['left', 'right'])
                                # Press direction key and jump
                                key_down(direction)
                                time.sleep(0.1)
                                # Use the jump key from the command book's Key class
                                jump_key = getattr(self.command_book.module.Key, 'JUMP', 'c')
                                press(jump_key, 2)  # Flash jump (2 presses)
                                key_up(direction)
                                time.sleep(0.5)
                                # Update position time after jump
                                self.position_time = now
                    except Exception as e:
                        print(f'[!] Error in position monitoring: {e}')
                        time.sleep(1)

                    # Highlight the current Point
                    try:
                        config.gui.view.routine.select(config.routine.index)
                        config.gui.view.details.display_info(config.routine.index)
                    except Exception as e:
                        print(f'[!] Error in GUI update: {e}')

                    # Execute next Point in the routine
                    try:
                        element = config.routine[config.routine.index]
                        if self.rune_active and isinstance(element, Point) \
                                and element.location == self.rune_closest_pos:
                            self._solve_rune()
                        element.execute()
                        config.routine.step()
                    except Exception as e:
                        print(f'[!] Error in routine execution: {e}')
                        time.sleep(1)
                else:
                    time.sleep(0.01)
                
                # Periodic garbage collection every ~1000 iterations to help free memory
                gc_counter += 1
                if gc_counter >= 1000:
                    import gc
                    gc.collect()
                    gc_counter = 0
            except Exception as e:
                print(f'[!] Critical error in main bot loop: {e}')
                import traceback
                traceback.print_exc()
                # Pause to allow recovery
                time.sleep(5)
                # Try to recalibrate minimap
                try:
                    config.capture.calibrated = False
                except:
                    pass

    @utils.run_if_enabled
    def _solve_rune(self):
        """
        移动到符文位置并解决箭头键谜题。
        使用箭头预测API (环境变量: ARROW_API_URL, PROXY_SECRET)。
        :return:    None
        """
        global attempts
        print("尝试次数: ", str(attempts))
        
        # 获取移动和调整命令
        move = self.command_book['move']
        # 移动到符文位置
        move(*self.rune_pos).execute()
        
        adjust = self.command_book['adjust']
        # 调整视角到符文位置
        adjust(*self.rune_pos).execute()
        time.sleep(0.4)
        adjust(*self.rune_pos).execute()
        time.sleep(0.4)
        
        # 按交互键开始解符文
        press(self.config['Interact'], 1, down_time=0.2)        # 继承自Configurable

        print('\n正在解决符文:')
        solution_found = False
        frame = None
        rune_frame = None
        
        # 尝试3次识别符文
        for i in range(3):
            # 获取当前游戏画面
            rune_frame = config.capture.frame
            # 使用预测API获取符文解决方案
            solution = self.prediction_client.predict_from_frame(rune_frame)

            print(f"解决方案 {i}: {solution}")
            # 检查解决方案是否有效（必须是4个箭头的序列）
            if solution and len(solution) == 4:
                print(', '.join(solution))
                print('找到解决方案，输入结果')
                # 执行箭头键序列
                for arrow in solution:
                    press(arrow, 1, down_time=0.1)
                time.sleep(1)
                
                # 检查符文buff是否出现，确认符文已被成功解决
                for _ in range(3):
                    time.sleep(0.3)
                    frame = config.capture.frame
                    # 在屏幕顶部区域查找符文buff图标
                    rune_buff = utils.multi_match(frame[:frame.shape[0] // 8, :],
                                                 RUNE_BUFF_TEMPLATE,
                                                 threshold=0.7)
                    if rune_buff:
                        # 找到最左边的符文buff图标
                        rune_buff_pos = min(rune_buff, key=lambda p: p[0])
                        # 计算绝对坐标
                        target = (
                            round(rune_buff_pos[0] + config.capture.window['left']),
                            round(rune_buff_pos[1] + config.capture.window['top'])
                        )
                        # 右键点击buff图标
                        click(target, button='right')
                        # 重置尝试次数
                        attempts = 0
                        solution_found = True
                # 标记符文为非活动状态
                self.rune_active = False
                break
        
        # 如果没有找到解决方案且有原始帧，保存失败的检测
        if not solution_found and frame is not None:
            self._save_failed_detection(frame)
        
        # 如果没有找到解决方案且有符文帧，保存失败的检测并重置符文状态
        if not solution_found and rune_frame is not None:
            print("检测到符文失败，尝试进入商城...")
            self._save_failed_detection(rune_frame)
            utils.enter_cash_shop()  # 进入现金商店以重置状态
            print("已尝试进入商城")
            self.rune_active = False  # 标记符文为非活动状态
            utils.exit_cash_shop()  # 退出现金商店
            print("已退出商城")
        
        # 增加尝试次数
        attempts += 1
        
        # 如果尝试次数超过9次，标记符文为非活动状态
        if attempts > 9:
            self.rune_active = False
        
        # 如果尝试次数超过10次，关闭游戏进程和当前进程
        if attempts > 10:
            os.system('taskkill /f /im "MapleStory.exe"')  # 强制关闭MapleStory进程
            os.system(f'taskkill /f /pid {os.getpid()}')  # 强制关闭当前进程

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
