"""一个用于检测和通知用户游戏中危险事件的模块。"""

from src.common import config, utils
import time
import os
import cv2
import pygame
import threading
import numpy as np
import keyboard as kb
from src.common.vkeys import press
from src.routine.components import Point


# 小地图上符文的符号
RUNE_RANGES = (
    ((141, 148, 245), (146, 158, 255)),
)
rune_filtered = utils.filter_color(cv2.imread('assets/rune_template.png'), RUNE_RANGES)
RUNE_TEMPLATE = cv2.cvtColor(rune_filtered, cv2.COLOR_BGR2GRAY)

# 小地图上其他玩家的符号
OTHER_RANGES = (
    ((0, 245, 215), (10, 255, 255)),
)
other_filtered = utils.filter_color(cv2.imread('assets/other_template.png'), OTHER_RANGES)
OTHER_TEMPLATE = cv2.cvtColor(other_filtered, cv2.COLOR_BGR2GRAY)

# 精英 boss 的警告标志
ELITE_TEMPLATE = cv2.imread('assets/elite_template.jpg', 0)

# Pollo 消息
POLLO_TEMPLATE = cv2.imread('assets/pollo_template.png', 0)

# Fritto 消息
FRITTO_TEMPLATE = cv2.imread('assets/fritto_template.png', 0)

# Especia 消息
ESPECIA_TEMPLATE = cv2.imread('assets/especia_template.png', 0)

# Twentoona 消息
TWENTOONA_TEMPLATE = cv2.imread('assets/twentoona_template.png', 0)

# Skull Death 左箭头
SKULL_DEATH_LEFT_ARROW_TEMPLATE = cv2.imread('assets/skull_death_left_arrow.png', 0)

# Skull Death 右箭头
SKULL_DEATH_RIGHT_ARROW_TEMPLATE = cv2.imread('assets/skull_death_right_arrow.png', 0)

# Skull Death 血条
SKULL_DEATH_HP_BAR_TEMPLATE = cv2.imread('assets/skull_death_hp_bar.png', 0)

# Skull Death 骷髅头
SKULL_DEATH_SKULL_TEMPLATE = cv2.imread('assets/skull_death_skull.png', 0)

# 测谎仪
LIE_DETECTOR_TEMPLATE = cv2.imread('assets/lie_detector.png', 0)

def get_alert_path(name):
    return os.path.join(Notifier.ALERTS_DIR, f'{name}.mp3')


