import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


REPOSITORY = pathlib.Path(__file__).resolve().parents[2]
RENDERER = REPOSITORY / "scripts" / "render-native-manifest.py"
EXTENSION_ID = "abcdefghijklmnopabcdefghijklmnop"


class RenderManifestTests(unittest.TestCase):
    """render-native-manifest.py is the single source of truth for the manifest.

    It is pure Python and platform-neutral, so a Windows `.bat` launcher renders
    exactly like a macOS `.sh` launcher; only the registration differs per OS.
    """

    def _render(self, launcher_name, launcher_body="launcher\n"):
        directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        launcher = directory / launcher_name
        launcher.write_text(launcher_body, encoding="utf-8")
        output = directory / "app.chessgenie.local_games.json"
        completed = subprocess.run(
            [
                sys.executable, str(RENDERER),
                "--extension-id", EXTENSION_ID,
                "--launcher", str(launcher),
                "--output", str(output),
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
        )
        return completed, launcher, output

    def _assert_valid_manifest(self, output, launcher):
        manifest = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "app.chessgenie.local_games")
        self.assertEqual(manifest["type"], "stdio")
        self.assertEqual(manifest["path"], str(launcher.resolve()))
        self.assertEqual(
            manifest["allowed_origins"],
            ["chrome-extension://{}/".format(EXTENSION_ID)],
        )

    def test_renders_a_manifest_for_a_windows_bat_launcher(self):
        completed, launcher, output = self._render(
            "launch.bat", "@echo off\r\npy -3 \"%~dp0host.py\" %*\r\n"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(output.is_file())
        self._assert_valid_manifest(output, launcher)
        self.assertTrue(json.loads(output.read_text())["path"].endswith("launch.bat"))

    def test_renders_a_manifest_for_a_macos_sh_launcher(self):
        completed, launcher, output = self._render("launch.sh")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self._assert_valid_manifest(output, launcher)
        self.assertTrue(json.loads(output.read_text())["path"].endswith("launch.sh"))

    def test_rejects_an_invalid_extension_id(self):
        directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        launcher = directory / "launch.bat"
        launcher.write_text("x", encoding="utf-8")
        output = directory / "manifest.json"
        completed = subprocess.run(
            [
                sys.executable, str(RENDERER),
                "--extension-id", "not-a-valid-extension-id",
                "--launcher", str(launcher),
                "--output", str(output),
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(output.exists())

    def test_rejects_a_missing_launcher(self):
        directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        completed = subprocess.run(
            [
                sys.executable, str(RENDERER),
                "--extension-id", EXTENSION_ID,
                "--launcher", str(directory / "does-not-exist.bat"),
                "--output", str(directory / "manifest.json"),
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
        )
        self.assertNotEqual(completed.returncode, 0)


if __name__ == "__main__":
    unittest.main()
