#!/usr/bin/python3
"""Chrome Native Messaging host for read-only Scid 5 queries.

Only stderr is used for diagnostics. Stdout is reserved for Chrome's framed
JSON protocol.
"""

import json
import os
import pathlib
import platform
import re
import struct
import subprocess
import sys
import tempfile
from typing import Any, BinaryIO, Dict, List, Optional, Sequence, Tuple


PROTOCOL_VERSION = 1
HOST_VERSION = "0.1.0"
MAX_INPUT_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 750 * 1024
MAX_PLAYER_LENGTH = 200
MAX_FIDE_ID_LENGTH = 12
MAX_SEARCH_RESULTS = 500
MAX_SEARCH_CURSOR = 2**31 - 1
# The complete result set is returned once, with the first page, so the caller
# can export beyond the games it has rendered. The ceiling keeps the response
# inside MAX_OUTPUT_BYTES and matches the 20 MB PGN export limit.
MAX_RESULT_GAME_NUMBERS = 20000
MAX_EXPORT_GAMES = 200
SEARCH_TIMEOUT_SECONDS = 30
# A FIDE-ID search scans the extra tags of every game instead of the name
# index, so it needs a longer ceiling than a name search.
FIDE_ID_SEARCH_TIMEOUT_SECONDS = 120
FIDE_ID_PATTERN = re.compile(r"[0-9]+")


class HostError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _config_path() -> pathlib.Path:
    override = os.environ.get("LUBRAS_CHESS_GENIE_CONFIG")
    if override:
        return pathlib.Path(override).expanduser()

    system = platform.system()
    if system == "Darwin":
        return pathlib.Path.home() / "Library/Application Support/LubrasChessGenie/config.json"
    if system == "Windows":
        base = pathlib.Path(os.environ.get("APPDATA", pathlib.Path.home()))
        return base / "LubrasChessGenie/config.json"

    base = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", pathlib.Path.home() / ".config"))
    return base / "lubras-chess-genie/config.json"


def _normalize_database_base(raw: str) -> pathlib.Path:
    value = raw.strip()
    if not value or any(ord(character) < 32 for character in value):
        raise HostError("DATABASE_PATH_INVALID", "The database path is invalid.")
    for extension in (".si5", ".sg5", ".sn5"):
        if value.lower().endswith(extension):
            value = value[: -len(extension)]
            break
    return pathlib.Path(value).expanduser().resolve()


def _normalize_fide_id(raw: Any) -> str:
    """Return a canonical FIDE ID or raise for anything that is not one.

    Only ASCII digits are accepted, so the value can safely be passed to Scid
    as a complete-value tag pattern. Leading zeros are dropped because stored
    tags never carry them; an all-zero value is rejected.
    """
    if not isinstance(raw, str):
        raise HostError("INVALID_FIDE_ID", "Enter a numeric FIDE ID.")
    value = raw.strip()
    if not value or len(value) > MAX_FIDE_ID_LENGTH or not FIDE_ID_PATTERN.fullmatch(value):
        raise HostError(
            "INVALID_FIDE_ID",
            "Enter a valid FIDE ID of up to {} digits.".format(MAX_FIDE_ID_LENGTH),
        )
    normalized = value.lstrip("0")
    if not normalized:
        raise HostError(
            "INVALID_FIDE_ID",
            "Enter a valid FIDE ID of up to {} digits.".format(MAX_FIDE_ID_LENGTH),
        )
    return normalized


def _validate_executable(raw: str) -> pathlib.Path:
    value = raw.strip()
    if not value or any(ord(character) < 32 for character in value):
        raise HostError("SCID_NOT_FOUND", "The configured Scid executable was not found.")
    path = pathlib.Path(value).expanduser().resolve()
    if not path.is_absolute() or not path.is_file():
        raise HostError("SCID_NOT_FOUND", "The configured Scid executable was not found.")
    if not os.access(str(path), os.X_OK):
        raise HostError("SCID_NOT_EXECUTABLE", "The configured Scid file is not executable.")
    return path


