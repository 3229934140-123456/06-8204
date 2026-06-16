import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gif_engine import (
    GIFDecoder,
    GIFEncoder,
    GIFRenderer,
    DisposalMethod,
    lzw_encode,
    lzw_decode,
)
from gif_engine.quantizer import (
    median_cut_quantize,
    interlace_indices,
    deinterlace_indices,
)


def generate_rainbow_frame(width: int, height: int, offset: int = 0):
    pixels = []
    for y in range(height):
        for x in range(width):
            r = (x + offset) % 256
            g = (y + offset * 2) % 256
            b = (x + y + offset) % 256
            pixels.append((r, g, b, 255))
    return pixels


def generate_moving_square_frames(width: int, height: int, num_frames: int = 10):
    frames = []
    square_size = 30
    bg = (30, 30, 60, 255)
    for i in range(num_frames):
        pixels = [bg] * (width * height)
        cx = (width - square_size) * i // max(1, num_frames - 1)
        cy = (height - square_size) * (num_frames - 1 - i) // max(1, num_frames - 1)
        for sy in range(square_size):
            for sx in range(square_size):
                px = cx + sx
                py = cy + sy
                if 0 <= px < width and 0 <= py < height:
                    r = 255 * sx // square_size
                    g = 255 * sy // square_size
                    b = 128
                    pixels[py * width + px] = (r, g, b, 255)
        frames.append(pixels)
    return frames


def generate_transparent_circle_frames(width: int, height: int, num_frames: int = 8):
    frames = []
    cx0, cy0 = width // 4, height // 2
    cx1, cy1 = 3 * width // 4, height // 2
    radius = 20
    for i in range(num_frames):
        t = i / num_frames
        cx = int(cx0 + (cx1 - cx0) * t)
        cy = int(cy0 + 30 * __import__("math").sin(t * 2 * 3.14159))
        pixels = [(0, 0, 0, 0)] * (width * height)
        for y in range(-radius, radius + 1):
            for x in range(-radius, radius + 1):
                if x * x + y * y <= radius * radius:
                    px = cx + x
                    py = cy + y
                    if 0 <= px < width and 0 <= py < height:
                        shade = int(255 * (1 - (x * x + y * y) / (radius * radius)))
                        pixels[py * width + px] = (255, shade, 50, 255)
        frames.append(pixels)
    return frames


def test_lzw_roundtrip():
    print("=== 测试 LZW 编解码 ===")
    data_2bit = [0, 1, 2, 3, 0, 1, 2, 3, 0, 0, 0, 1, 1, 1, 2, 2, 3, 3]
    for min_code_size in [2]:
        encoded = lzw_encode(data_2bit, min_code_size)
        decoded = lzw_decode(encoded, min_code_size, len(data_2bit))
        assert decoded == data_2bit, (
            f"LZW roundtrip failed for min_code_size={min_code_size}\n"
            f"Original: {data_2bit}\nDecoded: {decoded}"
        )
        print(f"  min_code_size={min_code_size}: OK ({len(encoded)} bytes)")

    data_3bit = [0, 1, 2, 3, 4, 5, 6, 7, 0, 1, 2, 3, 4, 5, 6, 7, 0, 0, 0, 1, 1, 1]
    for min_code_size in [3]:
        encoded = lzw_encode(data_3bit, min_code_size)
        decoded = lzw_decode(encoded, min_code_size, len(data_3bit))
        assert decoded == data_3bit, (
            f"LZW roundtrip failed for min_code_size={min_code_size}\n"
            f"Original: {data_3bit}\nDecoded: {decoded}"
        )
        print(f"  min_code_size={min_code_size}: OK ({len(encoded)} bytes)")

    data_4bit = list(range(16)) * 4
    for min_code_size in [4]:
        encoded = lzw_encode(data_4bit, min_code_size)
        decoded = lzw_decode(encoded, min_code_size, len(data_4bit))
        assert decoded == data_4bit, (
            f"LZW roundtrip failed for min_code_size={min_code_size}"
        )
        print(f"  min_code_size={min_code_size}: OK ({len(encoded)} bytes)")

    data_8bit = list(range(256)) * 2
    encoded = lzw_encode(data_8bit, 8)
    decoded = lzw_decode(encoded, 8, len(data_8bit))
    assert decoded == data_8bit, "LZW 8bit roundtrip failed"
    print(f"  min_code_size=8: OK ({len(encoded)} bytes)")

    longer = []
    for _ in range(100):
        longer.extend([i % 16 for i in range(64)])
    for mcs in [4, 5, 8]:
        enc = lzw_encode(longer, mcs)
        dec = lzw_decode(enc, mcs, len(longer))
        assert dec == longer, f"LZW long roundtrip failed for mcs={mcs}"
        print(f"  长序列 min_code_size={mcs}: OK ({len(enc)} bytes vs {len(longer)*1})")

    try:
        bad_data = [0, 1, 2, 3, 4]
        lzw_encode(bad_data, 2)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        print(f"  越界检查: OK - {e}")

    print("LZW 测试通过!\n")


def test_median_cut():
    print("=== 测试颜色量化 ===")
    import random

    random.seed(42)
    test_colors = []
    centers = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 255, 255)]
    for _ in range(1000):
        c = random.choice(centers)
        r = max(0, min(255, c[0] + random.randint(-10, 10)))
        g = max(0, min(255, c[1] + random.randint(-10, 10)))
        b = max(0, min(255, c[2] + random.randint(-10, 10)))
        test_colors.append((r, g, b))

    palette, indices = median_cut_quantize(test_colors, max_colors=8)
    assert len(palette) <= 8
    assert len(indices) == len(test_colors)
    assert all(0 <= i < len(palette) for i in indices)
    print(f"  生成调色板大小: {len(palette)}")
    print(f"  调色板: {palette[:5]}...")
    print("颜色量化测试通过!\n")


def test_interlace():
    print("=== 测试隔行扫描 ===")
    w, h = 4, 8
    normal = list(range(w * h))
    interlaced = interlace_indices(normal, w, h)
    restored = deinterlace_indices(interlaced, w, h)
    assert restored == normal, "隔行扫描往返失败"
    print(f"  4x8 矩阵: OK")

    w2, h2 = 10, 10
    normal2 = list(range(w2 * h2))
    interlaced2 = interlace_indices(normal2, w2, h2)
    restored2 = deinterlace_indices(interlaced2, w2, h2)
    assert restored2 == normal2
    print(f"  10x10 矩阵: OK")
    print("隔行扫描测试通过!\n")


def test_simple_gif_encode_decode():
    print("=== 测试简单 GIF 编码解码 ===")
    width, height = 32, 32

    encoder = GIFEncoder(width=width, height=height, loop_count=0)

    for i in range(5):
        frame = generate_rainbow_frame(width, height, offset=i * 20)
        encoder.add_frame(
            frame,
            delay_ms=200,
            disposal_method=DisposalMethod.DO_NOT_DISPOSE,
        )

    output_path = "test_simple.gif"
    encoder.save(output_path)
    print(f"  已生成: {output_path}")

    gif = GIFDecoder.from_file(output_path)
    print(f"  解析: 版本={gif.signature.version}, 帧={len(gif.frames)}")
    print(f"  尺寸: {gif.width}x{gif.height}")
    print(f"  循环次数: {gif.loop_count}")

    assert gif.width == width and gif.height == height
    assert len(gif.frames) == 5
    assert gif.loop_count == 0

    renderer = GIFRenderer(gif)
    frames = renderer.render_all_frames()
    assert len(frames) == 5
    for i, rf in enumerate(frames):
        assert rf.width == width and rf.height == height
        assert len(rf.rgba_data) == width * height
    print(f"  渲染 {len(frames)} 帧: OK")
    print("简单 GIF 测试通过!\n")


