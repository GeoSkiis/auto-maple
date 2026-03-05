import tkinter as tk
from tkinter import filedialog, messagebox
import cv2
import pickle
import os
import sys
import math
import numpy as np
import mss
import re

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common import utils

# 小地图识别相关常量
MINIMAP_TOP_BORDER = 5
MINIMAP_BOTTOM_BORDER = 9
WINDOWED_OFFSET_TOP = 36
WINDOWED_OFFSET_LEFT = 10

# 模板路径
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets')
MM_TL_TEMPLATE = cv2.imread(os.path.join(ASSETS_DIR, 'minimap_tl_template.png'), 0)
MM_BR_TEMPLATE = cv2.imread(os.path.join(ASSETS_DIR, 'minimap_br_template.png'), 0)
PLAYER_TEMPLATE = cv2.imread(os.path.join(ASSETS_DIR, 'player_template.png'), 0)

if MM_TL_TEMPLATE is None or MM_BR_TEMPLATE is None:
    print("警告: 小地图模板未找到，自动识别功能可能无法使用")

MMT_HEIGHT = max(MM_TL_TEMPLATE.shape[0], MM_BR_TEMPLATE.shape[0]) if MM_TL_TEMPLATE is not None and MM_BR_TEMPLATE is not None else 0
MMT_WIDTH = max(MM_TL_TEMPLATE.shape[1], MM_BR_TEMPLATE.shape[1]) if MM_TL_TEMPLATE is not None and MM_BR_TEMPLATE is not None else 0
PT_HEIGHT, PT_WIDTH = PLAYER_TEMPLATE.shape if PLAYER_TEMPLATE is not None else (0, 0)

# 平台检测相关常量
BG_THRESHOLD = 15
ERODE_SIZE = 2
MIN_PLATFORM_AREA = 30
MIN_ASPECT_RATIO = 2.0
PLATFORM_SHIFT_UP = 10

from PIL import ImageTk, Image
from src.routine.layout import Layout, Node

# 重写Layout类，使用更小的容差以便更容易添加点
class EditorLayout(Layout):
    TOLERANCE = 0.01  # 使用更小的容差，便于添加点
    
    def add(self, x, y):
        """添加点，使用更小的容差以便更容易添加点"""
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
            return math.sqrt((point[0] - x) ** 2 + (point[1] - y) ** 2) >= EditorLayout.TOLERANCE

        if self.root:
            # 搜索附近的点
            nodes = self.search(x - EditorLayout.TOLERANCE, x + EditorLayout.TOLERANCE, 
                               y - EditorLayout.TOLERANCE, y + EditorLayout.TOLERANCE)
            checks = map(check_collision, [(n.x, n.y) for n in nodes])
            if all(checks):
                self.root = add_helper(self.root)
                return True
            return False
        else:
            self.root = add_helper(self.root)
            return True

class LayoutEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Layout路径点编辑器")
        self.root.geometry("800x600")
        
        # 菜单栏
        menubar = tk.Menu(root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="打开", command=self.open_file)
        filemenu.add_command(label="保存", command=self.save_file)
        filemenu.add_command(label="保存为", command=self.save_as_file)
        filemenu.add_separator()
        filemenu.add_command(label="退出", command=root.quit)
        menubar.add_cascade(label="文件", menu=filemenu)
        root.config(menu=menubar)
        
        # 主框架
        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 左侧控制面板
        control_frame = tk.LabelFrame(main_frame, text="控制面板", width=200)
        control_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5, anchor=tk.N)
        control_frame.pack_propagate(False)  # 防止控件改变框架大小
        
        # 加载地图按钮
        self.load_map_btn = tk.Button(control_frame, text="加载地图", command=self.load_map)
        self.load_map_btn.pack(fill=tk.X, padx=5, pady=5)
        
        # 添加点按钮
        self.add_point_btn = tk.Button(control_frame, text="添加点", command=self.enable_add_point)
        self.add_point_btn.pack(fill=tk.X, padx=5, pady=5)
        
        # 删除点按钮
        self.delete_point_btn = tk.Button(control_frame, text="删除点", command=self.enable_delete_point)
        self.delete_point_btn.pack(fill=tk.X, padx=5, pady=5)
        
        # 清除所有点按钮
        self.clear_btn = tk.Button(control_frame, text="清除所有点", command=self.clear_points)
        self.clear_btn.pack(fill=tk.X, padx=5, pady=5)
        
        # 坐标显示
        self.coord_var = tk.StringVar()
        self.coord_var.set("坐标: (0.0, 0.0)")
        coord_label = tk.Label(control_frame, textvariable=self.coord_var)
        coord_label.pack(fill=tk.X, padx=5, pady=5)
        
        # 状态显示
        self.status_var = tk.StringVar()
        self.status_var.set("状态: 就绪")
        status_label = tk.Label(control_frame, textvariable=self.status_var, fg="blue")
        status_label.pack(fill=tk.X, padx=5, pady=5)
        
        # 批量生成路径点
        batch_frame = tk.LabelFrame(control_frame, text="批量生成路径点")
        batch_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 第一个点
        tk.Label(batch_frame, text="第一个点 (x,y):").pack(anchor=tk.W, padx=5, pady=2)
        self.point1_var = tk.StringVar()
        self.point1_var.set("0.0,0.0")
        tk.Entry(batch_frame, textvariable=self.point1_var).pack(fill=tk.X, padx=5, pady=2)
        
        # 第二个点
        tk.Label(batch_frame, text="第二个点 (x,y):").pack(anchor=tk.W, padx=5, pady=2)
        self.point2_var = tk.StringVar()
        self.point2_var.set("1.0,1.0")
        tk.Entry(batch_frame, textvariable=self.point2_var).pack(fill=tk.X, padx=5, pady=2)
        
        # 移动容差
        tk.Label(batch_frame, text="移动容差:").pack(anchor=tk.W, padx=5, pady=2)
        self.tolerance_var = tk.StringVar()
        self.tolerance_var.set("0.05")
        tk.Entry(batch_frame, textvariable=self.tolerance_var).pack(fill=tk.X, padx=5, pady=2)
        
        # 按钮区域
        btn_frame = tk.Frame(batch_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 预览按钮
        self.preview_btn = tk.Button(btn_frame, text="预览路径点", command=self.preview_points)
        self.preview_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        
        # 生成按钮
        self.generate_btn = tk.Button(btn_frame, text="生成路径点", command=self.generate_points)
        self.generate_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=2)
        
        # 自动识别地图
        auto_map_frame = tk.LabelFrame(control_frame, text="自动识别地图")
        auto_map_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 捕获小地图按钮
        self.capture_minimap_btn = tk.Button(auto_map_frame, text="从游戏捕获小地图", command=self.capture_minimap)
        self.capture_minimap_btn.pack(fill=tk.X, padx=5, pady=5)
        
        # 检测平台按钮
        self.detect_platforms_btn = tk.Button(auto_map_frame, text="检测平台并生成路径点", command=self.detect_platforms)
        self.detect_platforms_btn.pack(fill=tk.X, padx=5, pady=5)
        
        # 预览状态
        self.preview_points_list = []
        
        # 右侧画布
        canvas_frame = tk.LabelFrame(main_frame, text="地图")
        canvas_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.canvas = tk.Canvas(canvas_frame, bg='black')
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # 绑定事件
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<Button-1>", self.on_mouse_click)
        
        # 状态变量
        self.layout = None
        self.image = None
        self.image_tk = None
        self.mode = "view"  # view, add, delete
        self.current_file = None
        self.map_image = None
        self.map_width = 0
        self.map_height = 0
        # 小地图识别相关变量
        self.captured_minimap = None
        self.minimap_tl = None
        self.minimap_br = None
        
    def open_file(self):
        """打开layout文件"""
        file_path = filedialog.askopenfilename(
            title="选择Layout文件",
            filetypes=[("Layout文件", "*"), ("All files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'rb') as f:
                    # 尝试以不同的编码方式加载pickle文件
                    try:
                        loaded_layout = pickle.load(f)
                    except UnicodeDecodeError:
                        # 尝试使用latin1编码
                        f.seek(0)
                        loaded_layout = pickle.load(f, encoding='latin1')
                # 转换为EditorLayout
                self.layout = EditorLayout(loaded_layout.name)
                self.layout.root = loaded_layout.root
                self.current_file = file_path
                self.root.title(f"Layout路径点编辑器 - {os.path.basename(file_path)}")
                self.draw_layout()
                messagebox.showinfo("成功", f"已加载文件: {os.path.basename(file_path)}")
            except Exception as e:
                messagebox.showerror("错误", f"加载文件失败: {str(e)}")
                import traceback
                traceback.print_exc()
    
    def save_file(self):
        """保存文件"""
        if self.current_file:
            try:
                with open(self.current_file, 'wb') as f:
                    pickle.dump(self.layout, f)
                messagebox.showinfo("成功", "文件已保存")
            except Exception as e:
                messagebox.showerror("错误", f"保存文件失败: {str(e)}")
        else:
            self.save_as_file()
    
    def save_as_file(self):
        """另存为文件"""
        file_path = filedialog.asksaveasfilename(
            title="保存Layout文件",
            defaultextension="",
            filetypes=[("Layout文件", "*"), ("All files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'wb') as f:
                    pickle.dump(self.layout, f)
                self.current_file = file_path
                self.root.title(f"Layout路径点编辑器 - {os.path.basename(file_path)}")
                messagebox.showinfo("成功", f"文件已保存为: {os.path.basename(file_path)}")
            except Exception as e:
                messagebox.showerror("错误", f"保存文件失败: {str(e)}")
    
    def load_map(self):
        """加载地图图片"""
        file_path = filedialog.askopenfilename(
            title="选择地图图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg"), ("All files", "*.*")]
        )
        if file_path:
            try:
                self.map_image = cv2.imread(file_path)
                self.map_image = cv2.cvtColor(self.map_image, cv2.COLOR_BGR2RGB)
                self.map_height, self.map_width, _ = self.map_image.shape
                self.draw_layout()
                messagebox.showinfo("成功", "地图已加载")
            except Exception as e:
                messagebox.showerror("错误", f"加载地图失败: {str(e)}")
    
    def enable_add_point(self):
        """启用添加点模式"""
        self.mode = "add"
        self.root.title(f"Layout路径点编辑器 - 添加模式")
    
    def enable_delete_point(self):
        """启用删除点模式"""
        self.mode = "delete"
        self.root.title(f"Layout路径点编辑器 - 删除模式")
    
    def clear_points(self):
        """清除所有点"""
        if messagebox.askyesno("确认", "确定要清除所有点吗？"):
            if self.layout:
                self.layout.root = None
                self.draw_layout()
    
    def on_mouse_move(self, event):
        """鼠标移动事件"""
        if self.map_image is not None:
            # 计算相对坐标
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            # 保持图片比例
            ratio = min(canvas_width / self.map_width, canvas_height / self.map_height)
            new_width = int(self.map_width * ratio)
            new_height = int(self.map_height * ratio)
            
            # 计算图片位置
            x_offset = (canvas_width - new_width) // 2
            y_offset = (canvas_height - new_height) // 2
            
            # 检查鼠标是否在图片范围内
            if x_offset <= event.x < x_offset + new_width and y_offset <= event.y < y_offset + new_height:
                # 计算相对坐标 (0-1范围)
                rel_x = (event.x - x_offset) / new_width
                rel_y = 1.0 - (event.y - y_offset) / new_height  # 翻转y轴
                self.coord_var.set(f"坐标: ({rel_x:.3f}, {rel_y:.3f})")
            else:
                self.coord_var.set("坐标: (0.0, 0.0)")
        else:
            # 没有加载地图时，不显示坐标
            self.coord_var.set("坐标: (0.0, 0.0)")
    
    def on_mouse_click(self, event):
        """鼠标点击事件"""
        # 计算相对坐标
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        rel_x = 0.0
        rel_y = 0.0
        valid_click = False
        
        if self.map_image is not None:
            # 保持图片比例
            ratio = min(canvas_width / self.map_width, canvas_height / self.map_height)
            new_width = int(self.map_width * ratio)
            new_height = int(self.map_height * ratio)
            
            # 计算图片位置
            x_offset = (canvas_width - new_width) // 2
            y_offset = (canvas_height - new_height) // 2
            
            # 检查鼠标是否在图片范围内
            if x_offset <= event.x < x_offset + new_width and y_offset <= event.y < y_offset + new_height:
                # 计算相对坐标 (0-1范围)
                rel_x = (event.x - x_offset) / new_width
                rel_y = 1.0 - (event.y - y_offset) / new_height  # 翻转y轴
                valid_click = True
        else:
            # 没有加载地图时，使用整个画布作为参考
            # 计算相对坐标 (0-1范围)
            rel_x = event.x / canvas_width
            rel_y = 1.0 - event.y / canvas_height  # 翻转y轴
            valid_click = True
        
        if valid_click:
            if self.mode == "add":
                # 添加点
                if not self.layout:
                    self.layout = EditorLayout("new_layout")
                print(f"添加点: ({rel_x:.3f}, {rel_y:.3f})")
                success = self.layout.add(rel_x, rel_y)
                print(f"添加成功: {success}")
                print(f"添加后根节点: {self.layout.root}")
                if success:
                    self.draw_layout()
                    self.status_var.set("状态: 点添加成功")
                else:
                    self.status_var.set("状态: 该位置附近已有点")
                # 3秒后重置状态
                self.root.after(3000, lambda: self.status_var.set("状态: 就绪"))
            elif self.mode == "delete":
                # 删除点
                if self.layout:
                    # 找到并删除最近的点
                    deleted = self.delete_nearest_point(rel_x, rel_y)
                    if deleted:
                        self.draw_layout()
                        self.status_var.set("状态: 点删除成功")
                    else:
                        self.status_var.set("状态: 附近没有点")
                    # 3秒后重置状态
                    self.root.after(3000, lambda: self.status_var.set("状态: 就绪"))
    
    def draw_layout(self):
        """绘制布局"""
        # 获取画布尺寸（只获取一次，避免循环触发）
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        # 固定的默认背景大小和最小显示大小
        DEFAULT_WIDTH = 400
        DEFAULT_HEIGHT = 300
        MIN_DISPLAY_WIDTH = 300
        MIN_DISPLAY_HEIGHT = 200
        
        # 计算显示尺寸
        if self.map_image is None or self.map_width <= 0 or self.map_height <= 0:
            # 使用固定大小的空白背景
            display_width = DEFAULT_WIDTH
            display_height = DEFAULT_HEIGHT
        else:
            # 使用地图的实际大小，但确保有最小尺寸
            display_width = max(self.map_width, MIN_DISPLAY_WIDTH)
            display_height = max(self.map_height, MIN_DISPLAY_HEIGHT)
        
        # 计算缩放比例
        if display_width <= 0 or display_height <= 0:
            ratio = 1.0
        else:
            ratio = min(canvas_width / display_width, canvas_height / display_height)
        new_width = int(display_width * ratio)
        new_height = int(display_height * ratio)
        
        # 创建或调整图像
        if self.map_image is None or self.map_width <= 0 or self.map_height <= 0:
            # 创建固定大小的空白背景
            img = np.zeros((DEFAULT_HEIGHT, DEFAULT_WIDTH, 3), dtype=np.uint8) + 255
        else:
            # 复制图片
            img = self.map_image.copy()
        
        # 调整大小
        if new_width > 0 and new_height > 0:
            # 计算实际缩放比例，确保小地图在最小显示尺寸内居中显示
            if self.map_image is not None and self.map_width > 0 and self.map_height > 0 and (display_width > self.map_width or display_height > self.map_height):
                # 计算小地图在最小显示尺寸内的缩放比例
                scale_ratio = min(
                    (display_width - 40) / self.map_width,  # 40px 边距
                    (display_height - 40) / self.map_height
                )
                scaled_map_width = int(self.map_width * scale_ratio)
                scaled_map_height = int(self.map_height * scale_ratio)
                
                # 调整小地图大小
                if scaled_map_width > 0 and scaled_map_height > 0:
                    img = cv2.resize(img, (scaled_map_width, scaled_map_height), interpolation=cv2.INTER_AREA)
                
                # 创建一个最小尺寸的背景
                background = np.zeros((display_height, display_width, 3), dtype=np.uint8) + 255
                
                # 将小地图居中放置
                x_offset = (display_width - scaled_map_width) // 2
                y_offset = (display_height - scaled_map_height) // 2
                background[y_offset:y_offset+scaled_map_height, x_offset:x_offset+scaled_map_width] = img
                img = background
            
            # 调整到画布大小
            img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
        
        # 绘制路径点
        if self.layout:
            self.draw_nodes(img, self.layout.root)
        
        # 转换为ImageTk
        self.image_tk = ImageTk.PhotoImage(Image.fromarray(img))
        
        # 清除画布并绘制图片
        self.canvas.delete("all")
        
        # 计算居中位置
        x_offset = (canvas_width - new_width) // 2
        y_offset = (canvas_height - new_height) // 2
        
        # 绘制图片
        self.canvas.create_image(x_offset, y_offset, anchor=tk.NW, image=self.image_tk)
        
        # 为地图添加边界描边
        if self.map_image is not None:
            # 绘制地图边界矩形
            self.canvas.create_rectangle(
                x_offset, y_offset, 
                x_offset + new_width, 
                y_offset + new_height, 
                outline="red", width=2
            )
    
    def delete_nearest_point(self, x, y):
        """删除最近的点"""
        # 搜索附近的点
        nodes = self.layout.search(x - 0.1, x + 0.1, y - 0.1, y + 0.1)
        
        if not nodes:
            return False
        
        # 找到最近的点
        nearest_node = None
        min_distance = float('inf')
        
        for node in nodes:
            distance = math.sqrt((node.x - x) ** 2 + (node.y - y) ** 2)
            if distance < min_distance:
                min_distance = distance
                nearest_node = node
        
        if not nearest_node:
            return False
        
        # 从四叉树中删除该点
        self.layout.root = self._delete_node(self.layout.root, nearest_node.x, nearest_node.y)
        return True
    
    def _delete_node(self, node, x, y):
        """递归删除节点"""
        if not node:
            return None
        
        # 找到要删除的节点
        if node.x == x and node.y == y:
            # 处理叶子节点
            if not any([node.up_left, node.up_right, node.down_left, node.down_right]):
                return None
            # 处理非叶子节点（这里简化处理，直接返回第一个非空子节点）
            # 实际的四叉树删除需要更复杂的逻辑
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
    
    def preview_points(self):
        """预览将要生成的路径点"""
        try:
            # 解析第一个点
            point1_str = self.point1_var.get().strip()
            x1, y1 = map(float, point1_str.split(','))
            
            # 解析第二个点
            point2_str = self.point2_var.get().strip()
            x2, y2 = map(float, point2_str.split(','))
            
            # 解析容差
            tolerance = float(self.tolerance_var.get().strip())
            
            # 检查是否同轴
            preview_points = []
            if abs(x1 - x2) < 0.001:  # X轴相同
                # 计算Y轴方向的步数
                y_min = min(y1, y2)
                y_max = max(y1, y2)
                steps = int((y_max - y_min) / tolerance) + 1
                
                # 生成预览点
                for i in range(steps):
                    y = y_min + i * tolerance
                    preview_points.append((x1, y))
            elif abs(y1 - y2) < 0.001:  # Y轴相同
                # 计算X轴方向的步数
                x_min = min(x1, x2)
                x_max = max(x1, x2)
                steps = int((x_max - x_min) / tolerance) + 1
                
                # 生成预览点
                for i in range(steps):
                    x = x_min + i * tolerance
                    preview_points.append((x, y1))
            else:
                self.status_var.set("状态: 两点必须同轴")
                self.root.after(3000, lambda: self.status_var.set("状态: 就绪"))
                return
            
            # 保存预览点
            self.preview_points_list = preview_points
            
            # 绘制预览点
            self.draw_layout_with_preview()
            self.status_var.set(f"状态: 预览 {len(preview_points)} 个路径点")
            self.root.after(3000, lambda: self.status_var.set("状态: 就绪"))
        except Exception as e:
            self.status_var.set(f"状态: 输入格式错误")
            self.root.after(3000, lambda: self.status_var.set("状态: 就绪"))
    
    def generate_points(self):
        """批量生成路径点"""
        try:
            # 如果有预览点，直接使用预览点
            if self.preview_points_list:
                generated = 0
                if not self.layout:
                    self.layout = EditorLayout("new_layout")
                
                for point in self.preview_points_list:
                    if self.layout.add(point[0], point[1]):
                        generated += 1
                
                # 重绘布局
                self.draw_layout()
                self.status_var.set(f"状态: 成功生成 {generated} 个路径点")
                self.root.after(3000, lambda: self.status_var.set("状态: 就绪"))
                return
            
            # 否则按原逻辑生成
            # 解析第一个点
            point1_str = self.point1_var.get().strip()
            x1, y1 = map(float, point1_str.split(','))
            
            # 解析第二个点
            point2_str = self.point2_var.get().strip()
            x2, y2 = map(float, point2_str.split(','))
            
            # 解析容差
            tolerance = float(self.tolerance_var.get().strip())
            
            # 检查是否同轴
            if abs(x1 - x2) < 0.001:  # X轴相同
                # 计算Y轴方向的步数
                y_min = min(y1, y2)
                y_max = max(y1, y2)
                steps = int((y_max - y_min) / tolerance) + 1
                
                # 生成路径点
                generated = 0
                if not self.layout:
                    self.layout = EditorLayout("new_layout")
                
                for i in range(steps):
                    y = y_min + i * tolerance
                    if self.layout.add(x1, y):
                        generated += 1
            elif abs(y1 - y2) < 0.001:  # Y轴相同
                # 计算X轴方向的步数
                x_min = min(x1, x2)
                x_max = max(x1, x2)
                steps = int((x_max - x_min) / tolerance) + 1
                
                # 生成路径点
                generated = 0
                if not self.layout:
                    self.layout = EditorLayout("new_layout")
                
                for i in range(steps):
                    x = x_min + i * tolerance
                    if self.layout.add(x, y1):
                        generated += 1
            else:
                self.status_var.set("状态: 两点必须同轴")
                self.root.after(3000, lambda: self.status_var.set("状态: 就绪"))
                return
            
            # 重绘布局
            self.draw_layout()
            self.status_var.set(f"状态: 成功生成 {generated} 个路径点")
            self.root.after(3000, lambda: self.status_var.set("状态: 就绪"))
        except Exception as e:
            self.status_var.set(f"状态: 输入格式错误")
            self.root.after(3000, lambda: self.status_var.set("状态: 就绪"))
    
    def draw_layout_with_preview(self):
        """绘制布局并显示预览点"""
        # 获取画布尺寸
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        # 固定的默认背景大小和最小显示大小
        DEFAULT_WIDTH = 400
        DEFAULT_HEIGHT = 300
        MIN_DISPLAY_WIDTH = 300
        MIN_DISPLAY_HEIGHT = 200
        
        # 计算显示尺寸
        if self.map_image is None:
            # 使用固定大小的空白背景
            display_width = DEFAULT_WIDTH
            display_height = DEFAULT_HEIGHT
        else:
            # 使用地图的实际大小，但确保有最小尺寸
            display_width = max(self.map_width, MIN_DISPLAY_WIDTH)
            display_height = max(self.map_height, MIN_DISPLAY_HEIGHT)
        
        # 计算缩放比例
        ratio = min(canvas_width / display_width, canvas_height / display_height)
        new_width = int(display_width * ratio)
        new_height = int(display_height * ratio)
        
        # 创建或调整图像
        if self.map_image is None:
            # 创建固定大小的空白背景
            img = np.zeros((DEFAULT_HEIGHT, DEFAULT_WIDTH, 3), dtype=np.uint8) + 255
        else:
            # 复制图片
            img = self.map_image.copy()
        
        # 调整大小
        if new_width > 0 and new_height > 0:
            # 计算实际缩放比例，确保小地图在最小显示尺寸内居中显示
            if display_width > self.map_width or display_height > self.map_height:
                # 计算小地图在最小显示尺寸内的缩放比例
                scale_ratio = min(
                    (display_width - 40) / self.map_width,  # 40px 边距
                    (display_height - 40) / self.map_height
                )
                scaled_map_width = int(self.map_width * scale_ratio)
                scaled_map_height = int(self.map_height * scale_ratio)
                
                # 调整小地图大小
                if scaled_map_width > 0 and scaled_map_height > 0:
                    img = cv2.resize(img, (scaled_map_width, scaled_map_height), interpolation=cv2.INTER_AREA)
                
                # 创建一个最小尺寸的背景
                background = np.zeros((display_height, display_width, 3), dtype=np.uint8) + 255
                
                # 将小地图居中放置
                x_offset = (display_width - scaled_map_width) // 2
                y_offset = (display_height - scaled_map_height) // 2
                background[y_offset:y_offset+scaled_map_height, x_offset:x_offset+scaled_map_width] = img
                img = background
            
            # 调整到画布大小
            img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
        
        # 绘制路径点
        if self.layout:
            self.draw_nodes(img, self.layout.root)
        
        # 绘制预览点
        for point in self.preview_points_list:
            height, width, _ = img.shape
            x = int(point[0] * width)
            y = int((1.0 - point[1]) * height)  # 翻转y轴
            cv2.circle(img, (x, y), 3, (0, 0, 255), -1)  # 红色预览点
        
        # 转换为ImageTk
        self.image_tk = ImageTk.PhotoImage(Image.fromarray(img))
        
        # 清除画布并绘制图片
        self.canvas.delete("all")
        
        # 计算居中位置
        x_offset = (canvas_width - new_width) // 2
        y_offset = (canvas_height - new_height) // 2
        
        # 绘制图片
        self.canvas.create_image(x_offset, y_offset, anchor=tk.NW, image=self.image_tk)
        
        # 为地图添加边界描边
        if self.map_image is not None:
            # 绘制地图边界矩形
            self.canvas.create_rectangle(
                x_offset, y_offset, 
                x_offset + new_width, 
                y_offset + new_height, 
                outline="red", width=2
            )
    
    def draw_nodes(self, img, node):
        """递归绘制节点"""
        if node:
            # 绘制当前节点
            height, width, _ = img.shape
            x = int(node.x * width)
            y = int((1.0 - node.y) * height)  # 翻转y轴，因为布局中的y坐标是从下到上的
            cv2.circle(img, (x, y), 3, (0, 255, 0), -1)
            
            # 递归绘制子节点
            self.draw_nodes(img, node.up_left)
            self.draw_nodes(img, node.up_right)
            self.draw_nodes(img, node.down_left)
            self.draw_nodes(img, node.down_right)
    
    def capture_minimap(self):
        """从游戏屏幕捕获小地图"""
        try:
            self.status_var.set("状态: 正在捕获小地图...")
            
            # 直接使用auto-maple的方法来获取小地图
            import mss
            import numpy as np
            import ctypes
            from ctypes import wintypes
            from src.common import utils
            
            # 模板路径
            ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets')
            MM_TL_TEMPLATE = cv2.imread(os.path.join(ASSETS_DIR, 'minimap_tl_template.png'), 0)
            MM_BR_TEMPLATE = cv2.imread(os.path.join(ASSETS_DIR, 'minimap_br_template.png'), 0)
            PLAYER_TEMPLATE = cv2.imread(os.path.join(ASSETS_DIR, 'player_template.png'), 0)
            
            # 检查模板文件
            if MM_TL_TEMPLATE is None or MM_BR_TEMPLATE is None:
                self.status_var.set("状态: 模板文件缺失")
                messagebox.showerror("错误", "小地图模板文件未找到，请确保assets文件夹中有minimap_tl_template.png和minimap_br_template.png")
                return
            
            # 找到MapleStory窗口
            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware()
            handle = user32.FindWindowW(None, 'MapleStory')
            if not handle:
                self.status_var.set("状态: 游戏窗口未找到")
                messagebox.showerror("错误", "未能找到MapleStory窗口，请确保游戏已启动")
                return
            
            # 获取窗口位置和大小
            rect = wintypes.RECT()
            user32.GetWindowRect(handle, ctypes.pointer(rect))
            window_rect = (rect.left, rect.top, rect.right, rect.bottom)
            window_rect = tuple(max(0, x) for x in window_rect)
            print(f"MapleStory窗口位置: {window_rect}")
            
            # 计算窗口大小
            window_width = window_rect[2] - window_rect[0]
            window_height = window_rect[3] - window_rect[1]
            print(f"MapleStory窗口大小: {window_width}x{window_height}")
            
            # 截图MapleStory窗口
            with mss.mss() as sct:
                # 创建窗口区域
                monitor = {
                    'left': window_rect[0],
                    'top': window_rect[1],
                    'width': window_width,
                    'height': window_height
                }
                
                try:
                    # 截图
                    shot = sct.grab(monitor)
                    # 转换为numpy数组
                    frame = np.array(shot)
                    # 转换为BGR格式
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    
                    # 搜索小地图
                    h, w = frame.shape[:2]
                    print(f"截图大小: {w}x{h}")
                    # 只在左上角30%区域搜索
                    temp_frame = frame[0 : int(h * 0.3), 0 : int(w * 0.3)]
                    
                    # 模板匹配找到左上角和右下角
                    tl, _ = utils.single_match(temp_frame, MM_TL_TEMPLATE)
                    _, br = utils.single_match(temp_frame, MM_BR_TEMPLATE)
                    
                    found_minimap = None
                    if tl is not None and br is not None:
                        print(f"找到小地图模板: 左上角={tl}, 右下角={br}")
                        # 计算小地图的实际位置
                        MINIMAP_TOP_BORDER = 5
                        MINIMAP_BOTTOM_BORDER = 9
                        PT_HEIGHT, PT_WIDTH = PLAYER_TEMPLATE.shape if PLAYER_TEMPLATE is not None else (0, 0)
                        
                        mm_tl = (
                            tl[0] + MINIMAP_BOTTOM_BORDER,
                            tl[1] + MINIMAP_TOP_BORDER
                        )
                        mm_br = (
                            max(mm_tl[0] + PT_WIDTH, br[0] - MINIMAP_BOTTOM_BORDER),
                            max(mm_tl[1] + PT_HEIGHT, br[1] - MINIMAP_BOTTOM_BORDER)
                        )
                        
                        print(f"小地图区域: 左上角={mm_tl}, 右下角={mm_br}")
                        # 边界检查
                        if mm_br[0] > mm_tl[0] and mm_br[1] > mm_tl[1]:
                            if mm_tl[0] >= 0 and mm_tl[1] >= 0 and mm_br[0] <= w and mm_br[1] <= h:
                                # 提取小地图
                                minimap = frame[mm_tl[1]:mm_br[1], mm_tl[0]:mm_br[0]].copy()
                                if minimap.size > 0:
                                    found_minimap = minimap
                                    print(f"成功提取小地图，大小: {minimap.shape[1]}x{minimap.shape[0]}")
                except Exception as e:
                    print(f"捕获窗口时出错: {str(e)}")
                    import traceback
                    traceback.print_exc()
            
            if found_minimap is not None:
                try:
                    # 转换为RGB格式
                    minimap_rgb = cv2.cvtColor(found_minimap, cv2.COLOR_BGR2RGB)
                    if minimap_rgb is not None and hasattr(minimap_rgb, 'shape'):
                        self.captured_minimap = minimap_rgb
                        self.map_image = minimap_rgb
                        self.map_height, self.map_width, _ = minimap_rgb.shape
                        self.draw_layout()
                        self.status_var.set("状态: 小地图捕获成功")
                        messagebox.showinfo("成功", "小地图捕获成功！")
                    else:
                        self.status_var.set("状态: 小地图格式错误")
                        messagebox.showerror("错误", "获取的小地图格式错误，请重试")
                except Exception as e:
                    print(f"处理小地图时出错: {str(e)}")
                    self.status_var.set("状态: 小地图处理失败")
                    messagebox.showerror("错误", f"处理小地图时出错: {str(e)}")
            else:
                self.status_var.set("状态: 小地图捕获失败")
                messagebox.showerror("错误", "未能找到小地图，请确保游戏窗口可见且小地图在左上角")
        except Exception as e:
            print(f"捕获小地图时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            self.status_var.set("状态: 捕获失败")
            messagebox.showerror("错误", f"捕获小地图时出错: {str(e)}")
    
    def get_minimap_from_frame(self, frame):
        """从帧中提取小地图"""
        if frame is None or frame.size == 0:
            print("帧为空")
            return None
        
        try:
            # 搜索小地图的左上角和右下角
            h, w = frame.shape[:2]
            print(f"帧大小: {w}x{h}")
            # 只在左上角30%区域搜索
            search_height = int(h * 0.3)
            search_width = int(w * 0.3)
            print(f"搜索区域: {search_width}x{search_height}")
            temp_frame = frame[0 : search_height, 0 : search_width]
            
            # 转换为灰度图
            gray_frame = cv2.cvtColor(temp_frame, cv2.COLOR_BGR2GRAY)
            
            # 模板匹配找到左上角
            print("正在寻找左上角模板...")
            tl, _ = utils.single_match(gray_frame, MM_TL_TEMPLATE)
            print(f"左上角模板位置: {tl}")
            # 模板匹配找到右下角
            print("正在寻找右下角模板...")
            _, br = utils.single_match(gray_frame, MM_BR_TEMPLATE)
            print(f"右下角模板位置: {br}")
            
            if tl is None or br is None:
                print("未能找到小地图模板")
                return None
            
            # 计算小地图的实际位置
            mm_tl = (
                tl[0] + MINIMAP_BOTTOM_BORDER,
                tl[1] + MINIMAP_TOP_BORDER
            )
            mm_br = (
                max(mm_tl[0] + PT_WIDTH, br[0] - MINIMAP_BOTTOM_BORDER),
                max(mm_tl[1] + PT_HEIGHT, br[1] - MINIMAP_BOTTOM_BORDER)
            )
            
            print(f"小地图左上角: {mm_tl}")
            print(f"小地图右下角: {mm_br}")
            
            # 边界检查
            if mm_br[0] <= mm_tl[0] or mm_br[1] <= mm_tl[1]:
                print("小地图边界无效: 右下角坐标小于或等于左上角坐标")
                return None
            if mm_tl[0] < 0 or mm_tl[1] < 0 or mm_br[0] > w or mm_br[1] > h:
                print("小地图边界超出帧范围")
                return None
            
            # 保存小地图位置
            self.minimap_tl = mm_tl
            self.minimap_br = mm_br
            
            # 提取小地图
            minimap = frame[mm_tl[1]:mm_br[1], mm_tl[0]:mm_br[0]]
            print(f"提取的小地图大小: {minimap.shape[1]}x{minimap.shape[0]}")
            return minimap
        except Exception as e:
            print(f"提取小地图时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def detect_platforms(self):
        """检测平台并生成路径点"""
        try:
            if self.captured_minimap is None:
                messagebox.showerror("错误", "请先捕获小地图")
                return
            
            self.status_var.set("状态: 正在检测平台...")
            
            # 从地图图像生成路径点
            waypoints = self.waypoints_from_map_image(self.captured_minimap)
            
            if not waypoints:
                self.status_var.set("状态: 未检测到平台")
                messagebox.showinfo("提示", "未检测到平台，请确保小地图清晰可见")
                return
            
            # 创建或清空布局
            if not self.layout:
                self.layout = EditorLayout("auto_generated")
            else:
                self.layout.root = None
            
            # 添加路径点
            for waypoint in waypoints:
                self.layout.add(waypoint["x"], waypoint["y"])
            
            # 重绘布局
            self.draw_layout()
            self.status_var.set(f"状态: 成功生成 {len(waypoints)} 个路径点")
            messagebox.showinfo("成功", f"成功生成 {len(waypoints)} 个路径点！")
        except Exception as e:
            self.status_var.set("状态: 检测失败")
            messagebox.showerror("错误", f"检测平台时出错: {str(e)}")
    
    def waypoints_from_map_image(self, img, crop_top=0, crop_bottom=0, crop_left=0, crop_right=0):
        """从地图图像生成路径点"""
        if img is None:
            return []
        
        # 处理透明通道
        if img.ndim == 3 and img.shape[2] == 4:
            img = img[:, :, :3]
        
        # 转换为灰度图
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 二值化
        _, binary = cv2.threshold(gray, BG_THRESHOLD, 255, cv2.THRESH_BINARY)
        
        # 腐蚀操作
        kernel = np.ones((ERODE_SIZE, ERODE_SIZE), np.uint8)
        eroded = cv2.erode(binary, kernel)
        
        # 连通区域分析
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(eroded)
        h_img, w_img = gray.shape[:2]
        
        # 计算内容区域
        w_content = w_img - crop_left - crop_right
        h_content = h_img - crop_top - crop_bottom
        if w_content <= 0 or h_content <= 0:
            w_content, h_content = w_img, h_img
            crop_left = crop_right = crop_top = crop_bottom = 0
        
        # 收集有效的平台
        valid_platforms = []
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            width = stats[i, cv2.CC_STAT_WIDTH]
            height = stats[i, cv2.CC_STAT_HEIGHT]
            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP]
            
            # 过滤面积
            if area < MIN_PLATFORM_AREA:
                continue
            
            # 计算长宽比并过滤
            aspect_ratio = width / height if height > 0 else 0
            if aspect_ratio < MIN_ASPECT_RATIO:
                continue
            
            cx, cy = centroids[i]
            valid_platforms.append({
                'index': i,
                'cx': cx,
                'cy': cy,
                'x': x,
                'y': y,
                'width': width,
                'height': height,
                'area': area,
            })
        
        # 找到最底部的平台
        bottom_platform_index = None
        if valid_platforms:
            bottom_platform = max(valid_platforms, key=lambda p: p['cy'])
            bottom_platform_index = bottom_platform['index']
        
        # 生成路径点
        waypoints_raw = []
        for platform in valid_platforms:
            i = platform['index']
            cx = platform['cx']
            cy = platform['cy']
            x = platform['x']
            width = platform['width']
            
            if i == bottom_platform_index:
                # 底部平台生成三个点
                positions = [0.25, 0.5, 0.75]
                for pos_fraction in positions:
                    px = x + width * pos_fraction
                    py = cy
                    waypoints_raw.append({
                        "px": px, "py": py,
                        "is_bottom_platform": True
                    })
            else:
                # 其他平台生成中心点
                px = cx
                py = cy
                waypoints_raw.append({
                    "px": px, "py": py,
                    "is_bottom_platform": False
                })
        
        # 找到y坐标最高的3个点（地图上最低的点）并向上移动
        indices_to_shift = sorted(
            range(len(waypoints_raw)),
            key=lambda idx: waypoints_raw[idx]["py"],
            reverse=True
        )[:3]
        for idx in indices_to_shift:
            waypoints_raw[idx]["py"] -= PLATFORM_SHIFT_UP
        
        # 转换为相对坐标
        waypoints = []
        for w in waypoints_raw:
            x_rel = (w["px"] - crop_left) / w_content
            y_rel = (w["py"] - crop_top) / h_content
            # 确保坐标在0-1范围内
            x_rel = max(0.0, min(1.0, x_rel))
            y_rel = max(0.0, min(1.0, y_rel))
            waypoints.append({
                "x": round(x_rel, 4),
                "y": round(y_rel, 4),
                "is_bottom_platform": w["is_bottom_platform"]
            })
        
        return waypoints

if __name__ == "__main__":
    root = tk.Tk()
    app = LayoutEditor(root)
    root.mainloop()
