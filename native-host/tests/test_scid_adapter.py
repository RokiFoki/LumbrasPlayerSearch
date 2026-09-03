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


def fide_game_line(game_number, white, black, white_fide_id, black_fide_id, date="2026.01.02"):
    fields = [
        date,
        "Example Event",
        "1",
        white,
        black,
        "1-0",
        "2500",
        "2400",
        "C42",
        white_fide_id,
        black_fide_id,
    ]
    return "GAME\t{}\t{}".format(game_number, "\t".join(encoded(value) for value in fields))


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

    def test_name_search_output_still_uses_eleven_fields(self):
        # A FIDE-ID row carries two extra fields; the name search must ignore it.
        output = "\n".join(
            [
                "CANDIDATE\t1\t{}".format(encoded("Player, Example")),
                fide_game_line(42, "Player, Example", "Opponent, Example", "1503014", "1"),
                "META\t1\t1\t{}".format(encoded("Player, Example")),
            ]
        )
        with mock.patch.object(self.adapter, "_run", return_value=output):
            result = self.adapter.search_player("Player, Example", 0, 1)
        self.assertEqual(result["selectedPlayer"], "Player, Example")
        self.assertEqual(result["games"], [])

    def test_fide_search_runs_the_fide_script_with_bounded_arguments(self):
        with mock.patch.object(self.adapter, "_run", return_value="META\t0\t0\t0") as run:
            self.adapter.search_fide_id("1503014", 200, 100)
        run.assert_called_once_with(
            "search-fideid.tcl",
            ["1503014", "200", "100"],
            timeout=host.FIDE_ID_SEARCH_TIMEOUT_SECONDS,
        )

    def test_fide_search_returns_white_side_matches(self):
        output = "\n".join(
            [
                fide_game_line(10, "Player, Example", "Opponent, One", "1503014", "2"),
                "META\t1\t1\t1",
            ]
        )
        with mock.patch.object(self.adapter, "_run", return_value=output):
            result = self.adapter.search_fide_id("1503014", 0, 100)
        self.assertEqual([game["gameNumber"] for game in result["games"]], [10])
        self.assertEqual(result["games"][0]["white"], "Player, Example")
        self.assertEqual(result["games"][0]["whiteElo"], 2500)
        self.assertEqual(result["games"][0]["eco"], "C42")
        self.assertEqual(result["selectedPlayer"], "Player, Example")
        self.assertEqual(result["fideId"], "1503014")
        self.assertFalse(result["playerNotFound"])
        self.assertFalse(result["requiresPlayerChoice"])
        self.assertEqual(result["candidates"], [])

    def test_fide_search_returns_black_side_matches(self):
        output = "\n".join(
            [
                fide_game_line(11, "Opponent, One", "Player, Example", "2", "1503014"),
                "META\t1\t1\t1",
            ]
        )
        with mock.patch.object(self.adapter, "_run", return_value=output):
            result = self.adapter.search_fide_id("1503014", 0, 100)
        self.assertEqual([game["gameNumber"] for game in result["games"]], [11])
        self.assertEqual(result["games"][0]["black"], "Player, Example")
        self.assertEqual(result["selectedPlayer"], "Player, Example")

    def test_fide_search_combines_both_sides_and_keeps_scid_order(self):
        output = "\n".join(
            [
                fide_game_line(30, "Player, Example", "Opponent, One", "1503014", "2"),
                fide_game_line(20, "Opponent, Two", "Player, Example", "3", "1503014"),
                fide_game_line(10, "Player, Example", "Opponent, Three", "1503014", "4"),
                "META\t3\t3\t3",
            ]
        )
        with mock.patch.object(self.adapter, "_run", return_value=output):
            result = self.adapter.search_fide_id("1503014", 0, 100)
        self.assertEqual([game["gameNumber"] for game in result["games"]], [30, 20, 10])
        self.assertEqual(result["total"], 3)
        self.assertEqual(
            set(result["games"][0]),
            {"gameNumber", "date", "event", "round", "white", "black", "result", "whiteElo", "blackElo", "eco"},
        )

    def test_fide_search_removes_duplicate_game_numbers(self):
        output = "\n".join(
            [
                fide_game_line(10, "Player, Example", "Opponent, One", "1503014", "2"),
                fide_game_line(10, "Player, Example", "Opponent, One", "1503014", "2"),
                fide_game_line(9, "Player, Example", "Player, Example", "1503014", "1503014"),
                fide_game_line(9, "Player, Example", "Player, Example", "1503014", "1503014"),
                "META\t2\t4\t4",
            ]
        )
        with mock.patch.object(self.adapter, "_run", return_value=output):
            result = self.adapter.search_fide_id("1503014", 0, 100)
        self.assertEqual([game["gameNumber"] for game in result["games"]], [10, 9])

    def test_fide_search_requires_the_complete_identifier(self):
        output = "\n".join(
            [
                fide_game_line(1, "Player, Example", "Opponent", "1503014", "2"),
                fide_game_line(2, "Prefix, Player", "Opponent", "11503014", "2"),
                fide_game_line(3, "Suffix, Player", "Opponent", "15030141", "2"),
                fide_game_line(4, "Inner, Player", "Opponent", "115030141", "2"),
                fide_game_line(5, "Short, Player", "Opponent", "150301", "2"),
                fide_game_line(6, "Opponent", "Prefix, Player", "2", "11503014"),
                fide_game_line(7, "Opponent", "Suffix, Player", "2", "15030141"),
                fide_game_line(8, "Opponent", "Empty, Player", "", ""),
                fide_game_line(9, "Opponent", "Player, Example", "2", "1503014"),
                "META\t9\t9\t9",
            ]
        )
        with mock.patch.object(self.adapter, "_run", return_value=output):
            result = self.adapter.search_fide_id("1503014", 0, 100)
        self.assertEqual([game["gameNumber"] for game in result["games"]], [1, 9])
        self.assertEqual(result["selectedPlayer"], "Player, Example")

    def test_fide_search_resolves_the_most_common_stored_name(self):
        output = "\n".join(
            [
                fide_game_line(4, "Carlsen, M", "Opponent", "1503014", "2"),
                fide_game_line(3, "Opponent", "Carlsen, Magnus", "2", "1503014"),
                fide_game_line(2, "Carlsen, Magnus", "Opponent", "1503014", "2"),
                fide_game_line(1, "Opponent", "Carlsen, Magnus", "2", "1503014"),
                "META\t4\t4\t4",
            ]
        )
        with mock.patch.object(self.adapter, "_run", return_value=output):
            result = self.adapter.search_fide_id("1503014", 0, 100)
        self.assertEqual(result["selectedPlayer"], "Carlsen, Magnus")

    def test_fide_search_reports_no_results(self):
        with mock.patch.object(self.adapter, "_run", return_value="META\t0\t0\t0"):
            result = self.adapter.search_fide_id("999999999", 0, 100)
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["games"], [])
        self.assertTrue(result["playerNotFound"])
        self.assertFalse(result["requiresPlayerChoice"])
        self.assertIsNone(result["selectedPlayer"])
        self.assertIsNone(result["nextCursor"])
        self.assertEqual(result["fideId"], "999999999")

    def test_fide_search_pagination_cursor(self):
        page = "\n".join(
            [
                fide_game_line(3934, "Player, Example", "Opponent", "1503014", "2"),
                fide_game_line(3933, "Player, Example", "Opponent", "1503014", "2"),
                "META\t3934\t2\t2",
            ]
        )
        with mock.patch.object(self.adapter, "_run", return_value=page):
            first = self.adapter.search_fide_id("1503014", 0, 2)
        self.assertEqual(first["nextCursor"], 2)

        with mock.patch.object(self.adapter, "_run", return_value=page):
            middle = self.adapter.search_fide_id("1503014", 3930, 2)
        self.assertEqual(middle["nextCursor"], 3932)

        last = "\n".join(
            [
                fide_game_line(2, "Player, Example", "Opponent", "1503014", "2"),
                fide_game_line(1, "Player, Example", "Opponent", "1503014", "2"),
                "META\t3934\t2\t2",
            ]
        )
        with mock.patch.object(self.adapter, "_run", return_value=last):
            final = self.adapter.search_fide_id("1503014", 3932, 2)
        self.assertIsNone(final["nextCursor"])

    def test_fide_search_cursor_advances_past_rejected_rows(self):
        # Scid examined two rows; only one was a complete match. The cursor
        # still moves past both so paging never repeats or stalls.
        output = "\n".join(
            [
                fide_game_line(2, "Player, Example", "Opponent", "1503014", "2"),
                fide_game_line(1, "Other, Player", "Opponent", "11503014", "2"),
                "META\t5\t2\t2",
            ]
        )
        with mock.patch.object(self.adapter, "_run", return_value=output):
            result = self.adapter.search_fide_id("1503014", 0, 2)
        self.assertEqual([game["gameNumber"] for game in result["games"]], [2])
        self.assertEqual(result["nextCursor"], 2)

    def test_fide_search_ignores_malformed_rows(self):
        output = "\n".join(
            [
                "GAME\t1\tshort",
                "CANDIDATE\t1\t{}".format(encoded("Player, Example")),
                "",
                fide_game_line(5, "Player, Example", "Opponent", "1503014", "2"),
                "META\t1\t1\t1",
            ]
        )
        with mock.patch.object(self.adapter, "_run", return_value=output):
            result = self.adapter.search_fide_id("1503014", 0, 100)
        self.assertEqual([game["gameNumber"] for game in result["games"]], [5])

    def test_name_search_returns_the_complete_result_set(self):
        output = "\n".join(
            [
                "CANDIDATE\t3\t{}".format(encoded("Player, Example")),
                "GAME\t30\t{}".format("\t".join(encoded(v) for v in
                    ["2026.01.02", "E", "1", "Player, Example", "Opponent", "1-0", "2500", "2400", "C42"])),
                "META\t3\t1\t{}".format(encoded("Player, Example")),
                "NUMBERS\t30,20,10",
            ]
        )
        with mock.patch.object(self.adapter, "_run", return_value=output):
            result = self.adapter.search_player("Player, Example", 0, 1)
        # One page was rendered, but every match is exportable.
        self.assertEqual([game["gameNumber"] for game in result["games"]], [30])
        self.assertEqual(result["gameNumbers"], [30, 20, 10])

    def test_fide_search_returns_the_complete_result_set(self):
        output = "\n".join(
            [
                fide_game_line(30, "Player, Example", "Opponent", "1503014", "2"),
                "META\t3\t1\t1",
                "NUMBERS\t30,20,10",
            ]
        )
        with mock.patch.object(self.adapter, "_run", return_value=output):
            result = self.adapter.search_fide_id("1503014", 0, 1)
        self.assertEqual([game["gameNumber"] for game in result["games"]], [30])
        self.assertEqual(result["gameNumbers"], [30, 20, 10])

    def test_later_pages_omit_the_result_set(self):
        output = "\n".join(
            [
                fide_game_line(10, "Player, Example", "Opponent", "1503014", "2"),
                "META\t3\t1\t1",
            ]
        )
        with mock.patch.object(self.adapter, "_run", return_value=output):
            result = self.adapter.search_fide_id("1503014", 2, 1)
        self.assertEqual(result["gameNumbers"], [])

    def test_result_set_is_bounded_and_skips_invalid_entries(self):
        numbers = ",".join(str(n) for n in range(1, host.MAX_RESULT_GAME_NUMBERS + 500))
        output = "META\t99999\t0\t0\nNUMBERS\t{}".format(numbers)
        with mock.patch.object(self.adapter, "_run", return_value=output):
            result = self.adapter.search_fide_id("1503014", 0, 100)
        self.assertEqual(len(result["gameNumbers"]), host.MAX_RESULT_GAME_NUMBERS)

        output = "META\t2\t0\t0\nNUMBERS\t5,,0,-3,7"
        with mock.patch.object(self.adapter, "_run", return_value=output):
            result = self.adapter.search_fide_id("1503014", 0, 100)
        self.assertEqual(result["gameNumbers"], [5, 7])

        output = "META\t2\t0\t0\nNUMBERS\t5,oops"
        with mock.patch.object(self.adapter, "_run", return_value=output):
            with self.assertRaises(host.HostError) as raised:
                self.adapter.search_fide_id("1503014", 0, 100)
        self.assertEqual(raised.exception.code, "SCID_OUTPUT_INVALID")

    def test_no_result_search_has_an_empty_result_set(self):
        with mock.patch.object(self.adapter, "_run", return_value="META\t0\t0\t0"):
            result = self.adapter.search_fide_id("999999999", 0, 100)
        self.assertEqual(result["gameNumbers"], [])

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
