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
from .lzw import lzw_decode, lzw_encode
from .decoder import GIFDecoder
from .encoder import GIFEncoder
from .quantizer import quantize_image, median_cut_quantize
from .renderer import GIFRenderer, DisposalMethod

__all__ = [
    "GIFSignature",
    "LogicalScreenDescriptor",
    "ColorTable",
    "GraphicControlExtension",
    "ImageDescriptor",
    "ApplicationExtension",
    "CommentExtension",
    "GIFFrame",
    "GIFImage",
    "lzw_decode",
    "lzw_encode",
    "GIFDecoder",
    "GIFEncoder",
    "quantize_image",
    "median_cut_quantize",
    "GIFRenderer",
    "DisposalMethod",
]