def _validate_database(raw: str) -> pathlib.Path:
    base = _normalize_database_base(raw)
    if not base.is_absolute():
        raise HostError("DATABASE_PATH_INVALID", "The database path must be absolute.")

    missing = []
    for extension in (".si5", ".sg5", ".sn5"):
        path = pathlib.Path(str(base) + extension)
        if not path.is_file() or not os.access(str(path), os.R_OK):
            missing.append(extension)
    if missing:
        raise HostError(
            "DATABASE_MISSING",
            "The configured Scid database is incomplete or unreadable (missing {}).".format(
                ", ".join(missing)
            ),
        )
    return base


class ConfigStore:
    def __init__(self, path: Optional[pathlib.Path] = None) -> None:
        self.path = path or _config_path()

    def load(self) -> Optional[Dict[str, str]]:
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as error:
            raise HostError("CONFIG_INVALID", "The native-host configuration cannot be read.") from error

        if not isinstance(value, dict):
            raise HostError("CONFIG_INVALID", "The native-host configuration is invalid.")
        scid = value.get("scidExecutable")
        database = value.get("databaseBase")
        if not isinstance(scid, str) or not isinstance(database, str):
            raise HostError("CONFIG_INVALID", "The native-host configuration is invalid.")
        return {"scidExecutable": scid, "databaseBase": database}

    def save(self, scid_executable: pathlib.Path, database_base: pathlib.Path) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "scidExecutable": str(scid_executable),
            "databaseBase": str(database_base),
        }
        descriptor, temporary = tempfile.mkstemp(
            prefix="config.", suffix=".tmp", dir=str(self.path.parent)
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(temporary, self.path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise


def _decode_field(value: str) -> str:
    import base64

    try:
        return base64.b64decode(value, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as error:
        raise HostError("SCID_OUTPUT_INVALID", "Scid returned invalid data.") from error


class ScidAdapter:
    def __init__(self, scid_executable: pathlib.Path, database_base: pathlib.Path) -> None:
        self.scid_executable = scid_executable
        self.database_base = database_base
        self.script_directory = pathlib.Path(__file__).resolve().parent / "scid"

    def _sandbox_profile(self) -> str:
        directory = str(self.database_base.parent)
        escaped = directory.replace("\\", "\\\\").replace('"', '\\"')
        return "\n".join(
            [
                "(version 1)",
                "(allow default)",
                '(deny file-write* (subpath "{}"))'.format(escaped),
            ]
        )

    def _run(self, script_name: str, arguments: Sequence[str], timeout: int) -> str:
        if platform.system() != "Darwin":
            raise HostError(
                "READ_ONLY_UNAVAILABLE",
                "This build currently supports enforced read-only access on macOS only.",
            )
        sandbox = pathlib.Path("/usr/bin/sandbox-exec")
        if not sandbox.is_file():
            raise HostError(
                "READ_ONLY_UNAVAILABLE",
                "The macOS read-only sandbox is unavailable.",
            )

        script = self.script_directory / script_name
        command = [
            str(sandbox),
            "-p",
            self._sandbox_profile(),
            str(self.scid_executable),
            str(script),
            str(self.database_base),
            *arguments,
        ]
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise HostError("SCID_TIMEOUT", "The Scid operation timed out.") from error
        except OSError as error:
            raise HostError("SCID_START_FAILED", "Scid could not be started.") from error

        if completed.returncode != 0:
            if "READ_ONLY_REQUIRED" in completed.stderr:
                raise HostError(
                    "READ_ONLY_REQUIRED",
                    "The database could not be opened with enforced read-only access.",
                )
            if "PGN_TOO_LARGE" in completed.stderr or "EXPORT_TOO_LARGE" in completed.stderr:
                raise HostError(
                    "PGN_TOO_LARGE",
                    "One or more selected games are too large to export safely.",
                )
            if "INVALID_GAME_NUMBER" in completed.stderr:
                raise HostError("INVALID_GAMES", "One or more game numbers are invalid.")
            raise HostError("SCID_FAILED", "Scid could not complete the requested operation.")
        return completed.stdout

    @staticmethod
    def _parse_game_numbers(value: str) -> List[int]:
        numbers: List[int] = []
        for item in value.split(","):
            if not item:
                continue
            try:
                number = int(item)
            except ValueError as error:
                raise HostError("SCID_OUTPUT_INVALID", "Scid returned invalid data.") from error
            if number > 0:
                numbers.append(number)
            if len(numbers) >= MAX_RESULT_GAME_NUMBERS:
                break
        return numbers

    @staticmethod
    def _game_from_parts(parts: Sequence[str]) -> Dict[str, Any]:
        return {
            "gameNumber": int(parts[1]),
            "date": _decode_field(parts[2]) or None,
            "event": _decode_field(parts[3]) or None,
            "round": _decode_field(parts[4]) or None,
            "white": _decode_field(parts[5]) or None,
            "black": _decode_field(parts[6]) or None,
            "result": _decode_field(parts[7]) or None,
            "whiteElo": int(_decode_field(parts[8]) or 0) or None,
            "blackElo": int(_decode_field(parts[9]) or 0) or None,
            "eco": _decode_field(parts[10]) or None,
        }

    def search_player(self, player: str, offset: int, limit: int) -> Dict[str, Any]:
        output = self._run(
            "search-player.tcl",
            [player, str(offset), str(limit)],
            timeout=SEARCH_TIMEOUT_SECONDS,
        )
        candidates: List[Dict[str, Any]] = []
        games: List[Dict[str, Any]] = []
        game_numbers: List[int] = []
        total = 0
        selected_player: Optional[str] = None

        for line in output.splitlines():
            parts = line.split("\t")
            if not parts:
                continue
            if parts[0] == "CANDIDATE" and len(parts) == 3:
                candidates.append({"frequency": int(parts[1]), "name": _decode_field(parts[2])})
            elif parts[0] == "META" and len(parts) == 4:
                total = int(parts[1])
                selected_player = _decode_field(parts[3]) or None
            elif parts[0] == "NUMBERS" and len(parts) == 2:
                game_numbers = self._parse_game_numbers(parts[1])
            elif parts[0] == "GAME" and len(parts) == 11:
                games.append(self._game_from_parts(parts))

        if selected_player is None:
            return {
                "total": 0,
                "games": [],
                "gameNumbers": [],
                "candidates": candidates,
                "requiresPlayerChoice": bool(candidates),
                "playerNotFound": not candidates,
                "nextCursor": None,
            }

        next_cursor = offset + len(games) if offset + len(games) < total else None
        return {
            "total": total,
            "games": games,
            "gameNumbers": game_numbers,
            "candidates": candidates,
            "requiresPlayerChoice": False,
            "playerNotFound": False,
            "selectedPlayer": selected_player,
            "nextCursor": next_cursor,
        }

    def search_fide_id(self, fide_id: str, offset: int, limit: int) -> Dict[str, Any]:
        output = self._run(
            "search-fideid.tcl",
            [fide_id, str(offset), str(limit)],
            timeout=FIDE_ID_SEARCH_TIMEOUT_SECONDS,
        )
        games: List[Dict[str, Any]] = []
        game_numbers: List[int] = []
        seen_game_numbers: set = set()
        name_counts: Dict[str, int] = {}
        total = 0
        examined = 0

        for line in output.splitlines():
            parts = line.split("\t")
            if not parts:
                continue
            if parts[0] == "META" and len(parts) == 4:
                total = int(parts[1])
                examined = int(parts[3])
            elif parts[0] == "NUMBERS" and len(parts) == 2:
                game_numbers = self._parse_game_numbers(parts[1])
            elif parts[0] == "GAME" and len(parts) == 13:
                # Only a complete, character-for-character identifier counts;
                # a tag that merely contains the digits is never a match.
                white_matches = _decode_field(parts[11]).strip() == fide_id
                black_matches = _decode_field(parts[12]).strip() == fide_id
                if not white_matches and not black_matches:
                    continue
                game = self._game_from_parts(parts)
                if game["gameNumber"] in seen_game_numbers:
                    continue
                seen_game_numbers.add(game["gameNumber"])
                stored_name = game["white"] if white_matches else game["black"]
                if stored_name:
                    name_counts[stored_name] = name_counts.get(stored_name, 0) + 1
                games.append(game)

        # The name most often stored beside this identifier is the display name.
        selected_player = max(name_counts, key=name_counts.get) if name_counts else None
        advanced = examined if examined > 0 else len(games)
        next_cursor = offset + advanced if advanced and offset + advanced < total else None
        return {
            "total": total,
            "games": games,
            "gameNumbers": game_numbers,
            "candidates": [],
            "requiresPlayerChoice": False,
            "playerNotFound": total == 0,
            "selectedPlayer": selected_player,
            "fideId": fide_id,
            "nextCursor": next_cursor,
        }

    def export_games(self, game_numbers: Sequence[int]) -> List[Dict[str, Any]]:
        csv_numbers = ",".join(str(number) for number in game_numbers)
        output = self._run("export-games.tcl", [csv_numbers], timeout=45)
        games: List[Dict[str, Any]] = []
        for line in output.splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3 or parts[0] != "PGN":
                continue
            games.append({"gameNumber": int(parts[1]), "pgn": _decode_field(parts[2])})
        if len(games) != len(game_numbers):
            raise HostError("SCID_OUTPUT_INVALID", "Scid returned an incomplete PGN export.")
        return games


class NativeHost:
    def __init__(self, config_store: Optional[ConfigStore] = None) -> None:
        self.config_store = config_store or ConfigStore()

    def _status(self) -> Dict[str, Any]:
        config = self.config_store.load()
        if config is None:
            return {"configured": False, "ready": False}
        try:
            scid = _validate_executable(config["scidExecutable"])
            database = _validate_database(config["databaseBase"])
            return {
                "configured": True,
                "ready": True,
                "scidExecutable": str(scid),
                "databaseBase": str(database),
                "databaseLabel": database.name,
            }
        except HostError as error:
            return {
                "configured": True,
                "ready": False,
                "scidExecutable": config["scidExecutable"],
                "databaseBase": config["databaseBase"],
                "errorCode": error.code,
            }

    def _adapter(self) -> ScidAdapter:
        config = self.config_store.load()
        if config is None:
            raise HostError("HOST_NOT_CONFIGURED", "Configure Scid and a database first.")
        return ScidAdapter(
            _validate_executable(config["scidExecutable"]),
            _validate_database(config["databaseBase"]),
        )

    def dispatch(self, request: Any) -> Dict[str, Any]:
        if not isinstance(request, dict):
            raise HostError("INVALID_REQUEST", "The request must be a JSON object.")
        self._reject_unknown_fields(request, {"protocolVersion", "id", "command", "payload"})
        request_id = request.get("id")
        if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
            raise HostError("INVALID_REQUEST", "The request ID is invalid.")
        if request.get("protocolVersion") != PROTOCOL_VERSION:
            raise HostError("PROTOCOL_MISMATCH", "The protocol version is not supported.")
        command = request.get("command")
        payload = request.get("payload", {})
        if not isinstance(payload, dict):
            raise HostError("INVALID_REQUEST", "The request payload must be an object.")

        response: Dict[str, Any]
        if command == "hello":
            self._reject_unknown_fields(payload, set())
            response = {
                "hostVersion": HOST_VERSION,
                "protocolVersion": PROTOCOL_VERSION,
                "platform": platform.system().lower(),
            }
        elif command == "status":
            self._reject_unknown_fields(payload, set())
            response = self._status()
        elif command == "configure":
            self._reject_unknown_fields(payload, {"scidExecutable", "databaseBase"})
            scid_raw = payload.get("scidExecutable")
            database_raw = payload.get("databaseBase")
            if not isinstance(scid_raw, str) or not isinstance(database_raw, str):
                raise HostError("INVALID_REQUEST", "Both configuration paths are required.")
            scid = _validate_executable(scid_raw)
            database = _validate_database(database_raw)
            self.config_store.save(scid, database)
            response = self._status()
        elif command == "searchPlayer":
            self._reject_unknown_fields(payload, {"player", "limit", "cursor"})
            player = payload.get("player")
            if not isinstance(player, str) or not player.strip() or len(player) > MAX_PLAYER_LENGTH:
                raise HostError("INVALID_PLAYER", "Enter a valid player name.")
            cursor, limit = self._page_bounds(payload)
            response = self._adapter().search_player(player.strip(), cursor, limit)
        elif command == "searchFideId":
            self._reject_unknown_fields(payload, {"fideId", "limit", "cursor"})
            fide_id = _normalize_fide_id(payload.get("fideId"))
            cursor, limit = self._page_bounds(payload)
            response = self._adapter().search_fide_id(fide_id, cursor, limit)
        elif command == "getPgn":
            self._reject_unknown_fields(payload, {"gameNumbers"})
            game_numbers = payload.get("gameNumbers")
            if not isinstance(game_numbers, list) or not game_numbers:
                raise HostError("INVALID_GAMES", "Choose at least one game.")
            if len(game_numbers) > MAX_EXPORT_GAMES:
                raise HostError("INVALID_GAMES", "Too many games were requested at once.")
            if any(isinstance(number, bool) or not isinstance(number, int) or number <= 0 for number in game_numbers):
                raise HostError("INVALID_GAMES", "One or more game numbers are invalid.")
            if len(set(game_numbers)) != len(game_numbers):
                raise HostError("INVALID_GAMES", "Duplicate game numbers are not allowed.")

            exported = self._adapter().export_games(game_numbers)
            accepted: List[Dict[str, Any]] = []
            for game in exported:
                remaining = list(game_numbers[len(accepted) + 1 :])
                candidate = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "id": request_id,
                    "ok": True,
                    "games": accepted + [game],
                    "remainingGameNumbers": remaining,
                }
                encoded = json.dumps(candidate, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                if len(encoded) > MAX_OUTPUT_BYTES:
                    break
                accepted.append(game)
            if not accepted:
                raise HostError("PGN_TOO_LARGE", "A selected game is too large to export safely.")
            response = {
                "games": accepted,
                "remainingGameNumbers": list(game_numbers[len(accepted) :]),
            }
        else:
            raise HostError("UNKNOWN_COMMAND", "The requested command is not supported.")

        return {
            "protocolVersion": PROTOCOL_VERSION,
            "id": request_id,
            "ok": True,
            **response,
        }

    @staticmethod
    def _page_bounds(payload: Dict[str, Any]) -> Tuple[int, int]:
        limit = payload.get("limit", 100)
        cursor = payload.get("cursor", 0)
        if cursor is None:
            cursor = 0
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_SEARCH_RESULTS:
            raise HostError("INVALID_LIMIT", "The result limit is invalid.")
        if isinstance(cursor, bool) or not isinstance(cursor, int) or not 0 <= cursor <= MAX_SEARCH_CURSOR:
            raise HostError("INVALID_CURSOR", "The result cursor is invalid.")
        return cursor, limit

    @staticmethod
    def _reject_unknown_fields(value: Dict[str, Any], allowed: set) -> None:
        if set(value) - allowed:
            raise HostError("INVALID_REQUEST", "The request contains unsupported fields.")


def _read_exact(stream: BinaryIO, length: int) -> bytes:
    chunks = []
    remaining = length
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_message(stream: BinaryIO) -> Optional[Any]:
    header = _read_exact(stream, 4)
    if header == b"":
        return None
    if len(header) != 4:
        raise HostError("INVALID_FRAME", "The native message header is incomplete.")
    length = struct.unpack("=I", header)[0]
    if length == 0 or length > MAX_INPUT_BYTES:
        raise HostError("INVALID_FRAME", "The native message size is invalid.")
    payload = _read_exact(stream, length)
    if len(payload) != length:
        raise HostError("INVALID_FRAME", "The native message body is incomplete.")
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise HostError("INVALID_JSON", "The native message is not valid JSON.") from error


def write_message(stream: BinaryIO, message: Dict[str, Any]) -> None:
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_OUTPUT_BYTES:
        raise HostError("RESPONSE_TOO_LARGE", "The native response is too large.")
    stream.write(struct.pack("=I", len(payload)))
    stream.write(payload)
    stream.flush()


def _error_response(request_id: str, error: HostError) -> Dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "id": request_id,
        "ok": False,
        "error": {"code": error.code, "message": error.message},
    }


def main() -> int:
    host = NativeHost()
    input_stream = sys.stdin.buffer
    output_stream = sys.stdout.buffer
    while True:
        try:
            request = read_message(input_stream)
            if request is None:
                return 0
            request_id = request.get("id", "") if isinstance(request, dict) else ""
            try:
                response = host.dispatch(request)
            except HostError as error:
                response = _error_response(request_id, error)
            write_message(output_stream, response)
        except HostError as error:
            print("native host protocol error: {}".format(error.code), file=sys.stderr)
            try:
                write_message(output_stream, _error_response("", error))
            except HostError:
                pass
            return 1
        except Exception as error:  # Last-resort containment; details stay on stderr.
            print("native host internal error: {}".format(type(error).__name__), file=sys.stderr)
            try:
                write_message(
                    output_stream,
                    _error_response("", HostError("INTERNAL_ERROR", "The native host failed.")),
                )
            except HostError:
                pass
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
