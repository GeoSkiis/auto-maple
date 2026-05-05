"""A collection of functions and classes used across multiple modules."""

import math
import queue
import time
import cv2
import threading
import numpy as np
from src.common import config, settings
from src.common.vkeys import click, press
from src.common.decorators import run_if_enabled, run_if_disabled
from random import random


def distance(a, b):
    """
    Applies the distance formula to two points.
    :param a:   The first point.
    :param b:   The second point.
    :return:    The distance between the two points.
    """

    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


CASH_SHOP_ENTRY_TEMPLATE = cv2.imread('assets/cash_shop_entry.png', 0)
CASH_SHOP_EXIT_TEMPLATE = cv2.imread('assets/cash_shop_exit.png', 0)


def _cash_shop_roi_enter(frame):
    """Bottom 20% height, left 50% width (matches in-game HUD strip)."""
    h, w = frame.shape[:2]
    x0, x1 = 0, w // 2
    y0, y1 = int(h * 0.8), h
    return frame[y0:y1, x0:x1], (x0, y0)


def _cash_shop_roi_exit(frame):
    """Top-right corner: top 20% of height × rightmost 20% width (minimap UI)."""
    h, w = frame.shape[:2]
    x0, x1 = int(w * 0.8), w
    y0, y1 = 0, int(h * 0.2)
    return frame[y0:y1, x0:x1], (x0, y0)


def _click_roi_match_screen(matches, roi_origin):
    """Matches are ROI-local centers from multi_match_gray; click in screen coordinates."""
    if not matches or not getattr(config, 'capture', None):
        return
    cx_roi, cy_roi = matches[0]
    ox, oy = roi_origin
    fx = cx_roi + ox
    fy = cy_roi + oy
    win = config.capture.window
    click((int(round(fx + win['left'])), int(round(fy + win['top']))))


def separate_args(arguments):
    """
    Separates a given array ARGUMENTS into an array of normal arguments and a
    dictionary of keyword arguments.
    :param arguments:    The array of arguments to separate.
    :return:             An array of normal arguments and a dictionary of keyword arguments.
    """

    args = []
    kwargs = {}
    for a in arguments:
        a = a.strip()
        index = a.find('=')
        if index > -1:
            key = a[:index].strip()
            value = a[index+1:].strip()
            kwargs[key] = value
        else:
            args.append(a)
    return args, kwargs


def _frame_to_gray(frame):
    """Convert frame to grayscale; handle BGR (3ch) or BGRA (4ch, e.g. from mss)."""
    if frame.ndim == 2:
        return frame
    if frame.ndim == 3 and frame.shape[2] == 4:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def single_match(frame, template):
    """
    Finds the best match within FRAME.
    :param frame:       The image in which to search for TEMPLATE.
    :param template:    The template to match with.
    :return:            The top-left and bottom-right positions of the best match.
    """
    gray = _frame_to_gray(frame)
    result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF)
    _, _, _, top_left = cv2.minMaxLoc(result)
    w, h = template.shape[::-1]
    bottom_right = (top_left[0] + w, top_left[1] + h)
    return top_left, bottom_right


def multi_match(frame, template, threshold=0.95):
    """
    Finds all matches in FRAME that are similar to TEMPLATE by at least THRESHOLD.
    :param frame:       The image in which to search.
    :param template:    The template to match with.
    :param threshold:   The minimum percentage of TEMPLATE that each result must match.
    :return:            An array of matches that exceed THRESHOLD.
    """

    if template.shape[0] > frame.shape[0] or template.shape[1] > frame.shape[1]:
        return []
    gray = _frame_to_gray(frame)
    return multi_match_gray(gray, template, threshold)


def multi_match_gray(gray, template, threshold=0.95):
    """
    Finds all matches in GRAY (grayscale image) that are similar to TEMPLATE by at least THRESHOLD.
    Use this when you already have a grayscale image to avoid redundant conversions.
    :param gray:        The grayscale image in which to search (2D array).
    :param template:    The template to match with (must be grayscale).
    :param threshold:   The minimum percentage of TEMPLATE that each result must match.
    :return:            An array of matches that exceed THRESHOLD.
    """
    if template.shape[0] > gray.shape[0] or template.shape[1] > gray.shape[1]:
        return []
    result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= threshold)
    locations = list(zip(*locations[::-1]))
    results = []
    for p in locations:
        x = int(round(p[0] + template.shape[1] / 2))
        y = int(round(p[1] + template.shape[0] / 2))
        results.append((x, y))
    return results


