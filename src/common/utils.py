"""多个模块共用的函数和类的集合。"""

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
    应用距离公式计算两点之间的距离。
    :param a:   第一个点。
    :param b:   第二个点。
    :return:    两点之间的距离。
    """

    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def separate_args(arguments):
    """
    将给定的数组 ARGUMENTS 分离为普通参数数组和关键字参数字典。
    :param arguments:    要分离的参数数组。
    :return:             普通参数数组和关键字参数字典。
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
    """将帧转换为灰度；处理 BGR（3通道）或 BGRA（4通道，例如来自 mss）。"""
    if frame.ndim == 2:
        return frame
    if frame.ndim == 3 and frame.shape[2] == 4:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def single_match(frame, template):
    """
    在 FRAME 中找到最佳匹配。
    :param frame:       要在其中搜索 TEMPLATE 的图像。
    :param template:    要匹配的模板。
    :return:            最佳匹配的左上角和右下角位置。
    """
    gray = _frame_to_gray(frame)
    result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF)
    _, _, _, top_left = cv2.minMaxLoc(result)
    w, h = template.shape[::-1]
    bottom_right = (top_left[0] + w, top_left[1] + h)
    return top_left, bottom_right

def multi_match_color(frame, template, threshold=0.95):
    """
    (彩色匹配)(彩色匹配)(彩色匹配)(彩色匹配)(彩色匹配)(彩色匹配)(彩色匹配)

    在 FRAME 中找到所有与彩色 TEMPLATE 相似度至少为 THRESHOLD 的匹配项。
    :param frame:       要搜索的图像（彩色）。
    :param template:    彩色模板（BGR）。
    :param threshold:   最小相关性阈值。
    :return:            超过 THRESHOLD 的匹配项数组。
    """

    if template.shape[0] > frame.shape[0] or template.shape[1] > frame.shape[1]:
        return []

    if frame.ndim == 2:
        # 传入单通道时退回到灰度匹配
        gray = frame
        return multi_match_gray(gray, template if template.ndim == 2 else _frame_to_gray(template), threshold)

    # 仅在 color 模式下使用三通道模板
    if frame.ndim == 3 and template.ndim == 3:
        # 确保frame和template的类型相同
        if frame.dtype != template.dtype:
            template = template.astype(frame.dtype)
        # 确保frame和template的通道数相同
        if frame.shape[2] != template.shape[2]:
            if frame.shape[2] == 4:  # BGRA转BGR
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            elif template.shape[2] == 4:  # BGRA转BGR
                template = cv2.cvtColor(template, cv2.COLOR_BGRA2BGR)
        result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    else:
        # 兼容单通道模板的情况
        gray = _frame_to_gray(frame)
        t_gray = template if template.ndim == 2 else _frame_to_gray(template)
        return multi_match_gray(gray, t_gray, threshold)

    locations = np.where(result >= threshold)
    locations = list(zip(*locations[::-1]))
    results = []
    h, w = template.shape[:2]
    for p in locations:
        x = int(round(p[0] + w / 2))
        y = int(round(p[1] + h / 2))
        results.append((x, y))
    return results


def multi_match_gray(gray, template, threshold=0.95):
    """
    在 GRAY（灰度图像）中找到所有与 TEMPLATE 相似度至少为 THRESHOLD 的匹配项。
    当您已经有灰度图像时使用此方法，以避免冗余转换。
    :param gray:        要搜索的灰度图像（2D 数组）。
    :param template:    要匹配的模板（必须是灰度）。
    :param threshold:   每个结果必须匹配 TEMPLATE 的最小百分比。
    :return:            超过 THRESHOLD 的匹配项数组。
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
    与 multi_match 相同，但会尝试多个尺度的模板，以便不同分辨率/大小的相同图标仍然可以匹配（尺度不变）。
    选择相关性最好的尺度，然后返回该尺度上所有超过 THRESHOLD 的匹配项。
    :param frame:     要搜索的 BGR 或灰度图像。
    :param template:  灰度模板（例如从 cv2.imread(..., 0) 获得）。
    :param threshold: 视为匹配的最小相关性。
    :param scales:    要尝试的尺度因子元组（1.0 = 原始大小）。
    :return:          (x, y) 中心位置列表，格式与 multi_match 相同。
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
    将 POINT（像素）转换为基于 FRAME 的相对坐标 [0, 1]。
    x 和 y 使用相同的 0-1 尺度（帧宽度和高度）。
    """
    x = point[0] / frame.shape[1]
    y = point[1] / frame.shape[0]
    return x, y


