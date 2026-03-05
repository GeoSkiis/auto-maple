"""A module for saving map layouts and determining shortest paths."""

import os
import cv2
import math
import pickle
from src.common import config, settings, utils
from os.path import join, isfile, splitext, basename
from heapq import heappush, heappop


class Node:
    """Represents a vertex on a quadtree."""

    def __init__(self, x, y):
        """
        Creates a new Node at (X, Y). Also initializes the Node's children.
        :param x:   The x position of the node.
        :param y:   The y position of the node.
        """

        self.x = x
        self.y = y
        self.up_left = None
        self.up_right = None
        self.down_left = None
        self.down_right = None

    def children(self):
        """
        Returns an array of this Node's children if they exist.
        :return:    This Node's children.
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
        Returns a string representation of this Node as a coordinate point.
        :return:    A string of the form '(x, y)'.
        """

        return str(tuple(self))

    def __iter__(self):
        """
        Support converting a Node into a tuple.
        :return:    This Node's x and y positions.
        """

        yield self.x
        yield self.y


class Layout:
    """Uses a quadtree to represent possible player positions in a map layout."""

    TOLERANCE = settings.move_tolerance / 2
    # TOLERANCE = 0.017

    def __init__(self, name):
        """
        Creates a new Layout object with the given NAME.
        :param name:     The name of this layout.
        """

        self.name = name
        self.root = None

    @utils.run_if_enabled
    def add(self, x, y):
        """
        Adds a Node to the quadtree at position (X, Y) if it does not already exist.
        :param x:   The x-position of the new point.
        :param y:   The y-position of the new point.
        :return:    True if the point was added successfully, False otherwise.
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
        Returns a list of all Nodes bounded horizontally by X_MIN and X_MAX, and bounded
        vertically by Y_MIN and Y_MAX.
        :param x_min:   The left boundary of the range.
        :param x_max:   The right boundary of the range.
        :param y_min:   The bottom boundary of the range.
        :param y_max:   The top boundary of the range.
        :return:        A list of all Nodes in the range.
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
        Returns the shortest path from A to B using horizontal and vertical teleports.
        This method uses a variant of the A* search algorithm.
        :param source:  The position to start at.
        :param target:  The destination.
        :return:        A list of all Nodes on the shortest path in order.
        """

        fringe = []
        vertices = [source]
        distances = [0]
        edge_to = [0]

        def push_neighbors(index):
            """
            Adds possible Nodes that can be reached from POINT (using only one or
            two teleports) to the fringe. The Nodes that are returned are all closer
            to TARGET than POINT is.
            :param index:   The index of the current position.
            :return:        None
            """

            point = vertices[index]

            def push_best(nodes):
                """
                Pushes the Node closest to TARGET to the fringe.
                :param nodes:   A list of points to compare.
                :return:        None
                """

                if nodes:
                    points = [tuple(n) for n in nodes]
                    closest = utils.closest_point(points, target)

                    # Push to the fringe
                    distance = distances[index] + utils.distance(point, closest)
                    heuristic = distance + utils.distance(closest, target)
                    heappush(fringe, (heuristic, len(vertices)))

                    # Update vertex and edge lists to include the new node
                    vertices.append(closest)
                    distances.append(distance)
                    edge_to.append(index)

            x_error = (target[0] - point[0])
            y_error = (target[1] - point[1])
            delta = settings.move_tolerance / math.sqrt(2)

            # Push best possible node using horizontal teleport
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

            # Push best possible node using vertical teleport
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

        # Perform the A* search algorithm
        i = 0
        while utils.distance(vertices[i], target) > settings.move_tolerance:
            push_neighbors(i)
            if len(fringe) == 0:
                break
            i = heappop(fringe)[1]

        # Extract and return shortest path
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
        Draws the points in this QuadTree onto IMAGE using in-order traversal.
        :param image:   The image to draw on.
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
        Loads the Layout object associated with ROUTINE. Creates and returns a
        new Layout if the specified Layout does not exist.
        :param routine:     The routine associated with the desired Layout.
        :return:            A Layout instance.
        """

        layout_name = splitext(basename(routine))[0]
        target = os.path.join(get_layouts_dir(), layout_name)
        if isfile(target):
            print(f" -  Found existing Layout file at '{target}'.")
            with open(target, 'rb') as file:
                return pickle.load(file)
        else:
            print(f" -  Created new Layout file at '{target}'.")
            new_layout = Layout(layout_name)
            new_layout.save()
            return new_layout

    @utils.run_if_enabled
    def save(self):
        """
        Pickles this Layout instance to a file that is named after the routine in which
        this Layout was generated.
        :return:    None
        """

        layouts_dir = get_layouts_dir()
        if not os.path.exists(layouts_dir):
            os.makedirs(layouts_dir)
        with open(join(layouts_dir, self.name), 'wb') as file:
            pickle.dump(self, file)

    def delete_nearest(self, x, y):
        """
        Deletes the nearest layout point to the given coordinates (X, Y).
        :param x:   The x-coordinate to search from.
        :param y:   The y-coordinate to search from.
        :return:    True if a point was deleted, False otherwise.
        """

        # Search for nearby points
        nodes = self.search(x - 0.1, x + 0.1, y - 0.1, y + 0.1)

        if not nodes:
            return False

        # Find the nearest node
        nearest_node = None
        min_distance = float('inf')

        for node in nodes:
            distance = utils.distance((node.x, node.y), (x, y))
            if distance < min_distance:
                min_distance = distance
                nearest_node = node

        if not nearest_node:
            return False

        # Delete the node from the quadtree
        self.root = self._delete_node(self.root, nearest_node.x, nearest_node.y)
        return True

    def _delete_node(self, node, x, y):
        """
        Recursively deletes a node from the quadtree.
        :param node:    The current node being checked.
        :param x:       The x-coordinate of the node to delete.
        :param y:       The y-coordinate of the node to delete.
        :return:        The updated node after deletion.
        """
        if not node:
            return None

        # Find the node to delete
        if node.x == x and node.y == y:
            # Handle leaf node
            if not any([node.up_left, node.up_right, node.down_left, node.down_right]):
                return None
            # Handle non-leaf node (simplified: return the first non-empty child)
            if node.up_left:
                return node.up_left
            elif node.up_right:
                return node.up_right
            elif node.down_left:
                return node.down_left
            elif node.down_right:
                return node.down_right

        # Recursively search child nodes
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