def multi_match_multiscale(
    frame,
    template,
    threshold=0.95,
    scales=(0.7, 0.85, 1.0, 1.15, 1.3),
):
    """
    Same as multi_match but tries the template at several scales so the same
    icon at a different resolution/size still matches (scale-invariant).
    Picks the scale with the best correlation, then returns all matches at that
    scale above THRESHOLD.
    :param frame:     BGR or grayscale image to search in.
    :param template:  Grayscale template (e.g. from cv2.imread(..., 0)).
    :param threshold: Minimum correlation to count as a match.
    :param scales:    Tuple of scale factors to try (1.0 = original size).
    :return:          List of (x, y) center positions, same format as multi_match.
    """
    if frame.ndim == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        gray = frame
    th, tw = template.shape[:2]
    best_scale = 1.0
    best_result = None
    best_max_val = -1.0

    for s in scales:
        w = max(1, int(round(tw * s)))
        h = max(1, int(round(th * s)))
        if h > gray.shape[0] or w > gray.shape[1]:
            continue
        resized = cv2.resize(
            template, (w, h),
            interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR,
        )
        result = cv2.matchTemplate(gray, resized, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, _, _ = cv2.minMaxLoc(result)
        if max_val > best_max_val:
            best_max_val = max_val
            best_scale = s
            best_result = result
            best_w, best_h = w, h

    if best_result is None:
        return []
    locations = np.where(best_result >= threshold)
    locations = list(zip(*locations[::-1]))
    results = []
    for p in locations:
        x = int(round(p[0] + best_w / 2))
        y = int(round(p[1] + best_h / 2))
        results.append((x, y))
    return results


def convert_to_relative(point, frame):
    """
    Converts POINT (pixels) into relative coordinates [0, 1] based on FRAME.
    x and y use the same 0-1 scale (frame width and height).
    """
    x = point[0] / frame.shape[1]
    y = point[1] / frame.shape[0]
    return x, y


def convert_to_absolute(point, frame):
    """
    Converts POINT (0-1 relative) into pixel coordinates based on FRAME.
    x and y use the same 0-1 scale (frame width and height).
    """
    x = int(round(point[0] * frame.shape[1]))
    y = int(round(point[1] * frame.shape[0]))
    return x, y


def filter_color(img, ranges):
    """
    Returns a filtered copy of IMG that only contains pixels within the given RANGES.
    on the HSV scale.
    :param img:     The image to filter.
    :param ranges:  A list of tuples, each of which is a pair upper and lower HSV bounds.
    :return:        A filtered copy of IMG.
    """

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, ranges[0][0], ranges[0][1])
    for i in range(1, len(ranges)):
        mask = cv2.bitwise_or(mask, cv2.inRange(hsv, ranges[i][0], ranges[i][1]))

    # Mask the image
    color_mask = mask > 0
    result = np.zeros_like(img, np.uint8)
    result[color_mask] = img[color_mask]
    return result


def draw_location(minimap, pos, color):
    """
    Draws a visual representation of POINT onto MINIMAP. The radius of the circle represents
    the allowed error when moving towards POINT.
    :param minimap:     The image on which to draw.
    :param pos:         The location (as a tuple) to depict.
    :param color:       The color of the circle.
    :return:            None
    """

    center = convert_to_absolute(pos, minimap)
    cv2.circle(minimap,
               center,
               round(minimap.shape[1] * settings.move_tolerance),
               color,
               1)


def print_separator():
    """Prints a 3 blank lines for visual clarity."""

    print('\n\n')


def print_state():
    """Prints whether Auto Maple is currently enabled or disabled."""

    print_separator()
    print('#' * 18)
    print(f"#    {'ENABLED ' if config.enabled else 'DISABLED'}    #")
    print('#' * 18)


