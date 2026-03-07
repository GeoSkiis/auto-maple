"""用于执行例程的类集合。"""

import math
import random
import time
from src.common import config, settings, utils
from src.common.vkeys import key_down, key_up, press


#################################
#       Routine Components      #
#################################
class Component:
    id = 'Routine Component'
    PRIMITIVES = {int, str, bool, float}

    def __init__(self, *args, **kwargs):
        if len(args) > 1:
            raise TypeError('Component 超类 __init__ 只接受 1 个（可选）参数：LOCALS')
        if len(kwargs) != 0:
            raise TypeError('Component 超类 __init__ 不接受任何关键字参数')
        if len(args) == 0:
            self.kwargs = {}
        elif type(args[0]) != dict:
            raise TypeError("Component 超类 __init__ 只接受类型为 'dict' 的参数。")
        else:
            self.kwargs = args[0].copy()
            self.kwargs.pop('__class__')
            self.kwargs.pop('self')

    @utils.run_if_enabled
    def execute(self):
        self.main()

    def main(self):
        pass

    def update(self, *args, **kwargs):
        """使用新参数更新此组件的构造函数参数。"""

        self.__class__(*args, **kwargs)     # 在实际更新值之前验证参数
        self.__init__(*args, **kwargs)

    def info(self):
        """返回有关此组件的有用信息字典。"""

        return {
            'name': self.__class__.__name__,
            'vars': self.kwargs.copy()
        }

    def encode(self):
        """使用对象的 ID 及其 __init__ 参数对对象进行编码。"""

        arr = [self.id]
        for key, value in self.kwargs.items():
            if key != 'id' and type(self.kwargs[key]) in Component.PRIMITIVES:
                arr.append(f'{key}={value}')
        return ', '.join(arr)


class Point(Component):
    """表示用户定义例程中的位置。"""

    id = '*'

    def __init__(self, x, y, frequency=1, skip='False', adjust='False'):
        super().__init__(locals())
        self.x = float(x)
        self.y = float(y)
        self.location = (self.x, self.y)
        self.frequency = settings.validate_nonnegative_int(frequency)
        self.counter = int(settings.validate_boolean(skip))
        self.adjust = settings.validate_boolean(adjust)
        if not hasattr(self, 'commands'):       # 更新 Point 时不应清除命令
            self.commands = []

    def main(self):
        """执行与此 Point 关联的操作集。"""

        if self.counter == 0:
            move = config.bot.command_book['move']
            move(*self.location).execute()
            if self.adjust:
                adjust = config.bot.command_book['adjust']      # TODO: 使用 step('up') 进行调整？
                adjust(*self.location).execute()
            if settings.skill_rotation_mode:
                SkillRotation(duration=settings.skill_rotation_duration).execute()
            else:
                for command in self.commands:
                    command.execute()
        self._increment_counter()

    @utils.run_if_enabled
    def _increment_counter(self):
        """增加此 Point 的计数器，达到上限时回绕到 0。"""

        self.counter = (self.counter + 1) % self.frequency

    def info(self):
        curr = super().info()
        curr['vars'].pop('location', None)
        curr['vars']['commands'] = ', '.join([c.id for c in self.commands])
        return curr

    def __str__(self):
        return f'  * {self.location}'


class Label(Component):
    id = '@'

    def __init__(self, label):
        super().__init__(locals())
        self.label = str(label)
        if self.label in config.routine.labels:
            raise ValueError
        self.links = set()
        self.index = None

    def set_index(self, i):
        self.index = i

    def encode(self):
        return '\n' + super().encode()

    def info(self):
        curr = super().info()
        curr['vars']['index'] = self.index
        return curr

    def __delete__(self, instance):
        del self.links
        config.routine.labels.pop(self.label)

    def __str__(self):
        return f'{self.label}:'