def test_transparent_animation():
    print("=== 测试透明色动画 ===")
    width, height = 120, 80
    num_frames = 8

    bg_pixels = [(50, 80, 120, 255)] * (width * height)
    for y in range(height):
        for x in range(width):
            if (x // 10 + y // 10) % 2 == 0:
                bg_pixels[y * width + x] = (60, 90, 130, 255)

    encoder = GIFEncoder(width=width, height=height, loop_count=0)
    bg_color_table, bg_indices, _ = __import__("gif_engine.quantizer", fromlist=["quantize_image"]).quantize_image(
        bg_pixels, max_colors=4
    )
    encoder.set_global_color_table(bg_color_table)

    circle_frames = generate_transparent_circle_frames(width, height, num_frames)
    for i, circle_frame in enumerate(circle_frames):
        combined = []
        for bg, fg in zip(bg_pixels, circle_frame):
            if fg[3] < 128:
                combined.append(bg)
            else:
                combined.append(fg)

        diff_pixels = []
        for bi, ci in zip(bg_indices, [0] * len(combined)):
            px = combined[len(diff_pixels)]
            if px[3] == 0:
                diff_pixels.append((0, 0, 0, 0))
            else:
                diff_pixels.append(px)

        encoder.add_frame(
            combined,
            delay_ms=100,
            disposal_method=DisposalMethod.RESTORE_TO_BACKGROUND,
            use_local_palette=True,
            max_colors=64,
        )

    output_path = "test_transparent.gif"
    encoder.save(output_path)
    print(f"  已生成: {output_path}")

    gif = GIFDecoder.from_file(output_path)
    assert len(gif.frames) == num_frames

    for fi, frame in enumerate(gif.frames):
        if fi == 0:
            continue
        assert frame.disposal_method == DisposalMethod.RESTORE_TO_BACKGROUND, (
            f"Frame {fi} disposal: {frame.disposal_method}"
        )

    renderer = GIFRenderer(gif)
    rendered = renderer.render_all_frames()
    assert len(rendered) == num_frames
    print(f"  渲染透明动画 {len(rendered)} 帧: OK")
    print("透明色动画测试通过!\n")


def test_roundtrip_frame_data():
    print("=== 测试帧数据往返一致性 ===")
    width, height = 16, 16

    original_indices = list(range(256)) * 1
    original_indices = (original_indices * ((width * height) // len(original_indices) + 1))[
        : width * height
    ]

    from gif_engine.structures import (
        GIFSignature,
        LogicalScreenDescriptor,
        ColorTable,
        ImageDescriptor,
        GIFFrame,
        GIFImage,
    )

    palette_colors = [(i, i, i) for i in range(256)]
    ct = ColorTable(colors=palette_colors)

    gif = GIFImage()
    gif.signature = GIFSignature()
    gif.logical_screen = LogicalScreenDescriptor(
        width=width,
        height=height,
        global_color_table_flag=True,
        color_resolution=7,
        global_color_table_size=ct.size_code,
    )
    gif.global_color_table = ct

    desc = ImageDescriptor(
        left=0, top=0, width=width, height=height,
        local_color_table_flag=False,
    )
    frame = GIFFrame(
        image_descriptor=desc,
        pixel_indices=original_indices,
    )
    gif.frames.append(frame)

    from gif_engine.encoder import GIFEncoder as Enc
    encoded_bytes = Enc.from_gif_image(gif)
    decoded_gif = GIFDecoder.from_bytes(encoded_bytes)

    decoded_indices = decoded_gif.frames[0].pixel_indices
    assert decoded_indices == original_indices, (
        f"帧数据不一致\n前16原: {original_indices[:16]}\n前16解: {decoded_indices[:16]}"
    )
    print("  帧数据往返: OK")

    from gif_engine.structures import GraphicControlExtension
    gce = GraphicControlExtension(
        disposal_method=DisposalMethod.RESTORE_TO_BACKGROUND,
        transparent_color_flag=True,
        delay_time=50,
        transparent_color_index=42,
    )
    gif2 = GIFImage()
    gif2.signature = GIFSignature(version="89a")
    gif2.logical_screen = LogicalScreenDescriptor(
        width=width, height=height,
        global_color_table_flag=True,
        global_color_table_size=ct.size_code,
    )
    gif2.global_color_table = ct

    loop_data = __import__("struct").pack("<BH", 1, 7)
    from gif_engine.structures import ApplicationExtension
    app_ext = ApplicationExtension(
        application_identifier="NETSCAPE",
        authentication_code=b"2.0",
        data=loop_data,
    )
    gif2.application_extensions.append(app_ext)

    desc2 = ImageDescriptor(left=0, top=0, width=width, height=height)
    frame2 = GIFFrame(
        image_descriptor=desc2,
        pixel_indices=original_indices,
        graphic_control_extension=gce,
    )
    gif2.frames.append(frame2)

    encoded2 = Enc.from_gif_image(gif2)
    decoded2 = GIFDecoder.from_bytes(encoded2)
    assert decoded2.loop_count == 7, f"loop_count={decoded2.loop_count}"
    f = decoded2.frames[0]
    assert f.delay_time == 50
    assert f.has_transparency == True
    assert f.transparent_index == 42
    assert f.disposal_method == DisposalMethod.RESTORE_TO_BACKGROUND
    print("  GCE + 循环扩展往返: OK")

    print("帧数据往返测试通过!\n")


def test_disposal_methods():
    print("=== 测试处置方法 ===")
    width, height = 20, 20
    from gif_engine.structures import (
        GIFSignature,
        LogicalScreenDescriptor,
        ColorTable,
        ImageDescriptor,
        GraphicControlExtension,
        GIFFrame,
        GIFImage,
    )
    from gif_engine.encoder import GIFEncoder as Enc

    palette = ColorTable(colors=[
        (0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255),
    ])
    palette.pad_to_power_of_two()

    gif = GIFImage()
    gif.signature = GIFSignature(version="89a")
    gif.logical_screen = LogicalScreenDescriptor(
        width=width, height=height,
        global_color_table_flag=True,
        global_color_table_size=palette.size_code,
        background_color_index=0,
    )
    gif.global_color_table = palette

    bg = [0] * (width * height)
    red_square = list(bg)
    for y in range(4, 12):
        for x in range(2, 10):
            red_square[y * width + x] = 1

    green_square = list(bg)
    for y in range(6, 14):
        for x in range(8, 16):
            green_square[y * width + x] = 2

    for idx, (data, disp) in enumerate([
        (red_square, DisposalMethod.DO_NOT_DISPOSE),
        (green_square, DisposalMethod.RESTORE_TO_BACKGROUND),
        (bg, DisposalMethod.NO_DISPOSAL),
    ]):
        gce = GraphicControlExtension(disposal_method=disp, delay_time=10)
        desc = ImageDescriptor(left=0, top=0, width=width, height=height)
        frame = GIFFrame(
            image_descriptor=desc,
            pixel_indices=data,
            graphic_control_extension=gce,
        )
        gif.frames.append(frame)

    encoded = Enc.from_gif_image(gif)
    decoded = GIFDecoder.from_bytes(encoded)
    renderer = GIFRenderer(decoded)
    r0 = renderer.render_frame(0)
    assert r0.rgba_data[8 * width + 6] == (255, 0, 0, 255), "Frame0 should have red"

    r1 = renderer.render_frame(1)
    assert r1.rgba_data[10 * width + 12] == (0, 255, 0, 255), "Frame1 should have green"
    print("  处置方法渲染: OK")

    print("处置方法测试通过!\n")


def test_edge_solid_1x1():
    print("=== 边界测试: 1x1 单色图 ===")
    colors = [
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
        (255, 255, 255, 255),
        (0, 0, 0, 255),
        (123, 45, 67, 255),
    ]
    for rgba in colors:
        encoder = GIFEncoder(width=1, height=1)
        encoder.add_frame([rgba], delay_ms=50)
        data = encoder.get_bytes()
        gif = GIFDecoder.from_bytes(data)
        assert gif.width == 1 and gif.height == 1, "尺寸错误"
        assert len(gif.frames) == 1, "帧数错误"
        renderer = GIFRenderer(gif)
        rf = renderer.render_frame(0)
        got = rf.rgba_data[0]
        assert got[:3] == rgba[:3], f"颜色不匹配: 预期 {rgba[:3]}, 得到 {got[:3]}"
        assert got[3] == 255, "不透明度错误"
    print(f"  {len(colors)} 种 1x1 单色往返: OK")

    print("1x1 单色图测试通过!\n")


def test_edge_fully_transparent():
    print("=== 边界测试: 整帧全透明 ===")
    for W, H in [(1, 1), (2, 2), (5, 3)]:
        pix = [(0, 0, 0, 0)] * (W * H)
        encoder = GIFEncoder(width=W, height=H)
        encoder.add_frame(pix, delay_ms=50)
        data = encoder.get_bytes()
        gif = GIFDecoder.from_bytes(data)
        assert gif.width == W and gif.height == H
        f = gif.frames[0]
        assert f.has_transparency, "应标记透明色"
        assert f.transparent_index == 0, f"透明索引应为0, 得{f.transparent_index}"
        renderer = GIFRenderer(gif)
        rf = renderer.render_frame(0)
        assert all(c[3] == 0 for c in rf.rgba_data), "渲染后不是全透明"
    print(f"  {len([(1,1),(2,2),(5,3)])} 种尺寸全透明往返: OK")

    print("整帧全透明测试通过!\n")


def test_edge_single_opacity_with_transparent():
    print("=== 边界测试: 1种不透明色 + 透明 ===")
    W, H = 4, 4
    solid = (200, 100, 50, 255)
    pix = []
    for i in range(W * H):
        if i % 2 == 0:
            pix.append(solid)
        else:
            pix.append((0, 0, 0, 0))

    encoder = GIFEncoder(width=W, height=H)
    encoder.add_frame(pix, delay_ms=50)
    data = encoder.get_bytes()
    gif = GIFDecoder.from_bytes(data)
    f = gif.frames[0]
    assert f.has_transparency, "应有透明色标记"
    ct = gif.get_effective_color_table(0)
    print(f"  调色板大小: {len(ct)}")

    renderer = GIFRenderer(gif)
    rf = renderer.render_frame(0)
    for i in range(W * H):
        got = rf.rgba_data[i]
        expected = pix[i]
        if expected[3] == 0:
            assert got[3] == 0, f"idx {i} 应透明"
        else:
            assert got[:3] == solid[:3], f"idx {i} 颜色错误: {got[:3]} != {solid[:3]}"
            assert got[3] == 255
    print("  棋盘格式透明+单色往返: OK")

    print("单色+透明测试通过!\n")


def test_color_frame_switch_consistency():
    print("=== 边界测试: 多帧颜色切换准确性 ===")
    W, H = 3, 3
    frame_colors = [
        (255, 0, 0, 255),
        (0, 0, 255, 255),
        (0, 255, 0, 255),
        (255, 255, 0, 255),
        (255, 0, 255, 255),
        (0, 255, 255, 255),
    ]
    encoder = GIFEncoder(width=W, height=H, loop_count=3)
    for color in frame_colors:
        encoder.add_frame([color] * (W*H), delay_ms=60)
    data = encoder.get_bytes()
    print(f"  编码大小: {len(data)} bytes")

    gif = GIFDecoder.from_bytes(data)
    assert len(gif.frames) == len(frame_colors), "帧数不匹配"
    assert gif.loop_count == 3, f"循环次数错误: {gif.loop_count}"

    renderer = GIFRenderer(gif)
    for i, expected_color in enumerate(frame_colors):
        rf = renderer.render_frame(i)
        f = gif.frames[i]
        assert rf.width == W and rf.height == H
        sample = rf.rgba_data[0]
        assert sample[:3] == expected_color[:3], (
            f"Frame {i} 颜色不匹配: 预期 {expected_color[:3]}, 得 {sample[:3]}"
        )
        delay = f.delay_time * 10
        assert 50 <= delay <= 70, f"Frame {i} 延迟错误: {delay}"
        assert f.left == 0 and f.top == 0
        assert f.width == W and f.height == H
        if f.local_color_table:
            print(f"  Frame {i}: 使用局部调色板 ({len(f.local_color_table)}色)")
    print(f"  {len(frame_colors)} 帧颜色往返一致: OK")

    print("多帧颜色切换测试通过!\n")


def test_disposal_restore_to_previous():
    print("=== 边界测试: 处置方法3 RestoreToPrevious ===")
    W, H = 6, 6
    bg = (0, 0, 255, 255)
    red = (255, 0, 0, 255)
    green = (0, 255, 0, 255)

    encoder = GIFEncoder(width=W, height=H)
    frame0 = [bg] * (W*H)
    encoder.add_frame(frame0, delay_ms=10, disposal_method=DisposalMethod.DO_NOT_DISPOSE)

    frame1 = [bg] * (W*H)
    for y in range(0, 2):
        for x in range(0, 2):
            frame1[y*W + x] = red
    encoder.add_frame(
        frame1, delay_ms=10,
        disposal_method=DisposalMethod.RESTORE_TO_PREVIOUS,
    )

    frame2 = [bg] * (W*H)
    for y in range(H-2, H):
        for x in range(W-2, W):
            frame2[y*W + x] = green
    encoder.add_frame(frame2, delay_ms=10, disposal_method=DisposalMethod.NO_DISPOSAL)

    data = encoder.get_bytes()
    gif = GIFDecoder.from_bytes(data)
    assert len(gif.frames) == 3
    assert gif.frames[1].disposal_method == DisposalMethod.RESTORE_TO_PREVIOUS

    renderer = GIFRenderer(gif)
    r0 = renderer.render_frame(0)
    assert r0.rgba_data[0] == bg, "帧0背景错误"

    r1 = renderer.render_frame(1)
    assert r1.rgba_data[0] == red, "帧1左上应为红色"
    assert r1.rgba_data[1*W + 1] == red, "帧1(1,1)应为红色"
    print("  帧1红方块绘制: OK")

    r2 = renderer.render_frame(2)
    assert r2.rgba_data[0] == bg, (
        f"处置后(0,0)应恢复背景色, 实际{r2.rgba_data[0]}"
    )
    assert r2.rgba_data[1*W + 1] == bg, "处置后(1,1)应恢复背景色"
    assert r2.rgba_data[(H-1)*W + (W-1)] == green, "帧2右下应为绿色"
    assert r2.rgba_data[(H-2)*W + (W-2)] == green, "帧2(4,4)应为绿色"
    print("  帧2红方块消失+绿方块出现: OK")

    renderer.reset()
    r0_again = renderer.render_frame(0)
    r1_again = renderer.render_frame(1)
    r2_again = renderer.render_frame(2)
    assert r0_again.rgba_data == r0.rgba_data
    assert r1_again.rgba_data == r1.rgba_data
    assert r2_again.rgba_data == r2.rgba_data
    print("  重置后重新渲染一致: OK")

    print("处置方法 RestoreToPrevious 测试通过!\n")


def test_roundtrip_boundary_integration():
    print("=== 综合边界: 混合场景往返 ===")
    W, H = 5, 5
    encoder = GIFEncoder(width=W, height=H, loop_count=5)

    red = (255, 0, 0, 255)
    blue = (0, 0, 255, 255)
    green = (0, 255, 0, 255)
    trans = (0, 0, 0, 0)

    frames_data = [
        ([red] * (W*H), DisposalMethod.RESTORE_TO_BACKGROUND, 100),
        ([trans, blue, trans, blue, trans] * H, DisposalMethod.RESTORE_TO_PREVIOUS, 80),
        ([green] * (W*H), DisposalMethod.DO_NOT_DISPOSE, 120),
    ]
    expected_colors = [
        lambda px: all(p[:3] == (255,0,0) and p[3]==255 for p in px),
        lambda px: all(
            (px[i][3]==0 if (i % W) % 2 == 0 else (px[i][:3]==(0,0,255) and px[i][3]==255))
            for i in range(W*H)
        ),
        lambda px: all(p[:3] == (0,255,0) and p[3]==255 for p in px),
    ]

    for pixels, disp, delay in frames_data:
        encoder.add_frame(pixels, delay_ms=delay, disposal_method=disp)
    data = encoder.get_bytes()
    print(f"  编码大小: {len(data)} bytes")

    gif = GIFDecoder.from_bytes(data)
    assert gif.width == W and gif.height == H
    assert len(gif.frames) == len(frames_data)
    assert gif.loop_count == 5

    for i, (pixels, disp, delay) in enumerate(frames_data):
        f = gif.frames[i]
        assert f.disposal_method == disp, f"Frame{i} disp mismatch"
        assert abs(f.delay_time * 10 - delay) <= 10, (
            f"Frame{i} delay mismatch: {f.delay_time*10} vs {delay}"
        )

    renderer = GIFRenderer(gif)
    for i, check_fn in enumerate(expected_colors):
        rf = renderer.render_frame(i)
        assert check_fn(rf.rgba_data), f"Frame{i} 渲染内容错误"
    print("  混合场景 3 帧往返: OK")

    print("综合边界测试通过!\n")


def test_timeline_rendering():
    print("=== 时间轴渲染测试 ===")
    W, H = 2, 2
    delays = [100, 200, 300]
    colors = [
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
    ]

    print("  --- 无限循环 (loop=0) ---")
    encoder = GIFEncoder(width=W, height=H, loop_count=0)
    for color, delay in zip(colors, delays):
        encoder.add_frame([color] * (W * H), delay_ms=delay)
    data = encoder.get_bytes()
    gif = GIFDecoder.from_bytes(data)
    renderer = GIFRenderer(gif)

    assert renderer.total_duration_ms == sum(delays), (
        f"总时长错误: {renderer.total_duration_ms} != {sum(delays)}"
    )
    assert renderer.frame_durations_ms == delays, "帧延迟列表错误"

    time_points = [
        (0, 0, 0, colors[0][:3]),
        (50, 0, 50, colors[0][:3]),
        (99, 0, 99, colors[0][:3]),
        (100, 1, 0, colors[1][:3]),
        (200, 1, 100, colors[1][:3]),
        (299, 1, 199, colors[1][:3]),
        (300, 2, 0, colors[2][:3]),
        (599, 2, 299, colors[2][:3]),
        (600, 0, 0, colors[0][:3]),
        (700, 1, 0, colors[1][:3]),
        (1200, 0, 0, colors[0][:3]),
        (1499, 1, 199, colors[1][:3]),
        (1500, 2, 0, colors[2][:3]),
        (1799, 2, 299, colors[2][:3]),
        (1800, 0, 0, colors[0][:3]),
    ]
    for t, expected_frame, expected_elapsed, expected_color in time_points:
        info = renderer.get_time_info(t)
        assert info.frame_index == expected_frame, (
            f"t={t}ms: 帧={info.frame_index} != 预期{expected_frame}"
        )
        assert info.elapsed_in_frame_ms == expected_elapsed, (
            f"t={t}ms: 帧内耗时={info.elapsed_in_frame_ms} != 预期{expected_elapsed}"
        )
        assert info.loop_count == t // 600, (
            f"t={t}ms: 循环次数={info.loop_count}"
        )
        assert not info.is_paused, f"t={t}ms: 无限循环不应暂停"

        rf, info2 = renderer.render_at_time_ms(t)
        assert info2.frame_index == expected_frame
        assert rf.rgba_data[0][:3] == expected_color, (
            f"t={t}ms: 颜色={rf.rgba_data[0][:3]} != {expected_color}"
        )
    print("  无限循环时间轴: OK")

    print("  --- 有限循环 (loop=2, 播放2遍后停在最后帧) ---")
    encoder2 = GIFEncoder(width=W, height=H, loop_count=2)
    for color, delay in zip(colors, delays):
        encoder2.add_frame([color] * (W * H), delay_ms=delay)
    data2 = encoder2.get_bytes()
    gif2 = GIFDecoder.from_bytes(data2)
    renderer2 = GIFRenderer(gif2)

    assert gif2.loop_count == 2, f"循环次数错误: {gif2.loop_count}"

    max_time = sum(delays) * 2
    time_points2 = [
        (0, 0, False, colors[0][:3]),
        (599, 2, False, colors[2][:3]),
        (600, 0, False, colors[0][:3]),
        (1199, 2, False, colors[2][:3]),
        (1200, 2, True, colors[2][:3]),
        (2000, 2, True, colors[2][:3]),
        (9999, 2, True, colors[2][:3]),
    ]
    for t, expected_frame, expected_paused, expected_color in time_points2:
        info = renderer2.get_time_info(t)
        assert info.frame_index == expected_frame, (
            f"t={t}ms: 帧={info.frame_index} != 预期{expected_frame}"
        )
        assert info.is_paused == expected_paused, (
            f"t={t}ms: paused={info.is_paused} != 预期{expected_paused}"
        )
        rf, _ = renderer2.render_at_time_ms(t)
        assert rf.rgba_data[0][:3] == expected_color
    print("  有限循环+暂停最后帧: OK")

    print("  --- 帧索引查询 ---")
    for t, expected_frame, _, _ in time_points[:10]:
        got = renderer.get_frame_at_time(t)
        assert got == expected_frame, f"get_frame_at_time({t})={got} != {expected_frame}"
    print("  get_frame_at_time: OK")

    print("时间轴渲染测试通过!\n")


def test_extensions_roundtrip():
    print("=== 扩展信息往返测试 ===")
    W, H = 4, 4
    red = (255, 0, 0, 255)
    blue = (0, 0, 255, 255)

    encoder = GIFEncoder(width=W, height=H, loop_count=3)
    encoder.add_comment("First comment - test ASCII")
    encoder.add_comment("Second comment with ASCII: !@#$%")
    encoder.add_application_extension(
        "XMP Data",
        b"\x01\x02\x03",
        b"custom app data",
    )
    encoder.add_frame([red] * (W * H), delay_ms=100)
    encoder.add_frame([blue] * (W * H), delay_ms=200)

    data = encoder.get_bytes()
    print(f"  编码大小: {len(data)} bytes")

    gif = GIFDecoder.from_bytes(data)

    assert len(gif.comment_extensions) == 2, f"注释数: {len(gif.comment_extensions)} != 2"
    assert gif.comment_extensions[0].comment == "First comment - test ASCII"
    assert gif.comment_extensions[1].comment == "Second comment with ASCII: !@#$%"
    print("  注释块保留: OK")

    assert len(gif.application_extensions) == 2, (
        f"应用扩展数: {len(gif.application_extensions)} != 2"
    )
    netscape_exts = [e for e in gif.application_extensions if e.is_netscape_looping]
    assert len(netscape_exts) == 1, "NETSCAPE 循环扩展丢失"
    assert netscape_exts[0].loop_count == 3, (
        f"循环次数: {netscape_exts[0].loop_count} != 3"
    )

    custom_exts = [e for e in gif.application_extensions if not e.is_netscape_looping]
    assert len(custom_exts) == 1, "自定义应用扩展丢失"
    assert custom_exts[0].application_identifier == "XMP Data"
    assert custom_exts[0].authentication_code == b"\x01\x02\x03"
    assert custom_exts[0].data == b"custom app data"
    print("  应用扩展保留: OK")

    assert gif.loop_count == 3, f"GIFImage.loop_count: {gif.loop_count} != 3"
    print("  loop_count 属性: OK")

    assert len(gif.blocks) == 6, f"块数: {len(gif.blocks)} != 6 (2应用+2注释+2帧)"
    block_types = [b.type for b in gif.blocks]
    from gif_engine import BlockType
    expected_types = [
        BlockType.APPLICATION_EXTENSION,
        BlockType.APPLICATION_EXTENSION,
        BlockType.COMMENT_EXTENSION,
        BlockType.COMMENT_EXTENSION,
        BlockType.FRAME,
        BlockType.FRAME,
    ]
    assert block_types == expected_types, (
        f"块顺序: {block_types} != {expected_types}"
    )
    print("  块顺序保留: OK")

    print("  --- 重新编码一致性 ---")
    data2 = GIFEncoder.from_gif_image(gif)
    gif2 = GIFDecoder.from_bytes(data2)
    assert len(gif2.comment_extensions) == 2
    assert len(gif2.application_extensions) == 2
    assert gif2.loop_count == 3
    assert len(gif2.frames) == 2
    renderer = GIFRenderer(gif2)
    assert renderer.render_frame(0).rgba_data[0][:3] == (255, 0, 0)
    assert renderer.render_frame(1).rgba_data[0][:3] == (0, 0, 255)
    print("  decode->encode->decode 往返一致: OK")

    print("扩展信息往返测试通过!\n")


def test_disposal_restore_to_previous_local_area():
    print("=== RestoreToPrevious 局部区域/透明补牢测试 ===")
    W, H = 8, 8
    bg = (0, 0, 255, 255)
    red = (255, 0, 0, 255)
    green = (0, 255, 0, 255)
    trans = (0, 0, 0, 0)

    print("  --- 场景1: 帧2只画1个像素, 帧1的红方块应消失 ---")
    encoder = GIFEncoder(width=W, height=H)
    frame0 = [bg] * (W * H)
    encoder.add_frame(frame0, delay_ms=10, disposal_method=DisposalMethod.DO_NOT_DISPOSE)

    frame1 = [bg] * (W * H)
    for y in range(2, 6):
        for x in range(2, 6):
            frame1[y * W + x] = red
    encoder.add_frame(
        frame1, delay_ms=10, disposal_method=DisposalMethod.RESTORE_TO_PREVIOUS
    )

    frame2 = [bg] * (W * H)
    for y in range(H):
        for x in range(W):
            if not (x == 7 and y == 7):
                frame2[y * W + x] = trans
    frame2[7 * W + 7] = green
    encoder.add_frame(frame2, delay_ms=10, disposal_method=DisposalMethod.NO_DISPOSAL)

    data = encoder.get_bytes()
    gif = GIFDecoder.from_bytes(data)
    renderer = GIFRenderer(gif)

    r0 = renderer.render_frame(0)
    assert r0.rgba_data[0] == bg, "帧0背景错误"

    r1 = renderer.render_frame(1)
    assert r1.rgba_data[3 * W + 3] == red, "帧1红方块未绘制"
    assert r1.rgba_data[2 * W + 2] == red, "帧1红方块未绘制"
    print("    帧1红方块: OK")

    r2 = renderer.render_frame(2)
    assert r2.rgba_data[3 * W + 3] == bg, (
        f"帧2 (3,3) 应为背景色, 实际{r2.rgba_data[3 * W + 3]}"
    )
    assert r2.rgba_data[2 * W + 2] == bg, (
        f"帧2 (2,2) 应为背景色, 实际{r2.rgba_data[2 * W + 2]}"
    )
    assert r2.rgba_data[7 * W + 7] == green, "帧2 (7,7) 应为绿色"
    assert r2.rgba_data[7 * W + 6] == bg, "帧2 (6,7) 应为背景色(透明像素不覆盖)"
    print("    帧2红方块消失+仅1个绿像素: OK")

    print("  --- 场景2: 帧2只更新局部矩形, 帧1临时内容不残留 ---")
    renderer.reset()
    r0b = renderer.render_frame(0)
    r1b = renderer.render_frame(1)
    r2b = renderer.render_frame(2)
    for i in range(W * H):
        expected = frame2[i]
        got = r2b.rgba_data[i]
        if expected[3] == 0:
            if got == bg:
                continue
            assert got[3] == 0, f"idx {i}: 透明位置不应有残留 {got}"
        else:
            assert got[:3] == expected[:3], f"idx {i}: 颜色不匹配"
    print("    逐像素验证无残留: OK")

    print("  --- 场景3: 帧2使用 left/top 只画子区域 ---")
    encoder3 = GIFEncoder(width=W, height=H)
    encoder3.add_frame(frame0, delay_ms=10, disposal_method=DisposalMethod.DO_NOT_DISPOSE)
    encoder3.add_frame(
        frame1, delay_ms=10, disposal_method=DisposalMethod.RESTORE_TO_PREVIOUS
    )

    small_green = [green] * (2 * 2)
    encoder3.add_frame(
        small_green, frame_width=2, frame_height=2, left=6, top=6,
        delay_ms=10, disposal_method=DisposalMethod.NO_DISPOSAL,
    )

    data3 = encoder3.get_bytes()
    gif3 = GIFDecoder.from_bytes(data3)
    renderer3 = GIFRenderer(gif3)

    renderer3.render_frame(0)
    renderer3.render_frame(1)
    r_final = renderer3.render_frame(2)

    assert r_final.rgba_data[3 * W + 3] == bg, (
        f"子区域模式帧2 (3,3) 应为背景色, 实际{r_final.rgba_data[3 * W + 3]}"
    )
    assert r_final.rgba_data[2 * W + 2] == bg, (
        f"子区域模式帧2 (2,2) 应为背景色, 实际{r_final.rgba_data[2 * W + 2]}"
    )
    assert r_final.rgba_data[6 * W + 6] == green, "帧2 (6,6) 应为绿色"
    assert r_final.rgba_data[7 * W + 7] == green, "帧2 (7,7) 应为绿色"
    print("    子区域(left/top)模式无残留: OK")

    print("RestoreToPrevious 局部区域补牢测试通过!\n")


def test_cli_basic():
    print("=== CLI 工具测试 ===")
    import subprocess
    import tempfile
    import json

    W, H = 4, 4
    with tempfile.TemporaryDirectory() as tmpdir:
        test_gif = os.path.join(tmpdir, "test_cli.gif")
        cmd = [
            sys.executable, "-m", "gif_engine", "make",
            "--size", f"{W}x{H}",
            "--delay", "150",
            "--loop", "2",
            "--comment", "test comment 1",
            "--comment", "test comment 2",
            "--frame", "solid:#FF0000",
            "--frame", "checker:#00FF00",
            "--frame", "border:#0000FF",
            "-o", test_gif,
        ]
        print(f"  运行 make 命令...")
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd())
        assert result.returncode == 0, f"make 失败: {result.stderr}"
        assert os.path.exists(test_gif), "make 未生成文件"
        size = os.path.getsize(test_gif)
        assert size > 0, "生成文件为空"
        print(f"    make 成功, {size} bytes")

        cmd_info = [
            sys.executable, "-m", "gif_engine", "info",
            test_gif,
            "--json",
        ]
        print(f"  运行 info 命令...")
        result2 = subprocess.run(cmd_info, capture_output=True, text=True, cwd=os.getcwd())
        assert result2.returncode == 0, f"info 失败: {result2.stderr}"

        json_start = result2.stdout.find("--- JSON ---")
        if json_start >= 0:
            json_str = result2.stdout[json_start + len("--- JSON ---"):].strip()
            data = json.loads(json_str)
            assert data["width"] == W
            assert data["height"] == H
            assert data["num_frames"] == 3
            assert data["loop_count"] == 2
            assert data["num_comments"] == 2
            assert len(data["frames"]) == 3
            assert data["frames"][0]["delay_ms"] == 150
            print(f"    info JSON 输出: OK")
        else:
            raise AssertionError("info 未输出 JSON")

        export_dir = os.path.join(tmpdir, "export")
        cmd_export = [
            sys.executable, "-m", "gif_engine", "info",
            test_gif,
            "--export-frames", export_dir,
        ]
        result3 = subprocess.run(cmd_export, capture_output=True, text=True, cwd=os.getcwd())
        assert result3.returncode == 0, f"export 失败: {result3.stderr}"
        for i in range(3):
            frame_file = os.path.join(export_dir, f"frame_{i:03d}.rgba")
            assert os.path.exists(frame_file), f"帧 {i} 未导出"
            assert os.path.getsize(frame_file) == W * H * 4, f"帧 {i} 大小错误"
        print(f"    帧导出: OK")

    print("CLI 工具测试通过!\n")


