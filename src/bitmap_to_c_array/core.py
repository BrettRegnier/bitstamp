"""Convert images to a packed, monochrome C uint8_t array."""

from pathlib import Path
import re

from PIL import Image


def image_to_bytes(image_path: str | Path, white_threshold: int = 250) -> bytearray:
    """Pack non-white pixels as 1 bits, left-to-right then top-to-bottom.

    A pixel is white when all three RGB channels are >= white_threshold.
    Transparency is composited over white. Pixels are packed MSB first,
    with each row padded to a whole byte using zero low bits.
    """
    return _image_to_bitmap(image_path, white_threshold)[0]


def _image_to_bitmap(image_path: str | Path, white_threshold: int) -> tuple[bytearray, int, int, int]:
    """Return packed data, byte columns, pixel rows, and original pixel width."""
    if not 0 <= white_threshold <= 255:
        raise ValueError("white_threshold must be between 0 and 255")

    with Image.open(image_path) as source:
        rgba = source.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        rgb = Image.alpha_composite(background, rgba).convert("RGB")

    cols = (rgb.width + 7) // 8
    data = bytearray(cols * rgb.height)
    pixels = rgb.load()
    for y in range(rgb.height):
        for x in range(rgb.width):
            if min(pixels[x, y]) < white_threshold:
                data[y * cols + x // 8] |= 1 << (7 - x % 8)
    return data, cols, rgb.height, rgb.width


def format_c_array(
    data: bytes | bytearray, name: str = "bitmap", output_format: str = "binary",
    *, cols: int | None = None, rows: int | None = None,
    language: str = "c", width: int | None = None,
) -> str:
    """Format C data/macros or a C++ class with private constexpr members.

    C++ requires cols, rows, and the original pixel width. Height equals rows.
    """
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError("array name must be a valid C identifier")
    formats = {"binary": "#010b", "hex": "#04x", "decimal": "d"}
    if output_format not in formats:
        raise ValueError("output_format must be binary, hex, or decimal")
    if language not in ("c", "c++"):
        raise ValueError("language must be c or c++")

    lines = ["#include <stdint.h>", ""]
    if cols is not None or rows is not None:
        if cols is None or rows is None or cols <= 0 or rows <= 0 or cols * rows != len(data):
            raise ValueError("positive cols and rows must match the data length")
    if width is not None:
        if cols is None or rows is None or width <= 0 or (width + 7) // 8 != cols:
            raise ValueError("pixel width must match cols and requires rows")
    dimensions = {"cols": cols, "rows": rows}
    if width is not None:
        dimensions.update(width=width, height=rows)

    if language == "c++":
        if cols is None or rows is None or width is None:
            raise ValueError("C++ output requires cols, rows, and pixel width")
        lines.extend([f"class {name}_{width}x{rows}", "{", "private:",
                      "    // clang-format off"])
        lines.extend(f"    static constexpr unsigned int {key} = {value};"
                     for key, value in dimensions.items())
        lines.extend(["    static constexpr uint8_t bitmap[] =", "    {"])
        indent = "        "
    else:
        lines.extend(f"#define {name}_{key} {value}"
                     for key, value in dimensions.items() if value is not None)
        if cols is not None:
            lines.append("")
        lines.extend(["// clang-format off", f"const uint8_t {name}[] =", "{"])
        indent = "    "
    for start in range(0, len(data), 8):
        literals = ", ".join(format(value, formats[output_format])
                             for value in data[start:start + 8])
        lines.append(f"{indent}{literals},")
    if language == "c++":
        lines.extend(["    };", "    // clang-format on", "};"])
    else:
        lines.extend(["};", "// clang-format on"])
    return "\n".join(lines) + "\n"
