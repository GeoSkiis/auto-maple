"""A module for tracking useful in-game information."""

import time
import gc
import cv2
import threading
import ctypes
import mss
import mss.windows
import numpy as np
from src.common import config, utils
from ctypes import wintypes
user32 = ctypes.windll.user32
user32.SetProcessDPIAware()


# The distance between the top of the minimap and the top of the screen
MINIMAP_TOP_BORDER = 5

# The thickness of the other three borders of the minimap
MINIMAP_BOTTOM_BORDER = 9

# Offset in pixels to adjust for windowed mode
WINDOWED_OFFSET_TOP = 36
WINDOWED_OFFSET_LEFT = 10

# The top-left and bottom-right corners of the minimap
MM_TL_TEMPLATE = cv2.imread('assets/minimap_tl_template.png', 0)
MM_BR_TEMPLATE = cv2.imread('assets/minimap_br_template.png', 0)

MMT_HEIGHT = max(MM_TL_TEMPLATE.shape[0], MM_BR_TEMPLATE.shape[0])
MMT_WIDTH = max(MM_TL_TEMPLATE.shape[1], MM_BR_TEMPLATE.shape[1])

# The player's symbol on the minimap
PLAYER_TEMPLATE = cv2.imread('assets/player_template.png', 0)
PT_HEIGHT, PT_WIDTH = PLAYER_TEMPLATE.shape


