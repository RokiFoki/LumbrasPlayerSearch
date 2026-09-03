import json
import os
import pathlib
import struct
import subprocess
import tempfile
import unittest


REPOSITORY = pathlib.Path(__file__).resolve().parents[2]
INSTALLER = REPOSITORY / "scripts" / "install-macos.sh"
UNINSTALLER = REPOSITORY / "scripts" / "uninstall-macos.sh"
EXTENSION_ID = "abcdefghijklmnopabcdefghijklmnop"


class MacosInstallScriptTests(unittest.TestCase):
    def test_installs_runnable_host_outside_repository_and_uninstalls_it(self):
        with tempfile.TemporaryDirectory() as temporary_home:
            environment = os.environ.copy()
            environment["HOME"] = temporary_home

            installed = subprocess.run(
                [str(INSTALLER), EXTENSION_ID],
                cwd=REPOSITORY,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)

            application_support = (
                pathlib.Path(temporary_home) / "Library" / "Application Support"
            )
            installed_host = application_support / "LubrasChessGenie" / "native-host"
            launcher = installed_host / "launch.sh"
            manifest = (
                application_support
                / "Google"
                / "Chrome"
                / "NativeMessagingHosts"
                / "app.chessgenie.local_games.json"
            )

            self.assertTrue(launcher.is_file())
            self.assertTrue(os.access(launcher, os.X_OK))
            self.assertTrue((installed_host / "host.py").is_file())
            self.assertTrue((installed_host / "scid" / "search-player.tcl").is_file())
            self.assertTrue((installed_host / "scid" / "export-games.tcl").is_file())

            with manifest.open("r", encoding="utf-8") as handle:
                manifest_value = json.load(handle)
            self.assertEqual(manifest_value["path"], str(launcher.resolve()))
            self.assertNotIn(str(REPOSITORY), manifest_value["path"])
            self.assertEqual(
                manifest_value["allowed_origins"],
                ["chrome-extension://{}/".format(EXTENSION_ID)],
            )

            request = {
                "protocolVersion": 1,
                "id": "installed-host-test",
                "command": "hello",
                "payload": {},
            }
            payload = json.dumps(request).encode("utf-8")
            response = subprocess.run(
                [str(launcher)],
                input=struct.pack("=I", len(payload)) + payload,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(response.returncode, 0, response.stderr.decode("utf-8"))
            response_length = struct.unpack("=I", response.stdout[:4])[0]
            response_value = json.loads(
                response.stdout[4 : 4 + response_length].decode("utf-8")
            )
            self.assertTrue(response_value["ok"])

            uninstalled = subprocess.run(
                [str(UNINSTALLER)],
                cwd=REPOSITORY,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(uninstalled.returncode, 0, uninstalled.stderr)
            self.assertFalse(installed_host.exists())
            self.assertFalse(manifest.exists())


if __name__ == "__main__":
    unittest.main()
