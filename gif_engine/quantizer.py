from typing import List, Tuple, Optional
from .structures import ColorTable


def _color_distance(c1: Tuple[int, int, int], c2: Tuple[int, int, int]) -> int:
    return (c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2


def _find_nearest_color(
    color: Tuple[int, int, int], palette: List[Tuple[int, int, int]]
) -> Tuple[int, int]:
    best_idx = 0
    best_dist = _color_distance(color, palette[0])
    for i in range(1, len(palette)):
        dist = _color_distance(color, palette[i])
        if dist < best_dist:
            best_dist = dist
            best_idx = i
    return best_idx, best_dist


class _ColorBox:
    def __init__(self, colors: List[Tuple[int, int, int]]):
        self.colors = colors
        self._update_ranges()

    def _update_ranges(self) -> None:
        if not self.colors:
            self.r_min = self.r_max = 0
            self.g_min = self.g_max = 0
            self.b_min = self.b_max = 0
            return
        r_vals = [c[0] for c in self.colors]
        g_vals = [c[1] for c in self.colors]
        b_vals = [c[2] for c in self.colors]
        self.r_min, self.r_max = min(r_vals), max(r_vals)
        self.g_min, self.g_max = min(g_vals), max(g_vals)
        self.b_min, self.b_max = min(b_vals), max(b_vals)

    @property
    def longest_dimension(self) -> int:
        r_range = self.r_max - self.r_min
        g_range = self.g_max - self.g_min
        b_range = self.b_max - self.b_min
        if r_range >= g_range and r_range >= b_range:
            return 0
        elif g_range >= b_range:
            return 1
        else:
            return 2

    @property
    def volume(self) -> int:
        return (self.r_max - self.r_min + 1) * (self.g_max - self.g_min + 1) * (self.b_max - self.b_min + 1)

    @property
    def median(self) -> Tuple[int, int, int]:
        n = len(self.colors)
        if n == 0:
            return (0, 0, 0)
        sorted_r = sorted(c[0] for c in self.colors)
        sorted_g = sorted(c[1] for c in self.colors)
        sorted_b = sorted(c[2] for c in self.colors)
        mid = n // 2
        return (sorted_r[mid], sorted_g[mid], sorted_b[mid])

    @property
    def average(self) -> Tuple[int, int, int]:
        n = len(self.colors)
        if n == 0:
            return (0, 0, 0)
        r_sum = sum(c[0] for c in self.colors)
        g_sum = sum(c[1] for c in self.colors)
        b_sum = sum(c[2] for c in self.colors)
        return (r_sum // n, g_sum // n, b_sum // n)

    def split(self) -> Tuple["_ColorBox", "_ColorBox"]:
        dim = self.longest_dimension
        sorted_colors = sorted(self.colors, key=lambda c: c[dim])
        mid = len(sorted_colors) // 2
        if mid == 0:
            mid = 1
        if mid >= len(sorted_colors):
            mid = len(sorted_colors) - 1
        left = _ColorBox(sorted_colors[:mid])
        right = _ColorBox(sorted_colors[mid:])
        return left, right

    def __len__(self) -> int:
        return len(self.colors)


def median_cut_quantize(
    pixels: List[Tuple[int, int, int]],
    max_colors: int = 256,
) -> Tuple[List[Tuple[int, int, int]], List[int]]:
    if max_colors < 2 or max_colors > 256:
        raise ValueError(f"max_colors must be between 2 and 256, got {max_colors}")

    if not pixels:
        return [(0, 0, 0)], []

    unique_pixels = list(set(pixels))

    if len(unique_pixels) <= max_colors:
        palette = unique_pixels
        indices = [palette.index(c) for c in pixels]
        return palette, indices

    initial_box = _ColorBox(unique_pixels)
    boxes = [initial_box]

    while len(boxes) < max_colors:
        boxes.sort(key=lambda b: b.volume * len(b), reverse=True)
        split_idx = -1
        for i, box in enumerate(boxes):
            if len(box) >= 2:
                split_idx = i
                break
        if split_idx == -1:
            break

        box_to_split = boxes.pop(split_idx)
        left, right = box_to_split.split()
        if len(left) > 0:
            boxes.append(left)
        if len(right) > 0:
            boxes.append(right)

    palette = [box.average for box in boxes]

    while len(palette) < max_colors:
        palette.append((0, 0, 0))
    palette = palette[:max_colors]

    indices = [_find_nearest_color(c, palette)[0] for c in pixels]

    return palette, indices


def quantize_image(
    rgba_pixels: List[Tuple[int, int, int, int]],
    max_colors: int = 256,
    use_transparent: bool = True,
) -> Tuple[ColorTable, List[int], Optional[int]]:
    if not rgba_pixels:
        ct = ColorTable(colors=[(0, 0, 0), (255, 255, 255)])
        ct.pad_to_power_of_two()
        return ct, [], None

    has_transparency = any(p[3] < 128 for p in rgba_pixels)
    transparent_index: Optional[int] = None

    if has_transparency and use_transparent:
        opaque_pixels = [(p[0], p[1], p[2]) for p in rgba_pixels if p[3] >= 128]
        if not opaque_pixels:
            ct = ColorTable(colors=[(0, 0, 0)])
            ct.pad_to_power_of_two()
            transparent_index = 0
            indices = [0] * len(rgba_pixels)
            return ct, indices, transparent_index

        colors_for_palette = list(set(opaque_pixels))
        if len(colors_for_palette) > max_colors - 1:
            palette_list, _ = median_cut_quantize(opaque_pixels, max_colors - 1)
        else:
            palette_list = colors_for_palette

        palette_list.insert(0, (0, 0, 0))
        transparent_index = 0

        actual_palette = palette_list
        indices = []
        for p in rgba_pixels:
            if p[3] < 128:
                indices.append(transparent_index)
            else:
                idx, _ = _find_nearest_color((p[0], p[1], p[2]), actual_palette)
                indices.append(idx)
    else:
        rgb_pixels = [(p[0], p[1], p[2]) for p in rgba_pixels]
        palette_list, indices = median_cut_quantize(rgb_pixels, max_colors)

    ct = ColorTable(colors=palette_list)
    ct.pad_to_power_of_two()

    return ct, indices, transparent_index


def deinterlace_indices(
    interlaced: List[int], width: int, height: int
) -> List[int]:
    if len(interlaced) != width * height:
        raise ValueError(
            f"Interlaced data size mismatch: expected {width*height}, got {len(interlaced)}"
        )

    result = [0] * (width * height)
    src_row = 0

    for pass_num, (start, step) in enumerate(
        [(0, 8), (4, 8), (2, 4), (1, 2)]
    ):
        for dst_row in range(start, height, step):
            if src_row >= height:
                break
            src_start = src_row * width
            dst_start = dst_row * width
            for col in range(width):
                result[dst_start + col] = interlaced[src_start + col]
            src_row += 1

    return result


def interlace_indices(
    normal: List[int], width: int, height: int
) -> List[int]:
    if len(normal) != width * height:
        raise ValueError(
            f"Data size mismatch: expected {width*height}, got {len(normal)}"
        )

    result = [0] * (width * height)
    dst_row = 0

    for start, step in [(0, 8), (4, 8), (2, 4), (1, 2)]:
        for src_row in range(start, height, step):
            src_start = src_row * width
            dst_start = dst_row * width
            for col in range(width):
                result[dst_start + col] = normal[src_start + col]
            dst_row += 1

    return result