def test_import_and_basic_entrypoints():
    print("=== 包导入与基础入口测试 ===")

    import importlib
    import subprocess

    print("  --- import gif_engine ---")
    import gif_engine as ge
    required_symbols = [
        "GIFDecoder", "GIFEncoder", "GIFRenderer",
        "lzw_encode", "lzw_decode",
        "DisposalMethod", "TimeInfo",
        "quantize_image", "median_cut_quantize",
    ]
    for sym in required_symbols:
        assert hasattr(ge, sym), f"缺少符号: {sym}"
    print(f"  {len(required_symbols)} 个公开符号可访问: OK")

    print("  --- python -c \"import gif_engine\" ---")
    r = subprocess.run(
        [sys.executable, "-c", "import gif_engine; print('OK')"],
        capture_output=True, text=True, cwd=os.getcwd(),
    )
    assert r.returncode == 0, f"import 失败: {r.stderr}"
    assert "OK" in r.stdout, f"输出异常: {r.stdout}"
    print("  独立进程 import: OK")

    print("  --- python -m gif_engine --help ---")
    r = subprocess.run(
        [sys.executable, "-m", "gif_engine", "--help"],
        capture_output=True, text=True, cwd=os.getcwd(),
    )
    assert r.returncode == 0, f"--help 失败: {r.stderr}"
    assert "info" in r.stdout and "make" in r.stdout
    print("  -m 入口可用: OK")

    print("  --- python -m gif_engine info (无参数, 应显示错误而非崩溃) ---")
    r = subprocess.run(
        [sys.executable, "-m", "gif_engine", "info"],
        capture_output=True, text=True, cwd=os.getcwd(),
    )
    assert r.returncode != 0, "缺少参数应返回非 0"
    print(f"  info 无参数退出码={r.returncode} (预期!=0): OK")

    print("包导入与基础入口测试通过!\n")


