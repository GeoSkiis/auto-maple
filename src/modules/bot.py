"""一个读取并执行用户创建的例程的解释器。"""

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


# 符文的 buff 图标，改为彩色读取，单独匹配彩色模板
RUNE_BUFF_TEMPLATE = cv2.imread('assets/rune_buff_template.jpg', 1)

# 符文 buff 图标的 HSV 颜色范围（根据实际蓝色图标调整）
# HSV 范围格式：[(low_h, low_s, low_v), (high_h, high_s, high_v)]
# 扩大蓝色范围，匹配深浅不同的蓝色，但不匹配灰色（S>70确保是彩色）
RUNE_BUFF_HSV_RANGE = [
    (85, 70, 30),   # 低阈值：H扩大，S适中，V降低（深色）
    (150, 255, 255) # 高阈值：H扩大，S最大，V最大（浅色）
]

# 符文检测失败时保存帧的文件夹（项目根目录）
FAILED_DETECTIONS_FOLDER = "failed_detections"
attempts = 0

class Bot(Configurable):
    """一个解释和执行用户定义例程的类。"""

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
        """在启动时加载用户定义的例程并初始化此 Bot 的主线程。"""

        super().__init__('keybindings')
        config.bot = self

        self.rune_active = False
        self.rune_pos = (0, 0)
        self.rune_closest_pos = (0, 0)      # 最接近符文的点的位置
        self.submodules = []
        self.command_book = None            # CommandBook 实例
        self.prediction_client = ArrowPredictionClient()

        config.routine = Routine()

        self.ready = False
        self.thread = threading.Thread(target=self._main)
        self.thread.daemon = True
        
        # 位置监控变量
        self.last_position = (0, 0)
        self.position_time = time.time()

    def start(self):
        """
        启动此 Bot 对象的线程。
        :return:    None
        """

        self.update_submodules()
        print('\n[~] 启动主 bot 循环')
        self.thread.start()

    def _main(self):
        """
        Bot的主函数，负责执行用户的例程。
        :return:    None
        """

        print('\n[~] 无内置检测算法，已卸载到服务器')

        # 初始化状态
        self.ready = True  # 设置Bot为就绪状态
        config.listener.enabled = True  # 启用监听器
        last_fed = time.time()  # 记录上次喂食宠物的时间
        # 物品 buff 1-4：立即激活（last_used=0）。宠物：等待完整间隔。
        last_item_buff = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}  # 记录各物品buff的上次使用时间
        last_familiar_buff = time.time()  # 记录宠物buff的上次使用时间
        gc_counter = 0  # 周期性垃圾收集的计数器
        
        while True:
            try:
                # 自动例程：当有实时小地图时，从地图匹配解析路径点
                if config.enabled and self.command_book is not None and getattr(config.routine, 'auto_mode', False) and len(config.routine) == 0:
                    config.routine.resolve_auto_routine(
                        skill_rotation_duration=getattr(settings, 'skill_rotation_duration', 5.0),  # 技能轮转持续时间
                        move_tolerance=getattr(settings, 'move_tolerance', 0.075),  # 移动容差
                    )
                    time.sleep(0.5)  # 短暂延迟
                    continue
                
                # 当Bot启用且例程不为空且命令书已加载时
                if config.enabled and len(config.routine) > 0 and self.command_book is not None:
                    now = time.time()  # 当前时间
                    
                    # 增益buff和喂食宠物
                    try:
                        # 减少buff执行频率，每2帧执行一次
                        if gc_counter % 2 == 0:
                            self.command_book.buff.main()  # 执行命令书中的buff方法
                            pet_settings = config.gui.settings.pets  # 获取宠物设置
                            auto_feed = pet_settings.auto_feed.get()  # 获取是否自动喂食
                            num_pets = pet_settings.num_pets.get()  # 获取宠物数量
                            
                            # 自动喂食宠物
                            if auto_feed and now - last_fed > 1200 / num_pets:
                                press(self.config['Feed pet'], 1)  # 按下喂食宠物的按键
                                last_fed = now  # 更新上次喂食时间
                            
                            # 处理物品buff
                            ib = getattr(getattr(getattr(config, 'gui', None), 'settings', None), 'item_buffs', None)
                            ib = ib.settings if ib else None
                            if ib:
                                # 处理1-4号物品buff
                                for i in range(1, 5):
                                    interval = ib.get(f'Item buff {i}')  # 获取buff间隔
                                    # 如果间隔大于0且（首次使用或已超过间隔时间）
                                    if interval > 0 and (last_item_buff[i] == 0 or now - last_item_buff[i] >= interval):
                                        press(self.config[f'Item buff {i}'], 1)  # 按下物品buff按键
                                        time.sleep(1)  # 等待1秒（减少等待时间）
                                        last_item_buff[i] = now  # 更新上次使用时间
                                
                                # 处理宠物药水
                                fam_interval = ib.get('Familiar pot')  # 获取宠物药水间隔
                                if fam_interval > 0 and now - last_familiar_buff >= fam_interval:
                                    press(self.config['Familiar pot'], 1)  # 按下宠物药水按键
                                    time.sleep(1)  # 等待1秒（减少等待时间）
                                    last_familiar_buff = now  # 更新上次使用时间
                    except Exception as e:
                        print(f'[!] buff/喂食逻辑错误: {e}')
                        time.sleep(1)  # 出错后暂停1秒

                    # 位置监控：如果玩家3秒未移动则执行跳跃（仅在执行Adjust或Step时触发）
                    try:
                        if config.executing_movement:
                            current_pos = config.player_pos  # 获取当前玩家位置
                            if current_pos != (0, 0):  # 仅当位置有效时
                                distance = utils.distance(current_pos, self.last_position)  # 计算与上次位置的距离
                                if distance > settings.adjust_tolerance:  # 如果移动距离超过精确容差
                                    # 玩家已移动，更新上次位置和时间
                                    self.last_position = current_pos
                                    self.position_time = now
                                elif now - self.position_time > 3:  # 如果玩家3秒未移动
                                    # 玩家3秒未移动，执行跳跃
                                    print('[~] 玩家3秒未移动，执行跳跃')
                                    # 随机选择左右方向
                                    direction = random.choice(['left', 'right'])
                                    # 按下方向键并跳跃
                                    key_down(direction)
                                    time.sleep(0.05)  # 减少延迟
                                    # 使用命令书中Key类的跳跃键
                                    jump_key = getattr(self.command_book.module.Key, 'JUMP', 'c')
                                    press(jump_key, 1)  # 减少跳跃次数
                                    key_up(direction)  # 释放方向键
                                    time.sleep(0.3)  # 减少延迟
                                    # 跳跃后更新位置时间
                                    self.position_time = now
                    except Exception as e:
                        print(f'[!] 位置监控错误: {e}')
                        time.sleep(1)  # 出错后暂停1秒
                    # 执行例程中的下一个点
                    try:
                        element = config.routine[config.routine.index]
                        if self.rune_active and isinstance(element, Point) \
                                and element.location == self.rune_closest_pos:
                            self._solve_rune()
                        element.execute()
                        config.routine.step()
                    except Exception as e:
                        print(f'[!] 例程执行错误: {e}')
                        time.sleep(1)
                else:
                    time.sleep(0.02)  # 增加空闲时的延迟
                
                # 每约500次迭代进行一次垃圾回收以帮助释放内存
                gc_counter += 1
                if gc_counter >= 500:
                    import gc
                    gc.collect()
                    gc_counter = 0
            except Exception as e:
                print(f'[!] 主bot循环中的严重错误: {e}')
                import traceback
                traceback.print_exc()
                # 暂停以允许恢复
                time.sleep(5)
                # 严重错误后强制进行垃圾回收
                import gc
                gc.collect()
                # 尝试重新校准小地图
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
        time.sleep(1)
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
                # 检查符文buff是否出现，确认符文已被成功解决
                buff_found = False
                for _ in range(3):
                    time.sleep(0.5)
                    frame = config.capture.frame
                    # 直接进行彩色模板匹配（兼容任何颜色的模板，同时匹配颜色和图案）
                    search_region = frame[:frame.shape[0] // 8, :]
                    
                    # 提高阈值，减少误匹配（只匹配颜色和图案都非常相似的）
                    rune_buff = utils.multi_match_color(search_region, RUNE_BUFF_TEMPLATE, threshold=0.88)
                    if rune_buff:
                        # 重置尝试次数
                        print(f"检测到{len(rune_buff)}个符文buff，确认解符文成功")
                        attempts = 0
                        solution_found = True
                        buff_found = True
                        break
                # 如果没有找到足够的buff，不标记为成功
                if not buff_found:
                    print("未检测到足够的符文buff，可能解符文失败")
                    solution_found = False
                # 标记符文为非活动状态
                self.rune_active = False
                break
        
        # 如果没有找到解决方案且有原始帧，保存失败的检测
        if not solution_found and frame is not None:
            self._save_failed_detection(frame)
        
        # 如果没有找到解决方案且有符文帧，保存失败的检测并重置符文状态
        # if not solution_found and rune_frame is not None:
        if not solution_found:
            print("检测到符文失败，尝试进入商城...")
            # self._save_failed_detection(rune_frame)
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
        返回失败检测图像的下一个序号。
        扫描现有的 image_1.png, image_2.png, ... 使编号在重启后保持连续。
        """
        os.makedirs(FAILED_DETECTIONS_FOLDER, exist_ok=True)
        max_num = 0
        for name in os.listdir(FAILED_DETECTIONS_FOLDER):
            m = re.match(r'image_(\d+)\.png', name, re.IGNORECASE)
            if m:
                max_num = max(max_num, int(m.group(1)))
        return max_num + 1

    def _save_failed_detection(self, frame, vertical_offset: int = 50):
        """当符文检测失败时，将帧保存到 failed_detections/image_N.png。裁剪为 640x640，与检测时相同。"""
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
            print(f"已将失败检测保存到 {failed_image_path}")
        except Exception as e:
            print(f"保存失败检测时出错: {e}")

    def load_commands(self, file):
        try:
            self.command_book = CommandBook(file)
            config.gui.settings.update_class_bindings()
        except ValueError:
            pass    # TODO: UI警告弹窗，提示检查命令文件错误

    def update_submodules(self, force=False):
        """
        从子模块仓库拉取更新。如果 FORCE 为 True，
        通过覆盖所有本地更改来重建子模块。
        """

        utils.print_separator()
        print('[~] 获取最新子模块:')
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
                        repo.git.clone(url, path)       # 首次加载子模块
                        print(f" -  初始化子模块 '{path}'")
                    except git.exc.GitCommandError:
                        sub_repo = git.Repo(path)
                        if not force:
                            sub_repo.git.stash()        # 保存修改的内容
                        sub_repo.git.fetch('origin', 'main')
                        sub_repo.git.reset('--hard', 'FETCH_HEAD')
                        if not force:
                            try:                # 恢复修改的内容
                                sub_repo.git.checkout('stash', '--', '.')
                                print(f" -  更新子模块 '{path}'，恢复本地更改")
                            except git.exc.GitCommandError:
                                print(f" -  更新子模块 '{path}'")
                        else:
                            print(f" -  重建子模块 '{path}'")
                        sub_repo.git.stash('clear')
                    i += 3
                else:
                    i += 1
    
    def close(self):
        """关闭资源，释放内存"""
        # 关闭ArrowPredictionClient
        if hasattr(self, 'prediction_client') and self.prediction_client is not None:
            self.prediction_client.close()
            self.prediction_client = None