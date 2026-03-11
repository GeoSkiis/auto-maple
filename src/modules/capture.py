"""一个用于跟踪游戏内有用信息的模块。"""

import time
import gc
import cv2
import threading
import ctypes
import mss
import mss.windows
import numpy as np
from src.common import config, utils
from ctypes import wintypes
user32 = ctypes.windll.user32
user32.SetProcessDPIAware()


# 小地图顶部到屏幕顶部的距离
MINIMAP_TOP_BORDER = 5

# 小地图其他三个边框的厚度
MINIMAP_BOTTOM_BORDER = 9

# 窗口模式下的像素偏移调整
WINDOWED_OFFSET_TOP = 36
WINDOWED_OFFSET_LEFT = 10

# 小地图的左上角和右下角
MM_TL_TEMPLATE = cv2.imread('assets/minimap_tl_template.png', 0)
MM_BR_TEMPLATE = cv2.imread('assets/minimap_br_template.png', 0)

MMT_HEIGHT = max(MM_TL_TEMPLATE.shape[0], MM_BR_TEMPLATE.shape[0])
MMT_WIDTH = max(MM_TL_TEMPLATE.shape[1], MM_BR_TEMPLATE.shape[1])

# 小地图上的玩家符号
PLAYER_TEMPLATE = cv2.imread('assets/player_template.png', 0)
PT_HEIGHT, PT_WIDTH = PLAYER_TEMPLATE.shape


