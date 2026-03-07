import os
import inspect
import importlib
import traceback
from os.path import basename, splitext
from src.common import config, utils
from src.routine import components
from src.common.interfaces import Configurable


CB_KEYBINDING_DIR = os.path.join('resources', 'keybindings')


class CommandBook(Configurable):
    def __init__(self, file):
        self.name = splitext(basename(file))[0]
        self.buff = components.Buff()
        self.DEFAULT_CONFIG = {}
        result = self.load_commands(file)
        if result is None:
            raise ValueError(f"无效的命令书位于 '{file}'")
        self.dict, self.module = result
        super().__init__(self.name, directory=CB_KEYBINDING_DIR)
        
    def load_commands(self, file):
        """提示用户选择要导入的命令模块。更新配置的命令书。"""

        utils.print_separator()
        print(f"[~] 加载命令书 '{basename(file)}':")

        ext = splitext(file)[1]
        if ext != '.py':
            print(f" !  '{ext}' 不是支持的文件扩展名。")
            return

        new_step = components.step
        new_cb = {}
        for c in (components.Wait, components.Walk, components.Fall):
            new_cb[c.__name__.lower()] = c

        # 导入所需的命令书文件
        target = '.'.join(['resources', 'command_books', self.name])
        try:
            module = importlib.import_module(target)
            module = importlib.reload(module)
        except ImportError:     # 显示目标命令书中的错误
            print(' !  编译期间的错误:\n')
            for line in traceback.format_exc().split('\n'):
                line = line.rstrip()
                if line:
                    print(' ' * 4 + line)
            print(f"\n !  命令书 '{self.name}' 未加载")
            return

        # 加载按键映射
        if hasattr(module, 'Key'):
            default_config = {}
            for key, value in module.Key.__dict__.items():
                if not key.startswith('__') and not key.endswith('__'):
                    default_config[key] = value
            self.DEFAULT_CONFIG = default_config
        else:
            print(f" !  加载命令书 '{self.name}' 错误，缺少按键映射类 'Key'")
            return

        # 检查是否实现了 'step' 函数
        step_found = False
        for name, func in inspect.getmembers(module, inspect.isfunction):
            if name.lower() == 'step':
                step_found = True
                new_step = func

        # 填充新的命令书
        for name, command in inspect.getmembers(module, inspect.isclass):
            if issubclass(command, components.Command):
                new_cb[name.lower()] = command
        # 始终添加基于技能的轮换（基于冷却的随机技能使用）
        new_cb['skillrotation'] = components.SkillRotation

        # 检查是否实现和覆盖了必需的命令
        required_found = True
        for command in (components.Buff,):
            name = command.__name__.lower()
            if name not in new_cb:
                required_found = False
                new_cb[name] = command
                print(f" !  错误：必须实现必需的命令 '{name}'。")

        # 查找覆盖的移动命令
        movement_found = True
        for command in (components.Move, components.Adjust):
            name = command.__name__.lower()
            if name not in new_cb:
                movement_found = False
                new_cb[name] = command

        if not step_found and not movement_found:
            print(f" !  错误：必须实现 'Move' 和 'Adjust' 命令，"
                  f"或者实现 'step' 函数")
        if required_found and (step_found or movement_found):
            self.buff = new_cb['buff']()
            components.step = new_step
            config.gui.menu.file.enable_routine_state()
            config.gui.view.status.set_cb(basename(file))
            config.routine.clear()
            print(f" ~  成功加载命令书 '{self.name}'")
            return new_cb, module
        else:
            print(f" !  命令书 '{self.name}' 未加载")

    def __getitem__(self, item):
        return self.dict[item]

    def __contains__(self, item):
        return item in self.dict

    def load_config(self):
        super().load_config()
        self._set_keybinds()

    def save_config(self):
        self._set_keybinds()
        super().save_config()

    def _set_keybinds(self):
        for k, v in self.config.items():
            setattr(self.module.Key, k, v)