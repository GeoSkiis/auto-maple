# Auto Maple 项目 README 中文翻译

<h1 align="center">
  Auto Maple
</h1>

Auto Maple 是一个智能 Python AI，用于玩《冒险岛》（一款 2D 横向卷轴 MMORPG），它使用模拟按键、TensorFlow 机器学习、OpenCV 模板匹配和其他计算机视觉技术。

社区创建的资源，如每个职业的**命令书**和每个地图的**例程**，可以在**[资源仓库](https://github.com/liuzeyv123/auto-maple-resources)**中找到。

<br>

<h2 align="center">
  小地图
</h2>

<table align="center" border="0">
  <tr>
    <td>
Auto Maple 使用 <b>OpenCV 模板匹配</b> 来确定小地图的边界以及其中的各种元素，使其能够准确跟踪玩家在游戏中的位置。如果 <code>record_layout</code> 设置为 <code>True</code>，Auto Maple 将在基于 <b>四叉树</b> 的 Layout 对象中记录玩家之前的位置，该对象会定期保存到 "layouts" 目录中的文件中。每次加载新例程时，其对应的布局文件（如果存在）也会被加载。这个 Layout 对象使用其存储点上的 <b>A* 搜索算法</b> 来计算从玩家到任何目标位置的最短路径，这可以显著提高例程执行的准确性和速度。
    </td>
    <td align="center" width="400px">
      <img align="center" src="https://user-images.githubusercontent.com/69165598/123177212-b16f0700-d439-11eb-8a21-8b414273f1e1.gif"/>
    </td>
  </tr>
</table>

<br>

<h2 align="center">
  命令书
</h2>

<p align="center">
  <img src="https://user-images.githubusercontent.com/69165598/123372905-502e5d00-d539-11eb-81c2-46b8bbf929cc.gif" width="100%"/>
  <br>
  <sub>
    上面的视频显示 Auto Maple 一致执行机械高级能力组合。
  </sub>
</p>
  
<table align="center" border="0">
  <tr>
    <td width="100%">
Auto Maple 采用模块化设计，只要提供游戏内动作列表或"命令书"，就可以操作游戏中的任何角色。命令书是一个 Python 文件，包含多个类，每个类对应一个游戏内能力，告诉程序应该按哪些键以及何时按这些键。导入命令书后，其类会自动编译成一个字典，Auto Maple 可以使用该字典来解释例程中的命令。命令可以访问 Auto Maple 的所有全局变量，这使它们能够根据玩家的位置和游戏状态主动改变行为。
    </td>
  </tr>
</table>
  
<br>

<h2 align="center">
  例程
</h2>

<table align="center" border="0">
  <tr>
    <td width="350px">
      <p align="center">
        <img src="https://user-images.githubusercontent.com/69165598/150469699-d8a94ab4-7d70-49c3-8736-a9018996f39a.png"/>
        <br>
        <sub>
          点击 <a href="https://github.com/liuzeyv123/auto-maple/blob/f13d87c98e9344e0a4fa5c6f85ffb7e66860afc0/routines/dcup2.csv">这里</a> 查看整个例程。
        </sub>
      </p>
    </td>
    <td>
例程是用户创建的 CSV 文件，告诉 Auto Maple 在哪里移动以及在每个位置使用什么命令。Auto Maple 中的自定义编译器会解析选定的例程，并将其转换为可由程序执行的 <code>Component</code> 对象列表。对于包含无效参数的每一行，会打印错误消息，并且这些行在转换过程中会被忽略。 
<br><br>
以下是最常用的例程组件摘要：
<ul>
  <li>
    <b><code>Point</code></b> 存储直接在其下方的命令，并在角色位于指定位置的 <code>move_tolerance</code> 范围内时按该顺序执行这些命令。还有几个可选的关键字参数：
    <ul>
      <li>
        <code>adjust</code> 在执行任何命令之前，将角色的位置微调至目标位置的 <code>adjust_tolerance</code> 范围内。
      </li>
      <li>
        <code>frequency</code> 告诉 Point 执行的频率。如果设置为 N，此 Point 将每 N 次迭代执行一次。
      </li>
      <li>
        <code>skip</code> 告诉 Point 是否在第一次迭代时运行。如果设置为 True 且 frequency 为 N，此 Point 将在第 N-1 次迭代时执行。
      </li>
    </ul>
  </li>
  <li>
    <b><code>Label</code></b> 充当参考点，可以帮助将例程组织成部分并创建循环。
  </li>
  <li>
    <b><code>Jump</code></b> 从例程中的任何位置跳转到给定标签。
  </li>
  <li>
    <b><code>Setting</code></b> 将指定设置更新为给定值。它可以放在例程中的任何位置，因此同一例程的不同部分可以有不同的设置。所有可编辑设置可以在 <a href="https://github.com/liuzeyv123/auto-maple/blob/v2/settings.py">settings.py</a> 的底部找到。
  </li>
</ul>
    </td>
  </tr>
</table>

<br>

<h2 align="center">
  符文
</h2>

<p align="center">
  <img src="https://user-images.githubusercontent.com/69165598/123479558-f61fad00-d5b5-11eb-914c-8f002a96dd62.gif" width="100%"/>
</p>

<table align="center" border="0">
  <tr>
    <td width="100%">
Auto Maple 能够使用专有的在线符文求解器 API 自动解决"符文"或游戏内箭头键谜题。请参阅下面的设置部分，了解如何注册。
    </td>
  </tr>
</table>


<br>

<h2 align="center">
  视频演示
</h2>

<p align="center">
  <a href="https://youtu.be/iNj1CWW2--8?si=MA4n6EAHokI9FX8B"><b>点击下方观看完整视频</b></a>
</p>

<p align="center">
  <a href="https://youtu.be/iNj1CWW2--8?si=MA4n6EAHokI9FX8B">
    <img src="https://user-images.githubusercontent.com/69165598/123308656-c5b61100-d4d8-11eb-99ac-c465665474b5.gif" width="600px"/>
  </a>
</p>

<br>




<h2 align="center">
  设置
</h2>

<ol>
  <li>
    在 <a href="https://rapidapi.com/">RapidAPI</a> 上创建一个账户并获取您的 RapidAPI 密钥。然后转到 <a href="https://rapidapi.com/ge0403p/api/rune-solver">符文求解器 API</a> 页面并订阅 <b>免费套餐</b>（自动符文求解所需）。
  </li>
  <li>
    下载并安装 <a href="https://git-scm.com/download/win">Git</a>。
    <pre><code>winget install -e --id Git.Git</code></pre>
  </li>
  <li>
    下载并安装 <a href="https://www.python.org/downloads/">Python3</a>（3.12 最佳）。
    <pre><code>winget install -e --id Python.Python.3.12</code></pre>
  </li>
  <li>
    （可选）安装 <a href="https://github.com/UB-Mannheim/tesseract/wiki">Tesseract OCR</a>，用于使用自动例程时的自动地图检测。没有它，机器人仍然可以使用实时小地图或手动选择的地图运行。
    <pre><code>winget install -e UB-Mannheim.TesseractOCR</code></pre>
  </li>
  <li>
    下载并解压最新的 <a href="https://github.com/liuzeyv123/auto-maple/releases">Auto Maple 发布版</a>。
    <pre><code>git clone https://github.com/liuzeyv123/auto-maple</code></pre>
  </li>
  <li>
    在 Auto Maple 的主目录中，从 <code>.env.example</code> 创建一个 <code>.env</code> 文件，并填写您的 RapidAPI 详细信息（来自 <a href="https://rapidapi.com/ge0403p/api/rune-solver">符文求解器 API</a> 页面的 API URL 和代理密钥）。
    <pre><code>copy env.example .env</code></pre>
  </li>
  <li>
    在 Auto Maple 的主目录内，打开命令提示符并运行：
    <pre><code>pip install -r requirements.txt</code></pre>
  </li>
  <li>
    最后，通过运行创建桌面快捷方式：
    <pre><code>python setup.py --stay</code></pre>
    此快捷方式使用绝对路径，因此您可以随意移动它。但是，如果您移动 Auto Maple 的主目录，则需要再次运行 <code>python setup.py</code> 来生成新的快捷方式。要在 Auto Maple 关闭后保持命令提示符打开，请使用 <code>--stay</code> 标志运行上述命令。
  </li>
</ol>

<p>
  1.您的命令书、例程（包括自动例程）和小地图选择会自动保存。当您关闭并重新打开 Auto Maple 时，您之前的选择已经加载 - 无需再次选择它们。
</p>
<p>
  2.在UI界面可以设置手动添加layout的路径点（默认按键F9），删除最近的路径点（默认按键F10）但请谨慎使用
</p>
