"""A collection of classes used to execute a Routine."""

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
            raise TypeError('Component superclass __init__ only accepts 1 (optional) argument: LOCALS')
        if len(kwargs) != 0:
            raise TypeError('Component superclass __init__ does not accept any keyword arguments')
        if len(args) == 0:
            self.kwargs = {}
        elif type(args[0]) != dict:
            raise TypeError("Component superclass __init__ only accepts arguments of type 'dict'.")
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
        """Updates this Component's constructor arguments with new arguments."""

        self.__class__(*args, **kwargs)     # Validate arguments before actually updating values
        self.__init__(*args, **kwargs)

    def info(self):
        """Returns a dictionary of useful information about this Component."""

        return {
            'name': self.__class__.__name__,
            'vars': self.kwargs.copy()
        }

    def encode(self):
        """Encodes an object using its ID and its __init__ arguments."""

        arr = [self.id]
        for key, value in self.kwargs.items():
            if key != 'id' and type(self.kwargs[key]) in Component.PRIMITIVES:
                arr.append(f'{key}={value}')
        return ', '.join(arr)


class Point(Component):
    """Represents a location in a user-defined routine."""

    id = '*'

    def __init__(self, x, y, frequency=1, skip='False', adjust='False'):
        super().__init__(locals())
        self.x = float(x)
        self.y = float(y)
        self.location = (self.x, self.y)
        self.frequency = settings.validate_nonnegative_int(frequency)
        self.counter = int(settings.validate_boolean(skip))
        self.adjust = settings.validate_boolean(adjust)
        if not hasattr(self, 'commands'):       # Updating Point should not clear commands
            self.commands = []

    def main(self):
        """Executes the set of actions associated with this Point."""

        if self.counter == 0:
            move = config.bot.command_book['move']
            move(*self.location).execute()
            if self.adjust:
                adjust = config.bot.command_book['adjust']      # TODO: adjust using step('up')?
                adjust(*self.location).execute()
            if settings.skill_rotation_mode:
                SkillRotation(duration=settings.skill_rotation_duration).execute()
            else:
                for command in self.commands:
                    command.execute()
        self._increment_counter()

    @utils.run_if_enabled
    def _increment_counter(self):
        """Increments this Point's counter, wrapping back to 0 at the upper bound."""

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
    """Jumps to the given Label."""

    id = '>'

    def __init__(self, label, frequency=1, skip='False'):
        super().__init__(locals())
        self.label = str(label)
        self.frequency = settings.validate_nonnegative_int(frequency)
        self.counter = int(settings.validate_boolean(skip))
        self.link = None

    def main(self):
        if self.link is None:
            print(f"\n[!] Label '{self.label}' does not exist.")
        else:
            if self.counter == 0:
                config.routine.index = self.link.index
            self._increment_counter()

    @utils.run_if_enabled
    def _increment_counter(self):
        self.counter = (self.counter + 1) % self.frequency

    def bind(self):
        """
        Binds this Goto to its corresponding Label. If the Label's index changes, this Goto
        instance will automatically be able to access the updated value.
        :return:    Whether the binding was successful
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
    """Changes the value of the given setting variable."""

    id = '$'

    def __init__(self, target, value):
        super().__init__(locals())
        self.key = str(target)
        if self.key not in settings.SETTING_VALIDATORS:
            raise ValueError(f"Setting '{target}' does not exist")
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
    If the current command book has SKILL_COOLDOWNS, use one random off-cooldown skill.
    Uses the same CooldownTracker as SkillRotation so cooldowns stay in sync.
    """
    from src.routine.cooldown_tracker import CooldownTracker
    module = getattr(config.bot.command_book, 'module', None) if getattr(config.bot, 'command_book', None) else None
    cooldowns = getattr(module, 'SKILL_COOLDOWNS', None) if module else None
    if cooldowns is None:
        return
    tracker = getattr(config.bot, 'cooldown_tracker', None)
    if tracker is None or getattr(tracker, '_cooldowns_ref', None) is not cooldowns:
        tracker = CooldownTracker(cooldowns)
        tracker._cooldowns_ref = cooldowns
        setattr(config.bot, 'cooldown_tracker', tracker)
    skill_ids = [k for k, cd in cooldowns.items() if cd > 0]
    available = [k for k in tracker.get_available() if k in skill_ids]
    if not available:
        return
    skill_id = random.choice(available)
    press_count = 1
    if module is not None:
        skill_press_counts = getattr(module, 'SKILL_PRESS_COUNTS', None) or {}
        press_count = skill_press_counts.get(skill_id, 1)
    actual_key = _resolve_key(module, skill_id)
    press(actual_key, press_count, down_time=0.05, up_time=0.05)
    tracker.record_used(skill_id)
    time.sleep(0.05)


