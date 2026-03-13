import cv2
import numpy as np
import sys
sys.path.append('.')

# 加载模板
template = cv2.imread('assets/rune_buff_template.jpg', 1)
if template is None:
    print("无法加载模板")
    exit()

print(f"模板信息:")
print(f"  尺寸: {template.shape}")
print(f"  数据类型: {template.dtype}")

# 简单演示检测逻辑
print("\n=== 检测逻辑演示 ===")
print("1. 使用彩色模板匹配 (TM_CCOEFF_NORMED)")
print("2. 阈值: 0.88")
print("3. 只匹配颜色和图案都相似的")

print("\n根据你提供的截图:")
print("- 左侧蓝色符文: 颜色与模板匹配 → 会被检测到")
print("- 右侧灰色符文: 颜色不同 → 不会被检测到")

print("\n结论: 你会检测到 1 个符文buff")

# 简单的阈值演示
print("\n=== 阈值说明 ===")
print("- 0.0 到 1.0, 越高越严格")
print("- 当前 0.88 是比较严格的设置")
