import json
import os
import pathlib
import platform
import struct
import subprocess
import tempfile
import unittest
import uuid


REPOSITORY = pathlib.Path(__file__).resolve().parents[2]
INSTALLER = REPOSITORY / "scripts" / "install-windows.ps1"
UNINSTALLER = REPOSITORY / "scripts" / "uninstall-windows.ps1"
EXTENSION_ID = "abcdefghijklmnopabcdefghijklmnop"
HOST_NAME = "app.chessgenie.local_games"


def _powershell(script, *arguments):
    command = [
        "powershell", "-NoProfile", "-NonInteractive",
        "-ExecutionPolicy", "Bypass", "-File", str(script), *arguments,
    ]
    return subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
    )


def _read_registry_default(key_path):
    """Return the default value of an HKCU key, or None if the key is absent."""
    read = subprocess.run(
        [
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "if (Test-Path -Path '{0}') {{ (Get-ItemProperty -Path '{0}').'(default)' }}".format(key_path),
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
    )
    value = read.stdout.strip()
    return value or None


@unittest.skipUnless(platform.system() == "Windows", "Windows install scripts run on Windows only")
class WindowsInstallScriptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.temporary.name)
        self.install_root = root / "install"
        # A throwaway HKCU subtree so the real Chrome registration is untouched.
        self.registry_root = (
            "HKCU:\\Software\\LumbrasChessGenieTest\\" + uuid.uuid4().hex + "\\NativeMessagingHosts"
        )
        self.host_key = self.registry_root + "\\" + HOST_NAME
        self.installed_host = self.install_root / "native-host"
        self.launcher = self.installed_host / "launch.bat"
        self.manifest = self.install_root / (HOST_NAME + ".json")
        self.addCleanup(self._cleanup_registry)

    def tearDown(self):
        self.temporary.cleanup()

    def _cleanup_registry(self):
        subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                "Remove-Item -Path 'HKCU:\\Software\\LumbrasChessGenieTest' -Recurse -Force "
                "-ErrorAction SilentlyContinue",
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )

    def _install(self):
        return _powershell(
            INSTALLER, EXTENSION_ID,
            "-InstallRoot", str(self.install_root),
            "-RegistryRoot", self.registry_root,
        )

    def test_installs_registers_round_trips_and_uninstalls(self):
        installed = self._install()
        self.assertEqual(installed.returncode, 0, installed.stderr)

        # Files copied outside the repository.
        self.assertTrue(self.launcher.is_file())
        self.assertTrue((self.installed_host / "host.py").is_file())
        for script in ("search-player", "search-fideid", "list-games", "export-games"):
            self.assertTrue((self.installed_host / "scid" / (script + ".tcl")).is_file())

        # Manifest points at the installed launcher and carries the extension ID.
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(manifest["path"], str(self.launcher.resolve()))
        self.assertNotIn(str(REPOSITORY), manifest["path"])
        self.assertEqual(
            manifest["allowed_origins"],
            ["chrome-extension://{}/".format(EXTENSION_ID)],
        )

        # Registry value is the absolute manifest path.
        self.assertEqual(_read_registry_default(self.host_key), str(self.manifest.resolve()))

        # A hello request round-trips through the installed launch.bat.
        request = {
            "protocolVersion": 1, "id": "installed-windows-host", "command": "hello", "payload": {},
        }
        payload = json.dumps(request).encode("utf-8")
        response = subprocess.run(
            [str(self.launcher)],
            input=struct.pack("=I", len(payload)) + payload,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(response.returncode, 0, response.stderr.decode("utf-8", "replace"))
        length = struct.unpack("=I", response.stdout[:4])[0]
        value = json.loads(response.stdout[4 : 4 + length].decode("utf-8"))
        self.assertTrue(value["ok"])
        self.assertEqual(value["platform"], "windows")
        # Nothing but the framed response reached stdout.
        self.assertEqual(len(response.stdout), 4 + length)

        # Installing again is idempotent.
        again = self._install()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(_read_registry_default(self.host_key), str(self.manifest.resolve()))
        self.assertEqual(len(list((self.installed_host / "scid").glob("*.tcl"))), 4)

        # Uninstall removes everything.
        uninstalled = _powershell(
            UNINSTALLER,
            "-InstallRoot", str(self.install_root),
            "-RegistryRoot", self.registry_root,
        )
        self.assertEqual(uninstalled.returncode, 0, uninstalled.stderr)
        self.assertIsNone(_read_registry_default(self.host_key))
        self.assertFalse(self.installed_host.exists())
        self.assertFalse(self.manifest.exists())

    def test_uninstall_remove_config_deletes_only_with_the_switch(self):
        self.assertEqual(self._install().returncode, 0)
        config = pathlib.Path(self.temporary.name) / "config.json"
        config.write_text("{}", encoding="utf-8")

        # Without the switch the config is left in place.
        kept = _powershell(
            UNINSTALLER,
            "-InstallRoot", str(self.install_root),
            "-RegistryRoot", self.registry_root,
            "-ConfigPath", str(config),
        )
        self.assertEqual(kept.returncode, 0, kept.stderr)
        self.assertTrue(config.is_file())

        # With the switch it is removed.
        removed = _powershell(
            UNINSTALLER,
            "-InstallRoot", str(self.install_root),
            "-RegistryRoot", self.registry_root,
            "-ConfigPath", str(config),
            "-RemoveConfig",
        )
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse(config.exists())


if __name__ == "__main__":
    unittest.main()
