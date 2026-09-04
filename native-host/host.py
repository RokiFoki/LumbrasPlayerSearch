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
# Metadata for already-known game numbers is cheap, so the table can be
# filled without repeating a search.
MAX_DETAIL_GAMES = 1000
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
            # POSIX keeps the saved paths private to the user. Windows has no
            # equivalent file mode and lacks os.fchmod before Python 3.13, so
            # the restriction is applied only where it is meaningful.
            if hasattr(os, "fchmod"):
                try:
                    os.fchmod(descriptor, 0o600)
                except (OSError, NotImplementedError):
                    pass
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


# ---------------------------------------------------------------------------
# Windows enforced read-only launch.
#
# macOS denies writes to the database directory through sandbox-exec. Windows
# has no such per-path deny, but it does have Mandatory Integrity Control: a
# process launched at Low integrity can read ordinary (Medium) files yet cannot
# write them. Running Scid at Low integrity is therefore the direct analogue of
# the macOS deny-write, and it needs no third-party dependency -- only the
# standard library through ctypes and the Win32 API.
#
# The token is duplicated from this host's own token and merely *lowered* to the
# Low integrity SID (S-1-16-4096). Lowering the caller's own token to an equal
# or lower level does not require SeAssignPrimaryTokenPrivilege, so a normal
# interactive user can launch the child. Scid still needs somewhere writable for
# its temporary files, so it is given a dedicated scratch directory whose own
# integrity label is set to Low; the database directory is never made writable.
# ---------------------------------------------------------------------------