class Capture:
    """
    一个跟踪玩家位置和各种游戏内事件的类。它不断更新
    config 模块，提供有关这些事件的信息。它还会注释并
    在弹出窗口中显示小地图。
    """

    def __init__(self):
        """初始化此 Capture 对象的主线程。"""

        config.capture = self

        self.frame = None
        self.minimap = {}
        self.minimap_ratio = 1
        self.minimap_sample = None
        self.sct = None
        self.window = {
            'left': 0,
            'top': 0,
            'width': 1366,
            'height': 768
        }

        self.ready = False
        self.calibrated = False
        self.thread = threading.Thread(target=self._main)
        self.thread.daemon = True
        # 重用单个缓冲区进行屏幕截图，以避免每 ~1 毫秒分配 4+ MiB（ArrayMemoryError）。
        self._frame_buffer = None
        self._gc_counter = 0  # 周期性垃圾回收的计数器

    def start(self):
        """启动此 Capture 的线程。"""

        print('\n[~] 启动视频捕获')
        self.thread.start()

    def _main(self):
        """持续监控玩家位置和游戏内事件。"""

        mss.windows.CAPTUREBLT = 0
        while True:
            try:
                # 校准屏幕捕获
                handle = user32.FindWindowW(None, 'MapleStory')
                if not handle:
                    print('[!] 未找到 MapleStory 窗口，等待中...')
                    time.sleep(5)
                    continue
                
                rect = wintypes.RECT()
                user32.GetWindowRect(handle, ctypes.pointer(rect))
                rect = (rect.left, rect.top, rect.right, rect.bottom)
                rect = tuple(max(0, x) for x in rect)

                self.window['left'] = rect[0]
                self.window['top'] = rect[1]
                self.window['width'] = max(rect[2] - rect[0], MMT_WIDTH)
                self.window['height'] = max(rect[3] - rect[1], MMT_HEIGHT)

                # 通过找到小地图的左上角和右下角来校准
                try:
                    with mss.mss() as self.sct:
                        self.frame = self.screenshot()
                    if self.frame is None:
                        continue
                    # 仅在帧的左上角 30% 搜索（小地图总是在那里）
                    h_frame, w_frame = self.frame.shape[:2]
                    temp_frame = self.frame[0 : int(h_frame * 0.3), 0 : int(w_frame * 0.3)]
                    tl, _ = utils.single_match(temp_frame, MM_TL_TEMPLATE)
                    _, br = utils.single_match(temp_frame, MM_BR_TEMPLATE)
                    mm_tl = (
                        tl[0] + MINIMAP_BOTTOM_BORDER,
                        tl[1] + MINIMAP_TOP_BORDER
                    )
                    mm_br = (
                        max(mm_tl[0] + PT_WIDTH, br[0] - MINIMAP_BOTTOM_BORDER),
                        max(mm_tl[1] + PT_HEIGHT, br[1] - MINIMAP_BOTTOM_BORDER)
                    )
                    self.minimap_ratio = (mm_br[0] - mm_tl[0]) / (mm_br[1] - mm_tl[1])
                    self.minimap_sample = self.frame[mm_tl[1]:mm_br[1], mm_tl[0]:mm_br[0]]
                    self.calibrated = True
                    print('[~] 小地图校准成功')
                except Exception as e:
                    print(f'[!] 校准过程中出错: {e}')
                    time.sleep(2)
                    continue

                with mss.mss() as self.sct:
                    while True:
                        if not self.calibrated:
                            break

                        try:
                            # 截图
                            self.frame = self.screenshot()
                            if self.frame is None:
                                continue

                            # 裁剪帧以仅显示小地图（复制以便 GUI 线程
                            # 不会持有对完整帧的引用并导致内存压力）。
                            minimap = self.frame[mm_tl[1]:mm_br[1], mm_tl[0]:mm_br[0]].copy()

                            # 确定玩家位置
                            player = utils.multi_match_color(minimap, PLAYER_TEMPLATE, threshold=0.8)
                            if player:
                                config.player_pos = utils.convert_to_relative(player[0], minimap)
                            else:
                                # 如果未找到玩家，保持最后位置但不更新
                                pass

                            # 打包显示信息以供 GUI 轮询
                            self.minimap = {
                                'minimap': minimap,
                                'rune_active': config.bot.rune_active,
                                'rune_pos': config.bot.rune_pos,
                                'path': config.path,
                                'player_pos': config.player_pos
                            }

                            if not self.ready:
                                self.ready = True
                            
                            # 每约50帧（50fps下约1秒）进行一次垃圾回收，以帮助
                            # 在系统压力下释放内存（减少"无法分配"错误）。
                            self._gc_counter += 1
                            if self._gc_counter >= 50:
                                gc.collect()
                                self._gc_counter = 0
                            
                            # ~50 fps 以减少 mss 分配压力（grab 内部会分配）。
                            time.sleep(0.02)
                        except Exception as e:
                            print(f'[!] 捕获循环中的错误: {e}')
                            # 暂停并尝试恢复
                            time.sleep(1)
                            # 必要时尝试重新校准
                            if not self.calibrated:
                                break
            except Exception as e:
                print(f'[!] 捕获主循环中的严重错误: {e}')
                import traceback
                traceback.print_exc()
                # 暂停以允许恢复
                time.sleep(5)
                # 严重错误后强制进行垃圾回收
                gc.collect()

    def get_minimap_from_frame(self, frame):
        """
        通过在整个帧中搜索 TL/BR 角来找到小地图（无 ROI）。
        当预裁剪的小地图可能错误时使用此方法（例如，用于自动例程解析）。
        将 BGRA（mss）转换为 BGR，以便匹配测试小地图查找器 / cv2.imread。
        :param frame: 完整的游戏窗口图像（例如 self.frame），BGR 或 BGRA
        :return: 小地图裁剪作为 numpy 数组，如果未找到则返回 None
        """
        if frame is None or frame.size == 0:
            return None
        # 标准化为 BGR，以便匹配与测试脚本相同（保存的帧加载为 BGR）
        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        h, w = frame.shape[:2]
        if (MM_TL_TEMPLATE.shape[0] > h or MM_TL_TEMPLATE.shape[1] > w or
                MM_BR_TEMPLATE.shape[0] > h or MM_BR_TEMPLATE.shape[1] > w):
            return None
        tl, _ = utils.single_match(frame, MM_TL_TEMPLATE)
        _, br = utils.single_match(frame, MM_BR_TEMPLATE)
        mm_tl = (
            tl[0] + MINIMAP_BOTTOM_BORDER,
            tl[1] + MINIMAP_TOP_BORDER
        )
        mm_br = (
            max(mm_tl[0] + PT_WIDTH, br[0] - MINIMAP_BOTTOM_BORDER),
            max(mm_tl[1] + PT_HEIGHT, br[1] - MINIMAP_BOTTOM_BORDER)
        )
        # 边界检查，确保我们永远不会返回无效裁剪
        if mm_br[0] <= mm_tl[0] or mm_br[1] <= mm_tl[1]:
            return None
        if mm_tl[0] < 0 or mm_tl[1] < 0 or mm_br[0] > w or mm_br[1] > h:
            return None
        return frame[mm_tl[1]:mm_br[1], mm_tl[0]:mm_br[0]]

    def screenshot(self, delay=1):
        try:
            shot = self.sct.grab(self.window)
            h, w = shot.height, shot.width
            need_shape = (h, w, 4)
            if self._frame_buffer is None or self._frame_buffer.shape != need_shape:
                # 释放旧缓冲区（如果存在）
                if self._frame_buffer is not None:
                    # 显式释放内存
                    self._frame_buffer = None
                    gc.collect()
                self._frame_buffer = np.empty(need_shape, dtype=np.uint8)
            # 直接使用copyto，避免创建临时数组的引用
            np.copyto(
                self._frame_buffer,
                np.frombuffer(shot.raw, dtype=np.uint8).reshape(need_shape),
            )
            return self._frame_buffer
        except MemoryError:
            # mss 在 grab() 内部分配字节数组；当系统内存不足时
            # 这可能会失败。强制 GC 并暂停，然后重试，以便循环可以继续。
            print('\n[!] 捕获：截图时内存错误，强制 GC 然后重试...')
            gc.collect()
            time.sleep(2)
            return None
        except mss.exception.ScreenShotError:
            print(f'\n[!] 截图时出错，{delay} 秒后重试'
                  + ('s' if delay != 1 else ''))
            time.sleep(delay)
            return None