def convert_to_absolute(point, frame):
    """
    将 POINT（0-1 相对）转换为基于 FRAME 的像素坐标。
    x 和 y 使用相同的 0-1 尺度（帧宽度和高度）。
    """
    x = int(round(point[0] * frame.shape[1]))
    y = int(round(point[1] * frame.shape[0]))
    return x, y


def filter_color(img, ranges):
    """
    返回 IMG 的过滤副本，仅包含 HSV 尺度上给定 RANGES 内的像素。
    :param img:     要过滤的图像。
    :param ranges:  元组列表，每个元组是一对 HSV 上下边界。
    :return:        IMG 的过滤副本。
    """

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, ranges[0][0], ranges[0][1])
    for i in range(1, len(ranges)):
        mask = cv2.bitwise_or(mask, cv2.inRange(hsv, ranges[i][0], ranges[i][1]))

    # 遮罩图像
    color_mask = mask > 0
    result = np.zeros_like(img, np.uint8)
    result[color_mask] = img[color_mask]
    return result


def draw_location(minimap, pos, color):
    """
    在 MINIMAP 上绘制 POINT 的视觉表示。圆的半径表示向 POINT 移动时的允许误差。
    :param minimap:     要在其上绘制的图像。
    :param pos:         要描绘的位置（作为元组）。
    :param color:       圆的颜色。
    :return:            None
    """

    center = convert_to_absolute(pos, minimap)
    cv2.circle(minimap,
               center,
               round(minimap.shape[1] * settings.move_tolerance),
               color,
               1)


def print_separator():
    """打印 3 个空行以提高视觉清晰度。"""

    print('\n\n')


def print_state():
    """打印 Auto Maple 当前是启用还是禁用。"""

    print_separator()
    print('#' * 18)
    print(f"#    {'已启用 ' if config.enabled else '已禁用'}    #")
    print('#' * 18)


def closest_point(points, target):
    """
    返回 POINTS 中最接近 TARGET 的点。
    :param points:      要检查的点列表。
    :param target:      要检查的目标点。
    :return:            最接近 TARGET 的点，如果 POINTS 为空则返回 None。
    """

    if points:
        points.sort(key=lambda p: distance(p, target))
        return points[0]


def bernoulli(p):
    """
    返回概率为 P 的伯努利随机变量的值。
    :param p:   随机变量为 True 的概率。
    :return:    True 或 False。
    """

    return random() < p


def rand_float(start, end):
    """返回区间 [START, END) 中的随机浮点值。"""

    if start >= end:
        return start
    return (end - start) * random() + start


##########################
#       线程处理        #
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


def enter_cash_shop():
    """
    重复发送 F5 直到检测到商城图像。
    """
    import cv2
    import src.common.config as config
    
    # 加载商城图片模板
    shop_template = cv2.imread('assets/shop.png', 0)
    if shop_template is None:
        print("错误: 无法加载商城图片模板 assets/shop.png")
        return
    
    print("开始尝试进入商城，持续按 F5 直到检测到商城界面...")
    
    # 持续按 F5 直到检测到商城图片
    while True:
        # 按 F5
        press("f5", 3, down_time=0.2, up_time=0.2)
        # 等待一段时间让界面响应
        time.sleep(0.5)
        
        # 检查是否捕获到帧
        if hasattr(config, 'capture') and hasattr(config.capture, 'frame') and config.capture.frame is not None:
            # 尝试匹配商城图片
            matches = multi_match_color(config.capture.frame, shop_template, threshold=0.8)
            if matches:
                print("检测到商城界面，停止按 F5")
                break
        # 避免无限循环导致系统资源占用过高
        time.sleep(0.5)


def exit_cash_shop():
    """发送 Esc/Enter 序列离开商城并等待加载。"""
    print("开始退出商城...")
    time.sleep(1)
    print("已发送 Esc")
    press("esc", 1, down_time=0.2)
    time.sleep(1)
    print("已发送 Esc")
    press("esc", 1, down_time=0.2)
    time.sleep(1)
    print("已发送 Enter")
    press("enter", 1, down_time=0.2)
    time.sleep(5)
    print("退出商城完成")


def async_callback(context, function, *args, **kwargs):
    """返回可以由 GUI 异步运行的回调函数。"""

    def f():
        task = Async(function, *args, **kwargs)
        task.start()
        context.after(100, task.process_queue(context))
    return f