if platform.system() == "Windows":
    import ctypes
    import shutil
    import threading
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

    _LOW_INTEGRITY_SID = "S-1-16-4096"

    _TOKEN_DUPLICATE = 0x0002
    _TOKEN_QUERY = 0x0008
    _TOKEN_ASSIGN_PRIMARY = 0x0001
    _TOKEN_ADJUST_DEFAULT = 0x0080
    _TOKEN_ADJUST_SESSIONID = 0x0100
    _MAXIMUM_ALLOWED = 0x02000000

    _SecurityImpersonation = 2
    _TokenPrimary = 1
    _TokenIntegrityLevel = 25
    _SE_GROUP_INTEGRITY = 0x00000020

    _STARTF_USESTDHANDLES = 0x00000100
    _CREATE_NO_WINDOW = 0x08000000
    _CREATE_UNICODE_ENVIRONMENT = 0x00000400
    _HANDLE_FLAG_INHERIT = 0x00000001
    _WAIT_TIMEOUT = 0x00000102
    _INFINITE = 0xFFFFFFFF

    _LABEL_SECURITY_INFORMATION = 0x00000010
    _SE_FILE_OBJECT = 1
    _SDDL_REVISION_1 = 1

    _GENERIC_READ = 0x80000000
    _FILE_SHARE_READ = 0x00000001
    _FILE_SHARE_WRITE = 0x00000002
    _OPEN_EXISTING = 3

    class _STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class _PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    class _SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [
            ("nLength", wintypes.DWORD),
            ("lpSecurityDescriptor", wintypes.LPVOID),
            ("bInheritHandle", wintypes.BOOL),
        ]

    class _SID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Sid", wintypes.LPVOID), ("Attributes", wintypes.DWORD)]

    class _TOKEN_MANDATORY_LABEL(ctypes.Structure):
        _fields_ = [("Label", _SID_AND_ATTRIBUTES)]

    def _win_check(result, func, arguments):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())
        return result

    _advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)
    ]
    _advapi32.OpenProcessToken.errcheck = _win_check
    _advapi32.DuplicateTokenEx.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(_SECURITY_ATTRIBUTES),
        ctypes.c_int, ctypes.c_int, ctypes.POINTER(wintypes.HANDLE),
    ]
    _advapi32.DuplicateTokenEx.errcheck = _win_check
    _advapi32.SetTokenInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD
    ]
    _advapi32.SetTokenInformation.errcheck = _win_check
    _advapi32.ConvertStringSidToSidW.argtypes = [
        wintypes.LPCWSTR, ctypes.POINTER(wintypes.LPVOID)
    ]
    _advapi32.ConvertStringSidToSidW.errcheck = _win_check
    _advapi32.CreateProcessAsUserW.argtypes = [
        wintypes.HANDLE, wintypes.LPCWSTR, wintypes.LPWSTR,
        ctypes.POINTER(_SECURITY_ATTRIBUTES), ctypes.POINTER(_SECURITY_ATTRIBUTES),
        wintypes.BOOL, wintypes.DWORD, wintypes.LPVOID, wintypes.LPCWSTR,
        ctypes.POINTER(_STARTUPINFOW), ctypes.POINTER(_PROCESS_INFORMATION),
    ]
    _advapi32.CreateProcessAsUserW.errcheck = _win_check
    _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.ULONG),
    ]
    _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.errcheck = _win_check
    _advapi32.GetSecurityDescriptorSacl.argtypes = [
        wintypes.LPVOID, ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.BOOL),
    ]
    _advapi32.GetSecurityDescriptorSacl.errcheck = _win_check
    _advapi32.SetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD,
        wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID,
    ]

    _kernel32.CreatePipe.argtypes = [
        ctypes.POINTER(wintypes.HANDLE), ctypes.POINTER(wintypes.HANDLE),
        ctypes.POINTER(_SECURITY_ATTRIBUTES), wintypes.DWORD,
    ]
    _kernel32.CreatePipe.errcheck = _win_check
    _kernel32.SetHandleInformation.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD
    ]
    _kernel32.SetHandleInformation.errcheck = _win_check
    _kernel32.ReadFile.argtypes = [
        wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
    ]
    _kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(_SECURITY_ATTRIBUTES),
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)
    ]
    _kernel32.GetExitCodeProcess.errcheck = _win_check
    _kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    _kernel32.LocalFree.argtypes = [wintypes.HANDLE]

    def _label_directory_low(path: str) -> None:
        """Set a directory's mandatory label to Low so a Low-IL child may write it.

        Object and container inheritance ("OICI") makes files Scid creates in the
        scratch directory Low as well, so writing them is never a write-up.
        """
        descriptor = wintypes.LPVOID()
        _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            "S:(ML;OICI;NW;;;LW)", _SDDL_REVISION_1, ctypes.byref(descriptor), None
        )
        try:
            present = wintypes.BOOL()
            sacl = wintypes.LPVOID()
            defaulted = wintypes.BOOL()
            _advapi32.GetSecurityDescriptorSacl(
                descriptor, ctypes.byref(present), ctypes.byref(sacl), ctypes.byref(defaulted)
            )
            error = _advapi32.SetNamedSecurityInfoW(
                path, _SE_FILE_OBJECT, _LABEL_SECURITY_INFORMATION,
                None, None, None, sacl,
            )
            if error != 0:
                raise ctypes.WinError(error)
        finally:
            _kernel32.LocalFree(descriptor)

    def _create_low_integrity_token() -> "wintypes.HANDLE":
        """Duplicate this process's token and lower it to Low integrity."""
        process_token = wintypes.HANDLE()
        _advapi32.OpenProcessToken(
            _kernel32.GetCurrentProcess(),
            _TOKEN_DUPLICATE | _TOKEN_QUERY | _TOKEN_ASSIGN_PRIMARY
            | _TOKEN_ADJUST_DEFAULT | _TOKEN_ADJUST_SESSIONID,
            ctypes.byref(process_token),
        )
        try:
            low_token = wintypes.HANDLE()
            _advapi32.DuplicateTokenEx(
                process_token, _MAXIMUM_ALLOWED, None,
                _SecurityImpersonation, _TokenPrimary, ctypes.byref(low_token),
            )
        finally:
            _kernel32.CloseHandle(process_token)

        try:
            low_sid = wintypes.LPVOID()
            _advapi32.ConvertStringSidToSidW(_LOW_INTEGRITY_SID, ctypes.byref(low_sid))
            try:
                label = _TOKEN_MANDATORY_LABEL()
                label.Label.Sid = low_sid
                label.Label.Attributes = _SE_GROUP_INTEGRITY
                _advapi32.SetTokenInformation(
                    low_token, _TokenIntegrityLevel, ctypes.byref(label), ctypes.sizeof(label)
                )
            finally:
                _kernel32.LocalFree(low_sid)
        except OSError:
            # Never leak the duplicated token if lowering it failed; the caller
            # will fail closed on the raised error.
            _kernel32.CloseHandle(low_token)
            raise
        return low_token

    def _build_environment_block(overrides: Dict[str, str]) -> "ctypes.Array":
        environment = os.environ.copy()
        environment.update(overrides)
        block = "".join("{}={}\0".format(key, value) for key, value in environment.items()) + "\0"
        return ctypes.create_unicode_buffer(block)

    def _run_scid_low_integrity(
        application_name: str,
        command: Sequence[str],
        cwd: str,
        env_overrides: Dict[str, str],
        timeout_seconds: int,
    ) -> Tuple[int, str, str]:
        """Run Scid at Low integrity, capturing stdout/stderr; raise HostError on failure.

        A failure to build the lowered token or to label the scratch directory
        means the read-only sandbox is unavailable, so the caller fails closed
        rather than querying without it.
        """
        try:
            low_token = _create_low_integrity_token()
        except OSError as error:
            raise HostError(
                "READ_ONLY_UNAVAILABLE",
                "The Windows low-integrity sandbox could not be prepared.",
            ) from error

        security = _SECURITY_ATTRIBUTES()
        security.nLength = ctypes.sizeof(security)
        security.bInheritHandle = True
        security.lpSecurityDescriptor = None

        def make_pipe() -> Tuple["wintypes.HANDLE", "wintypes.HANDLE"]:
            read_end = wintypes.HANDLE()
            write_end = wintypes.HANDLE()
            _kernel32.CreatePipe(
                ctypes.byref(read_end), ctypes.byref(write_end), ctypes.byref(security), 0
            )
            _kernel32.SetHandleInformation(read_end, _HANDLE_FLAG_INHERIT, 0)
            return read_end, write_end

        out_read, out_write = make_pipe()
        err_read, err_write = make_pipe()
        nul = _kernel32.CreateFileW(
            "NUL", _GENERIC_READ, _FILE_SHARE_READ | _FILE_SHARE_WRITE,
            ctypes.byref(security), _OPEN_EXISTING, 0, None,
        )

        startup = _STARTUPINFOW()
        startup.cb = ctypes.sizeof(startup)
        startup.dwFlags = _STARTF_USESTDHANDLES
        startup.hStdInput = nul
        startup.hStdOutput = out_write
        startup.hStdError = err_write
        information = _PROCESS_INFORMATION()

        command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(list(command)))
        environment = _build_environment_block(env_overrides)

        try:
            _advapi32.CreateProcessAsUserW(
                low_token, application_name, command_line, None, None, True,
                _CREATE_NO_WINDOW | _CREATE_UNICODE_ENVIRONMENT,
                ctypes.cast(environment, wintypes.LPVOID), cwd,
                ctypes.byref(startup), ctypes.byref(information),
            )
        except OSError as error:
            for handle in (out_read, out_write, err_read, err_write, nul, low_token):
                _kernel32.CloseHandle(handle)
            raise HostError("SCID_START_FAILED", "Scid could not be started.") from error

        _kernel32.CloseHandle(out_write)
        _kernel32.CloseHandle(err_write)
        _kernel32.CloseHandle(nul)
        _kernel32.CloseHandle(low_token)

        collected = {"out": [], "err": []}

        def drain(handle: "wintypes.HANDLE", key: str) -> None:
            buffer = ctypes.create_string_buffer(65536)
            read = wintypes.DWORD()
            while True:
                ok = _kernel32.ReadFile(handle, buffer, len(buffer), ctypes.byref(read), None)
                if not ok or read.value == 0:
                    break
                collected[key].append(buffer.raw[: read.value])
            _kernel32.CloseHandle(handle)

        threads = [
            threading.Thread(target=drain, args=(out_read, "out")),
            threading.Thread(target=drain, args=(err_read, "err")),
        ]
        for thread in threads:
            thread.start()

        timed_out = False
        waited = _kernel32.WaitForSingleObject(
            information.hProcess, int(timeout_seconds * 1000)
        )
        if waited == _WAIT_TIMEOUT:
            timed_out = True
            _kernel32.TerminateProcess(information.hProcess, 1)
            _kernel32.WaitForSingleObject(information.hProcess, _INFINITE)
        for thread in threads:
            thread.join()

        exit_code = wintypes.DWORD()
        _kernel32.GetExitCodeProcess(information.hProcess, ctypes.byref(exit_code))
        _kernel32.CloseHandle(information.hProcess)
        _kernel32.CloseHandle(information.hThread)

        if timed_out:
            raise HostError("SCID_TIMEOUT", "The Scid operation timed out.")

        stdout = b"".join(collected["out"]).decode("utf-8", "replace")
        stderr = b"".join(collected["err"]).decode("utf-8", "replace")
        return exit_code.value, stdout, stderr


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
        """Run a Scid Tcl script with enforced read-only access to the database.

        The launch is platform-specific: macOS denies writes to the database
        directory with sandbox-exec, Windows runs Scid at Low integrity. Every
        other platform fails closed. The rest -- return-code and stderr mapping,
        timeout and start-failure handling -- is shared.
        """
        script = self.script_directory / script_name
        system = platform.system()
        if system == "Darwin":
            returncode, stdout, stderr = self._run_darwin(script, arguments, timeout)
        elif system == "Windows":
            returncode, stdout, stderr = self._run_windows(script, arguments, timeout)
        else:
            raise HostError(
                "READ_ONLY_UNAVAILABLE",
                "This build supports enforced read-only access on macOS and Windows only.",
            )
        return self._interpret(returncode, stdout, stderr)

    @staticmethod
    def _interpret(returncode: int, stdout: str, stderr: str) -> str:
        if returncode != 0:
            if "READ_ONLY_REQUIRED" in stderr:
                raise HostError(
                    "READ_ONLY_REQUIRED",
                    "The database could not be opened with enforced read-only access.",
                )
            if "PGN_TOO_LARGE" in stderr or "EXPORT_TOO_LARGE" in stderr:
                raise HostError(
                    "PGN_TOO_LARGE",
                    "One or more selected games are too large to export safely.",
                )
            if "INVALID_GAME_NUMBER" in stderr:
                raise HostError("INVALID_GAMES", "One or more game numbers are invalid.")
            raise HostError("SCID_FAILED", "Scid could not complete the requested operation.")
        return stdout

    def _run_darwin(
        self, script: pathlib.Path, arguments: Sequence[str], timeout: int
    ) -> Tuple[int, str, str]:
        sandbox = pathlib.Path("/usr/bin/sandbox-exec")
        if not sandbox.is_file():
            raise HostError(
                "READ_ONLY_UNAVAILABLE",
                "The macOS read-only sandbox is unavailable.",
            )

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
        return completed.returncode, completed.stdout, completed.stderr

    def _run_windows(
        self, script: pathlib.Path, arguments: Sequence[str], timeout: int
    ) -> Tuple[int, str, str]:
        command = [
            str(self.scid_executable),
            str(script),
            str(self.database_base),
            *arguments,
        ]
        # A dedicated Low-integrity scratch directory gives Scid somewhere to
        # write its temporary files; the database directory is never made
        # writable. It is created outside the database directory and removed
        # afterwards. Preparing it is part of the sandbox, so any failure fails
        # closed rather than querying without enforced read-only access.
        try:
            scratch = tempfile.mkdtemp(prefix="lubras-chess-genie-scratch.")
        except OSError as error:
            raise HostError(
                "READ_ONLY_UNAVAILABLE",
                "The Windows low-integrity sandbox could not be prepared.",
            ) from error
        try:
            try:
                _label_directory_low(scratch)
            except OSError as error:
                raise HostError(
                    "READ_ONLY_UNAVAILABLE",
                    "The Windows low-integrity sandbox could not be prepared.",
                ) from error
            environment = {"TEMP": scratch, "TMP": scratch, "TMPDIR": scratch}
            return _run_scid_low_integrity(
                str(self.scid_executable), command, scratch, environment, timeout
            )
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

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

    def list_games(self, game_numbers: Sequence[int]) -> List[Dict[str, Any]]:
        csv_numbers = ",".join(str(number) for number in game_numbers)
        output = self._run("list-games.tcl", [csv_numbers], timeout=SEARCH_TIMEOUT_SECONDS)
        games: List[Dict[str, Any]] = []
        for line in output.splitlines():
            parts = line.split("\t")
            if parts[0] == "GAME" and len(parts) == 11:
                games.append(self._game_from_parts(parts))
        if len(games) != len(game_numbers):
            raise HostError("SCID_OUTPUT_INVALID", "Scid returned incomplete game details.")
        return games

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
        elif command == "getGames":
            self._reject_unknown_fields(payload, {"gameNumbers"})
            game_numbers = self._validate_game_numbers(payload.get("gameNumbers"), MAX_DETAIL_GAMES)
            response = {"games": self._adapter().list_games(game_numbers)}
        elif command == "getPgn":
            self._reject_unknown_fields(payload, {"gameNumbers"})
            game_numbers = self._validate_game_numbers(payload.get("gameNumbers"), MAX_EXPORT_GAMES)

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
    def _validate_game_numbers(value: Any, maximum: int) -> List[int]:
        if not isinstance(value, list) or not value:
            raise HostError("INVALID_GAMES", "Choose at least one game.")
        if len(value) > maximum:
            raise HostError("INVALID_GAMES", "Too many games were requested at once.")
        if any(isinstance(number, bool) or not isinstance(number, int) or number <= 0 for number in value):
            raise HostError("INVALID_GAMES", "One or more game numbers are invalid.")
        if len(set(value)) != len(value):
            raise HostError("INVALID_GAMES", "Duplicate game numbers are not allowed.")
        return value

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
