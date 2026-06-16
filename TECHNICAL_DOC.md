# GIF 编解码引擎 - 完整技术说明

## 目录
1. [项目结构](#项目结构)
2. [GIF 文件格式概览](#gif-文件格式概览)
3. [全局与局部调色板的作用机制](#全局与局部调色板的作用机制)
4. [LZW 压缩算法详解](#lzw-压缩算法详解)
5. [图形控制扩展（延迟、透明色、处置方法）](#图形控制扩展延迟透明色处置方法)
6. [帧处置方法对渲染的影响](#帧处置方法对渲染的影响)
7. [颜色量化算法（Median Cut）](#颜色量化算法median-cut)
8. [隔行存储的处理](#隔行存储的处理)
9. [使用示例](#使用示例)

---

## 项目结构

```
gif_engine/
├── __init__.py          # 公开接口
├── structures.py        # 数据结构定义（文件头、调色板、帧等）
├── lzw.py               # LZW 编解码器
├── quantizer.py         # 颜色量化 + 隔行处理
├── decoder.py           # GIF 文件解析器
├── encoder.py           # GIF 文件生成器
└── renderer.py          # 动画帧渲染器
```

核心模块引用：
- [structures.py](file:///d:/trae-bz/TraeProjects/8204/gif_engine/structures.py)
- [lzw.py](file:///d:/trae-bz/TraeProjects/8204/gif_engine/lzw.py)
- [decoder.py](file:///d:/trae-bz/TraeProjects/8204/gif_engine/decoder.py)
- [encoder.py](file:///d:/trae-bz/TraeProjects/8204/gif_engine/encoder.py)
- [renderer.py](file:///d:/trae-bz/TraeProjects/8204/gif_engine/renderer.py)
- [quantizer.py](file:///d:/trae-bz/TraeProjects/8204/gif_engine/quantizer.py)

---

## GIF 文件格式概览

GIF (Graphics Interchange Format) 是一种基于块的二进制格式。完整文件结构如下：

```
+---------------------------+
|      GIF Signature        | 6 bytes: "GIF87a" 或 "GIF89a"
+---------------------------+
|  Logical Screen Descriptor| 7 bytes: 画布尺寸/颜色配置
+---------------------------+
|    Global Color Table     | 可选: 3 * 2^(N+1) bytes
+---------------------------+
|                           |
|   Data Blocks (循环)      | 扩展块 & 图像帧块交替出现
|                           |
+---------------------------+
|        Trailer            | 1 byte: 0x3B (文件结束符)
+---------------------------+
```

**数据块类型**：

| 引入字节 | 名称 | 说明 |
|---------|------|------|
| `0x21` | Extension Introducer | 扩展块标记，后跟标签字节 |
| `0x2C` | Image Separator | 图像帧标记 |
| `0x3B` | Trailer | 文件结束 |

**扩展块标签**：

| 标签 | 名称 | 作用 |
|------|------|------|
| `0xF9` | Graphic Control | 指定帧延迟、透明色、处置方法 |
| `0xFF` | Application | 应用扩展（如 NETSCAPE 循环计数） |
| `0xFE` | Comment | 注释文本 |
| `0x01` | Plain Text | 纯文本渲染（很少用） |

定义位置：
- 常量定义在 [decoder.py#L10-L17](file:///d:/trae-bz/TraeProjects/8204/gif_engine/decoder.py#L10-L17)
- 解析主循环在 [decoder.py#L54-L82](file:///d:/trae-bz/TraeProjects/8204/gif_engine/decoder.py#L54-L82)

---

## 全局与局部调色板的作用机制

GIF 使用索引色模型：每个像素不直接存储 RGB 值，而是存储一个**索引**，通过索引查表获得实际颜色。这个查找表就是调色板（Color Table）。

### 两种调色板

#### 1. 全局调色板 (Global Color Table)
- 存储位置：紧跟在 Logical Screen Descriptor 之后
- 作用范围：整个 GIF 文件中所有帧默认使用
- 启用标志：`LogicalScreenDescriptor.packed & 0x80 != 0`
- 大小计算：`2 ^ (global_color_table_size + 1)` 个条目，每个 3 字节 (RGB)
  - size_code=0 → 2 色
  - size_code=1 → 4 色
  - ...
  - size_code=7 → 256 色

#### 2. 局部调色板 (Local Color Table)
- 存储位置：每个 Image Descriptor 之后
- 作用范围：仅当前一帧
- 优先级：**高于全局调色板**（如果帧有局部调色板，就用局部的，否则用全局的）
- 启用标志：`ImageDescriptor.packed & 0x80 != 0`

### 作用优先级伪代码

```python
def get_effective_color_table(gif, frame_index):
    frame = gif.frames[frame_index]
    if frame.local_color_table is not None:
        return frame.local_color_table   # 局部优先
    if gif.global_color_table is not None:
        return gif.global_color_table    # 回退到全局
    raise ValueError("No color table!")
```

实现代码：
- [GIFImage.get_effective_color_table](file:///d:/trae-bz/TraeProjects/8204/gif_engine/structures.py#L312-L319)

### 典型使用场景
- **全局调色板**：所有帧共享一套颜色（如卡通动画、图标），节省空间
- **局部调色板**：某帧颜色差异很大（如照片过渡帧），单独分配调色板提升质量

### 背景色
`LogicalScreenDescriptor.background_color_index` 是全局调色板中的一个索引，指定画布初始填充色（透明通道通常不渲染，由解码器/渲染器决定）。

---

## LZW 压缩算法详解

GIF 使用 **LZW (Lempel-Ziv-Welch)** 压缩算法对像素索引序列进行压缩。这是一种无损的字典编码算法。

### 与通用 LZW 的关键差异

GIF LZW 在标准 LZW 基础上增加了三个特殊机制：

#### 1. 清除码 (Clear Code)
- 值为 `2 ^ min_code_size`
- **作用**：重置字典，从空状态重新开始构建
- **何时发送**：
  - 数据流最开头（强制首条）
  - 字典满 4096 条目后
  - 编码器认为重置更有利时
- **解码时**：收到清除码必须丢弃当前字典，重新初始化

#### 2. 信息结束码 (End of Information)
- 值为 `clear_code + 1`
- **作用**：标记图像数据结束
- 必须是最后一条码

#### 3. 动态位宽增长 (Variable-Length Codes)
GIF LZW 的码字长度不是固定的，而是根据字典大小动态增长：

| 阶段 | code_size | 可表示范围 |
|------|-----------|-----------|
| 初始 | min_code_size + 1 | 0 ~ 2^(min_code_size+1) - 1 |
| 字典条目数达到 2^code_size | code_size += 1 | 范围翻倍 |
| 上限 | 最多 12 bits | 0 ~ 4095 |

**增长触发条件**（编码器与解码器必须完全同步）：
> 每当添加一个新字典条目使 `num_elems == 2 ^ code_size` 时，**在写入/读取下一个码字之前**，将 code_size 加 1

这个判断条件是 LZW 实现中最容易出错的地方：
- **错误**：`next_code > max_code` 判断导致增长时机错位
- **正确**：`num_elems == (1 << code_size)` 在处理下一个码之前检查

### 编码流程详解

参见 [lzw.py#L119-L181](file:///d:/trae-bz/TraeProjects/8204/gif_engine/lzw.py#L119-L181)

```
输入: 像素索引序列 [P1, P2, P3, ..., Pn]
参数: min_code_size (与调色板大小匹配)

1. 初始化
   clear_code = 1 << min_code_size
   eoi_code   = clear_code + 1
   code_size  = min_code_size + 1
   num_elems  = eoi_code + 1
   字典 dict   = {(i,): i for i in range(clear_code)}
   写入 clear_code

2. current = (P1,)

3. 对每个后续像素 Pi (i from 2 to n):
   a. extended = current + (Pi,)
   b. 如果 extended 在 dict 中:
          current = extended    # 继续匹配更长序列
      否则:
          写入 dict[current]    # 输出当前匹配的码字
          如果 num_elems < 4096:
              dict[extended] = num_elems
              num_elems += 1
              # 位宽增长检查
              if num_elems == (1 << code_size) and code_size < 12:
                  code_size += 1
          如果 num_elems >= 4096:
              写入 clear_code
              重置字典和码长
          current = (Pi,)

4. 写入 dict[current]     # 输出最后一段
5. 写入 eoi_code           # 结束标记
```

### 解码流程详解

参见 [lzw.py#L16-L94](file:///d:/trae-bz/TraeProjects/8204/gif_engine/lzw.py#L16-L94)

解码是编码的逆过程，但有一个著名的 **KwKwK 问题**（也叫 BMP 问题）：
> 当收到的码字 `code == num_elems`（即这个条目还没被添加到字典）时，该如何解码？

**答案**：这是编码器恰好编码了 `W + W[0]` 形式的序列，因此解码器可以推导出：
```python
in_string = dict[old_code] + [dict[old_code][0]]
```

```
1. 初始化（与编码器相同）
2. 读取第一个码，如果是 clear_code 则重置后再读
3. old_code = 第一个有效码
   输出 dict[old_code]
   c = dict[old_code][0]

4. 循环读取每个后续码 code:
   a. 如果 code == clear_code: 重置字典，读取下一个码作为新的 old_code，continue
   b. 如果 code == eoi_code: 结束
   c. 解码 in_string:
      - 如果 code < num_elems: in_string = dict[code]
      - 如果 code == num_elems: in_string = dict[old_code] + [c]  (KwKwK 规则)
   d. 输出 in_string
   e. c = in_string[0]
   f. 如果 num_elems < 4096:
        dict[num_elems] = dict[old_code] + [c]
        num_elems += 1
        if num_elems == (1 << code_size) and code_size < 12:
            code_size += 1    # 与编码器同步增长
   g. old_code = code
```

### LZW 最小码长 (min_code_size) 与调色板的关系
- 调色板有 N 个颜色，索引范围是 0 ~ N-1
- `min_code_size` 必须满足 `2^min_code_size >= N`
  - 2 色 → min_code_size = 1？**不！GIF 规范强制 min_code_size ≥ 2**
  - 所以 2-4 色 → min_code_size = 2 (clear_code=4)
  - 5-8 色 → min_code_size = 3 (clear_code=8)
  - ...
  - 129-256 色 → min_code_size = 8 (clear_code=256)

实现代码参见 [ColorTable.size_code](file:///d:/trae-bz/TraeProjects/8204/gif_engine/structures.py#L97-L105) 和编码器 [encoder.py](file:///d:/trae-bz/TraeProjects/8204/gif_engine/encoder.py) 中的 `lzw_min_code_size` 计算。

---

## 图形控制扩展（延迟、透明色、处置方法）

Graphic Control Extension (GCE) 是 GIF89a 引入的扩展块，**必须紧挨着位于它所作用的图像帧之前**。

结构 (参见 [structures.py#L87-L121](file:///d:/trae-bz/TraeProjects/8204/gif_engine/structures.py#L87-L121))：

```
字节 0: Packed Fields
  Bit 0   : Transparent Color Flag (透明色标志)
  Bit 1   : User Input Flag (用户输入，很少用)
  Bit 2-4 : Disposal Method (处置方法, 0-7)
  Bit 5-7 : Reserved (保留, 0)

字节 1-2: Delay Time (延迟时间)
  - 单位: 1/100 秒，即 10ms 为一个单位
  - 值为 0 时，解码器通常默认 100ms 或立即显示下一帧
  - delay_ms = delay_time * 10

字节 3: Transparent Color Index (透明色索引)
  - 仅当透明色标志为 1 时有效
  - 解码时，像素索引等于此值的位置不覆盖画布
```

### 解析位置
- 解析器在 [decoder.py#L75-L78](file:///d:/trae-bz/TraeProjects/8204/gif_engine/decoder.py#L75-L78) 检测 GCE 并保存到 `pending_gce`
- 在下一个图像帧到来时，把 `pending_gce` 绑定到该帧
- 这保证了 GCE 和帧的对应关系

---

## 帧处置方法对渲染的影响

处置方法 (Disposal Method) 决定了**在显示完当前帧之后、显示下一帧之前，画布应该如何处理**。

### 四种标准处置方法

| 值 | 名称 | 行为 | 渲染时序 |
|----|------|------|---------|
| 0 | No Specification / No Action | 不做任何处理 | 直接叠加下一帧 |
| 1 | Do Not Dispose | 保留当前帧内容 | 保留当前帧内容作为下一帧的基底 |
| 2 | Restore to Background | 把当前帧覆盖的区域恢复为背景色 | 先擦除当前帧区域 → 再叠加下一帧 |
| 3 | Restore to Previous | 恢复到渲染当前帧**之前**的画布状态 | 回退画布 → 再叠加下一帧 |
| 4-7 | Reserved | 未定义行为 | 通常按 0 处理 |

### 渲染时序图解

假设：
- 帧 A (使用处置方法 X)
- 帧 B (待渲染)

流程：
```
时间线:  → 显示帧 A → [执行 A 的处置方法] → 渲染帧 B → 显示帧 B → ...
```

具体代码参见 [renderer.py#L68-L97](file:///d:/trae-bz/TraeProjects/8204/gif_engine/renderer.py#L68-L97) 和 [_dispose_previous_frame](file:///d:/trae-bz/TraeProjects/8204/gif_engine/renderer.py#L68-L83)：

```python
def render_frame(self, frame_idx):
    frame = self.gif.frames[frame_idx]

    # Step 1: 执行上一帧的处置方法
    if frame_idx > 0:
        prev_frame = self.gif.frames[frame_idx - 1]
        if prev_frame.disposal_method == RESTORE_TO_BACKGROUND:
            self._clear_frame_area(prev_frame)     # 擦除上一帧区域
        elif prev_frame.disposal_method == RESTORE_TO_PREVIOUS:
            pass   # 在渲染上一帧之前已经保存过画布

    # Step 2: 如果当前帧需要回退，先保存画布
    if frame.disposal_method == RESTORE_TO_PREVIOUS:
        self._save_canvas()    # 快照保存

    # Step 3: 渲染当前帧（不画透明像素）
    self._render_frame_to_canvas(frame)

    return RenderedFrame(self._canvas, delay_ms=frame.delay_time * 10)
```

### 处置方法使用建议

| 场景 | 推荐处置方法 | 原因 |
|------|-------------|------|
| 帧之间完全独立（如幻灯片） | 2 (Restore BG) | 每帧都从干净背景开始 |
| 帧逐步叠加（如绘画动画） | 1 (Do Not Dispose) | 累积前帧内容 |
| 需要临时覆盖某区域 | 3 (Restore Previous) | 动画消失后恢复原状 |
| 不确定 | 0 或 1 | 兼容性最好 |

---

## 颜色量化算法（Median Cut）

GIF 最多只能有 256 色调色板。对于 24 位真彩图像（1600 万色），需要通过**颜色量化**将颜色数缩减到 ≤ 256。

本引擎实现了 **Median Cut（中位切分）** 算法，参见 [quantizer.py#L53-L153](file:///d:/trae-bz/TraeProjects/8204/gif_engine/quantizer.py#L53-L153)。

### Median Cut 算法步骤

```
输入: RGB 像素列表 P，目标颜色数 K (K ≤ 256)
输出: 调色板 pal[0..K-1]，每个像素对应索引

1. 去重：将 P 中的唯一颜色放入列表 U
2. 如果 |U| ≤ K：直接返回 U 作为调色板，映射索引
3. 初始：创建颜色盒 Box0，包含 U 中所有颜色；Boxes = [Box0]

4. 循环直到 |Boxes| == K:
   a. 选择 Boxes 中 (体积 * 颜色数) 最大的盒子
   b. 如果所有盒子都只有 1 个颜色，无法继续切分，break
   c. 找出该盒子的 R/G/B 中范围最大的维度 dim
   d. 按 dim 维度排序盒子中的颜色
   e. 在中位数位置切分，得到左、右两个子盒
   f. 从 Boxes 中移除原盒子，加入两个子盒

5. 对每个盒子取其中所有颜色的平均值，作为该盒子代表色 → 调色板
6. 对每个原始像素，在调色板中找到最接近的颜色 → 索引映射
```

### 透明色处理

当输入图像带有 Alpha 通道时（RGBA）：
1. 分离出不透明像素 (alpha ≥ 128) 和透明像素 (alpha < 128)
2. 对不透明像素执行 Median Cut，但只分配 K-1 种颜色（预留 1 个给透明）
3. 在调色板第 0 位插入占位色
4. 透明像素都映射到索引 0，并设置 GCE 透明色标志 + 索引

参见 [quantize_image](file:///d:/trae-bz/TraeProjects/8204/gif_engine/quantizer.py#L156-L209)。

### 最近色查找

```python
def _find_nearest_color(color, palette):
    best_idx = 0
    best_dist = INF
    for i in range(len(palette)):
        dist = (color[0]-palette[i][0])² + (color[1]-palette[i][1])² + (color[2]-palette[i][2])²
        if dist < best_dist:
            best_dist = dist
            best_idx = i
    return best_idx
```

这是标准的欧氏距离。更高级的实现会用感知均匀的 Lab 色彩空间或八叉树索引加速，但简化版实现已足够。

### 调色板大小对齐

GIF 规范要求调色板条目数必须是 2 的幂（2, 4, 8, ..., 256）：
```python
def pad_to_power_of_two(self):
    target = 1
    while target < len(self.colors):
        target *= 2
    while len(self.colors) < target:
        self.colors.append((0, 0, 0))    # 用黑色填充
```

参见 [ColorTable.pad_to_power_of_two](file:///d:/trae-bz/TraeProjects/8204/gif_engine/structures.py#L87-L94)。

---

## 隔行存储的处理

GIF 支持**隔行扫描 (Interlace)**，即将图像行按四次扫描传递，允许解码器在网络传输中"渐进式"显示图像。

### 四次扫描模式

| 扫描次 | 起始行 | 行步长 | 例子 (h=16) 覆盖的行号 |
|-------|-------|-------|---------------------|
| Pass 1 | 0 | 8 | 0, 8 |
| Pass 2 | 4 | 8 | 4, 12 |
| Pass 3 | 2 | 4 | 2, 6, 10, 14 |
| Pass 4 | 1 | 2 | 1, 3, 5, 7, 9, 11, 13, 15 |

**存储顺序**：把四次扫描的行按顺序连起来存储。所以 LZW 解压后得到的像素是乱序的，需要重排。

### 去隔行（解码时）
参见 [deinterlace_indices](file:///d:/trae-bz/TraeProjects/8204/gif_engine/quantizer.py#L212-L238)：

```python
def deinterlace_indices(interlaced, w, h):
    result = [0] * (w * h)
    src_row = 0
    for start, step in [(0,8), (4,8), (2,4), (1,2)]:
        for dst_row in range(start, h, step):
            result[dst_row*w : (dst_row+1)*w] = interlaced[src_row*w : (src_row+1)*w]
            src_row += 1
    return result
```

### 加隔行（编码时）
参见 [interlace_indices](file:///d:/trae-bz/TraeProjects/8204/gif_engine/quantizer.py#L241-L263)，是去隔行的逆过程。

### 何时使用隔行？
- **适合**：大尺寸图像在慢网络上传输，用户能看到轮廓
- **不适合**：小尺寸图像（反而略微增加 LZW 压缩后大小，因为行相关性降低了）

---

## 使用示例

### 例 1：解码 GIF 并渲染所有帧

```python
from gif_engine import GIFDecoder, GIFRenderer

gif = GIFDecoder.from_file("animation.gif")
print(f"尺寸: {gif.width}x{gif.height}, 帧数: {len(gif.frames)}")
print(f"循环次数: {gif.loop_count if gif.loop_count is not None else '单次'}")

renderer = GIFRenderer(gif)
for idx, rendered in enumerate(renderer.render_all_frames()):
    frame = gif.frames[idx]
    print(f"帧 {idx}: 延迟 {rendered.delay_ms}ms, "
          f"尺寸 {frame.width}x{frame.height}+{frame.left}+{frame.top}")
    # rendered.rgba_data 是 width*height 个 (R,G,B,A) 元组
```

### 例 2：编码生成动画 GIF

```python
from gif_engine import GIFEncoder, DisposalMethod
import math

W, H = 100, 100
N = 20

encoder = GIFEncoder(width=W, height=H, loop_count=0)  # 0 = 无限循环

for i in range(N):
    t = i / N
    cx = int(W/2 + 30 * math.cos(t * 2*math.pi))
    cy = int(H/2 + 30 * math.sin(t * 2*math.pi))

    pixels = []
    for y in range(H):
        for x in range(W):
            dx, dy = x - cx, y - cy
            if dx*dx + dy*dy <= 15*15:
                shade = 255 - (dx*dx + dy*dy) * 255 // (15*15)
                pixels.append((shade, 50, 200, 255))
            else:
                pixels.append((20, 20, 40, 255))

    encoder.add_frame(
        pixels,
        delay_ms=50,
        disposal_method=DisposalMethod.RESTORE_TO_BACKGROUND,
        max_colors=64,
    )

encoder.save("circle_animation.gif")
print(f"已生成: {os.path.getsize('circle_animation.gif')} bytes")
```

### 例 3：纯数据结构构建 GIF（绕过高层 API）

```python
from gif_engine.structures import *
from gif_engine.encoder import GIFEncoder

# 构造调色板
palette = ColorTable(colors=[(0,0,0),(255,0,0),(0,255,0),(0,0,255)])
palette.pad_to_power_of_two()

# 构造帧数据
indices = [i % 4 for i in range(16*16)]

gce = GraphicControlExtension(
    disposal_method=DisposalMethod.DO_NOT_DISPOSE,
    delay_time=5,                         # 50ms
    transparent_color_flag=False,
)

desc = ImageDescriptor(left=0, top=0, width=16, height=16)
frame = GIFFrame(
    image_descriptor=desc,
    pixel_indices=indices,
    graphic_control_extension=gce,
)

gif = GIFImage()
gif.signature = GIFSignature(version="89a")
gif.logical_screen = LogicalScreenDescriptor(
    width=16, height=16,
    global_color_table_flag=True,
    global_color_table_size=palette.size_code,
)
gif.global_color_table = palette
gif.frames = [frame]

# 直接编码
bytes_data = GIFEncoder.from_gif_image(gif)
with open("raw.gif", "wb") as f:
    f.write(bytes_data)

# 验证往返
decoded = GIFDecoder.from_bytes(bytes_data)
assert decoded.frames[0].pixel_indices == indices
```

---

## 测试验证

运行测试套件：

```bash
python tests/test_gif_engine.py
```

测试覆盖：
- LZW 编解码往返一致性（2/3/4/8 bit 最小码长）
- Median Cut 颜色量化
- 隔行扫描往返
- 简单 GIF 编码 → 解码 → 渲染
- 透明色 + 处置方法动画
- 帧数据结构往返一致性（含 GCE、NETSCAPE 循环扩展）
- 处置方法渲染正确性

生成的测试文件位于项目根目录：
- `test_simple.gif`（32×32 彩虹渐变动画，5 帧）
- `test_transparent.gif`（120×80 透明圆在棋盘背景上运动，8 帧）

---

## 关键技术总结

| 技术点 | 核心机制 | 易错细节 |
|-------|---------|---------|
| 全局/局部调色板 | 帧级调色板优先级 > 文件级 | 没有全局也没有局部 → 错误 |
| LZW 清除码 | 字典满 4096 或起始时 | 清除后 next_code 必须重置 |
| LZW 位宽增长 | `num_elems == 2^code_size` 时 | 编解码判断条件必须完全等价 |
| KwKwK 解码 | `code == next_code` 时 | 用 prev 首字符 + prev 推导 |
| GCE 延迟 | 单位 10ms | 0 值替换为默认 100ms |
| 处置方法 2 | 只擦除帧覆盖的矩形区域 | 不是整个画布 |
| 处置方法 3 | 渲染前保存画布快照 | 不是保存当前帧像素 |
| 透明色 | 不写该像素到画布 | Alpha=0 不等同于透明索引 |
| Median Cut | 按最长维度中位数切分 | 盒子体积 * 数目选切分对象 |
| 隔行扫描 | 四次 pass: 0/8, 4/8, 2/4, 1/2 | LZW 解压后需重排行顺序 |