def closest_point(points, target):
    """
    Returns the point in POINTS that is closest to TARGET.
    :param points:      A list of points to check.
    :param target:      The point to check against.
    :return:            The point closest to TARGET, otherwise None if POINTS is empty.
    """

    if points:
        points.sort(key=lambda p: distance(p, target))
        return points[0]


def bernoulli(p):
    """
    Returns the value of a Bernoulli random variable with probability P.
    :param p:   The random variable's probability of being True.
    :return:    True or False.
    """

    return random() < p


def rand_float(start, end):
    """Returns a random float value in the interval [START, END)."""

    assert start < end, 'START must be less than END'
    return (end - start) * random() + start


##########################
#       Threading        #
##########################
class Async(threading.Thread):
    def __init__(self, function, *args, **kwargs):
        super().__init__()
        self.queue = queue.Queue()
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def run(self):
        self.function(*self.args, **self.kwargs)
        self.queue.put('x')

    def process_queue(self, root):
        def f():
            try:
                self.queue.get_nowait()
            except queue.Empty:
                root.after(100, self.process_queue(root))
        return f


def enter_cash_shop(interval_s=1.0, threshold=0.85, max_wait_s=120.0):
    """
    Open the cash shop by matching ``assets/cash_shop_entry.png`` in the bottom-left HUD
    ROI and clicking until **confirmed inside** via ``assets/cash_shop_exit.png`` in the
    top-right ROI (same template/ROI as ``exit_cash_shop``).

    We do **not** treat "entry HUD stopped matching" as success: the mouse can block the
    icon after a click while the shop is still closed.

    :param interval_s:  Seconds between click attempts while the entry icon matches.
    :param threshold:   Normalized TM_CCOEFF_NORMED minimum for ``multi_match_gray``.
    :param max_wait_s:  Stop the loop after this many seconds regardless of outcome.
    """
    if CASH_SHOP_ENTRY_TEMPLATE is None:
        print('[enter_cash_shop] missing assets/cash_shop_entry.png')
        return
    if CASH_SHOP_EXIT_TEMPLATE is None:
        print('[enter_cash_shop] missing assets/cash_shop_exit.png (needed to confirm inside shop)')
        return

    print(
        f'[enter_cash_shop] start threshold={threshold} interval_s={interval_s} max_wait_s={max_wait_s}'
    )
    tmpl_entry = CASH_SHOP_ENTRY_TEMPLATE
    tmpl_exit = CASH_SHOP_EXIT_TEMPLATE
    deadline = time.time() + max_wait_s
    saw_entry_match = False
    entry_clicks = 0
    no_frame_streak = 0
    scan_loops = 0
    while time.time() < deadline:
        scan_loops += 1
        cap = getattr(config, 'capture', None)
        frame = cap.frame if cap else None
        if frame is None:
            no_frame_streak += 1
            if no_frame_streak == 1 or no_frame_streak % 15 == 0:
                why = 'no capture object' if cap is None else 'capture.frame is None'
                print(f'[enter_cash_shop] waiting for frame ({why}, streak={no_frame_streak})')
            time.sleep(interval_s)
            continue
        no_frame_streak = 0

        roi_exit, _ = _cash_shop_roi_exit(frame)
        gray_exit = _frame_to_gray(roi_exit)
        exit_matches = multi_match_gray(gray_exit, tmpl_exit, threshold=threshold)
        if exit_matches:
            print(
                f'[enter_cash_shop] exit UI visible in top-right — confirmed inside shop '
                f'({scan_loops} loops, {entry_clicks} entry clicks)'
            )
            break

        roi, origin = _cash_shop_roi_enter(frame)
        gray = _frame_to_gray(roi)
        matches = multi_match_gray(gray, tmpl_entry, threshold=threshold)
        if matches:
            if not saw_entry_match:
                print(
                    f'[enter_cash_shop] entry HUD matched ({len(matches)} hit(s)); ROI origin={origin}, '
                    f'roi_gray shape={gray.shape}'
                )
            saw_entry_match = True
            entry_clicks += 1
            print(f'[enter_cash_shop] clicking entry icon (attempt {entry_clicks})')
            _click_roi_match_screen(matches, origin)
            time.sleep(interval_s)
        else:
            if scan_loops == 1 or scan_loops % 20 == 0:
                print(
                    f'[enter_cash_shop] no entry match yet / waiting for exit UI (loop {scan_loops}, '
                    f'{max(0.0, deadline - time.time()):.0f}s left)'
                )
            time.sleep(interval_s)
    else:
        if saw_entry_match:
            print(
                f'[enter_cash_shop] timed out after max_wait_s={max_wait_s}; '
                f'clicked entry {entry_clicks}x but exit UI never appeared (still not in shop?)'
            )
        else:
            print(
                f'[enter_cash_shop] timed out after max_wait_s={max_wait_s}; '
                'never matched entry HUD (check template / ROI / resolution)'
            )

    print('[enter_cash_shop] sleeping 10s before return')
    time.sleep(10)


