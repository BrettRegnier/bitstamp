import contextlib
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from PIL import Image

from bitmap_to_c_array import format_c_array, image_to_bytes
from bitmap_to_c_array.cli import main


class ImageConversionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def save_image(self, image, filename="image.png", **options):
        path = self.root / filename
        image.save(path, **options)
        return path

    def test_white_and_black_images_in_supported_formats(self):
        for extension in ("png", "jpg", "bmp"):
            for color, expected in (("white", 0x00), ("black", 0xFF)):
                with self.subTest(extension=extension, color=color):
                    path = self.save_image(Image.new("RGB", (16, 16), color),
                                           f"{color}.{extension}")
                    data = image_to_bytes(path)
                    self.assertIsInstance(data, bytearray)
                    self.assertEqual(data, bytearray([expected] * 32))

    def test_checkerboard_has_row_major_msb_first_order(self):
        image = Image.new("RGB", (16, 16), "white")
        for y in range(16):
            for x in range(16):
                if (x + y) % 2 == 0:
                    image.putpixel((x, y), (0, 0, 0))
        expected = bytearray([0xAA, 0xAA, 0x55, 0x55] * 8)
        self.assertEqual(image_to_bytes(self.save_image(image)), expected)

    def test_threshold_boundary_and_colored_pixels(self):
        image = Image.new("RGB", (16, 16), "white")
        colors = [(250, 250, 250), (249, 255, 255), (255, 249, 255),
                  (255, 255, 249), (255, 0, 0), (0, 255, 0),
                  (0, 0, 255), (254, 254, 254)]
        for x, color in enumerate(colors):
            image.putpixel((x, 0), color)
        path = self.save_image(image)
        self.assertEqual(image_to_bytes(path), bytearray([0b01111110] + [0] * 31))
        self.assertEqual(image_to_bytes(path, 255), bytearray([0xFF] + [0] * 31))
        self.assertEqual(image_to_bytes(path, 0), bytearray(32))

    def test_transparency_is_composited_over_white(self):
        image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        image.putpixel((0, 0), (0, 0, 0, 255))
        image.putpixel((1, 0), (0, 0, 0, 128))
        image.putpixel((2, 0), (0, 0, 0, 5))  # Becomes (250, 250, 250).
        self.assertEqual(image_to_bytes(self.save_image(image)),
                         bytearray([0b11000000] + [0] * 31))

    def test_grayscale_and_palette_images(self):
        gray = Image.new("L", (16, 16), 255)
        gray.putpixel((0, 0), 0)
        palette = Image.new("P", (16, 16), 0)
        palette.putpalette([255, 255, 255, 0, 0, 0] + [0] * 762)
        palette.putpixel((0, 0), 1)
        for image in (gray, palette):
            with self.subTest(mode=image.mode):
                self.assertEqual(image_to_bytes(self.save_image(image)),
                                 bytearray([0x80] + [0] * 31))

    def test_each_row_is_zero_padded_to_a_whole_byte(self):
        image = Image.new("RGB", (3, 3), "white")
        for point in ((0, 0), (0, 1), (2, 2)):
            image.putpixel(point, (0, 0, 0))
        self.assertEqual(image_to_bytes(self.save_image(image)),
                         bytearray([0b10000000, 0b10000000, 0b00100000]))

    def test_invalid_threshold(self):
        for threshold in (-1, 256):
            with self.subTest(threshold=threshold):
                with self.assertRaises(ValueError):
                    image_to_bytes(self.root / "unused.png", threshold)

    def test_invalid_image(self):
        path = self.root / "invalid.png"
        path.write_text("not an image", encoding="utf-8")
        with self.assertRaises(OSError):
            image_to_bytes(path)

    def test_cli_stdout_and_output_file(self):
        path = self.save_image(Image.new("RGB", (16, 16), "black"))
        expected = format_c_array(bytearray([255] * 32), "icon", cols=2, rows=16, width=16)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(main([str(path), "--name", "icon"]), 0)
        self.assertEqual(stdout.getvalue(), expected)

        output = self.root / "icon.h"
        self.assertEqual(main([str(path), "-n", "icon", "-o", str(output)]), 0)
        self.assertEqual(output.read_text(encoding="utf-8"), expected)

    def test_cli_default_name_format_and_dimensions(self):
        path = self.save_image(Image.new("RGB", (16, 16), "black"))
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(main([str(path)]), 0)
        text = stdout.getvalue()
        self.assertIn("#define bitmap_cols 2\n", text)
        self.assertIn("#define bitmap_rows 16\n", text)
        self.assertIn("#define bitmap_width 16\n", text)
        self.assertIn("#define bitmap_height 16\n", text)
        self.assertIn("const uint8_t bitmap[] =\n{", text)
        self.assertEqual(text.count("0b11111111"), 32)

    def test_cli_formats_and_dimensions_for_partial_byte_rows(self):
        path = self.save_image(Image.new("RGB", (9, 3), "black"))
        for output_format, expected in (
            ("binary", "0b11111111, 0b10000000"),
            ("hex", "0xff, 0x80"),
            ("decimal", "255, 128"),
        ):
            with self.subTest(output_format=output_format):
                output = self.root / f"{output_format}.h"
                self.assertEqual(main([str(path), "--format", output_format,
                                       "-o", str(output)]), 0)
                text = output.read_text(encoding="utf-8")
                self.assertIn("#define bitmap_cols 2\n", text)
                self.assertIn("#define bitmap_rows 3\n", text)
                self.assertEqual(text.count(expected), 3)

    def test_cli_cpp_uses_name_and_pixel_dimensions(self):
        path = self.save_image(Image.new("RGB", (9, 3), "black"))
        output = self.root / "icon.hpp"
        self.assertEqual(main([str(path), "--language", "c++", "--name", "My_Bitmap",
                               "--format", "hex", "--output", str(output)]), 0)
        text = output.read_text(encoding="utf-8")
        self.assertIn("class My_Bitmap_9x3\n{\nprivate:", text)
        self.assertIn("static constexpr unsigned int width = 9;", text)
        self.assertIn("static constexpr unsigned int height = 3;", text)
        self.assertIn("static constexpr unsigned int cols = 2;", text)
        self.assertIn("static constexpr unsigned int rows = 3;", text)
        self.assertIn("static constexpr uint8_t bitmap[] =\n    {", text)
        self.assertEqual(text.count("0xff, 0x80"), 3)
        self.assertNotIn("public:", text)
        self.assertLess(text.index("// clang-format off"), text.index("static constexpr"))
        self.assertGreater(text.index("// clang-format on"), text.index("bitmap[]"))

    def test_cli_rejects_invalid_format(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main(["unused.png", "--format", "octal"])
        self.assertEqual(error.exception.code, 2)

    def test_cli_reports_missing_file(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as error:
                main([str(self.root / "missing.png")])
        self.assertEqual(error.exception.code, 1)
        self.assertIn("error:", stderr.getvalue())


class CFormattingTests(unittest.TestCase):
    def test_default_array_name(self):
        self.assertIn("const uint8_t bitmap[] =\n{", format_c_array(b"\x00"))

    def test_binary_literals_and_declaration(self):
        self.assertEqual(
            format_c_array(bytearray([0, 0x81, 255]), "logo"),
            "#include <stdint.h>\n\n// clang-format off\nconst uint8_t logo[] =\n{\n"
            "    0b00000000, 0b10000001, 0b11111111,\n};\n// clang-format on\n",
        )

    def test_hex_and_decimal_literals(self):
        for output_format, expected in (("hex", "0x00, 0x81, 0xff"),
                                        ("decimal", "0, 129, 255")):
            with self.subTest(output_format=output_format):
                self.assertIn(expected, format_c_array(b"\x00\x81\xff",
                                                       output_format=output_format))

    def test_invalid_format(self):
        with self.assertRaises(ValueError):
            format_c_array(b"\x00", output_format="octal")

    def test_invalid_dimensions(self):
        for cols, rows in ((None, 1), (1, None), (0, 1), (1, -1), (2, 2)):
            with self.subTest(cols=cols, rows=rows):
                with self.assertRaises(ValueError):
                    format_c_array(b"\x00", cols=cols, rows=rows)

    def test_dimension_macros_are_name_prefixed(self):
        for name in ("cols", "rows"):
            with self.subTest(name=name):
                text = format_c_array(b"\x00", name=name, cols=1, rows=1)
                self.assertIn(f"#define {name}_cols 1\n", text)
                self.assertIn(f"#define {name}_rows 1\n", text)

    def test_invalid_language(self):
        with self.assertRaises(ValueError):
            format_c_array(b"\x00", language="rust")

    def test_cpp_requires_pixel_dimensions(self):
        for dimensions in ({}, {"cols": 1, "rows": 1}):
            with self.subTest(dimensions=dimensions):
                with self.assertRaises(ValueError):
                    format_c_array(b"\x00", language="c++", **dimensions)

    def test_invalid_pixel_width(self):
        for width in (0, -1, 9):
            with self.subTest(width=width):
                with self.assertRaises(ValueError):
                    format_c_array(b"\x00", cols=1, rows=1, width=width)

    def test_generated_output_compiles(self):
        if not shutil.which("gcc") or not shutil.which("g++"):
            self.skipTest("gcc and g++ are required for compilation checks")
        with tempfile.TemporaryDirectory() as directory:
            for language, compiler, standard in (("c", "gcc", "gnu11"),
                                                  ("c++", "g++", "c++17")):
                for output_format in ("binary", "hex", "decimal"):
                    with self.subTest(language=language, output_format=output_format):
                        source = format_c_array(b"\xff\x80" * 3, "icon", output_format,
                                                cols=2, rows=3, width=9, language=language)
                        if language == "c":
                            source += ('_Static_assert(icon_cols * icon_rows == sizeof(icon), "size");\n'
                                       '_Static_assert(icon_width == 9 && icon_height == 3, "pixels");\n')
                        else:
                            source += 'static_assert(sizeof(icon_9x3) > 0, "class exists");\n'
                        result = subprocess.run(
                            [compiler, "-x", language, f"-std={standard}", "-Wall", "-Wextra",
                             "-Werror", "-c", "-o", str(Path(directory) / "bitmap.o"), "-"],
                            input=source, text=True, capture_output=True,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_identifier(self):
        for name in ("", "123logo", "my-logo", "a; injected", "é"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    format_c_array(b"\x00", name)


if __name__ == "__main__":
    unittest.main()
