# bitmap-to-c-array

Convert PNG, JPEG, BMP, and other Pillow-supported images into packed monochrome
C arrays or C++ classes. Supports binary, hexadecimal, and decimal output.

## Installation

Requires Python 3.10 or later. Install from the project directory:

```sh
python -m pip install .
```

Pillow is installed automatically.

## Usage

```sh
bitmap-to-c-array image.png
bitmap-to-c-array logo.png --name logo --format hex --output logo.h
bitmap-to-c-array logo.png --language c++ --name Logo --output logo.hpp
bitmap-to-c-array image.png --white-threshold 240
```

Output goes to standard output unless `--output` is provided. You can also run
the tool with `python -m bitmap_to_c_array`.

| Option | Description | Default |
| --- | --- | --- |
| `-o`, `--output` | Output file | Standard output |
| `-n`, `--name` | Array name or C++ class name prefix | `bitmap` |
| `--language` | `c` or `c++` | `c` |
| `-f`, `--format` | `binary`, `hex`, or `decimal` | `binary` |
| `--white-threshold` | Minimum value of every RGB channel to count as white, from 0 to 255 | `250` |
| `--version` | Show the installed version | |
| `-h`, `--help` | Show usage information | |

### Output

A 16×1 image produces C output in this form:

```c
#include <stdint.h>

#define bitmap_cols 2
#define bitmap_rows 1
#define bitmap_width 16
#define bitmap_height 1

// clang-format off
const uint8_t bitmap[] =
{
    0b10000001, 0b00011000,
};
// clang-format on
```

Dimension macros use the supplied name as their prefix. `cols` is the row width
in bytes; `width` and `height` are measured in pixels.

C++ output uses a class named `<name>_<width>x<height>` with private
`static constexpr` members for the dimensions and bitmap array. C++17 or later
is recommended.

Binary literals require C23, C++14 or later, or a compiler extension. Use
`--format hex` or `--format decimal` for older language standards.

## Pixel format

- Pixels are read left to right, then top to bottom.
- A pixel is white when every RGB channel is at least the white threshold.
- White pixels become `0`; all other pixels become `1`.
- Transparent pixels are composited over white before conversion.
- Each byte holds eight pixels, starting with the most significant bit.
- Each row is padded with zero bits to a byte boundary.
- Animated images use the first frame.

The array contains `((width + 7) // 8) * height` bytes. Use PNG or BMP when exact
pixel values matter; JPEG compression can affect thresholding.

## Python API

```python
from bitmap_to_c_array import image_to_bytes, format_c_array

data = image_to_bytes("image.png", white_threshold=250)
source = format_c_array(data, name="logo", output_format="hex")
```

To include dimensions, pass `cols` and `rows`. For C++ output, also supply the
pixel width:

```python
source = format_c_array(
    data,
    name="Logo",
    language="c++",
    output_format="hex",
    cols=2,
    rows=16,
    width=16,
)
```

This example assumes a 16×16 source image.

## Development

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m unittest discover -v
```

On Windows, activate the environment with `.venv\Scripts\activate`.
Compiler integration tests run when GCC/G++ are available.

Build distributions:

```sh
python -m build
python -m twine check dist/*
```

## License

[MIT](LICENSE).
