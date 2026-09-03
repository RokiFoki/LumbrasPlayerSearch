import base64
import pathlib
import sys
import unittest
from unittest import mock


NATIVE_HOST_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(NATIVE_HOST_DIR))

import host  # noqa: E402


def encoded(value):
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


class ScidAdapterParsingTests(unittest.TestCase):
    def setUp(self):
        self.adapter = host.ScidAdapter(pathlib.Path("/tmp/scid"), pathlib.Path("/tmp/database"))

    def test_search_output_parsing(self):
        fields = [
            "2026.01.02",
            "Example Event",
            "7",
            "Player, Example",
            "Opponent, Example",
            "1-0",
            "2500",
            "2400",
            "C42",
        ]
        output = "\n".join(
            [
                "CANDIDATE\t12\t{}".format(encoded("Player, Example")),
                "GAME\t42\t{}".format("\t".join(encoded(value) for value in fields)),
                "META\t12\t1\t{}".format(encoded("Player, Example")),
            ]
        )
        with mock.patch.object(self.adapter, "_run", return_value=output):
            result = self.adapter.search_player("Player, Example", 0, 1)
        self.assertEqual(result["total"], 12)
        self.assertEqual(result["games"][0]["whiteElo"], 2500)
        self.assertEqual(result["nextCursor"], 1)

    def test_candidate_only_output_requires_choice(self):
        output = "\n".join(
            [
                "CANDIDATE\t12\t{}".format(encoded("Player, One")),
                "CANDIDATE\t8\t{}".format(encoded("Player, Two")),
                "META\t0\t0\t{}".format(encoded("")),
            ]
        )
        with mock.patch.object(self.adapter, "_run", return_value=output):
            result = self.adapter.search_player("Player", 0, 100)
        self.assertTrue(result["requiresPlayerChoice"])
        self.assertEqual(len(result["candidates"]), 2)

    def test_export_output_parsing(self):
        pgn = '[Event "Example"]\n\n1.e4 e5 1/2-1/2\n'
        output = "PGN\t42\t{}\n".format(encoded(pgn))
        with mock.patch.object(self.adapter, "_run", return_value=output):
            result = self.adapter.export_games([42])
        self.assertEqual(result, [{"gameNumber": 42, "pgn": pgn}])

    def test_sandbox_denies_writes_to_database_directory(self):
        profile = self.adapter._sandbox_profile()
        self.assertIn("deny file-write", profile)
        self.assertIn('/tmp', profile)


if __name__ == "__main__":
    unittest.main()