def test_timeline_no_loop_extension():
    print("=== 时间轴: 无循环扩展普通 GIF 测试 ===")
    W, H = 2, 2
    delays = [100, 200, 150]
    colors = [
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
    ]

    encoder = GIFEncoder(width=W, height=H, loop_count=None)
    for color, delay in zip(colors, delays):
        encoder.add_frame([color] * (W * H), delay_ms=delay)
    data = encoder.get_bytes()

    gif = GIFDecoder.from_bytes(data)
    assert gif.loop_count is None, f"loop_count 应为 None, 得 {gif.loop_count}"
    print(f"  无循环扩展, loop_count=None: OK")

    renderer = GIFRenderer(gif)
    total = sum(delays)
    assert renderer.total_duration_ms == total

    print("  --- 正常时间范围内 ---")
    time_points = [
        (0, 0, False, colors[0][:3]),
        (50, 0, False, colors[0][:3]),
        (99, 0, False, colors[0][:3]),
        (100, 1, False, colors[1][:3]),
        (299, 1, False, colors[1][:3]),
        (300, 2, False, colors[2][:3]),
        (449, 2, False, colors[2][:3]),
    ]
    for t, expected_frame, expected_paused, expected_color in time_points:
        info = renderer.get_time_info(t)
        assert info.frame_index == expected_frame, (
            f"t={t}: frame={info.frame_index} != {expected_frame}"
        )
        assert info.is_paused == expected_paused, (
            f"t={t}: paused={info.is_paused} != {expected_paused}"
        )
        rf, _ = renderer.render_at_time_ms(t)
        assert rf.rgba_data[0][:3] == expected_color, (
            f"t={t}: color={rf.rgba_data[0][:3]} != {expected_color}"
        )
    print(f"  {len(time_points)} 个时间点: OK")

    print("  --- 超过总时长后暂停在最后帧 ---")
    over_times = [total, total + 1, total + 100, total + 9999]
    for t in over_times:
        info = renderer.get_time_info(t)
        assert info.frame_index == 2, f"t={t}: frame={info.frame_index} != 2"
        assert info.is_paused == True, f"t={t}: paused 应为 True"
        rf, _ = renderer.render_at_time_ms(t)
        assert rf.rgba_data[0][:3] == (0, 0, 255), f"t={t}: 颜色错误"
    print(f"  超过总时长后暂停: OK")

    print("  --- 对比 loop_count=1 行为一致 ---")
    encoder1 = GIFEncoder(width=W, height=H, loop_count=1)
    for color, delay in zip(colors, delays):
        encoder1.add_frame([color] * (W * H), delay_ms=delay)
    data1 = encoder1.get_bytes()
    gif1 = GIFDecoder.from_bytes(data1)
    assert gif1.loop_count == 1
    renderer1 = GIFRenderer(gif1)
    for t in [0, 50, 100, 300, 449, 450, 1000]:
        info0 = renderer.get_time_info(t)
        info1 = renderer1.get_time_info(t)
        assert info0.frame_index == info1.frame_index, f"t={t}: frame 不一致"
        assert info0.is_paused == info1.is_paused, f"t={t}: paused 不一致"
    print("  loop_count=None 与 loop_count=1 行为一致: OK")

    print("无循环扩展时间轴测试通过!\n")


