"""用户友好的 GUI，用于与 Auto Maple 交互。"""

import os
import time
import threading
import tkinter as tk
from tkinter import ttk
from src.common import config, settings, session
from src.gui import Menu, View, Edit, Settings


class GUI:
    # 较低的速率（8）可减少长时间运行时 Tkinter 画布/项目配置的图像泄漏（原为 30）
    DISPLAY_FRAME_RATE = 8
    RESOLUTIONS = {
        'DEFAULT': '800x800',
        'Edit': '1400x800'
    }

    def __init__(self):
        config.gui = self

        self.root = tk.Tk()
        self.root.title('Auto Maple')
        icon = tk.PhotoImage(file='assets/icon.png')
        self.root.iconphoto(False, icon)
        self.root.geometry(GUI.RESOLUTIONS['DEFAULT'])
        self.root.resizable(True, True)

        # 初始化 GUI 变量
        self.routine_var = tk.StringVar()

        # 构建 GUI
        self.menu = Menu(self.root)
        self.root.config(menu=self.menu)

        self.navigation = ttk.Notebook(self.root)

        self.view = View(self.navigation)
        self.edit = Edit(self.navigation)
        self.settings = Settings(self.navigation)

        self.navigation.pack(expand=True, fill='both')
        self.navigation.bind('<<NotebookTabChanged>>', self._resize_window)
        self.root.focus()

        # 短暂延迟后恢复上一个会话（以便窗口显示）
        self.root.after(100, self._restore_session)

    def _restore_session(self):
        """从上次会话加载命令书、例程和小地图。"""
        data = session.load()
        if not data:
            return
        cb_path = data.get('command_book', '')
        routine_path = data.get('routine', '')
        minimap_path = data.get('minimap', '')
        if cb_path and os.path.isfile(cb_path):
            try:
                config.bot.load_commands(cb_path)
            except Exception:
                pass
        if routine_path and os.path.isfile(routine_path) and config.bot.command_book is not None:
            try:
                config.routine.load(routine_path)
            except Exception:
                pass
        if minimap_path and os.path.isfile(minimap_path):
            config.selected_minimap_path = minimap_path
            config.gui.view.status.set_minimap(os.path.basename(minimap_path))

    def set_routine(self, arr):
        self.routine_var.set(arr)

    def clear_routine_info(self):
        """
        清除各种 GUI 元素中关于当前例程的信息。
        不清除包含例程组件的列表框，因为这由 Routine 处理。
        """

        self.view.details.clear_info()
        self.view.status.set_routine('')

        self.edit.minimap.redraw()
        self.edit.routine.commands.clear_contents()
        self.edit.routine.commands.update_display()
        self.edit.editor.reset()

    def _resize_window(self, e):
        """每次选择新页面时调整整个 Tkinter 窗口大小的回调函数。"""

        nav = e.widget
        curr_id = nav.select()
        nav.nametowidget(curr_id).focus()     
        page = nav.tab(curr_id, 'text')
        if self.root.state() != 'zoomed':
            if page in GUI.RESOLUTIONS:
                self.root.geometry(GUI.RESOLUTIONS[page])
            else:
                self.root.geometry(GUI.RESOLUTIONS['DEFAULT'])

    def start(self):
        """启动 GUI 以及任何计划的函数。"""

        display_thread = threading.Thread(target=self._display_minimap)
        display_thread.daemon = True
        display_thread.start()

        layout_thread = threading.Thread(target=self._save_layout)
        layout_thread.daemon = True
        layout_thread.start()

        self.root.mainloop()

    def _display_minimap(self):
        delay = 1 / GUI.DISPLAY_FRAME_RATE
        while True:
            self.view.minimap.display_minimap()
            time.sleep(delay)

    def _save_layout(self):
        """定期保存当前的 Layout 对象。"""

        while True:
            if config.layout is not None and settings.record_layout:
                config.layout.save()
            time.sleep(5)


if __name__ == '__main__':
    gui = GUI()
    gui.start()