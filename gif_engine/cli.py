import argparse
import json
import os
import sys
from typing import List, Tuple

from .decoder import GIFDecoder
from .encoder import GIFEncoder
from .renderer import GIFRenderer, DisposalMethod
from .structures import GIFImage


DISPOSAL_NAMES = {
    0: "NO_DISPOSAL",
    1: "DO_NOT_DISPOSE",
    2: "RESTORE_TO_BACKGROUND",
    3: "RESTORE_TO_PREVIOUS",
}


def _disposal_name(dm: int) -> str:
    return DISPOSAL_NAMES.get(dm, f"UNKNOWN({dm})")


def cmd_info(args: argparse.Namespace) -> int:
    filepath = args.input
    if not os.path.exists(filepath):
        print(f"错误: 文件不存在: {filepath}", file=sys.stderr)
        return 1

    gif = GIFDecoder.from_file(filepath)
    renderer = GIFRenderer(gif)

    info = {
        "file": filepath,
        "version": gif.signature.version,
        "width": gif.width,
        "height": gif.height,
        "loop_count": gif.loop_count if gif.loop_count is not None else "infinite",
        "num_frames": len(gif.frames),
        "total_duration_ms": renderer.total_duration_ms,
        "has_global_palette": gif.global_color_table is not None,
        "global_palette_size": len(gif.global_color_table) if gif.global_color_table else 0,
        "num_comments": len(gif.comment_extensions),
        "num_app_extensions": len(gif.application_extensions),
    }

    print("=" * 60)
    print(f"GIF 文件信息: {filepath}")
    print("=" * 60)
    print(f"  版本:         {info['version']}")
    print(f"  尺寸:         {info['width']}x{info['height']}")
    print(f"  帧数:         {info['num_frames']}")
    print(f"  总时长:       {info['total_duration_ms']} ms")
    print(f"  循环次数:     {info['loop_count']}")
    print(f"  全局调色板:   {'是 (' + str(info['global_palette_size']) + '色)' if info['has_global_palette'] else '否'}")
    print(f"  注释块:       {info['num_comments']}")
    print(f"  应用扩展:     {info['num_app_extensions']}")

    if gif.comment_extensions:
        print("\n--- 注释内容 ---")
        for i, ext in enumerate(gif.comment_extensions):
            print(f"  [{i}] {repr(ext.comment)}")

    if gif.application_extensions:
        print("\n--- 应用扩展 ---")
        for i, ext in enumerate(gif.application_extensions):
            if ext.is_netscape_looping:
                print(f"  [{i}] NETSCAPE 循环 (loop_count={ext.loop_count})")
            else:
                print(
                    f"  [{i}] {ext.application_identifier} "
                    f"(auth={ext.authentication_code.hex()}, data_len={len(ext.data)})"
                )

    print(f"\n{'='*60}")
    print(f"{'帧号':>4} | {'偏移':>6} | {'尺寸':>10} | {'延迟':>8} | {'处置':>22} | {'透明':>6} | {'调色板'}")
    print(f"{'-'*60}")

    for i, frame in enumerate(gif.frames):
        delay = frame.delay_time * 10
        if delay == 0:
            delay = 100
        has_local = frame.local_color_table is not None
        palette_info = f"局部({len(frame.local_color_table)}色)" if has_local else "全局"
        offset_str = f"{frame.left},{frame.top}"
        size_str = f"{frame.width}x{frame.height}"
        disp_str = _disposal_name(frame.disposal_method)
        trans_str = f"idx={frame.transparent_index}" if frame.has_transparency else "否"

        print(
            f"{i:>4} | {offset_str:>6} | {size_str:>10} | {delay:>6}ms | {disp_str:>22} | {trans_str:>6} | {palette_info}"
        )

    if args.export_frames:
        out_dir = args.export_frames
        os.makedirs(out_dir, exist_ok=True)
        renderer.reset()
        print(f"\n导出帧到: {out_dir}/")
        for i in range(len(gif.frames)):
            rf = renderer.render_frame(i)
            out_path = os.path.join(out_dir, f"frame_{i:03d}.rgba")
            with open(out_path, "wb") as f:
                for r, g, b, a in rf.rgba_data:
                    f.write(bytes([r, g, b, a]))
            print(f"  帧 {i}: {out_path} ({rf.width}x{rf.height})")

    if args.json:
        frame_details = []
        for i, frame in enumerate(gif.frames):
            delay = frame.delay_time * 10 or 100
            frame_details.append({
                "index": i,
                "left": frame.left,
                "top": frame.top,
                "width": frame.width,
                "height": frame.height,
                "delay_ms": delay,
                "disposal": _disposal_name(frame.disposal_method),
                "has_transparency": frame.has_transparency,
                "transparent_index": frame.transparent_index if frame.has_transparency else None,
                "local_palette_size": len(frame.local_color_table) if frame.local_color_table else None,
                "interlaced": frame.interlaced,
            })
        info["frames"] = frame_details
        print(f"\n--- JSON ---\n{json.dumps(info, indent=2, ensure_ascii=False)}")

    return 0


def _parse_color(s: str) -> Tuple[int, int, int, int]:
    s = s.strip().lstrip("#")
    if len(s) == 6:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        return (r, g, b, 255)
    elif len(s) == 8:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        a = int(s[6:8], 16)
        return (r, g, b, a)
    else:
        raise ValueError(f"无效颜色格式: {s}, 使用 #RRGGBB 或 #RRGGBBAA")


