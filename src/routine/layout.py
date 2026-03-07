"""用于保存地图布局和确定最短路径的模块。"""

import os
import cv2
import math
import pickle
from src.common import config, settings, utils
from os.path import join, isfile, splitext, basename
from heapq import heappush, heappop


class Node:
    """表示四叉树上的一个顶点。"""

    def __init__(self, x, y):
        """
        在 (X, Y) 创建一个新的 Node。同时初始化 Node 的子节点。
        :param x:   节点的 x 位置。
        :param y:   节点的 y 位置。
        """

        self.x = x
        self.y = y
        self.up_left = None
        self.up_right = None
        self.down_left = None
        self.down_right = None

    def children(self):
        """
        如果存在，返回此 Node 的子节点数组。
        :return:    此 Node 的子节点。
        """

        result = []
        if self.up_left:
            result.append(self.up_left)
        if self.up_right:
            result.append(self.up_right)
        if self.down_left:
            result.append(self.down_left)
        if self.down_right:
            result.append(self.down_right)
        return result

    def __str__(self):
        """
        返回此 Node 作为坐标点的字符串表示。
        :return:    形式为 '(x, y)' 的字符串。
        """

        return str(tuple(self))

    def __iter__(self):
        """
        支持将 Node 转换为元组。
        :return:    此 Node 的 x 和 y 位置。
        """

        yield self.x
        yield self.y


