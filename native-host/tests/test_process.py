import json
import pathlib
import struct
import subprocess
import sys
import unittest


HOST = pathlib.Path(__file__).resolve().parents[1] / "host.py"


class NativeHostProcessTests(unittest.TestCase):
    def test_hello_over_real_stdio_frames(self):
        request = {
            "protocolVersion": 1,
            "id": "process-test",
            "command": "hello",
            "payload": {},
        }
        payload = json.dumps(request).encode("utf-8")
        completed = subprocess.run(
            [sys.executable, str(HOST)],
            input=struct.pack("=I", len(payload)) + payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
        self.assertGreaterEqual(len(completed.stdout), 4)
        length = struct.unpack("=I", completed.stdout[:4])[0]
        response = json.loads(completed.stdout[4 : 4 + length].decode("utf-8"))
        self.assertTrue(response["ok"])
        self.assertEqual(response["id"], "process-test")
        self.assertEqual(response["protocolVersion"], 1)


if __name__ == "__main__":
    unittest.main()
