"""
用户定义的设置列表，可由例程更改。还包含一组可用于强制参数类型的验证函数。
"""


#################################
#      验证函数      #
#################################
def validate_nonnegative_int(value):
    """
    检查 VALUE 是否可以是有效的非负整数。
    :param value:   要检查的字符串。
    :return:        作为整数的 VALUE。
    """

    if int(value) >= 1:
        return int(value)
    raise ValueError(f"'{value}' 不是有效的非负整数。")


def validate_boolean(value):
    """
    检查 VALUE 是否是有效的 Python 布尔值。
    :param value:   要检查的字符串。
    :return:        作为布尔值的 VALUE
    """

    value = value.lower()
    if value in {'true', 'false'}:
        return True if value == 'true' else False
    elif int(value) in {0, 1}:
        return bool(int(value))
    raise ValueError(f"'{value}' 不是有效的布尔值。")


def validate_arrows(key):
    """
    检查字符串 KEY 是否是箭头键。
    :param key:     要检查的键。
    :return:        如果是有效的箭头键，则返回小写的 KEY。
    """

    if isinstance(key, str):
        key = key.lower()
        if key in ['up', 'down', 'left', 'right']:
            return key
    raise ValueError(f"'{key}' 不是有效的箭头键。")


def validate_horizontal_arrows(key):
    """
    检查字符串 KEY 是否是左箭头键或右箭头键。
    :param key:     要检查的键。
    :return:        如果是有效的水平箭头键，则返回小写的 KEY。
    """

    if isinstance(key, str):
        key = key.lower()
        if key in ['left', 'right']:
            return key
    raise ValueError(f"'{key}' 不是有效的水平箭头键。")


#########################
#       设置        #
#########################
def validate_positive_float(value):
    v = float(value)
    if v > 0:
        return v
    raise ValueError(f"'{value}' 不是有效的正数。")


# 将每个设置映射到其验证函数的字典
SETTING_VALIDATORS = {
    'move_tolerance': float,
    'adjust_tolerance': float,
    'record_layout': validate_boolean,
    'buff_cooldown': validate_nonnegative_int,
    'skill_rotation_mode': validate_boolean,
    'skill_rotation_duration': validate_positive_float,
}


def reset():
    """将所有设置重置为默认值。"""

    global move_tolerance, adjust_tolerance, record_layout, buff_cooldown
    global skill_rotation_mode, skill_rotation_duration
    move_tolerance = 0.07
    adjust_tolerance = 0.02
    record_layout = False
    buff_cooldown = 180
    skill_rotation_mode = False
    skill_rotation_duration = 5.0


# 向 Point 移动时与目标的允许误差
move_tolerance = 0.07

# 调整到特定位置时与该位置的允许误差
adjust_tolerance = 0.02

# 机器人是否应该将新的玩家位置保存到当前布局
record_layout = False

# 每次调用 'buff' 命令之间等待的时间（以秒为单位）
buff_cooldown = 180

# 如果为 True，在每个 Point 运行随机的冷却技能，持续 skill_rotation_duration 时间，而不是执行该点的命令
skill_rotation_mode = False
skill_rotation_duration = 5.0

reset()