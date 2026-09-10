"""A module for detecting and notifying the user of dangerous in-game events."""

from src.common import config, utils
import time
import os
import cv2
import pygame
import threading
import numpy as np
import keyboard as kb
from datetime import datetime
from ctypes import wintypes
import ctypes
import mss
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

# Lie detector (full + split top/bottom for partial UI visibility)
LIE_DETECTOR_TEMPLATE = cv2.imread('assets/lie_detector_template.png', 0)
LIE_DETECTOR_TEMPLATE_TOP = cv2.imread('assets/lie_detector_template_top.png', 0)
LIE_DETECTOR_TEMPLATE_BOTTOM = cv2.imread('assets/lie_detector_template_bottom.png', 0)
LIE_DETECTOR_TEMPLATES = (
    ('full', LIE_DETECTOR_TEMPLATE),
    ('top', LIE_DETECTOR_TEMPLATE_TOP),
    ('bottom', LIE_DETECTOR_TEMPLATE_BOTTOM),
)

LIE_DETECTOR_RECORDINGS_DIR = 'lie_detector_recordings'
LIE_DETECTOR_RECORD_DELAY_SEC = 9
LIE_DETECTOR_RECORD_DURATION_SEC = 20
LIE_DETECTOR_RECORD_FPS = 30

_user32 = ctypes.windll.user32

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
        self._lie_record_lock = threading.Lock()
        self._lie_record_active = False

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
                if frame is None:
                    time.sleep(0.05)
                    continue
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

                # Copy only the region we need for message/skull/elite checks so we can
                # release the full frame before cv2.matchTemplate (reduces peak memory;
                # avoids OpenCV "Insufficient memory" when many template matches run).
                interrupting_message_frame = frame[height // 4:3 * height // 4, :].copy()
                del frame  # Release full-frame reference before allocating in multi_match
                del gray

                # Convert to grayscale ONCE and reuse for all template matches to avoid
                # allocating a new grayscale array for each multi_match call.
                interrupting_message_gray = cv2.cvtColor(interrupting_message_frame, cv2.COLOR_BGR2GRAY)
                del interrupting_message_frame  # Release color frame; we only need grayscale now

                # Check for Pollo Message
                pollo = utils.multi_match_gray(interrupting_message_gray, POLLO_TEMPLATE, threshold=0.9)
                if len(pollo) > 0:
                    print("Pollo Message Detected")
                    print(pollo)
                    press("esc", 1, down_time=0.1)

                # Check for Fritto Message
                fritto = utils.multi_match_gray(interrupting_message_gray, FRITTO_TEMPLATE, threshold=0.9)
                if len(fritto) > 0:
                    print("Fritto Message Detected")
                    print(fritto)
                    press("esc", 1, down_time=0.1)

                # Check for Especia Message
                especia = utils.multi_match_gray(interrupting_message_gray, ESPECIA_TEMPLATE, threshold=0.9)
                if len(especia) > 0:
                    print("Especia Message Detected")
                    print(especia)
                    press("esc", 1, down_time=0.1)

                # Check for Twentoona Message
                twentoona = utils.multi_match_gray(interrupting_message_gray, TWENTOONA_TEMPLATE, threshold=0.9)
                if len(twentoona) > 0:
                    print("Twentoona Message Detected")
                    print(twentoona)
                    press("esc", 1, down_time=0.1)

                # Check for Lie Detector (full, then top/bottom split templates)
                lie_match = self._check_lie_detector(interrupting_message_gray)
                if lie_match:
                    self._schedule_lie_detector_recording(lie_match)
                    self._alert('siren')

                # Check for Skull Death
                skull_death_left_arrow = utils.multi_match_gray(interrupting_message_gray, SKULL_DEATH_LEFT_ARROW_TEMPLATE, threshold=0.9)
                skull_death_right_arrow = utils.multi_match_gray(interrupting_message_gray, SKULL_DEATH_RIGHT_ARROW_TEMPLATE, threshold=0.9)
                skull_death_hp_bar = utils.multi_match_gray(interrupting_message_gray, SKULL_DEATH_HP_BAR_TEMPLATE, threshold=0.9)
                skull_death_skull = utils.multi_match_gray(interrupting_message_gray, SKULL_DEATH_SKULL_TEMPLATE, threshold=0.9)
                if len(skull_death_left_arrow) > 0 or len(skull_death_right_arrow) > 0 or len(skull_death_hp_bar) > 0 or len(skull_death_skull) > 0:
                    print("Skull Death Detected")
                    print(f"Detection: left arrow {skull_death_left_arrow}, right arrow {skull_death_right_arrow}, hp bar {skull_death_hp_bar}, skull {skull_death_skull}")
                    for _ in range(20):
                        press("left", 1, down_time=0.1)
                        press("right", 1, down_time=0.1)
                    print("Skull Death Avoided")

                # Check for elite warning: wait 7s, use Origin, wait 5s, use Ascent (6th job; not in skill rotation)
                elite = utils.multi_match_gray(interrupting_message_gray, ELITE_TEMPLATE, threshold=0.9)
                if len(elite) > 0:
                    print("Elite Boss Detected - using Origin then Ascent.")
                    module = getattr(config.bot.command_book, 'module', None) if getattr(config.bot, 'command_book', None) else None
                    if module and hasattr(module, 'Key'):
                        Key = module.Key
                        if getattr(Key, 'ORIGIN', None) and getattr(Key, 'ASCENT', None):
                            time.sleep(9)
                            press(Key.ASCENT, 3)
                            time.sleep(5)
                            press(Key.ORIGIN, 3)
                            print("Origin and Ascent used.")
                        else:
                            print("Command book has no ORIGIN/ASCENT keys.")
                    else:
                        print("No command book loaded for Origin/Ascent.")

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

    def _check_lie_detector(self, gray, threshold=0.9):
        """Match lie detector UI: full template first, then top/bottom splits."""
        for label, template in LIE_DETECTOR_TEMPLATES:
            if template is None:
                continue
            matches = utils.multi_match_gray(gray, template, threshold=threshold)
            if matches:
                print(f"Lie Detector detected ({label})")
                print(matches)
                return label
        return None

    def _schedule_lie_detector_recording(self, match_label):
        """Start a background countdown + screen recording for lie detector training data."""
        with self._lie_record_lock:
            if self._lie_record_active:
                print('[lie detector] recording already scheduled, skipping duplicate')
                return
            self._lie_record_active = True
        thread = threading.Thread(
            target=self._lie_detector_recording_worker,
            args=(match_label,),
            daemon=True,
        )
        thread.start()

    def _lie_detector_recording_worker(self, match_label):
        try:
            print(
                f"[lie detector] recording scheduled in {LIE_DETECTOR_RECORD_DELAY_SEC}s "
                f"({LIE_DETECTOR_RECORD_DURATION_SEC}s clip, match={match_label})"
            )
            for remaining in range(LIE_DETECTOR_RECORD_DELAY_SEC, 0, -1):
                print(f"[lie detector] recording starts in {remaining}s...")
                time.sleep(1)
            path = self._record_maplestory_clip(match_label)
            if path:
                print(f"[lie detector] saved training clip: {path}")
            else:
                print('[lie detector] recording failed (MapleStory window not found?)')
        finally:
            with self._lie_record_lock:
                self._lie_record_active = False

    @staticmethod
    def _maplestory_capture_region():
        """Return mss monitor dict for the MapleStory client window."""
        handle = _user32.FindWindowW(None, 'MapleStory')
        if handle:
            rect = wintypes.RECT()
            _user32.GetWindowRect(handle, ctypes.pointer(rect))
            width = max(rect.right - rect.left, 1)
            height = max(rect.bottom - rect.top, 1)
            return {
                'left': max(0, rect.left),
                'top': max(0, rect.top),
                'width': width,
                'height': height,
            }
        capture = getattr(config, 'capture', None)
        if capture is not None and getattr(capture, 'window', None):
            return dict(capture.window)
        return None

    def _record_maplestory_clip(self, match_label):
        """Capture LIE_DETECTOR_RECORD_DURATION_SEC of MapleStory footage to disk."""
        region = self._maplestory_capture_region()
        if not region:
            return None

        os.makedirs(LIE_DETECTOR_RECORDINGS_DIR, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"lie_detector_{match_label}_{stamp}.mp4"
        out_path = os.path.join(LIE_DETECTOR_RECORDINGS_DIR, filename)

        fps = LIE_DETECTOR_RECORD_FPS
        frame_total = int(LIE_DETECTOR_RECORD_DURATION_SEC * fps)
        interval = 1.0 / fps

        with mss.mss() as sct:
            probe = sct.grab(region)
            width, height = probe.width, probe.height
            if width <= 0 or height <= 0:
                return None

            writer = cv2.VideoWriter(
                out_path,
                cv2.VideoWriter_fourcc(*'mp4v'),
                fps,
                (width, height),
            )
            if not writer.isOpened():
                print('[lie detector] VideoWriter failed to open, trying XVID AVI')
                out_path = out_path.replace('.mp4', '.avi')
                writer = cv2.VideoWriter(
                    out_path,
                    cv2.VideoWriter_fourcc(*'XVID'),
                    fps,
                    (width, height),
                )
                if not writer.isOpened():
                    return None

            print(f"[lie detector] recording {frame_total} frames at {fps} fps -> {out_path}")
            for _ in range(frame_total):
                loop_start = time.time()
                shot = sct.grab(region)
                frame = np.array(shot, dtype=np.uint8)
                if frame.shape[2] == 4:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                writer.write(frame)
                sleep_for = interval - (time.time() - loop_start)
                if sleep_for > 0:
                    time.sleep(sleep_for)
            writer.release()
        return out_path

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