class Jump(Component):
    """跳转到指定的 Label。"""

    id = '>'

    def __init__(self, label, frequency=1, skip='False'):
        super().__init__(locals())
        self.label = str(label)
        self.frequency = settings.validate_nonnegative_int(frequency)
        self.counter = int(settings.validate_boolean(skip))
        self.link = None

    def main(self):
        if self.link is None:
            print(f"\n[!] 标签 '{self.label}' 不存在。")
        else:
            if self.counter == 0:
                config.routine.index = self.link.index
            self._increment_counter()

    @utils.run_if_enabled
    def _increment_counter(self):
        self.counter = (self.counter + 1) % self.frequency

    def bind(self):
        """
        将此 Jump 绑定到其对应的 Label。如果 Label 的索引更改，此 Jump
        实例将自动能够访问更新后的值。
        :return:    绑定是否成功
        """

        if self.label in config.routine.labels:
            self.link = config.routine.labels[self.label]
            self.link.links.add(self)
            return True
        return False

    def __delete__(self, instance):
        if self.link is not None:
            self.link.links.remove(self)

    def __str__(self):
        return f'  > {self.label}'


class Setting(Component):
    """更改给定设置变量的值。"""

    id = '$'

    def __init__(self, target, value):
        super().__init__(locals())
        self.key = str(target)
        if self.key not in settings.SETTING_VALIDATORS:
            raise ValueError(f"设置 '{target}' 不存在")
        self.value = settings.SETTING_VALIDATORS[self.key](value)

    def main(self):
        setattr(settings, self.key, self.value)

    def __str__(self):
        return f'  $ {self.key} = {self.value}'


SYMBOLS = {
    '*': Point,
    '@': Label,
    '>': Jump,
    '$': Setting
}


#############################
#       Shared Commands     #
#############################
class Command(Component):
    id = 'Command Superclass'

    def __init__(self, *args):
        super().__init__(*args)
        self.id = self.__class__.__name__

    def __str__(self):
        variables = self.__dict__
        result = '    ' + self.id
        if len(variables) - 1 > 0:
            result += ':'
        for key, value in variables.items():
            if key != 'id':
                result += f'\n        {key}={value}'
        return result


def _try_skill_during_move():
    """
    在移动过程中尝试使用技能
    如果当前命令书有 SKILL_COOLDOWNS 配置，则使用一个随机的冷却完毕的技能
    使用与 SkillRotation 相同的 CooldownTracker，确保冷却时间同步
    """
    # 导入冷却追踪器
    from src.routine.cooldown_tracker import CooldownTracker
    # 获取当前职业的模块
    module = getattr(config.bot.command_book, 'module', None) if getattr(config.bot, 'command_book', None) else None
    # 获取技能冷却配置
    cooldowns = getattr(module, 'SKILL_COOLDOWNS', None) if module else None
    # 如果没有冷却配置，直接返回
    if cooldowns is None:
        return
    # 获取或创建冷却追踪器
    tracker = getattr(config.bot, 'cooldown_tracker', None)
    # 如果追踪器不存在或冷却配置已更改，创建新的追踪器
    if tracker is None or getattr(tracker, '_cooldowns_ref', None) is not cooldowns:
        tracker = CooldownTracker(cooldowns)
        tracker._cooldowns_ref = cooldowns
        setattr(config.bot, 'cooldown_tracker', tracker)
    # 筛选出有冷却时间的技能（冷却时间大于0）
    skill_ids = [k for k, cd in cooldowns.items() if cd > 0]
    # 排除黑名单中的技能
    blacklist = getattr(module, 'SKILL_ROTATION_BLACKLIST', [])
    skill_ids = [k for k in skill_ids if k not in blacklist]
    # 筛选出当前可用的技能（冷却完毕的技能）
    available = [k for k in tracker.get_available() if k in skill_ids]
    # 如果没有可用技能，直接返回
    if not available:
        return
    # 随机选择一个可用技能
    skill_id = random.choice(available)
    # 默认为1次按键
    press_count = 1
    # 如果模块有技能按键次数配置，使用配置的值
    if module is not None:
        skill_press_counts = getattr(module, 'SKILL_PRESS_COUNTS', None) or {}
        press_count = skill_press_counts.get(skill_id, 1)
    # 解析技能按键（支持用户自定义按键绑定）
    actual_key = _resolve_key(module, skill_id)
    # 执行技能按键
    press(actual_key, press_count, down_time=0.05, up_time=0.05)
    # 记录技能使用时间（更新冷却时间）
    tracker.record_used(skill_id)
    # 短暂延迟，确保操作流畅
    time.sleep(0.1)