class Move(Command):
    """Moves to a given position using the shortest path based on the current Layout."""

    def __init__(self, x, y, max_steps=15):
        super().__init__(locals())
        self.target = (float(x), float(y))
        self.max_steps = settings.validate_nonnegative_int(max_steps)
        self.prev_direction = ''

    def _new_direction(self, new):
        key_down(new)
        if self.prev_direction and self.prev_direction != new:
            key_up(self.prev_direction)
        self.prev_direction = new

    def main(self):
        counter = self.max_steps
        path = config.layout.shortest_path(config.player_pos, self.target)
        for i, point in enumerate(path):
            toggle = True
            self.prev_direction = ''
            local_error = utils.distance(config.player_pos, point)
            global_error = utils.distance(config.player_pos, self.target)
            while config.enabled and counter > 0 and \
                    local_error > settings.move_tolerance and \
                    global_error > settings.move_tolerance:
                if toggle:
                    d_x = point[0] - config.player_pos[0]
                    if abs(d_x) > settings.move_tolerance / math.sqrt(2):
                        if d_x < 0:
                            key = 'left'
                        else:
                            key = 'right'
                        self._new_direction(key)
                        # Occasional jump during horizontal movement to avoid getting stuck on ladders
                        if random.random() < 0.3:
                            jump_key = getattr(
                                getattr(getattr(config.bot, 'command_book', None), 'module', None), 'Key', None
                            )
                            jump_key = getattr(jump_key, 'JUMP', 'space') if jump_key else 'space'
                            press(jump_key, 1, down_time=0.05, up_time=0.05)
                            time.sleep(utils.rand_float(0.05, 0.12))
                        step(key, point)
                        if settings.record_layout:
                            config.layout.add(*config.player_pos)
                        counter -= 1
                        _try_skill_during_move()
                        if i < len(path) - 1:
                            time.sleep(0.15)
                else:
                    d_y = point[1] - config.player_pos[1]
                    if abs(d_y) > settings.move_tolerance / math.sqrt(2):
                        if d_y < 0:
                            key = 'up'
                        else:
                            key = 'down'
                        # Never hold 'up' - step uses rope lift only, no up+jump
                        if key == 'up':
                            if self.prev_direction:
                                key_up(self.prev_direction)
                                self.prev_direction = ''
                        else:
                            self._new_direction(key)
                        step(key, point)
                        if settings.record_layout:
                            config.layout.add(*config.player_pos)
                        counter -= 1
                        _try_skill_during_move()
                        if i < len(path) - 1:
                            time.sleep(0.05)
                local_error = utils.distance(config.player_pos, point)
                global_error = utils.distance(config.player_pos, self.target)
                toggle = not toggle
            if self.prev_direction:
                key_up(self.prev_direction)


class Adjust(Command):
    """Fine-tunes player position using small movements."""

    def __init__(self, x, y, max_steps=5):
        super().__init__(locals())
        self.target = (float(x), float(y))
        self.max_steps = settings.validate_nonnegative_int(max_steps)


def step(direction, target):
    """
    The default 'step' function. If not overridden, immediately stops the bot.
    :param direction:   The direction in which to move.
    :param target:      The target location to step towards.
    :return:            None
    """

    print("\n[!] Function 'step' not implemented in current command book, aborting process.")
    config.enabled = False


class Wait(Command):
    """Waits for a set amount of time."""

    def __init__(self, duration):
        super().__init__(locals())
        self.duration = float(duration)

    def main(self):
        time.sleep(self.duration)


class Walk(Command):
    """Walks in the given direction for a set amount of time."""

    def __init__(self, direction, duration):
        super().__init__(locals())
        self.direction = settings.validate_horizontal_arrows(direction)
        self.duration = float(duration)

    def main(self):
        key_down(self.direction)
        time.sleep(self.duration)
        key_up(self.direction)
        time.sleep(0.05)


class Fall(Command):
    """
    Performs a down-jump and then free-falls until the player exceeds a given distance
    from their starting position.
    """

    def __init__(self, distance=settings.move_tolerance / 2):
        super().__init__(locals())
        self.distance = float(distance)

    def main(self):
        start = config.player_pos
        key_down('down')
        time.sleep(0.05)
        if config.stage_fright and utils.bernoulli(0.5):
            time.sleep(utils.rand_float(0.2, 0.4))
        counter = 6
        while config.enabled and \
                counter > 0 and \
                utils.distance(start, config.player_pos) < self.distance:
            press('space', 1, down_time=0.1)
            counter -= 1
        key_up('down')
        time.sleep(0.05)