class Capture:
    """
    A class that tracks player position and various in-game events. It constantly updates
    the config module with information regarding these events. It also annotates and
    displays the minimap in a pop-up window.
    """

    def __init__(self):
        """Initializes this Capture object's main thread."""

        config.capture = self

        self.frame = None
        self.minimap = {}
        self.minimap_ratio = 1
        self.minimap_sample = None
        self.sct = None
        self.window = {
            'left': 0,
            'top': 0,
            'width': 1366,
            'height': 768
        }

        self.ready = False
        self.calibrated = False
        self.thread = threading.Thread(target=self._main)
        self.thread.daemon = True
        # Reuse a single buffer for screenshots to avoid allocating 4+ MiB every ~1 ms (ArrayMemoryError).
        self._frame_buffer = None
        self._gc_counter = 0  # Counter for periodic garbage collection

    def start(self):
        """Starts this Capture's thread."""

        print('\n[~] Started video capture')
        self.thread.start()

    def _main(self):
        """Constantly monitors the player's position and in-game events."""

        mss.windows.CAPTUREBLT = 0
        while True:
            # Calibrate screen capture
            handle = user32.FindWindowW(None, 'MapleStory')
            rect = wintypes.RECT()
            user32.GetWindowRect(handle, ctypes.pointer(rect))
            rect = (rect.left, rect.top, rect.right, rect.bottom)
            rect = tuple(max(0, x) for x in rect)

            self.window['left'] = rect[0]
            self.window['top'] = rect[1]
            self.window['width'] = max(rect[2] - rect[0], MMT_WIDTH)
            self.window['height'] = max(rect[3] - rect[1], MMT_HEIGHT)

            # Calibrate by finding the top-left and bottom-right corners of the minimap
            with mss.mss() as self.sct:
                self.frame = self.screenshot()
            if self.frame is None:
                continue
            # Search only in the top-left 30% of the frame (minimap is always there)
            h_frame, w_frame = self.frame.shape[:2]
            temp_frame = self.frame[0 : int(h_frame * 0.3), 0 : int(w_frame * 0.3)]
            tl, _ = utils.single_match(temp_frame, MM_TL_TEMPLATE)
            _, br = utils.single_match(temp_frame, MM_BR_TEMPLATE)
            mm_tl = (
                tl[0] + MINIMAP_BOTTOM_BORDER,
                tl[1] + MINIMAP_TOP_BORDER
            )
            mm_br = (
                max(mm_tl[0] + PT_WIDTH, br[0] - MINIMAP_BOTTOM_BORDER),
                max(mm_tl[1] + PT_HEIGHT, br[1] - MINIMAP_BOTTOM_BORDER)
            )
            self.minimap_ratio = (mm_br[0] - mm_tl[0]) / (mm_br[1] - mm_tl[1])
            self.minimap_sample = self.frame[mm_tl[1]:mm_br[1], mm_tl[0]:mm_br[0]]
            self.calibrated = True

            with mss.mss() as self.sct:
                while True:
                    if not self.calibrated:
                        break

                    # Take screenshot
                    self.frame = self.screenshot()
                    if self.frame is None:
                        continue

                    # Crop the frame to only show the minimap (copy so GUI thread
                    # does not hold a reference to the full frame and cause memory pressure).
                    minimap = self.frame[mm_tl[1]:mm_br[1], mm_tl[0]:mm_br[0]].copy()

                    # Determine the player's position
                    player = utils.multi_match(minimap, PLAYER_TEMPLATE, threshold=0.8)
                    if player:
                        config.player_pos = utils.convert_to_relative(player[0], minimap)

                    # Package display information to be polled by GUI
                    self.minimap = {
                        'minimap': minimap,
                        'rune_active': config.bot.rune_active,
                        'rune_pos': config.bot.rune_pos,
                        'path': config.path,
                        'player_pos': config.player_pos
                    }

                    if not self.ready:
                        self.ready = True
                    
                    # Periodic garbage collection every ~100 frames (~1.6s at 60fps) to help
                    # free memory when system is under pressure (reduces "unable to alloc" errors).
                    self._gc_counter += 1
                    if self._gc_counter >= 100:
                        gc.collect()
                        self._gc_counter = 0
                    
                    # ~60 fps to reduce mss allocation pressure (grab allocates internally).
                    time.sleep(0.016)

    def get_minimap_from_frame(self, frame):
        """
        Find the minimap by searching the entire frame for TL/BR corners (no ROI).
        Use this when the pre-cropped minimap might be wrong (e.g. for auto routine resolution).
        Converts BGRA (mss) to BGR so matching matches test_minimap_finder / cv2.imread.
        :param frame: Full game window image (e.g. self.frame), BGR or BGRA
        :return: Minimap crop as numpy array, or None if not found
        """
        if frame is None or frame.size == 0:
            return None
        # Normalise to BGR so matching is same as test script (saved frame loaded as BGR)
        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        h, w = frame.shape[:2]
        if (MM_TL_TEMPLATE.shape[0] > h or MM_TL_TEMPLATE.shape[1] > w or
                MM_BR_TEMPLATE.shape[0] > h or MM_BR_TEMPLATE.shape[1] > w):
            return None
        tl, _ = utils.single_match(frame, MM_TL_TEMPLATE)
        _, br = utils.single_match(frame, MM_BR_TEMPLATE)
        mm_tl = (
            tl[0] + MINIMAP_BOTTOM_BORDER,
            tl[1] + MINIMAP_TOP_BORDER
        )
        mm_br = (
            max(mm_tl[0] + PT_WIDTH, br[0] - MINIMAP_BOTTOM_BORDER),
            max(mm_tl[1] + PT_HEIGHT, br[1] - MINIMAP_BOTTOM_BORDER)
        )
        # Bounds check so we never return invalid crop
        if mm_br[0] <= mm_tl[0] or mm_br[1] <= mm_tl[1]:
            return None
        if mm_tl[0] < 0 or mm_tl[1] < 0 or mm_br[0] > w or mm_br[1] > h:
            return None
        return frame[mm_tl[1]:mm_br[1], mm_tl[0]:mm_br[0]]

    def screenshot(self, delay=1):
        try:
            shot = self.sct.grab(self.window)
            h, w = shot.height, shot.width
            need_shape = (h, w, 4)
            if self._frame_buffer is None or self._frame_buffer.shape != need_shape:
                self._frame_buffer = np.empty(need_shape, dtype=np.uint8)
            np.copyto(
                self._frame_buffer,
                np.frombuffer(shot.raw, dtype=np.uint8).reshape(need_shape),
            )
            return self._frame_buffer
        except MemoryError:
            # mss allocates a bytearray inside grab(); when system is low on memory
            # that can fail. Force GC and pause, then retry so the loop can continue.
            print('\n[!] Capture: memory error in screenshot, forcing GC then retrying...')
            gc.collect()
            time.sleep(2)
            return None
        except mss.exception.ScreenShotError:
            print(f'\n[!] Error while taking screenshot, retrying in {delay} second'
                  + ('s' if delay != 1 else ''))
            time.sleep(delay)
