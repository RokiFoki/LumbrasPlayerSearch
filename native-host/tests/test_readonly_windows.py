"""Prove Windows enforced read-only access, the analogue of the macOS sandbox.

macOS denies writes to the database directory with sandbox-exec. Windows runs
Scid at Low integrity, which can read ordinary files but cannot write them.
These tests exercise the exact primitives host._run_windows uses to launch Scid
-- _label_directory_low and _run_scid_low_integrity -- with a stand-in child
process instead of Scid, so they prove the enforcement without needing Scid
installed. The child is a hostile actor: it tries to write the database
directory. A differential control shows a normal (Medium) child *can* write it,
so the denial is the integrity level and not a file-permission accident.
"""

import hashlib
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


NATIVE_HOST_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(NATIVE_HOST_DIR))

import host  # noqa: E402


HOSTILE_CHILD = r'''
import os, sys
db_dir = sys.argv[1]
db_file = os.path.join(db_dir, "Base.si5")
try:
    with open(db_file, "r", encoding="utf-8") as handle:
        handle.read()
    print("READ_DB_OK")
except Exception as error:
    print("READ_DB_FAIL", type(error).__name__)
try:
    with open(os.path.join(db_dir, "attack.txt"), "w", encoding="utf-8") as handle:
        handle.write("pwned")
    print("WRITE_DB_OK")
except Exception as error:
    print("WRITE_DB_DENIED", type(error).__name__)
try:
    with open(db_file, "a", encoding="utf-8") as handle:
        handle.write("tampered")
    print("APPEND_DB_OK")
except Exception as error:
    print("APPEND_DB_DENIED", type(error).__name__)
'''


def _fingerprint(database_files):
    state = {}
    for path in database_files:
        data = path.read_bytes()
        stat = path.stat()
        state[path.name] = (len(data), hashlib.sha256(data).hexdigest(), stat.st_mtime_ns)
    return state


@unittest.skipUnless(platform.system() == "Windows", "Low-integrity launch is Windows only")
class WindowsReadOnlyEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="lcg-readonly-"))
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        self.child = self.root / "hostile_child.py"
        self.child.write_text(HOSTILE_CHILD, encoding="utf-8")

    def _make_database(self, name):
        database_dir = self.root / name
        database_dir.mkdir()
        files = []
        for index, extension in enumerate((".si5", ".sg5", ".sn5")):
            path = database_dir / ("Base" + extension)
            path.write_bytes(b"SCID-5-DATABASE-CONTENT-" + bytes([index]) * 64)
            files.append(path)
        return database_dir, files

    def _run_low_integrity(self, database_dir):
        scratch = tempfile.mkdtemp(prefix="lcg-scratch-")
        self.addCleanup(lambda: shutil.rmtree(scratch, ignore_errors=True))
        host._label_directory_low(scratch)
        return host._run_scid_low_integrity(
            sys.executable,
            [sys.executable, str(self.child), str(database_dir)],
            scratch,
            {"TEMP": scratch, "TMP": scratch, "TMPDIR": scratch},
            30,
        )

    def test_low_integrity_child_cannot_write_the_database_directory(self):
        database_dir, files = self._make_database("db")
        before = _fingerprint(files)

        code, stdout, stderr = self._run_low_integrity(database_dir)

        self.assertEqual(code, 0, stderr)
        # The child could read the database but every write was refused.
        self.assertIn("READ_DB_OK", stdout)
        self.assertIn("WRITE_DB_DENIED", stdout)
        self.assertIn("APPEND_DB_DENIED", stdout)
        self.assertNotIn("WRITE_DB_OK", stdout)
        self.assertNotIn("APPEND_DB_OK", stdout)

        # No new file appeared and every database file is byte-for-byte identical.
        self.assertFalse((database_dir / "attack.txt").exists())
        self.assertEqual(_fingerprint(files), before)

    def test_a_normal_child_can_write_so_the_denial_is_the_integrity_level(self):
        # Control: the same hostile child, run at the default (Medium) integrity,
        # *does* write the database directory. This proves the read-only test
        # above is enforced by the Low integrity level, not by file permissions.
        database_dir, _ = self._make_database("control")
        completed = subprocess.run(
            [sys.executable, str(self.child), str(database_dir)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
        )
        self.assertIn("WRITE_DB_OK", completed.stdout)
        self.assertTrue((database_dir / "attack.txt").exists())

    def test_low_integrity_launch_times_out_and_terminates_the_child(self):
        # A child that outlives the timeout is terminated and mapped to
        # SCID_TIMEOUT, and the call returns promptly rather than hanging.
        slow_child = self.root / "slow_child.py"
        slow_child.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        scratch = tempfile.mkdtemp(prefix="lcg-scratch-")
        self.addCleanup(lambda: shutil.rmtree(scratch, ignore_errors=True))
        host._label_directory_low(scratch)

        started = time.monotonic()
        with self.assertRaises(host.HostError) as raised:
            host._run_scid_low_integrity(
                sys.executable,
                [sys.executable, str(slow_child)],
                scratch,
                {"TEMP": scratch, "TMP": scratch, "TMPDIR": scratch},
                1,
            )
        elapsed = time.monotonic() - started
        self.assertEqual(raised.exception.code, "SCID_TIMEOUT")
        self.assertLess(elapsed, 15, "the timed-out child should be terminated promptly")

    def test_unsupported_platform_would_fail_closed(self):
        # host._run fails closed on any platform without an enforced read-only
        # launch. Windows and Darwin are the supported strategies; everything
        # else raises READ_ONLY_UNAVAILABLE rather than querying unprotected.
        adapter = host.ScidAdapter(pathlib.Path("C:/scid.exe"), pathlib.Path("C:/db/Base"))
        with mock.patch.object(host.platform, "system", return_value="Linux"):
            with self.assertRaises(host.HostError) as raised:
                adapter._run("search-player.tcl", [], 1)
        self.assertEqual(raised.exception.code, "READ_ONLY_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
