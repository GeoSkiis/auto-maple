import pickle
import os

# 布局文件路径
layout_path = "c:\\Users\\Administrator\\auto-maple\\resources\\layouts\\hayato\\5-aa2"

# 检查文件是否存在
if not os.path.exists(layout_path):
    print(f"文件不存在: {layout_path}")
    exit(1)

# 检查文件大小
file_size = os.path.getsize(layout_path)
print(f"文件大小: {file_size} 字节")

# 尝试读取文件
try:
    with open(layout_path, 'rb') as f:
        layout = pickle.load(f)
    print("成功加载布局文件")
    print(f"布局名称: {layout.name}")
    print(f"根节点: {layout.root}")
    
    # 收集所有节点
    def collect_nodes(node, nodes):
        if node:
            nodes.append((node.x, node.y))
            collect_nodes(node.up_left, nodes)
            collect_nodes(node.up_right, nodes)
            collect_nodes(node.down_left, nodes)
            collect_nodes(node.down_right, nodes)
    
    nodes = []
    collect_nodes(layout.root, nodes)
    
    print(f"共找到 {len(nodes)} 个路径点:")
    for i, (x, y) in enumerate(nodes, 1):
        print(f"点 {i}: ({x:.4f}, {y:.4f})")
        
except Exception as e:
    print(f"读取布局文件失败: {str(e)}")
    import traceback
    traceback.print_exc()
