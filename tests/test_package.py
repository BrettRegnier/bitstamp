"""Check the installed distribution and its public entry points."""

from importlib.metadata import metadata, version
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from PIL import Image


class InstalledPackageTests(unittest.TestCase):
    def test_distribution_metadata(self):
        info = metadata("bitmap-to-c-array")
        self.assertEqual(info["Requires-Python"], ">=3.10")
        self.assertEqual(info["License-Expression"], "MIT")
        self.assertTrue(any(requirement.startswith("Pillow")
                            for requirement in info.get_all("Requires-Dist")))

    def test_module_and_console_entry_points(self):
        executable = shutil.which("bitmap-to-c-array")
        self.assertIsNotNone(executable, "Install the project before running the tests")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.png"
            Image.new("RGB", (16, 16), "black").save(path)
            for command in ([sys.executable, "-m", "bitmap_to_c_array"], [executable]):
                with self.subTest(command=command):
                    result = subprocess.run(
                        [*command, str(path), "--format", "hex", "--name", "icon"],
                        cwd=directory, capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("#define icon_cols 2\n", result.stdout)
                    self.assertIn("const uint8_t icon[] =\n{", result.stdout)
                    self.assertEqual(result.stdout.count("0xff"), 32)
                    result = subprocess.run(
                        [*command, "--version"], cwd=directory, capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), version("bitmap-to-c-array"))
