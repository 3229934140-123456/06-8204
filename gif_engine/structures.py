from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union
import struct


@dataclass
class GIFSignature:
    signature: str = "GIF"
    version: str = "89a"

    @classmethod
    def from_bytes(cls, data: bytes) -> "GIFSignature":
        sig = data[:3].decode("ascii")
        ver = data[3:6].decode("ascii")
        if sig != "GIF":
            raise ValueError(f"Invalid GIF signature: {sig}")
        if ver not in ("87a", "89a"):
            raise ValueError(f"Unsupported GIF version: {ver}")
        return cls(signature=sig, version=ver)

    def to_bytes(self) -> bytes:
        return (self.signature + self.version).encode("ascii")


@dataclass
class LogicalScreenDescriptor:
    width: int = 0
    height: int = 0
    global_color_table_flag: bool = False
    color_resolution: int = 7
    sort_flag: bool = False
    global_color_table_size: int = 0
    background_color_index: int = 0
    pixel_aspect_ratio: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> "LogicalScreenDescriptor":
        if len(data) < 7:
            raise ValueError("Logical Screen Descriptor too short")
        width, height = struct.unpack("<HH", data[0:4])
        packed = data[4]
        gct_flag = bool(packed & 0x80)
        color_res = (packed >> 4) & 0x07
        sort = bool(packed & 0x08)
        gct_size = packed & 0x07
        bg_idx = data[5]
        aspect = data[6]
        return cls(
            width=width,
            height=height,
            global_color_table_flag=gct_flag,
            color_resolution=color_res,
            sort_flag=sort,
            global_color_table_size=gct_size,
            background_color_index=bg_idx,
            pixel_aspect_ratio=aspect,
        )

    def to_bytes(self) -> bytes:
        packed = 0
        if self.global_color_table_flag:
            packed |= 0x80
        packed |= (self.color_resolution & 0x07) << 4
        if self.sort_flag:
            packed |= 0x08
        packed |= self.global_color_table_size & 0x07
        return struct.pack(
            "<HHBBB",
            self.width,
            self.height,
            packed,
            self.background_color_index,
            self.pixel_aspect_ratio,
        )

    @property
    def global_color_table_entries(self) -> int:
        if not self.global_color_table_flag:
            return 0
        return 2 ** (self.global_color_table_size + 1)


@dataclass
class ColorTable:
    colors: List[Tuple[int, int, int]] = field(default_factory=list)

    @classmethod
    def from_bytes(cls, data: bytes, num_colors: int) -> "ColorTable":
        expected = num_colors * 3
        if len(data) < expected:
            raise ValueError(
                f"Color table too short: expected {expected}, got {len(data)}"
            )
        colors = []
        for i in range(num_colors):
            r = data[i * 3]
            g = data[i * 3 + 1]
            b = data[i * 3 + 2]
            colors.append((r, g, b))
        return cls(colors=colors)

    def to_bytes(self) -> bytes:
        result = bytearray()
        for r, g, b in self.colors:
            result.append(r & 0xFF)
            result.append(g & 0xFF)
            result.append(b & 0xFF)
        return bytes(result)

    def __len__(self) -> int:
        return len(self.colors)

    def __getitem__(self, idx: int) -> Tuple[int, int, int]:
        return self.colors[idx]

    def pad_to_power_of_two(self) -> None:
        if not self.colors:
            self.colors = [(0, 0, 0)]
        target = 2
        while target < len(self.colors):
            target *= 2
        target = min(target, 256)
        while len(self.colors) < target:
            self.colors.append((0, 0, 0))

    @property
    def size_code(self) -> int:
        self.pad_to_power_of_two()
        n = len(self.colors)
        size = 0
        while (1 << (size + 1)) < n:
            size += 1
        return min(size, 7)


@dataclass
class GraphicControlExtension:
    disposal_method: int = 0
    user_input_flag: bool = False
    transparent_color_flag: bool = False
    delay_time: int = 0
    transparent_color_index: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> "GraphicControlExtension":
        if len(data) < 4:
            raise ValueError("Graphic Control Extension too short")
        packed = data[0]
        disposal = (packed >> 2) & 0x07
        user_input = bool(packed & 0x02)
        tc_flag = bool(packed & 0x01)
        delay = struct.unpack("<H", data[1:3])[0]
        tc_idx = data[3]
        return cls(
            disposal_method=disposal,
            user_input_flag=user_input,
            transparent_color_flag=tc_flag,
            delay_time=delay,
            transparent_color_index=tc_idx,
        )

    def to_bytes(self) -> bytes:
        packed = 0
        packed |= (self.disposal_method & 0x07) << 2
        if self.user_input_flag:
            packed |= 0x02
        if self.transparent_color_flag:
            packed |= 0x01
        delay_bytes = struct.pack("<H", self.delay_time & 0xFFFF)
        return bytes([packed]) + delay_bytes + bytes([self.transparent_color_index & 0xFF])


