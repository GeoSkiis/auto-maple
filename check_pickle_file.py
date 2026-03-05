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

# 读取文件的前几个字节，检查是否是有效的pickle文件
try:
    with open(layout_path, 'rb') as f:
        header = f.read(10)
    print(f"文件前10个字节: {header}")
    
    # 检查是否是有效的pickle文件头
    # pickle文件通常以\x80\x03开头（Python 3）
    if header.startswith(b'\x80\x03'):
        print("这是一个有效的Python 3 pickle文件")
    else:
        print("这不是一个有效的Python 3 pickle文件")
        
    # 尝试读取文件的更多内容，看看是否有明显的问题
    with open(layout_path, 'rb') as f:
        content = f.read(100)
    print(f"文件前100个字节: {content}")
    
except Exception as e:
    print(f"读取文件失败: {str(e)}")
