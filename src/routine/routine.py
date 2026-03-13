"""Auto Maple 编译器为每个例程生成的 '机器代码' 中使用的类集合。"""

from src.common import config, settings, utils
import csv
import json
import os
import re
from os.path import splitext, basename
from src.routine.components import Point, Label, Jump, Setting, Command, SYMBOLS, SkillRotation
from src.routine.layout import Layout
import random


def _save_failed_frame(frame, failed_dir, reason=""):
    """将帧保存到 failed_detections/failed_minimap_finder_{n}.jpg 以供检查（BGR 格式，以便测试脚本匹配）。"""
    try:
        import cv2
        os.makedirs(failed_dir, exist_ok=True)
        # 保存为 BGR 格式，以便使用 cv2.imread 加载时与实时匹配一致（mss 提供 BGRA 格式）
        save_frame = frame
        if frame.ndim == 3 and frame.shape[2] == 4:
            save_frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        existing = [f for f in os.listdir(failed_dir) if re.match(r"failed_minimap_finder_\d+\.jpg", f)]
        nums = [int(re.search(r"\d+", f).group()) for f in existing]
        n = max(nums, default=0) + 1
        path = os.path.join(failed_dir, f"failed_minimap_finder_{n}.jpg")
        cv2.imwrite(path, save_frame)
        print(f"[~] 保存帧以供检查 ({reason}): {path}")
    except Exception as e:
        print(f"[!] 无法保存失败帧: {e}")


def update(func):
    """
    装饰器函数，用于更新所有可变 Routine 操作的显示例程和详细信息。
    """

    def f(self, *args, **kwargs):
        result = func(self, *args, **kwargs)
        config.gui.set_routine(self.display)
        config.gui.view.details.update_details()
        return result
    return f


def dirty(func):
    """为可变 Routine 操作设置脏位的装饰器函数。"""

    def f(self, *args, **kwargs):
        result = func(self, *args, **kwargs)
        self.dirty = True
        return result
    return f


