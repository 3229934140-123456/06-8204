from enum import IntEnum
from typing import List, Optional, Tuple, Callable

from .structures import GIFImage, GIFFrame, ColorTable


class DisposalMethod(IntEnum):
    NO_DISPOSAL = 0
    DO_NOT_DISPOSE = 1
    RESTORE_TO_BACKGROUND = 2
    RESTORE_TO_PREVIOUS = 3


class RenderedFrame:
    def __init__(
        self,
        rgba_data: List[Tuple[int, int, int, int]],
        width: int,
        height: int,
        delay_ms: int,
    ):
        self.rgba_data = rgba_data
        self.width = width
        self.height = height
        self.delay_ms = delay_ms

    def get_pixel(self, x: int, y: int) -> Tuple[int, int, int, int]:
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return (0, 0, 0, 0)
        return self.rgba_data[y * self.width + x]


class GIFRenderer:
    def __init__(self, gif_image: GIFImage):
        self.gif = gif_image
        self.width = gif_image.width
        self.height = gif_image.height
        self._canvas: List[Tuple[int, int, int, int]] = []
        self._saved_canvas: List[Tuple[int, int, int, int]] = []
        self._initialize_canvas()

    def _initialize_canvas(self) -> None:
        bg_color = self._get_background_color()
        self._canvas = [bg_color] * (self.width * self.height)
        self._saved_canvas = [bg_color] * (self.width * self.height)

    def _get_background_color(self) -> Tuple[int, int, int, int]:
        if self.gif.global_color_table and self.gif.logical_screen.background_color_index < len(
            self.gif.global_color_table
        ):
            r, g, b = self.gif.global_color_table[
                self.gif.logical_screen.background_color_index
            ]
            return (r, g, b, 255)
        return (0, 0, 0, 0)

    def _get_frame_color_table(self, frame: GIFFrame) -> ColorTable:
        return self.gif.get_effective_color_table(self.gif.frames.index(frame))

    def _dispose_previous_frame(self, frame: GIFFrame, frame_idx: int) -> None:
        if frame_idx == 0:
            return

        prev_frame = self.gif.frames[frame_idx - 1]
        disposal = prev_frame.disposal_method

        if disposal == DisposalMethod.NO_DISPOSAL:
            pass
        elif disposal == DisposalMethod.DO_NOT_DISPOSE:
            pass
        elif disposal == DisposalMethod.RESTORE_TO_BACKGROUND:
            self._clear_frame_area(prev_frame)
        elif disposal == DisposalMethod.RESTORE_TO_PREVIOUS:
            self._restore_saved_canvas()

    def _save_canvas(self) -> None:
        self._saved_canvas = list(self._canvas)

    def _restore_saved_canvas(self) -> None:
        self._canvas = list(self._saved_canvas)

    def _clear_frame_area(self, frame: GIFFrame) -> None:
        bg_color = self._get_background_color()
        for y in range(frame.top, frame.top + frame.height):
            if y < 0 or y >= self.height:
                continue
            for x in range(frame.left, frame.left + frame.width):
                if x < 0 or x >= self.width:
                    continue
                self._canvas[y * self.width + x] = bg_color

    def _render_frame_to_canvas(self, frame: GIFFrame) -> None:
        color_table = self._get_frame_color_table(frame)
        transparent_idx = frame.transparent_index if frame.has_transparency else -1

        for rel_y in range(frame.height):
            abs_y = frame.top + rel_y
            if abs_y < 0 or abs_y >= self.height:
                continue
            for rel_x in range(frame.width):
                abs_x = frame.left + rel_x
                if abs_x < 0 or abs_x >= self.width:
                    continue

                idx_pos = rel_y * frame.width + rel_x
                if idx_pos >= len(frame.pixel_indices):
                    continue

                pixel_idx = frame.pixel_indices[idx_pos]

                if frame.has_transparency and pixel_idx == transparent_idx:
                    continue

                if pixel_idx < 0 or pixel_idx >= len(color_table):
                    continue

                r, g, b = color_table[pixel_idx]
                self._canvas[abs_y * self.width + abs_x] = (r, g, b, 255)

    def render_frame(self, frame_idx: int) -> RenderedFrame:
        if frame_idx < 0 or frame_idx >= len(self.gif.frames):
            raise IndexError(f"Frame index {frame_idx} out of range")

        frame = self.gif.frames[frame_idx]

        if frame_idx > 0:
            prev_frame = self.gif.frames[frame_idx - 1]
            if prev_frame.disposal_method == DisposalMethod.RESTORE_TO_PREVIOUS:
                pass
            elif prev_frame.disposal_method == DisposalMethod.RESTORE_TO_BACKGROUND:
                self._clear_frame_area(prev_frame)

        current_disposal = frame.disposal_method
        if current_disposal == DisposalMethod.RESTORE_TO_PREVIOUS:
            self._save_canvas()

        self._render_frame_to_canvas(frame)

        delay_ms = frame.delay_time * 10
        if delay_ms == 0:
            delay_ms = 100

        return RenderedFrame(
            rgba_data=list(self._canvas),
            width=self.width,
            height=self.height,
            delay_ms=delay_ms,
        )

    def render_all_frames(self) -> List[RenderedFrame]:
        self._initialize_canvas()
        results = []
        for i in range(len(self.gif.frames)):
            results.append(self.render_frame(i))
        return results

    def reset(self) -> None:
        self._initialize_canvas()

    def iterate_frames(
        self, callback: Callable[[int, RenderedFrame], None]
    ) -> None:
        self._initialize_canvas()
        for i in range(len(self.gif.frames)):
            rendered = self.render_frame(i)
            callback(i, rendered)

    @property
    def loop_count(self) -> Optional[int]:
        return self.gif.loop_count

    @property
    def num_frames(self) -> int:
        return len(self.gif.frames)
