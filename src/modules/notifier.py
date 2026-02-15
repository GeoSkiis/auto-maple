"""A module for detecting and notifying the user of dangerous in-game events."""

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


# A rune's symbol on the minimap
RUNE_RANGES = (
    ((141, 148, 245), (146, 158, 255)),
)
rune_filtered = utils.filter_color(cv2.imread('assets/rune_template.png'), RUNE_RANGES)
RUNE_TEMPLATE = cv2.cvtColor(rune_filtered, cv2.COLOR_BGR2GRAY)

# Other players' symbols on the minimap
OTHER_RANGES = (
    ((0, 245, 215), (10, 255, 255)),
)
other_filtered = utils.filter_color(cv2.imread('assets/other_template.png'), OTHER_RANGES)
OTHER_TEMPLATE = cv2.cvtColor(other_filtered, cv2.COLOR_BGR2GRAY)

# The Elite Boss's warning sign
ELITE_TEMPLATE = cv2.imread('assets/elite_template.jpg', 0)

# Pollo Message
POLLO_TEMPLATE = cv2.imread('assets/pollo_template.png', 0)

# Fritto Message
FRITTO_TEMPLATE = cv2.imread('assets/fritto_template.png', 0)

# Especia Message
ESPECIA_TEMPLATE = cv2.imread('assets/especia_template.png', 0)

# Twentoona Message
TWENTOONA_TEMPLATE = cv2.imread('assets/twentoona_template.png', 0)

# Skull Death left arrow
SKULL_DEATH_LEFT_ARROW_TEMPLATE = cv2.imread('assets/skull_death_left_arrow.png', 0)

# Skull Death right arrow
SKULL_DEATH_RIGHT_ARROW_TEMPLATE = cv2.imread('assets/skull_death_right_arrow.png', 0)

# Skull Death hp bar
SKULL_DEATH_HP_BAR_TEMPLATE = cv2.imread('assets/skull_death_hp_bar.png', 0)

# Skull Death skull
SKULL_DEATH_SKULL_TEMPLATE = cv2.imread('assets/skull_death_skull.png', 0)

def get_alert_path(name):
    return os.path.join(Notifier.ALERTS_DIR, f'{name}.mp3')


