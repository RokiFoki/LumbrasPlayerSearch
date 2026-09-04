"""Windows read-only proof: run a real Scid 5 query at Low integrity and show the
database is byte-for-byte unchanged.

This is the Windows analogue of run-readonly-proof.sh. Where macOS denies writes
to the database directory with sandbox-exec, Windows runs Scid at Low integrity
using the exact launcher host.py uses in production (host._run_scid_low_integrity
against a Low-labeled scratch directory). It then compares the size, SHA-256, and
modification time of every database file before and after the query.

Usage:
    py -3 native-host\\proof\\run-readonly-proof-windows.py ^
        "C:\\path\\to\\scid.exe" ^
        "C:\\path\\to\\DatabaseName" ^
        "Carlsen, Magnus"

The database base path is given without the .si5/.sg5/.sn5 extension.
"""

import hashlib
import pathlib
import shutil
import sys
import tempfile


NATIVE_HOST_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(NATIVE_HOST_DIR))

import host  # noqa: E402


def fingerprint(database_base):
    state = {}
    for extension in (".si5", ".sg5", ".sn5"):
        path = pathlib.Path(str(database_base) + extension)
        if not path.is_file():
            raise SystemExit("Missing or unreadable database file: {}".format(path))
        data = path.read_bytes()
        stat = path.stat()
        state[extension] = (len(data), hashlib.sha256(data).hexdigest(), stat.st_mtime_ns)
    return state


def main(argv):
    if len(argv) != 3:
        raise SystemExit(
            "usage: run-readonly-proof-windows.py SCID_EXECUTABLE DATABASE_BASE PLAYER_QUERY"
        )
    if host.platform.system() != "Windows":
        raise SystemExit("This proof runs on Windows only.")

    scid_executable, database_base, player_query = argv
    query_script = pathlib.Path(__file__).resolve().parent / "query-player.tcl"

    before = fingerprint(database_base)

    scratch = tempfile.mkdtemp(prefix="lubras-chess-genie-proof.")
    try:
        host._label_directory_low(scratch)
        output_pgn = str(pathlib.Path(scratch) / "first-match.proof.pgn")
        command = [
            scid_executable,
            str(query_script),
            database_base,
            player_query,
            output_pgn,
        ]
        code, stdout, stderr = host._run_scid_low_integrity(
            scid_executable,
            command,
            scratch,
            {"TEMP": scratch, "TMP": scratch, "TMPDIR": scratch},
            120,
        )
        print(stdout, end="")
        if code != 0:
            sys.stderr.write(stderr)
            raise SystemExit("Scid query failed with exit code {}.".format(code))

        exported = pathlib.Path(output_pgn)
        pgn_bytes = exported.stat().st_size if exported.is_file() else 0
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    after = fingerprint(database_base)

    if before != after:
        for extension in before:
            if before[extension] != after[extension]:
                print("CHANGED {}: {} -> {}".format(extension, before[extension], after[extension]))
        raise SystemExit("FAILED: database files changed during the proof.")

    print("first_match_pgn_bytes={}".format(pgn_bytes))
    print("database_unchanged=1")


if __name__ == "__main__":
    main(sys.argv[1:])