def test_cli_rgba_file_roundtrip():
    print("=== CLI: RGBA 原始文件合成+导出往返测试 ===")
    import subprocess
    import tempfile

    W, H = 4, 4
    red = (255, 0, 0, 255)
    blue = (0, 0, 255, 255)
    green = (0, 255, 0, 255)
    pixels0 = [red] * (W * H)
    pixels1 = [green] * (W * H)
    pixels2 = [blue if i % 2 == 0 else (0, 0, 0, 0) for i in range(W * H)]

    with tempfile.TemporaryDirectory() as tmpdir:
        paths = []
        for idx, pixels in enumerate([pixels0, pixels1, pixels2]):
            p = os.path.join(tmpdir, f"frame{idx}.rgba")
            with open(p, "wb") as f:
                for r, g, b, a in pixels:
                    f.write(bytes([r, g, b, a]))
            paths.append(p)

        print(f"  写入 {len(paths)} 个 RGBA 文件")

        out_gif = os.path.join(tmpdir, "from_rgba.gif")
        cmd = [
            sys.executable, "-m", "gif_engine", "make",
            "--size", f"{W}x{H}",
            "--delay", "200",
            "--disposal", "2",
            "--loop", "0",
            "--frame", paths[0],
            "--frame", paths[1],
            "--frame", paths[2],
            "-o", out_gif,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd())
        assert r.returncode == 0, f"make 失败: {r.stderr}\nSTDOUT:{r.stdout}"
        assert os.path.exists(out_gif), f"未生成 {out_gif}"
        print(f"  make 成功, {os.path.getsize(out_gif)} bytes: OK")

        export_dir = os.path.join(tmpdir, "exported")
        cmd_info = [
            sys.executable, "-m", "gif_engine", "info",
            out_gif,
            "--export-frames", export_dir,
            "--json",
        ]
        r2 = subprocess.run(cmd_info, capture_output=True, text=True, cwd=os.getcwd())
        assert r2.returncode == 0, f"info+export 失败: {r2.stderr}\nSTDOUT:{r2.stdout}"

        from gif_engine import GIFDecoder, GIFRenderer
        gif_check = GIFDecoder.from_file(out_gif)
        renderer_check = GIFRenderer(gif_check)

        for i in range(3):
            exported_path = os.path.join(export_dir, f"frame_{i:03d}.rgba")
            assert os.path.exists(exported_path), f"未导出 {exported_path}"
            size = os.path.getsize(exported_path)
            expected_size = W * H * 4
            assert size == expected_size, (
                f"frame{i} 大小 {size} != 预期 {expected_size}"
            )

            with open(exported_path, "rb") as f:
                raw = f.read()
            got_pixels = []
            for j in range(0, len(raw), 4):
                got_pixels.append((raw[j], raw[j+1], raw[j+2], raw[j+3]))

            renderer_check.reset()
            rendered = None
            for k in range(i + 1):
                rendered = renderer_check.render_frame(k)
            expected_rendered = rendered.rgba_data

            match_count = sum(1 for g, e in zip(got_pixels, expected_rendered) if g == e)
            assert match_count == W * H, (
                f"frame{i} {match_count}/{W*H} 像素匹配渲染结果"
            )
            print(f"  帧 {i}: {match_count}/{W*H} 像素匹配 (文件大小={size} bytes): OK")

        print(f"  info JSON 验证...")
        import json
        json_start = r2.stdout.find("--- JSON ---")
        assert json_start >= 0, "未输出 JSON"
        j = json.loads(r2.stdout[json_start + len("--- JSON ---"):].strip())
        assert j["width"] == W and j["height"] == H
        assert j["num_frames"] == 3
        assert j["loop_count"] == 0
        assert len(j["frames"]) == 3
        assert j["frames"][0]["delay_ms"] == 200
        assert j["frames"][0]["width"] == W and j["frames"][0]["height"] == H
        assert j["frames"][0]["disposal"] == "RESTORE_TO_BACKGROUND"
        print(f"  info JSON 一致: OK")

    print("CLI RGBA 文件往返测试通过!\n")