class Layout:
    """使用四叉树表示地图布局中可能的玩家位置。"""

    TOLERANCE = settings.move_tolerance / 2
    # TOLERANCE = 0.017

    def __init__(self, name):
        """
        创建一个具有给定名称的新 Layout 对象。
        :param name:     此布局的名称。
        """

        self.name = name
        self.root = None

    @utils.run_if_enabled
    def add(self, x, y):
        """
        如果位置 (X, Y) 不存在节点，则向四叉树添加一个 Node。
        :param x:   新点的 x 位置。
        :param y:   新点的 y 位置。
        :return:    如果点添加成功则为 True，否则为 False。
        """

        def add_helper(node):
            if not node:
                return Node(x, y)
            if y >= node.y and x < node.x:
                node.up_left = add_helper(node.up_left)
            elif y >= node.y and x >= node.x:
                node.up_right = add_helper(node.up_right)
            elif y < node.y and x < node.x:
                node.down_left = add_helper(node.down_left)
            else:
                node.down_right = add_helper(node.down_right)
            return node

        def check_collision(point):
            return utils.distance(tuple(point), (x, y)) >= Layout.TOLERANCE

        checks = map(check_collision, self.search(x - Layout.TOLERANCE,
                                                  x + Layout.TOLERANCE,
                                                  y - Layout.TOLERANCE,
                                                  y + Layout.TOLERANCE))
        if all(checks):
            self.root = add_helper(self.root)
            # 打印记录的点坐标
            print(f"记录路径点({x:.4f}, {y:.4f})")
            return True
        return False

    def search(self, x_min, x_max, y_min, y_max):
        """
        返回水平边界为 X_MIN 和 X_MAX，垂直边界为 Y_MIN 和 Y_MAX 的所有 Node。
        :param x_min:   范围的左边界。
        :param x_max:   范围的右边界。
        :param y_min:   范围的下边界。
        :param y_max:   范围的上边界。
        :return:        范围内的所有 Node 列表。
        """

        nodes = []

        def search_helper(node):
            if node:
                if x_min <= node.x <= x_max and y_min <= node.y <= y_max:
                    nodes.append(node)
                if x_min < node.x:
                    if y_min < node.y:
                        search_helper(node.down_left)
                    if y_max >= node.y:
                        search_helper(node.up_left)
                if x_max >= node.x:
                    if y_min < node.y:
                        search_helper(node.down_right)
                    if y_max >= node.y:
                        search_helper(node.up_right)

        search_helper(self.root)
        return nodes

    def shortest_path(self, source, target):
        """
        使用水平和垂直传送返回从 A 到 B 的最短路径。
        此方法使用 A* 搜索算法的变体。
        :param source:  起始位置。
        :param target:  目标位置。
        :return:        按顺序排列的最短路径上的所有 Node 列表。
        """

        fringe = []
        vertices = [source]
        distances = [0]
        edge_to = [0]

        def push_neighbors(index):
            """
            添加可以从 POINT 到达的可能 Node（仅使用一个或两个传送）到边缘。
            返回的所有 Node 都比 POINT 更接近 TARGET。
            :param index:   当前位置的索引。
            :return:        None
            """

            point = vertices[index]

            def push_best(nodes):
                """
                将最接近 TARGET 的 Node 推入边缘。
                :param nodes:   要比较的点列表。
                :return:        None
                """

                if nodes:
                    points = [tuple(n) for n in nodes]
                    closest = utils.closest_point(points, target)

                    # 推入边缘
                    distance = distances[index] + utils.distance(point, closest)
                    heuristic = distance + utils.distance(closest, target)
                    heappush(fringe, (heuristic, len(vertices)))

                    # 更新顶点和边列表以包含新节点
                    vertices.append(closest)
                    distances.append(distance)
                    edge_to.append(index)

            x_error = (target[0] - point[0])
            y_error = (target[1] - point[1])
            delta = settings.move_tolerance / math.sqrt(2)

            # 使用水平传送推送最佳可能节点
            if abs(x_error) > settings.move_tolerance:
                if x_error > 0:
                    x_min = point[0] + settings.move_tolerance / 4
                    x_max = point[0] + settings.move_tolerance * 2
                else:
                    x_min = point[0] - settings.move_tolerance * 2
                    x_max = point[0] - settings.move_tolerance / 4
                candidates = self.search(x_min,
                                         x_max,
                                         point[1] - delta,
                                         point[1] + delta)
                push_best(candidates)

            # 使用垂直传送推送最佳可能节点
            if abs(y_error) > settings.move_tolerance:
                if y_error > 0:
                    y_min = point[1] + settings.move_tolerance / 4
                    y_max = 1
                else:
                    y_min = 0
                    y_max = point[1] - settings.move_tolerance / 4
                candidates = self.search(point[0] - delta,
                                         point[0] + delta,
                                         y_min,
                                         y_max)
                push_best(candidates)

        # 执行 A* 搜索算法
        i = 0
        while utils.distance(vertices[i], target) > settings.move_tolerance:
            push_neighbors(i)
            if len(fringe) == 0:
                break
            i = heappop(fringe)[1]

        # 提取并返回最短路径
        path = [target]
        while i != 0:
            path.append(vertices[i])
            i = edge_to[i]

        path.append(source)
        path = list(reversed(path))
        config.path = path.copy()
        return path

    def draw(self, image):
        """
        使用中序遍历在 IMAGE 上绘制此四叉树中的点。
        :param image:   要绘制的图像。
        :return:        None
        """

        def draw_helper(node):
            if node:
                draw_helper(node.up_left)
                draw_helper(node.down_left)

                center = utils.convert_to_absolute(tuple(node), image)
                cv2.circle(image, center, 1, (255, 165, 0), -1)

                draw_helper(node.up_right)
                draw_helper(node.down_right)

        draw_helper(self.root)

    @staticmethod
    def load(routine):
        """
        加载与 ROUTINE 关联的 Layout 对象。如果指定的 Layout 不存在，则创建并返回一个新的 Layout。
        :param routine:     与所需 Layout 关联的例程。
        :return:            Layout 实例。
        """

        layout_name = splitext(basename(routine))[0]
        target = os.path.join(get_layouts_dir(), layout_name)
        if isfile(target):
            print(f" -  找到现有的 Layout 文件位于 '{target}'。")
            with open(target, 'rb') as file:
                return pickle.load(file)
        else:
            print(f" -  在 '{target}' 创建新的 Layout 文件。")
            new_layout = Layout(layout_name)
            new_layout.save()
            return new_layout

    @utils.run_if_enabled
    def save(self):
        """
        将此 Layout 实例序列化到一个以生成此 Layout 的例程命名的文件中。
        :return:    None
        """

        layouts_dir = get_layouts_dir()
        if not os.path.exists(layouts_dir):
            os.makedirs(layouts_dir)
        with open(join(layouts_dir, self.name), 'wb') as file:
            pickle.dump(self, file)

    def delete_nearest(self, x, y):
        """
        删除最接近给定坐标 (X, Y) 的布局点。
        :param x:   搜索的 x 坐标。
        :param y:   搜索的 y 坐标。
        :return:    如果删除了点则为 True，否则为 False。
        """

        # 搜索附近的点
        nodes = self.search(x - 0.1, x + 0.1, y - 0.1, y + 0.1)

        if not nodes:
            return False

        # 找到最近的节点
        nearest_node = None
        min_distance = float('inf')

        for node in nodes:
            distance = utils.distance((node.x, node.y), (x, y))
            if distance < min_distance:
                min_distance = distance
                nearest_node = node

        if not nearest_node:
            return False

        # 从四叉树中删除节点
        self.root = self._delete_node(self.root, nearest_node.x, nearest_node.y)
        return True

    def _delete_node(self, node, x, y):
        """
        递归地从四叉树中删除节点。
        :param node:    当前正在检查的节点。
        :param x:       要删除的节点的 x 坐标。
        :param y:       要删除的节点的 y 坐标。
        :return:        删除后的更新节点。
        """
        if not node:
            return None

        # 找到要删除的节点
        if node.x == x and node.y == y:
            # 处理叶节点
            if not any([node.up_left, node.up_right, node.down_left, node.down_right]):
                return None
            # 处理非叶节点（简化：返回第一个非空子节点）
            if node.up_left:
                return node.up_left
            elif node.up_right:
                return node.up_right
            elif node.down_left:
                return node.down_left
            elif node.down_right:
                return node.down_right

        # 递归搜索子节点
        if y >= node.y and x < node.x:
            node.up_left = self._delete_node(node.up_left, x, y)
        elif y >= node.y and x >= node.x:
            node.up_right = self._delete_node(node.up_right, x, y)
        elif y < node.y and x < node.x:
            node.down_left = self._delete_node(node.down_left, x, y)
        else:
            node.down_right = self._delete_node(node.down_right, x, y)

        return node


def get_layouts_dir():
    # 使用相对路径
    return os.path.join(config.RESOURCES_DIR, 'layouts', config.bot.command_book.name)