# Standard keys for skill rotation (fallback when Key lookup fails)
SKILL_ROTATION_MAIN_ATTACK_KEY = 'ctrl'
SKILL_ROTATION_JUMP_KEY = 'space'


def _resolve_key(module, skill_id: str) -> str:
    """Resolve skill ID to physical key. Supports rebinds via Key class.
    If skill_id is a Key attribute (e.g. STRIKE), returns Key.STRIKE (user's binding).
    Otherwise returns skill_id as literal key (backwards compat for key-based cooldowns)."""
    if module is None or not hasattr(module, 'Key'):
        return skill_id
    return getattr(module.Key, skill_id, skill_id)


class SkillRotation(Command):
    """
    Alternate between main-attack phase and skill phase for a duration.
    - Main attack: hold main attack key + left or right for 1–3 sec (attack while moving).
    - Skill phase: use one random skill that is off cooldown; if all on CD,
      keep attacking with direction until one is ready.
    Uses Key class for key lookup so user rebinds are respected.
    """
    id = 'SkillRotation'

    def __init__(self, duration=5):
        super().__init__(locals())
        self.duration = float(duration)

    def _main_attack_phase(self, main_key: str, max_sec: float = 5.0) -> None:
        """Hold main attack key + a direction (left/right) to attack while moving for 1–3 sec."""
        if max_sec <= 0.05:
            return
        if max_sec >= 1.0:
            duration = utils.rand_float(1.0, min(3.0, max_sec))
        elif max_sec > 0.2:
            duration = utils.rand_float(0.2, max_sec)
        else:
            duration = utils.rand_float(0.05, max_sec)
        direction = random.choice(('left', 'right'))
        key_down(direction)
        key_down(main_key)
        end_hold = time.time() + duration
        while config.enabled and time.time() < end_hold:
            time.sleep(0.05)
        key_up(main_key)
        key_up(direction)
        time.sleep(0.03)

    def main(self):
        from src.routine.cooldown_tracker import CooldownTracker
        module = getattr(config.bot.command_book, 'module', None) if getattr(config.bot, 'command_book', None) else None
        cooldowns = getattr(module, 'SKILL_COOLDOWNS', None) if module else None
        if cooldowns is None:
            cooldowns = {}
        tracker = getattr(config.bot, 'cooldown_tracker', None)
        if tracker is None or getattr(tracker, '_cooldowns_ref', None) is not cooldowns:
            tracker = CooldownTracker(cooldowns)
            tracker._cooldowns_ref = cooldowns
            setattr(config.bot, 'cooldown_tracker', tracker)
        # Main attack = first skill with 0 cd (or fallback)
        main_attack_id = next((k for k, cd in cooldowns.items() if cd == 0), None)
        main_key = _resolve_key(module, main_attack_id) if main_attack_id else SKILL_ROTATION_MAIN_ATTACK_KEY
        # Skills with cd > 0 for rotation
        skill_ids = [k for k, cd in cooldowns.items() if cd > 0]
        end = time.time() + self.duration
        while config.enabled and time.time() < end:
            remaining = end - time.time()
            self._main_attack_phase(main_key, max_sec=min(5.0, max(0.2, remaining)))
            if not config.enabled or time.time() >= end:
                break
            available = [k for k in tracker.get_available() if k in skill_ids]
            while config.enabled and time.time() < end and not available:
                self._main_attack_phase(main_key, max_sec=0.3)
                available = [k for k in tracker.get_available() if k in skill_ids]
            if not config.enabled or time.time() >= end:
                break
            if available:
                skill_id = random.choice(available)
                press_count = 1
                if module is not None:
                    skill_press_counts = getattr(module, 'SKILL_PRESS_COUNTS', None) or {}
                    press_count = skill_press_counts.get(skill_id, 1)
                actual_key = _resolve_key(module, skill_id)
                press(actual_key, press_count, down_time=0.05, up_time=0.05)
                tracker.record_used(skill_id)
            time.sleep(0.05)


class Buff(Command):
    """Undefined 'buff' command for the default command book."""

    def main(self):
        print("\n[!] 'Buff' command not implemented in current command book, aborting process.")
        config.enabled = False