def exit_cash_shop(interval_s=1.0, threshold=0.85, max_wait_s=120.0):
    """
    Leave the cash shop by matching grayscale ``assets/cash_shop_exit.png`` in the live
    map frame ROI (top 20% height, rightmost 20% width), clicking the center every
    INTERVAL_S while visible until the sprite is gone.

    :param interval_s:  Seconds between attempts while exit UI still matches.
    :param threshold:   Normalized correlation threshold for matching.
    :param max_wait_s:  Stop after this many seconds regardless.
    """
    if CASH_SHOP_EXIT_TEMPLATE is None:
        print('[exit_cash_shop] missing assets/cash_shop_exit.png')
        return

    print(
        f'[exit_cash_shop] start threshold={threshold} interval_s={interval_s} max_wait_s={max_wait_s}'
    )
    tmpl = CASH_SHOP_EXIT_TEMPLATE
    deadline = time.time() + max_wait_s
    saw_match = False
    exit_clicks = 0
    no_frame_streak = 0
    scan_loops = 0
    while time.time() < deadline:
        scan_loops += 1
        cap = getattr(config, 'capture', None)
        frame = cap.frame if cap else None
        if frame is None:
            no_frame_streak += 1
            if no_frame_streak == 1 or no_frame_streak % 15 == 0:
                why = 'no capture object' if cap is None else 'capture.frame is None'
                print(f'[exit_cash_shop] waiting for frame ({why}, streak={no_frame_streak})')
            time.sleep(interval_s)
            continue
        no_frame_streak = 0

        roi, origin = _cash_shop_roi_exit(frame)
        gray = _frame_to_gray(roi)
        matches = multi_match_gray(gray, tmpl, threshold=threshold)
        if matches:
            if not saw_match:
                print(
                    f'[exit_cash_shop] exit UI matched ({len(matches)} hit(s)); ROI origin={origin}, '
                    f'roi_gray shape={gray.shape}'
                )
            saw_match = True
            exit_clicks += 1
            print(f'[exit_cash_shop] clicking exit (attempt {exit_clicks})')
            _click_roi_match_screen(matches, origin)
            time.sleep(interval_s)
        elif saw_match:
            print(
                f'[exit_cash_shop] exit UI gone after {exit_clicks} click(s); assuming left shop '
                f'({scan_loops} scan loops)'
            )
            break
        else:
            if scan_loops == 1 or scan_loops % 20 == 0:
                print(
                    f'[exit_cash_shop] scanning for exit UI (loop {scan_loops}, '
                    f'{deadline - time.time():.0f}s left on deadline)'
                )
            time.sleep(interval_s)
    else:
        if saw_match:
            print(
                f'[exit_cash_shop] timed out after max_wait_s={max_wait_s}; '
                f'exit control may still be visible ({exit_clicks} clicks so far)'
            )
        else:
            print(
                f'[exit_cash_shop] timed out after max_wait_s={max_wait_s}; '
                'never matched exit template (check template / ROI / resolution)'
            )

    print('[exit_cash_shop] sleeping 5s before return')
    time.sleep(5)


def async_callback(context, function, *args, **kwargs):
    """Returns a callback function that can be run asynchronously by the GUI."""

    def f():
        task = Async(function, *args, **kwargs)
        task.start()
        context.after(100, task.process_queue(context))
    return f
