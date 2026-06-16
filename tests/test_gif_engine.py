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