class Move(Command):
    """使用基于当前布局的最短路径移动到指定位置。"""

    def __init__(self, x, y, max_steps=15):
        super().__init__(locals())
        self.target = (float(x), float(y))
        self.max_steps = settings.validate_nonnegative_int(max_steps)
        self.prev_direction = ''
        self.last_attack_time = 0  # 上次攻击时间

    def _new_direction(self, new):
        key_down(new)
        if self.prev_direction and self.prev_direction != new:
            key_up(self.prev_direction)
        self.prev_direction = new
        
    def _check_and_perform_main_attack(self, direction):
        """
        检查是否需要执行主要攻击
        当 Jump_Attack_TYPE = False 且 MAIN_ATTACK_TYPE = 'tap' 时，每2秒进行2次主要攻击
        """
        # 获取当前职业模块
        module = getattr(config.bot.command_book, 'module', None) if getattr(config.bot, 'command_book', None) else None
        if module is None:
            return
        
        # 检查是否满足攻击条件
        jump_attack_type = getattr(module, 'Jump_Attack_TYPE', True)
        main_attack_type = getattr(module, 'MAIN_ATTACK_TYPE', 'hold').lower()
        
        if not jump_attack_type and main_attack_type == 'tap':
            # 检查是否达到攻击时间间隔（2秒）
            current_time = time.time()
            if current_time - self.last_attack_time >= 2:
                # 直接获取技能冷却为0的技能
                cooldowns = getattr(module, 'SKILL_COOLDOWNS', {})
                # 遍历所有技能，找到冷却时间为0的技能
                for skill_id, cd in cooldowns.items():
                    if cd == 0:
                        # 解析技能按键
                        main_key = _resolve_key(module, skill_id)
                        # 执行2次攻击
                        press(main_key, 2, down_time=0.05, up_time=0.05)
                        # 更新上次攻击时间
                        self.last_attack_time = current_time
                        # 找到一个就足够了，退出循环
                        break

    def main(self):
        """
        执行移动操作，将角色移动到目标位置
        """
        counter = self.max_steps  # 剩余步数计数器
        # 获取从当前位置到目标位置的最短路径
        path = config.layout.shortest_path(config.player_pos, self.target)
        
        # 遍历路径上的每个点
        for i, point in enumerate(path):
            toggle = True  # 用于切换水平和垂直移动
            self.prev_direction = ''  # 记录上次移动方向
            # 计算当前位置到当前路径点的距离
            local_error = utils.distance(config.player_pos, point)
            # 计算当前位置到最终目标的距离
            global_error = utils.distance(config.player_pos, self.target)
            
            # 当Bot启用、还有步数、且未到达目标时继续移动
            while config.enabled and counter > 0 and \
                    local_error > settings.move_tolerance and \
                    global_error > settings.move_tolerance:
                if toggle:
                    # 水平移动
                    d_x = point[0] - config.player_pos[0]  # 计算x方向距离
                    # 如果距离大于移动容差的对角线分量
                    if abs(d_x) > settings.move_tolerance / math.sqrt(2):
                        # 确定移动方向
                        if d_x < 0:
                            key = 'left'
                        else:
                            key = 'right'
                        # 更新移动方向
                        self._new_direction(key)
                        # 30%概率在水平移动时跳跃，避免被梯子卡住
                        if random.random() < 0.1:
                            # 获取跳跃键（优先从命令书获取，否则使用默认值'space'）
                            jump_key = getattr(
                                getattr(getattr(config.bot, 'command_book', None), 'module', None), 'Key', None
                            )
                            jump_key = getattr(jump_key, 'JUMP', 'space') if jump_key else 'space'
                            # 执行跳跃
                            press(jump_key, 1, down_time=0.05, up_time=0.05)
                            # 随机延迟
                            time.sleep(utils.rand_float(0.05, 0.12))
                        # 执行移动步骤
                        step(key, point)
                        # 如果启用布局记录，添加当前位置到布局
                        if settings.record_layout:
                            time.sleep(0.3)
                            config.layout.add(*config.player_pos)
                        # 减少剩余步数
                        counter -= 1
                        # 尝试在移动过程中使用技能
                        _try_skill_during_move()
                        # 检查是否需要执行主要攻击
                        self._check_and_perform_main_attack(key)
                        # 如果不是最后一个路径点，添加短暂延迟
                        if i < len(path) - 1:
                            time.sleep(0.15)
                else:
                    # 垂直移动
                    d_y = point[1] - config.player_pos[1]  # 计算y方向距离
                    # 如果距离大于移动容差的对角线分量
                    if abs(d_y) > settings.move_tolerance / math.sqrt(2):
                        # 确定移动方向
                        if d_y < 0:
                            key = 'up'
                        else:
                            key = 'down'
                        # 永远不要按住'up'键 - step函数只使用绳索提升，不使用上+跳
                        if key == 'up':
                            if self.prev_direction:
                                key_up(self.prev_direction)  # 释放之前的方向键
                                self.prev_direction = ''
                        else:
                            # 更新移动方向
                            self._new_direction(key)
                        # 执行移动步骤
                        step(key, point)
                        # 如果启用布局记录，添加当前位置到布局
                        if settings.record_layout:
                            time.sleep(0.3)
                            config.layout.add(*config.player_pos)
                        # 减少剩余步数
                        counter -= 1
                        # 尝试在移动过程中使用技能
                        _try_skill_during_move()
                        # 如果不是最后一个路径点，添加短暂延迟
                        if i < len(path) - 1:
                            time.sleep(0.05)
                # 更新距离值
                local_error = utils.distance(config.player_pos, point)
                global_error = utils.distance(config.player_pos, self.target)
                # 切换移动模式（水平/垂直）
                toggle = not toggle
            # 如果还有按下的方向键，释放它
            if self.prev_direction:
                key_up(self.prev_direction)