def _make_test_pattern(
    pattern: str, width: int, height: int, color: Tuple[int, int, int, int]
) -> List[Tuple[int, int, int, int]]:
    bg = (0, 0, 0, 0)
    pixels = [bg] * (width * height)

    if pattern == "solid":
        return [color] * (width * height)

    elif pattern == "checker":
        for y in range(height):
            for x in range(width):
                if (x + y) % 2 == 0:
                    pixels[y * width + x] = color

    elif pattern == "border":
        for y in range(height):
            for x in range(width):
                if x == 0 or x == width - 1 or y == 0 or y == height - 1:
                    pixels[y * width + x] = color

    elif pattern == "center":
        cx, cy = width // 2, height // 2
        r = min(width, height) // 4
        for y in range(height):
            for x in range(width):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    pixels[y * width + x] = color

    elif pattern == "gradient":
        for y in range(height):
            for x in range(width):
                t = x / max(width - 1, 1)
                r = int(color[0] * t)
                g = int(color[1] * t)
                b = int(color[2] * t)
                pixels[y * width + x] = (r, g, b, color[3])

    else:
        raise ValueError(f"未知图案: {pattern}")

    return pixels


def cmd_make(args: argparse.Namespace) -> int:
    width, height = args.size
    delay_ms = args.delay
    output = args.output
    loop_count = args.loop
    disposal = args.disposal

    if len(args.frames) == 0:
        print("错误: 请指定至少一帧 (--frame)", file=sys.stderr)
        return 1

    encoder = GIFEncoder(width=width, height=height, loop_count=loop_count)

    if args.comment:
        for c in args.comment:
            encoder.add_comment(c)

    for frame_def in args.frames:
        if os.path.exists(frame_def):
            with open(frame_def, "rb") as f:
                raw = f.read()
            expected = width * height * 4
            if len(raw) != expected:
                print(
                    f"错误: 文件 {frame_def} 大小 {len(raw)} != 期望 {expected} ({width}x{height} RGBA)",
                    file=sys.stderr,
                )
                return 1
            pixels = []
            for i in range(0, len(raw), 4):
                pixels.append((raw[i], raw[i + 1], raw[i + 2], raw[i + 3]))
            print(f"  添加帧: {frame_def} ({len(pixels)} 像素, {width}x{height})")
        else:
            if ":" in frame_def:
                pattern, color_str = frame_def.rsplit(":", 1)
            else:
                pattern, color_str = "solid", frame_def

            try:
                color = _parse_color(color_str)
            except ValueError as e:
                print(f"错误: {e}", file=sys.stderr)
                return 1

            pixels = _make_test_pattern(pattern, width, height, color)
            print(f"  添加帧: {pattern} {color_str} ({len(pixels)} 像素)")

        encoder.add_frame(
            pixels,
            delay_ms=delay_ms,
            disposal_method=disposal,
            use_local_palette=args.local_palette,
            interlaced=args.interlaced,
        )

    encoder.save(output)
    size = os.path.getsize(output)
    print(f"\n已生成: {output} ({size} bytes, {len(args.frames)} 帧)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gif-engine",
        description="GIF 编解码引擎命令行工具",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    info_parser = subparsers.add_parser("info", help="查看 GIF 文件信息")
    info_parser.add_argument("input", help="输入 GIF 文件路径")
    info_parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    info_parser.add_argument(
        "--export-frames", metavar="DIR", help="导出所有帧为 RGBA 原始文件到指定目录"
    )
    info_parser.set_defaults(func=cmd_info)

    make_parser = subparsers.add_parser("make", help="合成测试 GIF")
    make_parser.add_argument(
        "--size",
        type=lambda s: tuple(int(x) for x in s.split("x")),
        default=(32, 32),
        metavar="WxH",
        help="画布尺寸, 默认 32x32",
    )
    make_parser.add_argument(
        "--delay", type=int, default=100, help="每帧延迟(ms), 默认 100"
    )
    make_parser.add_argument(
        "--loop", type=int, default=0, help="循环次数, 0=无限, 默认 0"
    )
    make_parser.add_argument(
        "--disposal",
        type=int,
        default=1,
        choices=[0, 1, 2, 3],
        help="处置方法: 0=无 1=不处理 2=恢复背景 3=恢复前帧, 默认 1",
    )
    make_parser.add_argument(
        "--local-palette",
        action="store_true",
        help="每帧使用独立局部调色板",
    )
    make_parser.add_argument(
        "--interlaced",
        action="store_true",
        help="使用隔行扫描存储",
    )
    make_parser.add_argument(
        "--comment",
        action="append",
        help="添加注释块, 可多次指定",
    )
    make_parser.add_argument(
        "-o", "--output",
        required=True,
        help="输出 GIF 文件路径",
    )
    make_parser.add_argument(
        "--frame",
        dest="frames",
        action="append",
        required=True,
        metavar="SPEC",
        help=(
            "帧定义, 可多次指定. 格式: [图案:]颜色 或 文件路径. "
            "图案: solid/checker/border/center/gradient. "
            "颜色: #RRGGBB 或 #RRGGBBAA. "
            "例: --frame solid:#FF0000 --frame checker:#00FF00FF"
        ),
    )
    make_parser.set_defaults(func=cmd_make)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
