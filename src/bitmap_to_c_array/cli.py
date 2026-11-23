"""Command-line interface for converting images to C or C++."""

import argparse
from importlib.metadata import version
from pathlib import Path
import sys

from PIL import Image

from .core import _image_to_bitmap, format_c_array


def main(argv: list[str] | None = None) -> int:
    """Run the CLI, returning zero on success."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=version("bitmap-to-c-array"))
    parser.add_argument("image", type=Path, help="input image (PNG, JPEG, BMP, etc.)")
    parser.add_argument("-o", "--output", type=Path, help="output file (default: stdout)")
    parser.add_argument("-n", "--name", default="bitmap", help="C array name (default: bitmap)")
    parser.add_argument(
        "--language", choices=("c", "c++"), default="c",
        help="output language (default: c)",
    )
    parser.add_argument(
        "-f", "--format", choices=("binary", "hex", "decimal"), default="binary",
        help="byte literal format (default: binary)",
    )
    parser.add_argument(
        "--white-threshold", type=int, default=250, metavar="0-255",
        help="minimum value of every RGB channel to count as white (default: 250)",
    )
    args = parser.parse_args(argv)

    try:
        data, cols, rows, width = _image_to_bitmap(args.image, args.white_threshold)
        output = format_c_array(data, args.name, args.format, cols=cols, rows=rows,
                                width=width, language=args.language)
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            sys.stdout.write(output)
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        parser.exit(1, f"error: {error}\n")
    return 0