class Adjust(Command):
    """使用小幅度移动微调玩家位置。"""

    def __init__(self, x, y, max_steps=5):
        super().__init__(locals())
        self.target = (float(x), float(y))  # 目标位置
        self.max_steps = settings.validate_nonnegative_int(max_steps)  # 最大调整步数


def step(direction, target):
    """
    默认的'step'函数。如果未被覆盖，将立即停止Bot。
    :param direction:   移动方向
    :param target:      要移动到的目标位置
    :return:            None
    """

    print("\n[!] 当前命令书中未实现'step'函数，中止进程。")
    config.enabled = False


class Wait(Command):
    """等待指定的时间。"""

    def __init__(self, duration):
        super().__init__(locals())
        self.duration = float(duration)  # 等待时间（秒）

    def main(self):
        time.sleep(self.duration)  # 执行等待


class Walk(Command):
    """向指定方向行走指定的时间。"""

    def __init__(self, direction, duration):
        super().__init__(locals())
        # 验证并设置水平方向
        self.direction = settings.validate_horizontal_arrows(direction)
        self.duration = float(duration)  # 行走时间（秒）

    def main(self):
        key_down(self.direction)  # 按下方向键
        time.sleep(self.duration)  # 持续指定时间
        key_up(self.direction)  # 释放方向键
        time.sleep(0.05)  # 短暂延迟