def test_info_loop_display_distinction():
    print("=== info 循环信息三种状态区分测试 ===")
    import subprocess
    import tempfile
    import json

    W, H = 2, 2

    print("  --- 无限循环 (loop=0) ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "inf.gif")
        cmd = [
            sys.executable, "-m", "gif_engine", "make",
            "--size", f"{W}x{H}", "--delay", "100", "--loop", "0",
            "--frame", "solid:#FF0000", "--frame", "solid:#00FF00",
            "-o", out,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd())
        assert r.returncode == 0, f"make 失败: {r.stderr}"

        cmd2 = [sys.executable, "-m", "gif_engine", "info", out, "--json"]
        r2 = subprocess.run(cmd2, capture_output=True, text=True, cwd=os.getcwd())
        assert "无限循环" in r2.stdout, "终端输出应显示'无限循环'"
        j_start = r2.stdout.find("--- JSON ---")
        j = json.loads(r2.stdout[j_start + len("--- JSON ---"):].strip())
        assert j["loop_count"] == 0, f"JSON loop_count 应为 0, 得 {j['loop_count']}"
        assert j["loop_description"] == "无限循环", f"loop_description 错误: {j['loop_description']}"
        print("    终端: 无限循环 | JSON: loop_count=0, description='无限循环': OK")

    print("  --- 指定次数 (loop=3) ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "loop3.gif")
        cmd = [
            sys.executable, "-m", "gif_engine", "make",
            "--size", f"{W}x{H}", "--delay", "100", "--loop", "3",
            "--frame", "solid:#FF0000", "--frame", "solid:#00FF00",
            "-o", out,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd())
        assert r.returncode == 0

        cmd2 = [sys.executable, "-m", "gif_engine", "info", out, "--json"]
        r2 = subprocess.run(cmd2, capture_output=True, text=True, cwd=os.getcwd())
        assert "3 次" in r2.stdout, "终端输出应显示'3 次'"
        j_start = r2.stdout.find("--- JSON ---")
        j = json.loads(r2.stdout[j_start + len("--- JSON ---"):].strip())
        assert j["loop_count"] == 3
        assert j["loop_description"] == "3 次"
        print("    终端: 3 次 | JSON: loop_count=3, description='3 次': OK")

    print("  --- 无循环扩展 (单帧无NETSCAPE) ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "noloop.gif")
        enc = GIFEncoder(width=W, height=H, loop_count=None)
        enc.add_frame([(255, 0, 0, 255)] * (W * H), delay_ms=100)
        enc.save(out)

        cmd2 = [sys.executable, "-m", "gif_engine", "info", out, "--json"]
        r2 = subprocess.run(cmd2, capture_output=True, text=True, cwd=os.getcwd())
        assert "无循环扩展" in r2.stdout, "终端输出应显示'无循环扩展'"
        assert "无限" not in r2.stdout.split("--- JSON ---")[0], "无循环扩展不能显示为无限"
        j_start = r2.stdout.find("--- JSON ---")
        j = json.loads(r2.stdout[j_start + len("--- JSON ---"):].strip())
        assert j["loop_count"] is None, f"JSON loop_count 应为 null, 得 {j['loop_count']}"
        assert "无循环扩展" in j["loop_description"]
        print("    终端: 无循环扩展(播放一遍) | JSON: loop_count=null: OK")

    print("info 循环信息区分测试通过!\n")


def test_timeline_subcommand():
    print("=== timeline 子命令测试 ===")
    import subprocess
    import tempfile
    import json

    W, H = 2, 2
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "anim.gif")
        cmd = [
            sys.executable, "-m", "gif_engine", "make",
            "--size", f"{W}x{H}", "--delay", "100", "--loop", "0",
            "--frame", "solid:#FF0000",
            "--frame", "solid:#00FF00",
            "--frame", "solid:#0000FF",
            "-o", out,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd())
        assert r.returncode == 0

        export_dir = os.path.join(tmpdir, "timeline_export")
        cmd2 = [
            sys.executable, "-m", "gif_engine", "timeline",
            out,
            "--time", "0", "--time", "50", "--time", "100",
            "--time", "199", "--time", "200",
            "--time", "299",
            "--export-frames", export_dir,
            "--json",
        ]
        r2 = subprocess.run(cmd2, capture_output=True, text=True, cwd=os.getcwd())
        assert r2.returncode == 0, f"timeline 失败: {r2.stderr}\nSTDOUT:{r2.stdout}"

        assert "帧号" in r2.stdout, "应输出帧号列"
        assert "暂停" in r2.stdout or "播放中" in r2.stdout, "应输出状态列"

        j_start = r2.stdout.find("--- JSON ---")
        assert j_start >= 0, "未输出 JSON"
        j = json.loads(r2.stdout[j_start + len("--- JSON ---"):].strip())
        results = j["results"]
        assert len(results) == 6, f"应去重后 6 个时间点, 得 {len(results)}"

        checks = [
            (0, 0, False),
            (50, 0, False),
            (100, 1, False),
            (199, 1, False),
            (200, 2, False),
            (299, 2, False),
        ]
        for res, (t, expected_frame, expected_paused) in zip(results, checks):
            assert res["frame_index"] == expected_frame, (
                f"t={t}: frame={res['frame_index']} != {expected_frame}"
            )
            assert res["is_paused"] == expected_paused, (
                f"t={t}: paused={res['is_paused']} != {expected_paused}"
            )
        print("  时间轴查询结果: OK")

        for idx in [0, 1, 2]:
            fpath = os.path.join(export_dir, f"frame_{idx:03d}.rgba")
            assert os.path.exists(fpath), f"帧 {idx} 未导出"
            assert os.path.getsize(fpath) == W * H * 4
        print("  帧导出: OK")

        manifest_path = os.path.join(export_dir, "manifest.json")
        assert os.path.exists(manifest_path), "manifest.json 未生成"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["gif_width"] == W and manifest["gif_height"] == H
        assert manifest["loop_count"] == 0
        assert len(manifest["exported_frames"]) == 3
        assert "timeline_results" in manifest
        assert manifest["exported_frames"][0]["disposal_code"] == 1
        print("  manifest.json: OK")

    print("timeline 子命令测试通过!\n")


def test_make_per_frame_params():
    print("=== make 每帧独立参数测试 ===")
    import subprocess
    import tempfile

    W, H = 16, 16
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "perframe.gif")
        cmd = [
            sys.executable, "-m", "gif_engine", "make",
            "--size", f"{W}x{H}", "--loop", "0",
            "--frame", "solid:#FF0000,delay=200,disposal=1",
            "--frame", "solid:#00FF00,delay=300,disposal=2,left=4,top=4,size=8x8",
            "--frame", "solid:#0000FF,delay=100,disposal=3,left=8,top=8,size=4x4",
            "-o", out,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd())
        assert r.returncode == 0, f"make 失败: {r.stderr}\nSTDOUT:{r.stdout}"
        assert os.path.exists(out)
        print(f"  make 成功, {os.path.getsize(out)} bytes")

        from gif_engine import GIFDecoder, GIFRenderer
        gif = GIFDecoder.from_file(out)
        assert len(gif.frames) == 3

        f0 = gif.frames[0]
        assert f0.delay_time * 10 == 200, f"帧0延迟: {f0.delay_time * 10}"
        assert f0.disposal_method == 1
        assert f0.left == 0 and f0.top == 0
        assert f0.width == W and f0.height == H
        print(f"  帧0: delay=200ms, disposal=1, pos=(0,0), size={W}x{H}: OK")

        f1 = gif.frames[1]
        assert f1.delay_time * 10 == 300, f"帧1延迟: {f1.delay_time * 10}"
        assert f1.disposal_method == 2
        assert f1.left == 4 and f1.top == 4
        assert f1.width == 8 and f1.height == 8
        print(f"  帧1: delay=300ms, disposal=2, pos=(4,4), size=8x8: OK")

        f2 = gif.frames[2]
        assert f2.delay_time * 10 == 100, f"帧2延迟: {f2.delay_time * 10}"
        assert f2.disposal_method == 3
        assert f2.left == 8 and f2.top == 8
        assert f2.width == 4 and f2.height == 4
        print(f"  帧2: delay=100ms, disposal=3, pos=(8,8), size=4x4: OK")

        renderer = GIFRenderer(gif)
        rf0 = renderer.render_frame(0)
        rf1 = renderer.render_frame(1)
        rf2 = renderer.render_frame(2)
        assert rf0.rgba_data[0][:3] == (255, 0, 0)
        assert rf1.rgba_data[4 * W + 4][:3] == (0, 255, 0)
        assert rf2.rgba_data[8 * W + 8][:3] == (0, 0, 255)
        print("  渲染颜色验证: OK")

    print("make 每帧独立参数测试通过!\n")


def test_manifest_on_export():
    print("=== manifest.json 生成测试 ===")
    import subprocess
    import tempfile
    import json

    W, H = 4, 4
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "test.gif")
        cmd = [
            sys.executable, "-m", "gif_engine", "make",
            "--size", f"{W}x{H}", "--delay", "150", "--loop", "2",
            "--disposal", "2",
            "--frame", "solid:#FF0000",
            "--frame", "checker:#00FF00",
            "-o", out,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd())
        assert r.returncode == 0

        export_dir = os.path.join(tmpdir, "export")
        cmd2 = [
            sys.executable, "-m", "gif_engine", "info",
            out, "--export-frames", export_dir,
        ]
        r2 = subprocess.run(cmd2, capture_output=True, text=True, cwd=os.getcwd())
        assert r2.returncode == 0

        manifest_path = os.path.join(export_dir, "manifest.json")
        assert os.path.exists(manifest_path), "manifest.json 未生成"
        with open(manifest_path, "r", encoding="utf-8") as f:
            m = json.load(f)

        assert m["gif_width"] == W
        assert m["gif_height"] == H
        assert m["num_frames"] == 2
        assert m["total_duration_ms"] == 300
        assert m["loop_count"] == 2
        assert "2 次" in m["loop_description"]
        assert len(m["frames"]) == 2

        for i, fm in enumerate(m["frames"]):
            assert fm["index"] == i
            assert fm["filename"] == f"frame_{i:03d}.rgba"
            assert fm["width"] == W
            assert fm["height"] == H
            assert fm["file_size"] == W * H * 4
            assert fm["delay_ms"] == 150
            assert fm["disposal"] == "RESTORE_TO_BACKGROUND"
            assert fm["disposal_code"] == 2
            assert fm["left"] == 0
            assert fm["top"] == 0
            assert fm["frame_width"] == W
            assert fm["frame_height"] == H

            rgba_path = os.path.join(export_dir, fm["filename"])
            assert os.path.exists(rgba_path)
            assert os.path.getsize(rgba_path) == fm["file_size"]

        print(f"  manifest 结构正确, 2 帧全部字段匹配: OK")
        print(f"  rgba 文件大小与 manifest 一致: OK")

    print("manifest.json 生成测试通过!\n")


def main():
    print("=" * 60)
    print("GIF 编解码引擎测试套件")
    print("=" * 60 + "\n")

    try:
        test_lzw_roundtrip()
        test_median_cut()
        test_interlace()
        test_simple_gif_encode_decode()
        test_transparent_animation()
        test_roundtrip_frame_data()
        test_disposal_methods()
        test_edge_solid_1x1()
        test_edge_fully_transparent()
        test_edge_single_opacity_with_transparent()
        test_color_frame_switch_consistency()
        test_disposal_restore_to_previous()
        test_roundtrip_boundary_integration()
        test_timeline_rendering()
        test_extensions_roundtrip()
        test_disposal_restore_to_previous_local_area()
        test_cli_basic()
        test_import_and_basic_entrypoints()
        test_timeline_no_loop_extension()
        test_cli_rgba_file_roundtrip()
        test_info_loop_display_distinction()
        test_timeline_subcommand()
        test_make_per_frame_params()
        test_manifest_on_export()

        print("=" * 60)
        print("所有测试通过! 生成的文件:")
        for f in ["test_simple.gif", "test_transparent.gif"]:
            if os.path.exists(f):
                size = os.path.getsize(f)
                print(f"  {f}: {size} bytes")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
