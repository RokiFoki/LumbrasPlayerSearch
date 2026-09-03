import io
import json
import os
import pathlib
import stat
import struct
import sys
import tempfile
import unittest
from unittest import mock


NATIVE_HOST_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(NATIVE_HOST_DIR))

import host  # noqa: E402


class FakeAdapter:
    def __init__(self):
        self.fide_id_calls = []

    def search_player(self, player, offset, limit):
        return {
            "total": 1,
            "games": [
                {
                    "gameNumber": 42,
                    "date": "2026.01.02",
                    "event": "Example",
                    "round": "1",
                    "white": player,
                    "black": "Opponent, Example",
                    "result": "1-0",
                    "whiteElo": 2500,
                    "blackElo": 2400,
                    "eco": "C42",
                }
            ],
            "candidates": [{"name": player, "frequency": 1}],
            "requiresPlayerChoice": False,
            "playerNotFound": False,
            "selectedPlayer": player,
            "nextCursor": None,
        }

    def search_fide_id(self, fide_id, offset, limit):
        self.fide_id_calls.append((fide_id, offset, limit))
        return {
            "total": 2,
            "games": [
                {
                    "gameNumber": 7 + offset,
                    "date": "2026.01.02",
                    "event": "Example",
                    "round": "1",
                    "white": "Player, Example",
                    "black": "Opponent, Example",
                    "result": "1-0",
                    "whiteElo": 2500,
                    "blackElo": 2400,
                    "eco": "C42",
                }
            ],
            "candidates": [],
            "requiresPlayerChoice": False,
            "playerNotFound": False,
            "selectedPlayer": "Player, Example",
            "fideId": fide_id,
            "nextCursor": offset + 1 if offset + 1 < 2 else None,
        }

    def export_games(self, game_numbers):
        return [
            {"gameNumber": number, "pgn": '[Event "Example"]\n\n1.e4 e5 1/2-1/2\n'}
            for number in game_numbers
        ]


class FakeNativeHost(host.NativeHost):
    def __init__(self, config_store=None):
        super().__init__(config_store)
        self.adapter = FakeAdapter()

    def _adapter(self):
        return self.adapter


class ChunkedReader(io.BytesIO):
    def read(self, size=-1):
        if size > 1:
            size = 1
        return super().read(size)


class HostTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.temporary.name)
        self.config_path = root / "config.json"
        self.executable = root / "scid"
        self.executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.executable.chmod(self.executable.stat().st_mode | stat.S_IXUSR)
        self.database = root / "database"
        for extension in (".si5", ".sg5", ".sn5"):
            pathlib.Path(str(self.database) + extension).write_bytes(b"fixture")

    def tearDown(self):
        self.temporary.cleanup()

    def request(self, command, payload=None):
        return {
            "protocolVersion": 1,
            "id": "test-request",
            "command": command,
            "payload": payload or {},
        }

    def test_message_frame_round_trip(self):
        message = self.request("hello")
        output = io.BytesIO()
        host.write_message(output, message)
        encoded = output.getvalue()
        self.assertEqual(struct.unpack("=I", encoded[:4])[0], len(encoded[4:]))
        self.assertEqual(host.read_message(io.BytesIO(encoded)), message)

    def test_message_frame_handles_partial_pipe_reads(self):
        message = self.request("hello")
        output = io.BytesIO()
        host.write_message(output, message)
        self.assertEqual(host.read_message(ChunkedReader(output.getvalue())), message)

    def test_oversized_input_frame_is_rejected(self):
        stream = io.BytesIO(struct.pack("=I", host.MAX_INPUT_BYTES + 1))
        with self.assertRaisesRegex(host.HostError, "size"):
            host.read_message(stream)

    def test_configure_normalizes_extension_and_reports_ready(self):
        native = host.NativeHost(host.ConfigStore(self.config_path))
        response = native.dispatch(
            self.request(
                "configure",
                {
                    "scidExecutable": str(self.executable),
                    "databaseBase": str(self.database) + ".si5",
                },
            )
        )
        self.assertTrue(response["ok"])
        self.assertTrue(response["ready"])
        self.assertEqual(response["databaseBase"], str(self.database.resolve()))
        self.assertEqual(stat.S_IMODE(self.config_path.stat().st_mode), 0o600)

    def test_incomplete_database_is_rejected(self):
        pathlib.Path(str(self.database) + ".sn5").unlink()
        with self.assertRaises(host.HostError) as raised:
            host._validate_database(str(self.database))
        self.assertEqual(raised.exception.code, "DATABASE_MISSING")

    def test_search_response_is_source_agnostic(self):
        native = FakeNativeHost(host.ConfigStore(self.config_path))
        response = native.dispatch(
            self.request("searchPlayer", {"player": "Player, Example", "limit": 100})
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["games"][0]["gameNumber"], 42)
        encoded = json.dumps(response).lower()
        self.assertNotIn("chessgenie.app", encoded)
        self.assertNotIn("upload", encoded)

    def test_name_search_still_accepts_names_that_contain_digits(self):
        native = FakeNativeHost(host.ConfigStore(self.config_path))
        response = native.dispatch(self.request("searchPlayer", {"player": "Player 2, Example"}))
        self.assertTrue(response["ok"])
        self.assertEqual(response["selectedPlayer"], "Player 2, Example")
        self.assertEqual(native.adapter.fide_id_calls, [])

    def test_search_by_fide_id_returns_games_and_stored_name(self):
        native = FakeNativeHost(host.ConfigStore(self.config_path))
        response = native.dispatch(
            self.request("searchFideId", {"fideId": "1503014", "limit": 100, "cursor": 0})
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["fideId"], "1503014")
        self.assertEqual(response["selectedPlayer"], "Player, Example")
        self.assertEqual(response["games"][0]["gameNumber"], 7)
        self.assertFalse(response["playerNotFound"])
        self.assertFalse(response["requiresPlayerChoice"])
        self.assertEqual(native.adapter.fide_id_calls, [("1503014", 0, 100)])

    def test_fide_id_search_defaults_limit_and_cursor(self):
        native = FakeNativeHost(host.ConfigStore(self.config_path))
        native.dispatch(self.request("searchFideId", {"fideId": "1503014"}))
        self.assertEqual(native.adapter.fide_id_calls, [("1503014", 0, 100)])

    def test_fide_id_is_normalized_before_reaching_scid(self):
        native = FakeNativeHost(host.ConfigStore(self.config_path))
        native.dispatch(self.request("searchFideId", {"fideId": "  0001503014 "}))
        self.assertEqual(native.adapter.fide_id_calls, [("1503014", 0, 100)])

    def test_fide_id_pagination_keeps_the_original_id(self):
        native = FakeNativeHost(host.ConfigStore(self.config_path))
        first = native.dispatch(self.request("searchFideId", {"fideId": "1503014", "limit": 1}))
        self.assertEqual(first["nextCursor"], 1)
        second = native.dispatch(
            self.request(
                "searchFideId",
                {"fideId": "1503014", "limit": 1, "cursor": first["nextCursor"]},
            )
        )
        self.assertIsNone(second["nextCursor"])
        self.assertEqual(second["fideId"], "1503014")
        self.assertEqual(
            native.adapter.fide_id_calls, [("1503014", 0, 1), ("1503014", 1, 1)]
        )

    def test_invalid_fide_ids_are_rejected_before_scid_runs(self):
        native = FakeNativeHost(host.ConfigStore(self.config_path))
        for value in [
            "",
            "   ",
            "0",
            "000",
            "1503014a",
            "150 3014",
            "-1503014",
            "1.5e6",
            "\u0661\u0665\u0660\u0663",  # Arabic-Indic digits
            "\uff11\uff15\uff10\uff13",  # full-width digits
            "1" * (host.MAX_FIDE_ID_LENGTH + 1),
            "1" * 1000,
            1503014,
            None,
            True,
            ["1503014"],
        ]:
            with self.subTest(value=value):
                with self.assertRaises(host.HostError) as raised:
                    native.dispatch(self.request("searchFideId", {"fideId": value}))
                self.assertEqual(raised.exception.code, "INVALID_FIDE_ID")
        self.assertEqual(native.adapter.fide_id_calls, [])

    def test_fide_id_search_accepts_the_maximum_length(self):
        native = FakeNativeHost(host.ConfigStore(self.config_path))
        value = "9" * host.MAX_FIDE_ID_LENGTH
        native.dispatch(self.request("searchFideId", {"fideId": value}))
        self.assertEqual(native.adapter.fide_id_calls, [(value, 0, 100)])

    def test_fide_id_search_validates_limit_and_cursor(self):
        native = FakeNativeHost(host.ConfigStore(self.config_path))
        for payload, code in [
            ({"fideId": "1503014", "limit": 0}, "INVALID_LIMIT"),
            ({"fideId": "1503014", "limit": host.MAX_SEARCH_RESULTS + 1}, "INVALID_LIMIT"),
            ({"fideId": "1503014", "limit": True}, "INVALID_LIMIT"),
            ({"fideId": "1503014", "cursor": -1}, "INVALID_CURSOR"),
            ({"fideId": "1503014", "cursor": "0"}, "INVALID_CURSOR"),
            ({"fideId": "1503014", "cursor": host.MAX_SEARCH_CURSOR + 1}, "INVALID_CURSOR"),
        ]:
            with self.subTest(payload=payload):
                with self.assertRaises(host.HostError) as raised:
                    native.dispatch(self.request("searchFideId", payload))
                self.assertEqual(raised.exception.code, code)
        self.assertEqual(native.adapter.fide_id_calls, [])

    def test_fide_id_search_rejects_unknown_and_missing_fields(self):
        native = FakeNativeHost(host.ConfigStore(self.config_path))
        with self.assertRaises(host.HostError) as raised:
            native.dispatch(
                self.request("searchFideId", {"fideId": "1503014", "player": "Player, Example"})
            )
        self.assertEqual(raised.exception.code, "INVALID_REQUEST")
        with self.assertRaises(host.HostError) as raised:
            native.dispatch(self.request("searchFideId", {}))
        self.assertEqual(raised.exception.code, "INVALID_FIDE_ID")
        self.assertEqual(native.adapter.fide_id_calls, [])

    def test_fide_id_search_response_is_source_agnostic(self):
        native = FakeNativeHost(host.ConfigStore(self.config_path))
        response = native.dispatch(self.request("searchFideId", {"fideId": "1503014"}))
        encoded = json.dumps(response).lower()
        self.assertNotIn("chessgenie.app", encoded)
        self.assertNotIn("fide.com", encoded)
        self.assertNotIn("http", encoded)

    def test_pgn_export_works_for_games_found_by_fide_id(self):
        native = FakeNativeHost(host.ConfigStore(self.config_path))
        found = native.dispatch(self.request("searchFideId", {"fideId": "1503014"}))
        numbers = [game["gameNumber"] for game in found["games"]]
        exported = native.dispatch(self.request("getPgn", {"gameNumbers": numbers}))
        self.assertTrue(exported["ok"])
        self.assertEqual([game["gameNumber"] for game in exported["games"]], numbers)
        self.assertTrue(exported["games"][0]["pgn"].startswith('[Event "Example"]'))
        self.assertEqual(exported["remainingGameNumbers"], [])

    def test_export_rejects_duplicate_game_numbers(self):
        native = FakeNativeHost(host.ConfigStore(self.config_path))
        with self.assertRaises(host.HostError) as raised:
            native.dispatch(self.request("getPgn", {"gameNumbers": [42, 42]}))
        self.assertEqual(raised.exception.code, "INVALID_GAMES")

    def test_export_is_bounded_and_returns_remainder(self):
        native = FakeNativeHost(host.ConfigStore(self.config_path))
        with mock.patch.object(host, "MAX_OUTPUT_BYTES", 360):
            response = native.dispatch(
                self.request("getPgn", {"gameNumbers": [1, 2, 3, 4, 5]})
            )
        self.assertTrue(response["games"])
        self.assertTrue(response["remainingGameNumbers"])
        self.assertEqual(
            [game["gameNumber"] for game in response["games"]]
            + response["remainingGameNumbers"],
            [1, 2, 3, 4, 5],
        )
        encoded = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.assertLessEqual(len(encoded), 360)

    def test_protocol_mismatch_is_rejected(self):
        native = FakeNativeHost(host.ConfigStore(self.config_path))
        request = self.request("hello")
        request["protocolVersion"] = 999
        with self.assertRaises(host.HostError) as raised:
            native.dispatch(request)
        self.assertEqual(raised.exception.code, "PROTOCOL_MISMATCH")

    def test_unknown_fields_are_rejected(self):
        native = FakeNativeHost(host.ConfigStore(self.config_path))
        request = self.request("searchPlayer", {"player": "Player, Example", "limit": 10})
        request["websiteUrl"] = "https://example.invalid"
        with self.assertRaises(host.HostError) as raised:
            native.dispatch(request)
        self.assertEqual(raised.exception.code, "INVALID_REQUEST")

    def test_boolean_game_number_is_rejected(self):
        native = FakeNativeHost(host.ConfigStore(self.config_path))
        with self.assertRaises(host.HostError) as raised:
            native.dispatch(self.request("getPgn", {"gameNumbers": [True]}))
        self.assertEqual(raised.exception.code, "INVALID_GAMES")


if __name__ == "__main__":
    unittest.main()