class Fall(Command):
    """
    执行下跳，然后自由落体直到玩家超过与起始位置的给定距离。
    """

    def __init__(self, distance=settings.move_tolerance / 2):
        super().__init__(locals())
        self.distance = float(distance)  # 下落距离阈值

    def main(self):
        start = config.player_pos  # 记录起始位置
        key_down('down')  # 按下下方向键
        time.sleep(0.05)  # 短暂延迟
        # 如果启用舞台恐惧模式，有50%概率添加随机延迟
        if config.stage_fright and utils.bernoulli(0.5):
            time.sleep(utils.rand_float(0.2, 0.4))
        counter = 6  # 最大跳跃次数
        # 当Bot启用、还有跳跃次数、且未达到距离阈值时继续
        while config.enabled and \
                counter > 0 and \
                utils.distance(start, config.player_pos) < self.distance:
            press('space', 1, down_time=0.1)  # 按空格键跳跃
            counter -= 1
        key_up('down')  # 释放下方向键
        time.sleep(0.05)  # 短暂延迟


# 技能轮转的标准按键（当Key查找失败时的备用值）
SKILL_ROTATION_MAIN_ATTACK_KEY = 'ctrl'  # 主攻击键
SKILL_ROTATION_JUMP_KEY = 'space'  # 跳跃键


def _resolve_key(module, skill_id: str) -> str:
    """Resolve skill ID to physical key. Supports rebinds via Key class.
    If skill_id is a Key attribute (e.g. STRIKE), returns Key.STRIKE (user's binding).
    Otherwise returns skill_id as literal key (backwards compat for key-based cooldowns)."""
    if module is None or not hasattr(module, 'Key'):
        return skill_id
    return getattr(module.Key, skill_id, skill_id)