class Notifier:
    ALERTS_DIR = os.path.join('assets', 'alerts')

    def __init__(self):
        """Initializes this Notifier object's main thread."""

        pygame.mixer.init()
        self.mixer = pygame.mixer.music

        self.ready = False
        self.thread = threading.Thread(target=self._main)
        self.thread.daemon = True

        self.room_change_threshold = 0.9
        self.rune_alert_delay = 270         # 4.5 minutes

    def start(self):
        """Starts this Notifier's thread."""

        print('\n[~] Started notifier')
        self.thread.start()

    def _main(self):
        self.ready = True
        prev_others = 0
        rune_start_time = time.time()
        while True:
            if config.enabled:
                frame = config.capture.frame
                height, width, _ = frame.shape
                minimap = config.capture.minimap['minimap']

                # Check for unexpected black screen
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if np.count_nonzero(gray < 15) / height / width > self.room_change_threshold:
                    time.sleep(40)
                    frame = config.capture.frame
                    height, width, _ = frame.shape
                    minimap = config.capture.minimap['minimap']

                    # Check for unexpected black screen
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    if np.count_nonzero(gray < 15) / height / width > self.room_change_threshold:
                        self._alert('siren')

                # Check for Pollo Message
                interrupting_message_frame = frame[height // 4:3 * height // 4, :]
                # cv2.imwrite('interrupting_frame.png', interrupting_message_frame)
                pollo = utils.multi_match(interrupting_message_frame, POLLO_TEMPLATE, threshold=0.9)
                if len(pollo) > 0:
                    print("Pollo Message Detected")
                    print(pollo)
                    press("esc", 1, down_time=0.1)

                # Check for Fritto Message
                fritto = utils.multi_match(interrupting_message_frame, FRITTO_TEMPLATE, threshold=0.9)
                if len(fritto) > 0:
                    print("Fritto Message Detected")
                    print(fritto)
                    press("esc", 1, down_time=0.1)

                # Check for Especia Message
                especia = utils.multi_match(interrupting_message_frame, ESPECIA_TEMPLATE, threshold=0.9)
                if len(especia) > 0:
                    print("Especia Message Detected")
                    print(especia)
                    press("esc", 1, down_time=0.1)

                # Check for Twentoona Message
                twentoona = utils.multi_match(interrupting_message_frame, TWENTOONA_TEMPLATE, threshold=0.9)
                if len(twentoona) > 0:
                    print("Twentoona Message Detected")
                    print(twentoona)
                    press("esc", 1, down_time=0.1)

                # Check for Skull Death
                skull_death_left_arrow = utils.multi_match(interrupting_message_frame, SKULL_DEATH_LEFT_ARROW_TEMPLATE, threshold=0.9)
                skull_death_right_arrow = utils.multi_match(interrupting_message_frame, SKULL_DEATH_RIGHT_ARROW_TEMPLATE, threshold=0.9)
                skull_death_hp_bar = utils.multi_match(interrupting_message_frame, SKULL_DEATH_HP_BAR_TEMPLATE, threshold=0.9)
                skull_death_skull = utils.multi_match(interrupting_message_frame, SKULL_DEATH_SKULL_TEMPLATE, threshold=0.9)
                if len(skull_death_left_arrow) > 0 or len(skull_death_right_arrow) > 0 or len(skull_death_hp_bar) > 0 or len(skull_death_skull) > 0:
                    print("Skull Death Detected")
                    print(f"Detection: left arrow {skull_death_left_arrow}, right arrow {skull_death_right_arrow}, hp bar {skull_death_hp_bar}, skull {skull_death_skull}")
                    for _ in range(20):
                        press("left", 1, down_time=0.1)
                        press("right", 1, down_time=0.1)
                    print("Skull Death Avoided")

                # Check for elite warning
                elite = utils.multi_match(interrupting_message_frame, ELITE_TEMPLATE, threshold=0.9)
                if len(elite) > 0:
                    print("Elite Boss Detected")
                #     self._alert('siren')

                # Check for other players entering the map
                filtered = utils.filter_color(minimap, OTHER_RANGES)
                others = len(utils.multi_match(filtered, OTHER_TEMPLATE, threshold=0.5))
                config.stage_fright = others > 0
                if others != prev_others:
                    if others > prev_others:
                        self._ping('ding')
                    prev_others = others

                # Check for rune
                now = time.time()
                if not config.bot.rune_active:
                    filtered = utils.filter_color(minimap, RUNE_RANGES)
                    matches = utils.multi_match(filtered, RUNE_TEMPLATE, threshold=0.9)
                    rune_start_time = now
                    if matches and config.routine.sequence:
                        abs_rune_pos = (matches[0][0], matches[0][1])
                        config.bot.rune_pos = utils.convert_to_relative(abs_rune_pos, minimap)
                        distances = list(map(distance_to_rune, config.routine.sequence))
                        index = np.argmin(distances)
                        config.bot.rune_closest_pos = config.routine[index].location
                        config.bot.rune_active = True
                        self._ping('rune_appeared', volume=0.75)
                # elif now - rune_start_time > self.rune_alert_delay:     # Alert if rune hasn't been solved
                #     config.bot.rune_active = False
                #     self._alert('siren')
            time.sleep(0.05)

    def _alert(self, name, volume=0.75):
        """
        Plays an alert to notify user of a dangerous event. Stops the alert
        once the key bound to 'Start/stop' is pressed.
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
        """A quick notification for non-dangerous events."""

        self.mixer.load(get_alert_path(name))
        self.mixer.set_volume(volume)
        self.mixer.play()


#################################
#       Helper Functions        #
#################################
def distance_to_rune(point):
    """
    Calculates the distance from POINT to the rune.
    :param point:   The position to check.
    :return:        The distance from POINT to the rune, infinity if it is not a Point object.
    """

    if isinstance(point, Point):
        return utils.distance(config.bot.rune_pos, point.location)
    return float('inf')
