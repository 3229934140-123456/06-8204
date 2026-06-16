import struct
from typing import List, Optional, Tuple

from .structures import (
    GIFSignature,
    LogicalScreenDescriptor,
    ColorTable,
    GraphicControlExtension,
    ImageDescriptor,
    ApplicationExtension,
    GIFFrame,
    GIFImage,
)
from .lzw import lzw_encode
from .quantizer import quantize_image, interlace_indices


EXTENSION_INTRODUCER = 0x21
IMAGE_DESCRIPTOR_SEPARATOR = 0x2C
TRAILER = 0x3B
LABEL_GRAPHIC_CONTROL = 0xF9
LABEL_APPLICATION = 0xFF


class GIFEncoder:
    def __init__(
        self,
        width: int = 0,
        height: int = 0,
        loop_count: Optional[int] = 0,
        background_color_index: int = 0,
    ):
        self.width = width
        self.height = height
        self.loop_count = loop_count
        self.background_color_index = background_color_index
        self.global_color_table: Optional[ColorTable] = None
        self._frames: List[dict] = []

    def set_global_color_table(self, color_table: ColorTable) -> None:
        self.global_color_table = color_table

    def add_frame(
        self,
        rgba_pixels: List[Tuple[int, int, int, int]],
        frame_width: Optional[int] = None,
        frame_height: Optional[int] = None,
        left: int = 0,
        top: int = 0,
        delay_ms: int = 100,
        disposal_method: int = 0,
        use_local_palette: bool = False,
        interlaced: bool = False,
        max_colors: int = 256,
    ) -> None:
        if frame_width is None or frame_height is None:
            frame_width = self.width - left
            frame_height = self.height - top

        expected_pixels = frame_width * frame_height
        if len(rgba_pixels) != expected_pixels:
            raise ValueError(
                f"Pixel count mismatch: expected {expected_pixels}, got {len(rgba_pixels)}"
            )

        color_table, indices, transparent_idx = quantize_image(
            rgba_pixels, max_colors=max_colors
        )

        if interlaced:
            indices = interlace_indices(indices, frame_width, frame_height)

        frame_info = {
            "rgba_pixels": rgba_pixels,
            "width": frame_width,
            "height": frame_height,
            "left": left,
            "top": top,
            "delay_time": delay_ms // 10,
            "disposal_method": disposal_method,
            "interlaced": interlaced,
            "color_table": color_table,
            "indices": indices,
            "transparent_index": transparent_idx if transparent_idx is not None else -1,
            "has_transparency": transparent_idx is not None,
            "use_local_palette": use_local_palette,
        }
        self._frames.append(frame_info)

        if not use_local_palette and self.global_color_table is None:
            self.global_color_table = color_table

    def _build_gif_image(self) -> GIFImage:
        gif = GIFImage()
        gif.signature = GIFSignature(version="89a")

        has_gct = self.global_color_table is not None
        gct_size_code = 0
        if has_gct:
            self.global_color_table.pad_to_power_of_two()
            gct_size_code = self.global_color_table.size_code

        gif.logical_screen = LogicalScreenDescriptor(
            width=self.width,
            height=self.height,
            global_color_table_flag=has_gct,
            color_resolution=7,
            sort_flag=False,
            global_color_table_size=gct_size_code,
            background_color_index=self.background_color_index if has_gct else 0,
            pixel_aspect_ratio=0,
        )

        if has_gct:
            gif.global_color_table = self.global_color_table

        if self.loop_count is not None and len(self._frames) > 1:
            loop_data = struct.pack("<BH", 1, self.loop_count & 0xFFFF)
            app_ext = ApplicationExtension(
                application_identifier="NETSCAPE",
                authentication_code=b"2.0",
                data=loop_data,
            )
            gif.application_extensions.append(app_ext)

        for frame_info in self._frames:
            use_local = frame_info["use_local_palette"] or not has_gct
            ct = frame_info["color_table"]
            if use_local:
                ct.pad_to_power_of_two()

            lct_flag = use_local
            lct_size = ct.size_code if use_local else 0

            gce = GraphicControlExtension(
                disposal_method=frame_info["disposal_method"],
                user_input_flag=False,
                transparent_color_flag=frame_info["has_transparency"],
                delay_time=frame_info["delay_time"],
                transparent_color_index=frame_info["transparent_index"]
                if frame_info["has_transparency"]
                else 0,
            )

            desc = ImageDescriptor(
                left=frame_info["left"],
                top=frame_info["top"],
                width=frame_info["width"],
                height=frame_info["height"],
                local_color_table_flag=lct_flag,
                interlace_flag=frame_info["interlaced"],
                sort_flag=False,
                local_color_table_size=lct_size,
            )

            frame = GIFFrame(
                image_descriptor=desc,
                pixel_indices=frame_info["indices"],
                local_color_table=ct if use_local else None,
                graphic_control_extension=gce,
            )
            gif.frames.append(frame)

        return gif

    def encode(self) -> bytes:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Invalid canvas dimensions")
        if not self._frames:
            raise ValueError("No frames to encode")

        gif = self._build_gif_image()
        return self._encode_gif_image(gif)

    def _encode_gif_image(self, gif: GIFImage) -> bytes:
        result = bytearray()

        result.extend(gif.signature.to_bytes())
        result.extend(gif.logical_screen.to_bytes())

        if gif.global_color_table is not None:
            result.extend(gif.global_color_table.to_bytes())

        for ext in gif.application_extensions:
            result.append(EXTENSION_INTRODUCER)
            result.append(LABEL_APPLICATION)
            result.append(11)
            app_id_bytes = ext.application_identifier.encode("ascii")[:8]
            app_id_bytes = app_id_bytes.ljust(8, b"\x00")
            result.extend(app_id_bytes)
            auth_bytes = ext.authentication_code[:3]
            auth_bytes = auth_bytes.ljust(3, b"\x00")
            result.extend(auth_bytes)
            self._write_sub_blocks(result, ext.data)

        for frame in gif.frames:
            if frame.graphic_control_extension is not None:
                result.append(EXTENSION_INTRODUCER)
                result.append(LABEL_GRAPHIC_CONTROL)
                result.append(4)
                result.extend(frame.graphic_control_extension.to_bytes())
                result.append(0)

            result.append(IMAGE_DESCRIPTOR_SEPARATOR)
            result.extend(frame.image_descriptor.to_bytes())

            if frame.local_color_table is not None:
                result.extend(frame.local_color_table.to_bytes())

            effective_ct = gif.get_effective_color_table(gif.frames.index(frame))
            lzw_min_code_size = max(2, effective_ct.size_code + 1)
            if lzw_min_code_size < 2:
                lzw_min_code_size = 2

            compressed = lzw_encode(frame.pixel_indices, lzw_min_code_size)
            result.append(lzw_min_code_size)
            self._write_sub_blocks(result, compressed)

        result.append(TRAILER)
        return bytes(result)

    @staticmethod
    def _write_sub_blocks(buffer: bytearray, data: bytes) -> None:
        offset = 0
        while offset < len(data):
            block_size = min(255, len(data) - offset)
            buffer.append(block_size)
            buffer.extend(data[offset : offset + block_size])
            offset += block_size
        buffer.append(0)

    def save(self, filepath: str) -> None:
        data = self.encode()
        with open(filepath, "wb") as f:
            f.write(data)

    def get_bytes(self) -> bytes:
        return self.encode()

    @staticmethod
    def from_gif_image(gif: GIFImage) -> bytes:
        result = bytearray()

        result.extend(gif.signature.to_bytes())
        result.extend(gif.logical_screen.to_bytes())

        if gif.global_color_table is not None:
            result.extend(gif.global_color_table.to_bytes())

        for ext in gif.application_extensions:
            result.append(EXTENSION_INTRODUCER)
            result.append(LABEL_APPLICATION)
            result.append(11)
            app_id_bytes = ext.application_identifier.encode("ascii")[:8]
            app_id_bytes = app_id_bytes.ljust(8, b"\x00")
            result.extend(app_id_bytes)
            auth_bytes = ext.authentication_code[:3]
            auth_bytes = auth_bytes.ljust(3, b"\x00")
            result.extend(auth_bytes)
            GIFEncoder._write_sub_blocks(result, ext.data)

        for ext in gif.comment_extensions:
            result.append(EXTENSION_INTRODUCER)
            result.append(0xFE)
            comment_bytes = ext.comment.encode("latin-1")
            GIFEncoder._write_sub_blocks(result, comment_bytes)

        for frame_idx, frame in enumerate(gif.frames):
            if frame.graphic_control_extension is not None:
                result.append(EXTENSION_INTRODUCER)
                result.append(LABEL_GRAPHIC_CONTROL)
                result.append(4)
                result.extend(frame.graphic_control_extension.to_bytes())
                result.append(0)

            result.append(IMAGE_DESCRIPTOR_SEPARATOR)
            result.extend(frame.image_descriptor.to_bytes())

            if frame.local_color_table is not None:
                result.extend(frame.local_color_table.to_bytes())

            effective_ct = gif.get_effective_color_table(frame_idx)
            lzw_min_code_size = max(2, effective_ct.size_code + 1)

            compressed = lzw_encode(frame.pixel_indices, lzw_min_code_size)
            result.append(lzw_min_code_size)
            GIFEncoder._write_sub_blocks(result, compressed)

        result.append(TRAILER)
        return bytes(result)