class SkillRotation(Command):
    """
    在指定持续时间内交替执行主攻击阶段和技能阶段。
    - 主攻击：按住主攻击键 + 左右方向键 1-3 秒（边移动边攻击）。
    - 技能阶段：使用一个随机的冷却完毕的技能；如果所有技能都在冷却中，
      则继续按住方向键攻击直到有技能冷却完毕。
    使用 Key 类进行按键查找，以尊重用户的按键绑定。
    """
    id = 'SkillRotation'

    def __init__(self, duration=5):
        """初始化SkillRotation命令
        
        Args:
            duration: 技能轮换的持续时间（秒），默认为5秒
        """
        super().__init__(locals())
        self.duration = float(duration)

    def _main_attack_phase(self, main_key: str, max_sec: float = 5.0, attack_type: str = 'jump_att') -> None:
        """执行主攻击阶段
        
        Args:
            main_key: 主攻击键
            max_sec: 最大攻击持续时间（秒）
            attack_type: 攻击类型，'hold'表示按住，'tap'表示点按，'jump_att'表示跳跃攻击
        """
        if max_sec <= 0.05:
            return
        # 根据最大时间确定实际攻击持续时间
        if max_sec >= 1.0:
            duration = utils.rand_float(1.0, min(3.0, max_sec))
        elif max_sec > 0.2:
            duration = utils.rand_float(0.2, max_sec)
        else:
            duration = utils.rand_float(0.05, max_sec)
        
        # 模拟人类操作：随机小延迟
        if utils.bernoulli(0.7):
            time.sleep(utils.rand_float(0.05, 0.15))
        
        # 随机选择左或右方向
        direction = random.choice(('left', 'right'))
        
        # 模拟人类操作：方向键按下前的随机延迟
        if utils.bernoulli(0.5):
            time.sleep(utils.rand_float(0.02, 0.08))
        
        # 按下方向键
        key_down(direction)
        
        # 检查是否启用跳跃攻击模式
        if attack_type == 'jump_att':
            # 双击跳跃
            jump_key = SKILL_ROTATION_JUMP_KEY
            # 从模块中获取跳跃键（如果有）
            module = getattr(config.bot.command_book, 'module', None) if getattr(config.bot, 'command_book', None) else None
            if module and hasattr(module, 'Key') and hasattr(module.Key, 'JUMP'):
                jump_key = getattr(module.Key, 'JUMP')
            
            # 模拟人类操作：跳跃前的随机延迟
            if utils.bernoulli(0.6):
                time.sleep(utils.rand_float(0.03, 0.1))
            
            # 随机调整跳跃次数，模拟人类操作
            jump_presses = random.choice([2, 2, 2, 1])  # 大部分情况下按2次，偶尔按1次
            # 随机调整按下和释放时间
            down_time = utils.rand_float(0.04, 0.08)
            up_time = utils.rand_float(0.04, 0.08)
            press(jump_key, jump_presses, down_time=down_time, up_time=up_time)
            
            # 模拟人类操作：攻击前的随机延迟
            if utils.bernoulli(0.7):
                time.sleep(utils.rand_float(0.05, 0.12))
            
            # 随机调整攻击次数，模拟人类操作
            attack_presses = random.choice([3, 4, 4])  # 大部分情况下按4次，偶尔按3次
            # 随机调整按下和释放时间
            down_time = utils.rand_float(0.04, 0.08)
            up_time = utils.rand_float(0.04, 0.08)
            press(main_key, attack_presses, down_time=down_time, up_time=up_time)
            
            # 模拟人类操作：攻击后的随机延迟
            if utils.bernoulli(0.6):
                time.sleep(utils.rand_float(0.05, 0.15))
        
        elif attack_type == 'hold':
            # 按住攻击模式
            # 模拟人类操作：攻击前的随机延迟
            if utils.bernoulli(0.6):
                time.sleep(utils.rand_float(0.03, 0.09))
            
            key_down(main_key)
            # 计算攻击结束时间
            end_hold = time.time() + duration
            # 持续攻击直到时间结束
            while config.enabled and time.time() < end_hold:
                # 模拟人类操作：随机小延迟
                time.sleep(utils.rand_float(0.04, 0.06))
                # 模拟人类操作：偶尔松开再按下攻击键
                if utils.bernoulli(0.15):
                    key_up(main_key)
                    time.sleep(utils.rand_float(0.05, 0.1))
                    key_down(main_key)
            # 释放攻击键
            key_up(main_key)
        else:
            # 点按攻击模式
            # 计算点按攻击结束时间
            end_time = time.time() + duration
            # 持续点按攻击直到时间结束
            while config.enabled and time.time() < end_time:
                # 点按攻击键一次
                # 模拟人类操作：随机的按下和释放时间
                down_time = utils.rand_float(0.08, 0.15)
                up_time = utils.rand_float(0.08, 0.15)
                press(main_key, 1, down_time=down_time, up_time=up_time)
                # 随机间隔，模拟人类点击
                time.sleep(utils.rand_float(0.1, 0.4))
        
        # 模拟人类操作：释放方向键前的随机延迟
        if utils.bernoulli(0.5):
            time.sleep(utils.rand_float(0.02, 0.08))
        
        # 释放方向键
        key_up(direction)
        # 短暂延迟
        time.sleep(utils.rand_float(0.02, 0.05))

    def main(self):
        """执行技能轮换逻辑
        
        执行流程：
        1. 导入冷却追踪器
        2. 获取当前职业的技能冷却配置
        3. 初始化或更新冷却追踪器
        4. 确定主攻击技能
        5. 确定可用于轮换的技能（有冷却时间的技能）
        6. 在指定持续时间内循环执行：
           a. 执行主攻击阶段
           b. 检查是否有冷却完毕的技能
           c. 如果没有可用技能，继续主攻击直到有技能可用
           d. 如果有可用技能，随机选择一个使用
        """
        # 导入冷却追踪器
        from src.routine.cooldown_tracker import CooldownTracker
        # 获取当前职业的模块
        module = getattr(config.bot.command_book, 'module', None) if getattr(config.bot, 'command_book', None) else None
        # 获取技能冷却配置
        cooldowns = getattr(module, 'SKILL_COOLDOWNS', None) if module else None
        if cooldowns is None:
            cooldowns = {}
        # 获取或创建冷却追踪器
        tracker = getattr(config.bot, 'cooldown_tracker', None)
        if tracker is None or getattr(tracker, '_cooldowns_ref', None) is not cooldowns:
            tracker = CooldownTracker(cooldowns)
            tracker._cooldowns_ref = cooldowns
            setattr(config.bot, 'cooldown_tracker', tracker)
        # 确定主攻击技能（选择第一个冷却时间为0的技能）
        main_attack_id = next((k for k, cd in cooldowns.items() if cd == 0), None)
        main_key = _resolve_key(module, main_attack_id) if main_attack_id else SKILL_ROTATION_MAIN_ATTACK_KEY
        # 获取攻击类型配置，默认为'hold'（按住）
        attack_type = 'hold'
        if module is not None:
            attack_type = getattr(module, 'MAIN_ATTACK_TYPE', 'hold').lower()
            # 确保攻击类型有效
            if attack_type not in ['hold', 'tap', 'jump_att']:
                attack_type = 'hold'
        # 确定可用于轮换的技能（冷却时间大于0的技能）
        skill_ids = [k for k, cd in cooldowns.items() if cd > 0]
        # 排除黑名单中的技能
        if module is not None:
            blacklist = getattr(module, 'SKILL_ROTATION_BLACKLIST', [])
            skill_ids = [k for k in skill_ids if k not in blacklist]
        # 计算技能轮换结束时间
        end = time.time() + self.duration
        # 主循环
        while config.enabled and time.time() < end:
            # 计算剩余时间
            remaining = end - time.time()
            # 执行主攻击阶段
            self._main_attack_phase(main_key, max_sec=min(5.0, max(0.2, remaining)), attack_type=attack_type)
            # 检查是否需要退出
            if not config.enabled or time.time() >= end:
                break
            # 获取当前可用的技能
            available = [k for k in tracker.get_available() if k in skill_ids]
            # 如果没有可用技能，继续主攻击直到有技能可用
            while config.enabled and time.time() < end and not available:
                self._main_attack_phase(main_key, max_sec=0.3, attack_type=attack_type)
                available = [k for k in tracker.get_available() if k in skill_ids]
            # 检查是否需要退出
            if not config.enabled or time.time() >= end:
                break
            # 如果有可用技能，选择一个使用
            if available:
                # 优先处理终极无限1号和2号的交替释放
                ultimate_skills = ['终极无限1号', '终极无限2号']
                available_ultimate = [skill for skill in available if skill in ultimate_skills]
                
                if len(available_ultimate) > 1:
                    # 检查是否都是初始状态（上次使用时间为0）
                    all_initial = all(tracker.last_used.get(skill, 0) == 0 for skill in available_ultimate)
                    if all_initial:
                        # 初始状态下，只选择一个终极无限技能（默认选择1号）
                        skill_id = '终极无限1号'
                    else:
                        # 如果两个终极无限都可用，选择上次使用时间更早的
                        skill_id = min(available_ultimate, key=lambda skill: tracker.last_used.get(skill, 0))
                elif available_ultimate:
                    # 如果只有一个终极无限可用，使用它
                    skill_id = available_ultimate[0]
                else:
                    # 否则随机选择一个其他技能
                    skill_id = random.choice(available)
                
                press_count = 1
                # 检查是否有指定的技能按键次数
                if module is not None:
                    skill_press_counts = getattr(module, 'SKILL_PRESS_COUNTS', None) or {}
                    press_count = skill_press_counts.get(skill_id, 1)
                # 解析技能按键
                actual_key = _resolve_key(module, skill_id)
                # 执行技能
                press(actual_key, press_count, down_time=0.05, up_time=0.05)
                # 记录技能使用时间
                tracker.record_used(skill_id)
                # 等待技能后摇结束
                time.sleep(0.5)
            # 短暂延迟
            time.sleep(0.05)


class Buff(Command):
    """默认命令书中未定义的 'buff' 命令。"""

    def main(self):
        print("\n[!] 当前命令书中未实现 'Buff' 命令，中止进程。")
        config.enabled = False