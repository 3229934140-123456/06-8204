import struct
from io import BytesIO
from typing import Optional

from .structures import (
    GIFSignature,
    LogicalScreenDescriptor,
    ColorTable,
    GraphicControlExtension,
    ImageDescriptor,
    ApplicationExtension,
    CommentExtension,
    GIFFrame,
    GIFImage,
)
from .lzw import lzw_decode
from .quantizer import deinterlace_indices


EXTENSION_INTRODUCER = 0x21
IMAGE_DESCRIPTOR_SEPARATOR = 0x2C
TRAILER = 0x3B

LABEL_GRAPHIC_CONTROL = 0xF9
LABEL_APPLICATION = 0xFF
LABEL_COMMENT = 0xFE
LABEL_PLAIN_TEXT = 0x01


class GIFDecoder:
    def __init__(self, data: Optional[bytes] = None):
        self._data = data
        self._pos = 0
        self._result: Optional[GIFImage] = None

    def decode(self, data: Optional[bytes] = None) -> GIFImage:
        if data is not None:
            self._data = data
            self._pos = 0

        if self._data is None:
            raise ValueError("No data provided for decoding")

        result = GIFImage()

        result.signature = self._decode_signature()
        result.logical_screen = self._decode_logical_screen()

        if result.logical_screen.global_color_table_flag:
            num_colors = result.logical_screen.global_color_table_entries
            gct_bytes = self._read(num_colors * 3)
            result.global_color_table = ColorTable.from_bytes(gct_bytes, num_colors)

        pending_gce: Optional[GraphicControlExtension] = None

        while self._pos < len(self._data):
            block_type = self._read_byte()

            if block_type == TRAILER:
                break
            elif block_type == EXTENSION_INTRODUCER:
                label = self._read_byte()
                if label == LABEL_GRAPHIC_CONTROL:
                    pending_gce = self._decode_graphic_control_extension()
                elif label == LABEL_APPLICATION:
                    app_ext = self._decode_application_extension()
                    result.application_extensions.append(app_ext)
                elif label == LABEL_COMMENT:
                    comment_ext = self._decode_comment_extension()
                    result.comment_extensions.append(comment_ext)
                elif label == LABEL_PLAIN_TEXT:
                    self._skip_sub_blocks()
                else:
                    self._skip_sub_blocks()
            elif block_type == IMAGE_DESCRIPTOR_SEPARATOR:
                frame = self._decode_image_descriptor_and_data(pending_gce)
                result.frames.append(frame)
                pending_gce = None
            else:
                raise ValueError(
                    f"Unexpected block type at offset {self._pos - 1}: 0x{block_type:02X}"
                )

        self._result = result
        return result

    def _decode_signature(self) -> GIFSignature:
        data = self._read(6)
        return GIFSignature.from_bytes(data)

    def _decode_logical_screen(self) -> LogicalScreenDescriptor:
        data = self._read(7)
        return LogicalScreenDescriptor.from_bytes(data)

    def _decode_graphic_control_extension(self) -> GraphicControlExtension:
        block_size = self._read_byte()
        if block_size != 4:
            raise ValueError(
                f"Invalid Graphic Control Extension block size: {block_size}"
            )
        data = self._read(4)
        self._expect_block_terminator()
        return GraphicControlExtension.from_bytes(data)

    def _decode_application_extension(self) -> ApplicationExtension:
        block_size = self._read_byte()
        if block_size != 11:
            raise ValueError(
                f"Invalid Application Extension block size: {block_size}"
            )
        header = self._read(11)
        data_blocks = self._read_sub_blocks()
        return ApplicationExtension.from_bytes(header + data_blocks)

    def _decode_comment_extension(self) -> CommentExtension:
        data = self._read_sub_blocks()
        return CommentExtension.from_bytes(data)

    def _decode_image_descriptor_and_data(
        self, gce: Optional[GraphicControlExtension]
    ) -> GIFFrame:
        desc_bytes = self._read(9)
        descriptor = ImageDescriptor.from_bytes(desc_bytes)

        local_color_table: Optional[ColorTable] = None
        if descriptor.local_color_table_flag:
            num_colors = descriptor.local_color_table_entries
            lct_bytes = self._read(num_colors * 3)
            local_color_table = ColorTable.from_bytes(lct_bytes, num_colors)

        lzw_min_code_size = self._read_byte()
        image_data = self._read_sub_blocks()

        expected_pixels = descriptor.width * descriptor.height
        indices = lzw_decode(image_data, lzw_min_code_size, expected_pixels)

        if descriptor.interlace_flag:
            indices = deinterlace_indices(indices, descriptor.width, descriptor.height)

        frame = GIFFrame(
            image_descriptor=descriptor,
            pixel_indices=indices,
            local_color_table=local_color_table,
            graphic_control_extension=gce,
        )
        return frame

    def _read(self, n: int) -> bytes:
        if self._pos + n > len(self._data):
            raise ValueError(
                f"Unexpected end of data at offset {self._pos}, need {n} bytes"
            )
        result = self._data[self._pos : self._pos + n]
        self._pos += n
        return result

    def _read_byte(self) -> int:
        return self._read(1)[0]

    def _read_sub_block(self) -> Optional[bytes]:
        size = self._read_byte()
        if size == 0:
            return None
        return self._read(size)

    def _read_sub_blocks(self) -> bytes:
        result = bytearray()
        while True:
            block = self._read_sub_block()
            if block is None:
                break
            result.extend(block)
        return bytes(result)

    def _skip_sub_blocks(self) -> None:
        while True:
            size = self._read_byte()
            if size == 0:
                break
            self._read(size)

    def _expect_block_terminator(self) -> None:
        term = self._read_byte()
        if term != 0:
            raise ValueError(
                f"Expected block terminator (0x00) at offset {self._pos - 1}, got 0x{term:02X}"
            )

    @classmethod
    def from_file(cls, filepath: str) -> GIFImage:
        with open(filepath, "rb") as f:
            data = f.read()
        decoder = cls(data)
        return decoder.decode()

    @classmethod
    def from_bytes(cls, data: bytes) -> GIFImage:
        decoder = cls(data)
        return decoder.decode()
