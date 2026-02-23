"""A collection of functions and classes used across multiple modules."""

import math
import queue
import time
import cv2
import threading
import numpy as np
from src.common import config, settings
from src.common.vkeys import press
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


def enter_cash_shop(repeat: int = 10):
    """
    Send F5 + Enter repeatedly to open the cash shop.
    :param repeat: Number of F5+Enter cycles (default 10).
    """
    for _ in range(repeat):
        press("f5", 1, down_time=0.1)
        press("enter", 1, down_time=0.1)
        time.sleep(1)


def exit_cash_shop():
    """Send Esc/Enter sequence to leave the cash shop and wait for loading."""
    time.sleep(5)
    press("esc", 1, down_time=0.1)
    time.sleep(1)
    press("esc", 1, down_time=0.1)
    time.sleep(1)
    press("enter", 1, down_time=0.1)
    time.sleep(5)


def async_callback(context, function, *args, **kwargs):
    """Returns a callback function that can be run asynchronously by the GUI."""

    def f():
        task = Async(function, *args, **kwargs)
        task.start()
        context.after(100, task.process_queue(context))
    return f