class Notifier:
    ALERTS_DIR = os.path.join('assets', 'alerts')

    def __init__(self):
        """初始化此 Notifier 对象的主线程。"""

        pygame.mixer.init()
        self.mixer = pygame.mixer.music

        self.ready = False
        self.thread = threading.Thread(target=self._main)
        self.thread.daemon = True

        self.rune_alert_delay = 270         # 4.5 分钟
        self.last_rune_time = 0             # 上一次符文识别的时间

    def start(self):
        """启动此 Notifier 的线程。"""

        print('\n[~] 启动通知器')
        self.thread.start()

    def _main(self):
        self.ready = True
        prev_others = 0
        rune_start_time = time.time()
        gc_counter = 0  # 垃圾回收计数器
        while True:
            if config.enabled:
                frame = config.capture.frame
                if frame is None:
                    time.sleep(0.05)
                    continue
                
                # 检查 frame 是否有效
                if frame.size == 0:
                    time.sleep(0.05)
                    continue
                    
                height, width, _ = frame.shape
                minimap = config.capture.minimap.get('minimap')
                if minimap is None or minimap.size == 0:
                    time.sleep(0.05)
                    continue

                # 仅复制我们需要用于消息/骷髅/精英检查的区域，以便我们可以
                # 在 cv2.matchTemplate 之前释放完整帧（减少峰值内存；
                # 避免当运行许多模板匹配时 OpenCV "内存不足" 错误）。
                try:
                    interrupting_message_frame = frame[height // 4:3 * height // 4, :].copy()
                    del frame  # 在 multi_match 中分配之前释放完整帧引用

                    # 转换为灰度一次并在所有模板匹配中重用，以避免
                    # 为每个 multi_match 调用分配新的灰度数组。
                    interrupting_message_gray = cv2.cvtColor(interrupting_message_frame, cv2.COLOR_BGR2GRAY)
                    del interrupting_message_frame  # 释放彩色帧；我们现在只需要灰度

                    # 限制模板匹配的频率，每2帧执行一次
                    if gc_counter % 2 == 0:
                        # 检查 Pollo 消息
                        try:
                            pollo = utils.multi_match_gray(interrupting_message_gray, POLLO_TEMPLATE, threshold=0.9)
                            if len(pollo) > 0:
                                print("检测到 Pollo 消息")
                                press("esc", 1, down_time=0.1)
                        except Exception as e:
                            print(f"[!] Pollo 检测错误: {e}")

                        # 检查 Fritto 消息
                        try:
                            fritto = utils.multi_match_gray(interrupting_message_gray, FRITTO_TEMPLATE, threshold=0.9)
                            if len(fritto) > 0:
                                print("检测到 Fritto 消息")
                                press("esc", 1, down_time=0.1)
                        except Exception as e:
                            print(f"[!] Fritto 检测错误: {e}")

                        # 检查 Especia 消息
                        try:
                            especia = utils.multi_match_gray(interrupting_message_gray, ESPECIA_TEMPLATE, threshold=0.9)
                            if len(especia) > 0:
                                print("检测到 Especia 消息")
                                press("esc", 1, down_time=0.1)
                        except Exception as e:
                            print(f"[!] Especia 检测错误: {e}")

                        # 检查 Twentoona 消息
                        try:
                            twentoona = utils.multi_match_gray(interrupting_message_gray, TWENTOONA_TEMPLATE, threshold=0.9)
                            if len(twentoona) > 0:
                                print("检测到 Twentoona 消息")
                                press("esc", 1, down_time=0.1)
                        except Exception as e:
                            print(f"[!] Twentoona 检测错误: {e}")

                        # 检查测谎仪
                        try:
                            if LIE_DETECTOR_TEMPLATE is not None:
                                lie_detector = utils.multi_match_gray(interrupting_message_gray, LIE_DETECTOR_TEMPLATE, threshold=0.9)
                                if len(lie_detector) > 0:
                                    print("检测到测谎仪")
                                    os.system('taskkill /f /im "MapleStory.exe"')
                                    os.system(f'taskkill /f /pid {os.getpid()}')
                        except Exception as e:
                            print(f"[!] 测谎仪检测错误: {e}")

                        # 检查 Skull Death
                        try:
                            skull_death_left_arrow = utils.multi_match_gray(interrupting_message_gray, SKULL_DEATH_LEFT_ARROW_TEMPLATE, threshold=0.9)
                            skull_death_right_arrow = utils.multi_match_gray(interrupting_message_gray, SKULL_DEATH_RIGHT_ARROW_TEMPLATE, threshold=0.9)
                            skull_death_hp_bar = utils.multi_match_gray(interrupting_message_gray, SKULL_DEATH_HP_BAR_TEMPLATE, threshold=0.9)
                            skull_death_skull = utils.multi_match_gray(interrupting_message_gray, SKULL_DEATH_SKULL_TEMPLATE, threshold=0.9)
                            if len(skull_death_left_arrow) > 0 or len(skull_death_right_arrow) > 0 or len(skull_death_hp_bar) > 0 or len(skull_death_skull) > 0:
                                print("检测到 Skull Death")
                                # 减少按键次数，避免系统资源占用过高
                                for _ in range(10):
                                    press("left", 1, down_time=0.05)
                                    press("right", 1, down_time=0.05)
                                print("已避免 Skull Death")
                        except Exception as e:
                            print(f"[!] Skull Death 检测错误: {e}")

                        # 检查精英警告：等待7秒，使用 Origin，等待5秒，使用 Ascent（6转技能；不在技能循环中）
                        try:
                            elite = utils.multi_match_gray(interrupting_message_gray, ELITE_TEMPLATE, threshold=0.9)
                            if len(elite) > 0:
                                print("检测到精英 Boss - 使用 Origin 然后 Ascent。")
                                module = getattr(config.bot.command_book, 'module', None) if getattr(config.bot, 'command_book', None) else None
                                if module and hasattr(module, 'Key'):
                                    Key = module.Key
                                    if getattr(Key, 'ORIGIN', None) and getattr(Key, 'ASCENT', None):
                                        time.sleep(7)
                                        press(Key.ORIGIN, 3)
                                        time.sleep(5)
                                        press(Key.ASCENT, 3)
                                        print("已使用 Origin 和 Ascent。")
                                    else:
                                        print("命令书没有 ORIGIN/ASCENT 键。")
                                else:
                                    print("没有为 Origin/Ascent 加载命令书。")
                        except Exception as e:
                            print(f"[!] 精英检测错误: {e}")
                            # 释放内存
                            import gc
                            gc.collect()

                    # 检查其他玩家进入地图
                    try:
                        filtered = utils.filter_color(minimap, OTHER_RANGES)
                        others = len(utils.multi_match_color(filtered, OTHER_TEMPLATE, threshold=0.5))
                        config.stage_fright = others > 0
                        if others != prev_others:
                            if others > prev_others:
                                self._ping('ding')
                            prev_others = others
                    except Exception as e:
                        print(f"[!] 其他玩家检测错误: {e}")

                    # 检查符文
                    now = time.time()
                    rune_start_time = now
                    try:
                        if not config.bot.rune_active:
                            filtered = utils.filter_color(minimap, RUNE_RANGES)
                            matches = utils.multi_match_color(filtered, RUNE_TEMPLATE, threshold=0.9)
                            rune_start_time = now
                            if matches and config.routine.sequence:
                                # 检查两次符文识别的时间间隔
                                # if now - self.last_rune_time < 10 * 60:  # 10分钟
                                #     print("检测到符文时间间隔小于10分钟，执行商城重置操作")
                                #     utils.enter_cash_shop()  # 进入现金商店
                                #     utils.exit_cash_shop()   # 退出现金商店
                                #     print("商城重置操作完成")
                                # 更新上一次符文识别时间
                                self.last_rune_time = now
                                abs_rune_pos = (matches[0][0], matches[0][1])
                                config.bot.rune_pos = utils.convert_to_relative(abs_rune_pos, minimap)
                                distances = list(map(distance_to_rune, config.routine.sequence))
                                index = np.argmin(distances)
                                config.bot.rune_closest_pos = config.routine[index].location
                                config.bot.rune_active = True
                                self._ping('rune_appeared', volume=0.75)
                    except Exception as e:
                        print(f"[!] 符文检测错误: {e}")
                    if now - rune_start_time > self.rune_alert_delay:     # 如果符文未被解决则发出警报
                        config.bot.rune_active = False
                        self._alert('siren')
                except Exception as e:
                    print(f"[!] 通知器处理错误: {e}")
                finally:
                    # 释放内存
                    try:
                        del interrupting_message_gray
                        del minimap
                    except:
                        pass
                    
                # 定期垃圾回收
                gc_counter += 1
                if gc_counter >= 30:
                    import gc
                    gc.collect()
                    gc_counter = 0
                
            # 增加循环间隔，减少内存使用
            time.sleep(0.1)  # 从0.075秒增加到0.1秒，减少处理频率

    def _alert(self, name, volume=0.75):
        """
        播放警报以通知用户危险事件。当绑定到 'Start/stop' 的键被按下时停止警报。
        """

        config.enabled = False
        config.listener.enabled = False
        self.mixer.load(get_alert_path(name))
        self.mixer.set_volume(volume)
        self.mixer.play(-1)
        while not kb.is_pressed(config.listener.config['Start/stop']):
            time.sleep(0.1)
        self.mixer.stop()
        time.sleep(2)
        config.listener.enabled = True

    def _ping(self, name, volume=0.5):
        """非危险事件的快速通知。"""

        self.mixer.load(get_alert_path(name))
        self.mixer.set_volume(volume)
        self.mixer.play()


#################################
#       辅助函数        #
#################################
def distance_to_rune(point):
    """
    计算从 POINT 到符文的距离。
    :param point:   要检查的位置。
    :return:        从 POINT 到符文的距离，如果不是 Point 对象则为无穷大。
    """

    if isinstance(point, Point):
        return utils.distance(config.bot.rune_pos, point.location)
    return float('inf')