class Routine:
    """描述 Auto Maple 自定义 '机器代码' 中的例程文件。"""

    def __init__(self):
        self.dirty = False
        self.path = ''
        self.labels = {}
        self.index = 0
        self.sequence = []
        self.display = []       # 与 sequence 一起更新
        self.auto_mode = False  # 加载 auto.csv 时为 True：运行时从 minimap 匹配解析路径点

    @dirty
    @update
    def set(self, arr):
        self.sequence = arr
        self.display = [str(x) for x in arr]

    @dirty
    @update
    def append_component(self, p):
        self.sequence.append(p)
        self.display.append(str(p))

    @dirty
    @update
    def append_command(self, i, c):
        """将 Command 对象 C 追加到序列中索引 I 处的 Point。"""

        target = self.sequence[i]
        target.commands.append(c)

    @dirty
    @update
    def move_component_up(self, i):
        """如果可能，将索引 I 处的组件向上移动。"""

        if i > 0:
            temp_s = self.sequence[i-1]
            temp_d = self.display[i-1]
            self.sequence[i-1] = self.sequence[i]
            self.display[i-1] = self.display[i]
            self.sequence[i] = temp_s
            self.display[i] = temp_d
            return i - 1
        return i

    @dirty
    @update
    def move_component_down(self, i):
        if i < len(self.sequence) - 1:
            temp_s = self.sequence[i+1]
            temp_d = self.display[i+1]
            self.sequence[i+1] = self.sequence[i]
            self.display[i+1] = self.display[i]
            self.sequence[i] = temp_s
            self.display[i] = temp_d
            return i + 1
        return i

    @dirty
    @update
    def move_command_up(self, i, j):
        """
        在例程索引 I 处的 Point 内，如果可能，将索引 J 处的 Command 向上移动
        并更新编辑 UI。
        """

        point = self.sequence[i]
        if j > 0:
            temp = point.commands[j-1]
            point.commands[j-1] = point.commands[j]
            point.commands[j] = temp
            return j - 1
        return j

    @dirty
    @update
    def move_command_down(self, i, j):
        point = self.sequence[i]
        if j < len(point.commands) - 1:
            temp = point.commands[j+1]
            point.commands[j+1] = point.commands[j]
            point.commands[j] = temp
            return j + 1
        return j

    @dirty
    @update
    def delete_component(self, i):
        """删除索引 I 处的 Component。"""

        self.sequence.pop(i)
        self.display.pop(i)

    @dirty
    @update
    def delete_command(self, i, j):
        """在例程索引 I 处的 Point 内，删除索引 J 处的 Command。"""

        point = self.sequence[i]
        point.commands.pop(j)

    @update
    def update_component(self, i, new_kwargs):
        target = self.sequence[i]
        try:
            target.update(**new_kwargs)
            self.display[i] = str(target)
            self.dirty = True
        except (ValueError, TypeError) as e:
            print(f"\n[!] 发现 '{target.__class__.__name__}' 的无效参数：")
            print(f"{' ' * 4} -  {e}")

    @update
    def update_command(self, i, j, new_kwargs):
        target = self.sequence[i].commands[j]
        try:
            target.update(**new_kwargs)
            self.display[i] = str(self.sequence[i])
            self.dirty = True
        except (ValueError, TypeError) as e:
            print(f"\n[!] 发现 '{target.__class__.__name__}' 的无效参数：")
            print(f"{' ' * 4} -  {e}")

    @utils.run_if_enabled
    def step(self):
        """增加 config.seq_index 并在 config.sequence 结束时回绕到 0。"""
        # self.index = random.randint(0, len(self.sequence) - 1)
        self.index = (self.index + 1) % len(self.sequence)

    def save(self, file_path):
        """在位置 PATH 编码并保存当前 Routine。"""

        result = []
        for item in self.sequence:
            result.append(item.encode())
            if isinstance(item, Point):
                for c in item.commands:
                    result.append(' ' * 4 + c.encode())
        result.append('')

        with open(file_path, 'w') as file:
            file.write('\n'.join(result))
        self.dirty = False

        utils.print_separator()
        print(f"[~] 已保存例程到 '{basename(file_path)}'。")

    def clear(self):
        self.index = 0
        self.set([])
        self.dirty = False
        self.path = ''
        self.auto_mode = False
        config.layout = None
        settings.reset()

        config.gui.clear_routine_info()

    def load(self, file=None):
        """
        尝试将 FILE 加载到 Component 序列中。如果未提供文件路径，尝试加载
        之前的例程文件。
        :param file:    文件的路径。
        :return:        None
        """

        utils.print_separator()
        print(f"[~] 加载例程 '{basename(file)}':")

        if not file:
            if self.path:
                file = self.path
                print(' *  未提供文件路径，使用之前加载的例程')
            else:
                print('[!] 未提供文件路径，之前也未加载任何例程')
                return False

        ext = splitext(file)[1]
        if ext != '.csv':
            print(f" !  '{ext}' 不是支持的文件扩展名。")
            return False

        self.clear()
        # 重置，以便没有该设置的 CSV 不会继承之前例程的模式
        settings.skill_rotation_mode = False
        settings.skill_rotation_duration = 5.0

        # 编译和链接
        self.compile(file)
        for c in self.sequence:
            if isinstance(c, Jump):
                c.bind()

        self.dirty = False
        self.path = file
        # auto.csv 为空（或只有 $ 设置）：通过 minimap 匹配在机器人运行时解析路径点
        if basename(file).lower() == 'auto.csv':
            self.auto_mode = True
            print(' ~  自动例程：开始时将从 minimap 匹配解析路径点。')
        config.layout = Layout.load(file)
        config.gui.view.status.set_routine(basename(file))
        config.gui.edit.minimap.draw_default()
        print(f" ~  完成加载例程 '{basename(splitext(file)[0])}'。")

    def compile(self, file):
        self.labels = {}
        with open(file, newline='') as f:
            csv_reader = csv.reader(f, skipinitialspace=True)
            curr_point = None
            line = 1
            for row in csv_reader:
                result = self._eval(row, line)
                if result:
                    if isinstance(result, Command):
                        if curr_point:
                            curr_point.commands.append(result)
                    else:
                        self.append_component(result)
                        if isinstance(result, Point):
                            curr_point = result
                line += 1

    def _eval(self, row, i):
        if row and isinstance(row, list):
            first, rest = row[0].strip().lower(), row[1:]
            if not first:
                return
            args, kwargs = utils.separate_args(rest)
            line_error = f' !  第 {i} 行: '

            if first in SYMBOLS:
                c = SYMBOLS[first]
            elif first in config.bot.command_book:
                c = config.bot.command_book[first]
            else:
                print(line_error + f"命令 '{first}' 不存在。")
                return

            try:
                obj = c(*args, **kwargs)
                if isinstance(obj, Label):
                    obj.set_index(len(self))
                    self.labels[obj.label] = obj
                return obj
            except (ValueError, TypeError) as e:
                print(line_error + f"发现 '{c.__name__}' 的无效参数：")
                print(f"{' ' * 4} -  {e}")

    def resolve_auto_routine(self, skill_rotation_duration=5.0, move_tolerance=0.075):
        """
        解析自动例程：如果通过文件 > 加载小地图选择了小地图，则使用它并跳过 OCR。
        否则将当前游戏小地图与 assets/minimaps 中的 PNG 匹配（OCR），然后构建路径点。
        如果没有资产匹配，则使用 config.capture 中的实时小地图。将序列设置为每个位置都有
        SkillRotation 的 Points；启用 skill_rotation_mode。当机器人启用且 auto_mode 为 True 时调用。
        """
        from src.map.waypoints_from_map import (
            find_matching_map,
            waypoints_from_map_path,
            waypoints_from_map_image,
        )
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        failed_dir = os.path.join(root, 'failed_detections')
        map_path = None
        waypoints = None

        # 用户选择了小地图（文件 > 加载小地图）：直接使用它，跳过 OCR
        selected = getattr(config, 'selected_minimap_path', None)
        if selected and os.path.isfile(selected):
            map_path = selected
            waypoints = waypoints_from_map_path(map_path)
            print('\n[~] 自动例程：使用选定的小地图（跳过 OCR）。')
        else:
            # 无选择：使用帧 + OCR 匹配地图，或实时小地图
            frame = config.capture.frame if config.capture else None
            minimap = config.capture.get_minimap_from_frame(frame) if config.capture and frame is not None else None
            if minimap is None:
                print('\n[!] 自动例程：小地图尚未可用（捕获未就绪）。')
                if frame is not None:
                    _save_failed_frame(frame, failed_dir, "minimap_extract")
                return False
            minimaps_dir = os.path.join(root, 'assets', 'minimaps')
            map_path = find_matching_map(frame, minimaps_dir, threshold=0.7)
            if map_path:
                waypoints = waypoints_from_map_path(map_path)
            else:
                print('\n[~] 自动例程：在 assets/minimaps 中未找到小地图；使用当前游戏小地图作为路径点。')
                if frame is not None:
                    _save_failed_frame(frame, failed_dir, "minimap_match")
                waypoints = waypoints_from_map_image(minimap)
        if not waypoints:
            print('\n[!] 自动例程：无路径点（小地图上未检测到平台）。')
            return False
        sequence = []
        for w in waypoints:
            p = Point(
                x=w['x'], y=w['y'],
                frequency=1, skip='False', adjust='True'
            )
            p.commands = [SkillRotation(duration=skill_rotation_duration)]
            sequence.append(p)
        self.sequence = sequence
        self.display = [str(x) for x in sequence]
        self.labels = {}
        self.index = 0
        self.auto_mode = False
        settings.skill_rotation_mode = True
        settings.skill_rotation_duration = skill_rotation_duration
        settings.move_tolerance = move_tolerance
        config.gui.set_routine(self.display)
        config.gui.view.details.update_details()
        utils.print_separator()
        source = os.path.basename(map_path) if map_path else "当前小地图"
        print(f"[~] 自动例程已解析：{source}，{len(sequence)} 个路径点，技能轮换 {skill_rotation_duration}秒。")
        return True

    @dirty
    @update
    def load_waypoints_from_json(self, path, skill_rotation_duration=5):
        """
        从 JSON 文件加载路径点（例如从 mark_platform_centers.py 输出）。
        每个路径点成为一个 Point，其唯一命令为 SkillRotation(duration=...)。
        在加载命令书后调用（以便 move/adjust 存在）。
        """
        with open(path, 'r') as f:
            waypoints = json.load(f)
        sequence = []
        for w in waypoints:
            p = Point(
                x=w['x'], y=w['y'],
                frequency=1, skip='False', adjust='True'
            )
            p.commands = [SkillRotation(duration=skill_rotation_duration)]
            sequence.append(p)
        self.sequence = sequence
        self.display = [str(x) for x in sequence]
        self.labels = {}
        self.index = 0
        self.path = path

    @staticmethod
    def get_all_components():
        """返回将所有可创建的 Components 映射到其名称的字典。"""

        options = config.bot.command_book.dict.copy()
        for e in (Point, Label, Jump, Setting):
            options[e.__name__.lower()] = e
        return options

    def __getitem__(self, i):
        return self.sequence[i]

    def __len__(self):
        return len(self.sequence)