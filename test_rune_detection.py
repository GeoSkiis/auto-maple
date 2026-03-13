import cv2
import sys
sys.path.append('.')
from src.common.utils import multi_match_color

# 加载模板
template = cv2.imread('assets/rune_buff_template.jpg', 1)
if template is None:
    print("无法加载模板图片 assets/rune_buff_template.jpg")
    exit()

print(f"模板尺寸: {template.shape}")

# 加载用户提供的截图
screenshot = cv2.imread('user_screenshot.png', 1)
if screenshot is None:
    print("无法加载用户截图 user_screenshot.png")
    exit()

print(f"截图尺寸: {screenshot.shape}")

# 使用与代码相同的阈值进行检测
print("\n开始检测...")
results = multi_match_color(screenshot, template, threshold=0.88)

print(f"\n检测结果:")
print(f"找到 {len(results)} 个匹配项")

if results:
    for i, pos in enumerate(results):
        print(f"  匹配 {i+1}: 位置 {pos}")

