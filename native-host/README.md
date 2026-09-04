# Native host

Chrome extensions cannot directly read arbitrary local files. The production
design therefore uses Chrome Native Messaging:

```text
extension -> length-prefixed JSON -> local native host -> Scid database
```

The `proof` directory demonstrates the Scid side against a real `.si5` database.
It calls an official Scid 5.2 executable with a Tcl script, refuses to continue
unless `sc_base isReadOnly` returns true, searches the indexed player headers,
and exports the first match as PGN.

For development, the official macOS Scid 5.2 application bundle is sufficient;
it carries its own Tcl/Tk 9.0.4 runtime. Nothing needs to be installed through
Homebrew, and Tcl 8.6 is not required for this route.

The implemented Python host uses only the Python standard library. It provides:

- Chrome's four-byte length-prefixed JSON protocol;
- host-owned configuration in the user's application-support directory;
- strict path, command, player, FIDE ID, cursor, and result validation;
- player candidate lookup and newest-first paginated game metadata, plus the
  complete bounded result set with the first page;
- exact FIDE ID lookup across the `WhiteFideId` and `BlackFideId` tags, merged
  without duplicates and resolved to the stored player name;
- bounded game metadata for known game numbers, so a client can complete a
  result set without repeating a search;
- bounded selected-game PGN export;
- timeouts and stable safe error codes.

Enforced read-only access is platform-specific, but everything else — request
framing, validation, dispatch, the search logic, timeouts, and the response cap
— is shared:

- **macOS:** every Scid child process runs through `/usr/bin/sandbox-exec` with
  writes denied to the database directory.
- **Windows:** every Scid child process runs at **Low integrity level** through
  the Win32 API (`CreateProcessAsUserW` with the process token lowered to the
  Low mandatory-integrity SID). A Low-integrity process can read ordinary files
  but cannot write them, so the database directory is immutable to it. Scid is
  given a dedicated Low-integrity scratch directory for its temporary files; the
  database directory is never made writable. Only the Python standard library
  and the built-in Windows API are used.

On both platforms the Tcl adapter additionally refuses to continue unless Scid
reports `sc_base isReadOnly` as true. If the platform sandbox cannot be prepared
(or the platform is neither macOS nor Windows) the helper fails closed and
returns `READ_ONLY_UNAVAILABLE` rather than querying without enforced read-only
access.

`native-host/proof/run-readonly-proof.sh` (macOS) and
`native-host/proof/run-readonly-proof-windows.py` (Windows) run a real query and
prove the database files are byte-for-byte unchanged.

## Development registration (macOS)

1. Load `extension/` as an unpacked Chrome extension.
2. Copy its 32-character extension ID.
3. Run `scripts/install-macos.sh EXTENSION_ID`.
4. Restart Chrome.
5. In the popup, enter the executable inside Scid.app and the common database
   base path without its extension.

Registration is deliberately not automatic. The script installs a private copy
of the helper outside protected Desktop and Documents folders:

```text
~/Library/Application Support/LubrasChessGenie/native-host/
```

It then writes Chrome's per-user registration manifest:

```text
~/Library/Application Support/Google/Chrome/NativeMessagingHosts/
  app.chessgenie.local_games.json
```

Run `scripts/uninstall-macos.sh` to remove the installed helper and manifest.
Add `--remove-config` to also remove the saved local paths.

## Development registration (Windows)

1. Load `extension/` as an unpacked Chrome extension.
2. Copy its 32-character extension ID.
3. Run `powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1 EXTENSION_ID`.
4. Fully quit and reopen Chrome.
5. In the popup, enter the full path to the Scid executable and the common
   database base path without its extension.

Chrome finds a native host on Windows through the registry rather than a
manifest directory. The installer copies a private helper outside the
repository:

```text
%LOCALAPPDATA%\LumbrasChessGenie\native-host\
```

renders the manifest next to it with the same
`scripts/render-native-manifest.py` used on macOS:

```text
%LOCALAPPDATA%\LumbrasChessGenie\app.chessgenie.local_games.json
```

and points Chrome at that manifest with a registry value whose default data is
the manifest's absolute path:

```text
HKCU\Software\Google\Chrome\NativeMessagingHosts\app.chessgenie.local_games
```

Run `powershell -ExecutionPolicy Bypass -File scripts\uninstall-windows.ps1` to
remove the installed helper, manifest, and registry value. Add `-RemoveConfig`
to also remove the saved local paths.
