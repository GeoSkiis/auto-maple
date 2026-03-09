"""将所有模块连接在一起的中央程序。"""

import time
import signal
import sys
from src.modules.bot import Bot
from src.modules.capture import Capture
from src.modules.notifier import Notifier
from src.modules.listener import Listener
from src.modules.gui import GUI


def signal_handler(sig, frame):
    """处理信号，确保资源被正确释放"""
    print('\n[~] 正在关闭 Auto Maple...')
    # 关闭Bot资源
    if 'bot' in locals() and bot is not None:
        bot.close()
    print('\n[~] Auto Maple 已关闭')
    sys.exit(0)

# 注册信号处理
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

bot = Bot()
capture = Capture()
notifier = Notifier()
listener = Listener()

bot.start()
while not bot.ready:
    time.sleep(0.01)

capture.start()
while not capture.ready:
    time.sleep(0.01)

notifier.start()
while not notifier.ready:
    time.sleep(0.01)

listener.start()
while not listener.ready:
    time.sleep(0.01)

print('\n[~] Auto Maple 初始化成功')
print('\n[~] 按 Ctrl+C 退出')

gui = GUI()
gui.start()

# 保持主线程运行
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    signal_handler(None, None)