@dataclass
class ImageDescriptor:
    left: int = 0
    top: int = 0
    width: int = 0
    height: int = 0
    local_color_table_flag: bool = False
    interlace_flag: bool = False
    sort_flag: bool = False
    local_color_table_size: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> "ImageDescriptor":
        if len(data) < 9:
            raise ValueError("Image Descriptor too short")
        left, top, width, height = struct.unpack("<HHHH", data[0:8])
        packed = data[8]
        lct_flag = bool(packed & 0x80)
        interlace = bool(packed & 0x40)
        sort = bool(packed & 0x20)
        lct_size = packed & 0x07
        return cls(
            left=left,
            top=top,
            width=width,
            height=height,
            local_color_table_flag=lct_flag,
            interlace_flag=interlace,
            sort_flag=sort,
            local_color_table_size=lct_size,
        )

    def to_bytes(self) -> bytes:
        packed = 0
        if self.local_color_table_flag:
            packed |= 0x80
        if self.interlace_flag:
            packed |= 0x40
        if self.sort_flag:
            packed |= 0x20
        packed |= self.local_color_table_size & 0x07
        return struct.pack("<HHHHB", self.left, self.top, self.width, self.height, packed)

    @property
    def local_color_table_entries(self) -> int:
        if not self.local_color_table_flag:
            return 0
        return 2 ** (self.local_color_table_size + 1)


@dataclass
class ApplicationExtension:
    application_identifier: str = ""
    authentication_code: bytes = b""
    data: bytes = b""

    @classmethod
    def from_bytes(cls, data: bytes) -> "ApplicationExtension":
        if len(data) < 11:
            raise ValueError("Application Extension too short")
        app_id = data[0:8].decode("ascii", errors="replace")
        auth = data[8:11]
        app_data = data[11:]
        return cls(
            application_identifier=app_id,
            authentication_code=auth,
            data=app_data,
        )

    @property
    def is_netscape_looping(self) -> bool:
        return (
            self.application_identifier == "NETSCAPE"
            and self.authentication_code == b"2.0"
        )

    @property
    def loop_count(self) -> Optional[int]:
        if not self.is_netscape_looping or len(self.data) < 3:
            return None
        return struct.unpack("<H", self.data[1:3])[0]


@dataclass
class CommentExtension:
    comment: str = ""

    @classmethod
    def from_bytes(cls, data: bytes) -> "CommentExtension":
        return cls(comment=data.decode("latin-1", errors="replace"))


@dataclass
class GIFFrame:
    image_descriptor: ImageDescriptor
    pixel_indices: List[int] = field(default_factory=list)
    local_color_table: Optional[ColorTable] = None
    graphic_control_extension: Optional[GraphicControlExtension] = None

    @property
    def width(self) -> int:
        return self.image_descriptor.width

    @property
    def height(self) -> int:
        return self.image_descriptor.height

    @property
    def left(self) -> int:
        return self.image_descriptor.left

    @property
    def top(self) -> int:
        return self.image_descriptor.top

    @property
    def interlaced(self) -> bool:
        return self.image_descriptor.interlace_flag

    @property
    def disposal_method(self) -> int:
        if self.graphic_control_extension:
            return self.graphic_control_extension.disposal_method
        return 0

    @property
    def delay_time(self) -> int:
        if self.graphic_control_extension:
            return self.graphic_control_extension.delay_time
        return 0

    @property
    def has_transparency(self) -> bool:
        if self.graphic_control_extension:
            return self.graphic_control_extension.transparent_color_flag
        return False

    @property
    def transparent_index(self) -> int:
        if self.graphic_control_extension:
            return self.graphic_control_extension.transparent_color_index
        return -1


@dataclass
class GIFImage:
    signature: GIFSignature = field(default_factory=GIFSignature)
    logical_screen: LogicalScreenDescriptor = field(default_factory=LogicalScreenDescriptor)
    global_color_table: Optional[ColorTable] = None
    frames: List[GIFFrame] = field(default_factory=list)
    application_extensions: List[ApplicationExtension] = field(default_factory=list)
    comment_extensions: List[CommentExtension] = field(default_factory=list)
    blocks: List[Block] = field(default_factory=list)

    @property
    def width(self) -> int:
        return self.logical_screen.width

    @property
    def height(self) -> int:
        return self.logical_screen.height

    @property
    def loop_count(self) -> Optional[int]:
        for ext in self.application_extensions:
            lc = ext.loop_count
            if lc is not None:
                return lc
        return None

    def get_effective_color_table(self, frame_idx: int) -> ColorTable:
        frame = self.frames[frame_idx]
        if frame.local_color_table is not None:
            return frame.local_color_table
        if self.global_color_table is not None:
            return self.global_color_table
        raise ValueError("No color table available for frame")

    def rebuild_blocks_from_frames(self) -> None:
        self.blocks = []
        for ext in self.application_extensions:
            self.blocks.append(Block(type=BlockType.APPLICATION_EXTENSION, data=ext))
        for ext in self.comment_extensions:
            self.blocks.append(Block(type=BlockType.COMMENT_EXTENSION, data=ext))
        for i, frame in enumerate(self.frames):
            self.blocks.append(Block(type=BlockType.FRAME, data=frame, index=i))


class BlockType:
    APPLICATION_EXTENSION = "application"
    COMMENT_EXTENSION = "comment"
    FRAME = "frame"


@dataclass
class Block:
    type: str
    data: Union["ApplicationExtension", "CommentExtension", "GIFFrame"]
    index: int = -1
