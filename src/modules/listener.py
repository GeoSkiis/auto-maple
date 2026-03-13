"""一个用于跟踪用户输入的键盘监听器。"""

import time
import threading
import winsound
import keyboard as kb
from src.common.interfaces import Configurable
from src.common import config, utils
from datetime import datetime


class Listener(Configurable):
    DEFAULT_CONFIG = {
        'Start/stop': 'insert',
        'Reload routine': 'f6',
        'Record position': 'f7',
        'Add layout point': 'f9',
        'Delete nearest layout point': 'f10'
    }
    BLOCK_DELAY = 1         # 阻止受限按钮按下后的延迟

    def __init__(self):
        """初始化此 Listener 对象的主线程。"""

        super().__init__('controls')
        config.listener = self

        self.enabled = False
        self.ready = False
        self.block_time = 0
        self.thread = threading.Thread(target=self._main)
        self.thread.daemon = True

    def start(self):
        """
        开始监听用户输入。
        :return:    None
        """

        print('\n[~] 启动键盘监听器')
        self.thread.start()

    def _main(self):
        """
        持续监听用户输入并相应地更新 config 中的变量。
        :return:    None
        """

        self.ready = True
        while True:
            try:
                if self.enabled:
                    try:
                        if kb.is_pressed(self.config['Start/stop']):
                            Listener.toggle_enabled()
                        elif kb.is_pressed(self.config['Reload routine']):
                            Listener.reload_routine()
                        elif self.restricted_pressed('Record position'):
                            Listener.record_position()
                        elif kb.is_pressed(self.config['Add layout point']):
                            Listener.add_layout_point()
                        elif kb.is_pressed(self.config['Delete nearest layout point']):
                            Listener.delete_nearest_layout_point()
                    except Exception as e:
                        print(f'[!] 键盘输入处理错误: {e}')
                        # 暂停以避免快速错误循环
                        time.sleep(0.1)
                time.sleep(0.01)
            except OSError as e:
                # 当系统处于严重内存/句柄压力下时，可能会发生 WinError 1450 "系统资源不足"；记录并继续。
                if getattr(e, 'winerror', None) != 1450:
                    print(f'[!] 监听器中的严重 OS 错误: {e}')
                    time.sleep(1)
                    continue
                print('\n[!] 监听器: 系统资源暂时不足 (1450)，继续运行...')
                time.sleep(0.5)
            except Exception as e:
                print(f'[!] 监听器主循环中的严重错误: {e}')
                import traceback
                traceback.print_exc()
                # 暂停以允许恢复
                time.sleep(1)

    def restricted_pressed(self, action):
        """仅当机器人禁用时，返回绑定到 ACTION 的键是否被按下。"""

        if kb.is_pressed(self.config[action]):
            if not config.enabled:
                return True
            now = time.time()
            if now - self.block_time > Listener.BLOCK_DELAY:
                print(f"\n[!] 启用 Auto Maple 时无法使用 '{action}'")
                self.block_time = now
        return False

    @staticmethod
    def toggle_enabled():
        """恢复或暂停当前例程。播放声音通知用户。"""

        config.bot.rune_active = False

        if not config.enabled:
            Listener.recalibrate_minimap()      # 仅在启用时重新校准。

        config.enabled = not config.enabled
        utils.print_state()

        if config.enabled:
            winsound.Beep(784, 333)     # G5
        else:
            winsound.Beep(523, 333)     # C5
        time.sleep(0.267)

    @staticmethod
    def reload_routine():
        Listener.recalibrate_minimap()

        config.routine.load(config.routine.path)

        winsound.Beep(523, 200)     # C5
        winsound.Beep(659, 200)     # E5
        winsound.Beep(784, 200)     # G5

    @staticmethod
    def recalibrate_minimap():
        config.capture.calibrated = False
        while not config.capture.calibrated:
            time.sleep(0.01)
        config.gui.edit.minimap.redraw()

    @staticmethod
    def record_position():
        pos = tuple('{:.3f}'.format(round(i, 3)) for i in config.player_pos)
        now = datetime.now().strftime('%I:%M:%S %p')
        config.gui.edit.record.add_entry(now, pos)
        print(f'\n[~] 记录位置 ({pos[0]}, {pos[1]}) 在 {now}')
        time.sleep(0.6)

    @staticmethod
    def add_layout_point():
        if config.layout is None:
            print('\n[!] 未加载布局。请先加载例程。')
            winsound.Beep(523, 200)     # C5
            winsound.Beep(392, 200)     # G4
            time.sleep(0.1)
            return
        x, y = config.player_pos
        success = config.layout.add(x, y)
        if success:
            config.layout.save()
            print(f'\n[~] 添加布局点 ({x:.3f}, {y:.3f})')
            winsound.Beep(659, 200)     # E5
            winsound.Beep(784, 200)     # G5
        else:
            print(f'\n[!] 点 ({x:.3f}, {y:.3f}) 已存在或离现有点太近。')
        time.sleep(0.1)

    @staticmethod
    def delete_nearest_layout_point():
        if config.layout is None:
            print('\n[!] 未加载布局。请先加载例程。')
            winsound.Beep(523, 200)     # C5
            winsound.Beep(392, 200)     # G4
            time.sleep(0.1)
            return
        x, y = config.player_pos
        success = config.layout.delete_nearest(x, y)
        if success:
            config.layout.save()
            print(f'\n[~] 删除离 ({x:.3f}, {y:.3f}) 最近的布局点')
            winsound.Beep(784, 200)     # G5
            winsound.Beep(659, 200)     # E5
        else:
            print(f'\n[!] 在 ({x:.3f}, {y:.3f}) 附近未找到布局点。')
        time.sleep(0.1)