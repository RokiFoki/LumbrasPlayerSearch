# LubrasChessGenie

LubrasChessGenie is an open-source Chrome extension for searching a local Scid
5 chess database by player name or FIDE ID and exporting selected games as
standard PGN.

## Features

- Searches for games by player name or by numeric FIDE ID.
- Offers exact player choices when several names match a search.
- Shows the stored player name for games found by FIDE ID.
- Shows matching games with date, players, ratings, result, event, and ECO.
- Exports every matching game, without paging through the results first.
- Produces standard PGN that works with Chess Genie's Prepare functionality.
- Downloads selected games as a `.pgn` file.
- Copies selected PGN to the clipboard.
- Keeps the database local and opens it read-only.

## Supported database files

A Scid 5 database consists of three companion files with the same base name:

```text
DatabaseName.si5
DatabaseName.sg5
DatabaseName.sn5
```

Keep all three files together. When configuring the extension, enter their
shared base path without an extension. For example, for the files above, enter
`/path/to/DatabaseName`.

Scid 4 (`.si4`) databases are not supported by the current version.

Searching by FIDE ID uses the `WhiteFideId` and `BlackFideId` PGN tags stored
with each game. Games that were imported without those tags can only be found
by player name.

## Requirements (macOS)

- macOS
- Google Chrome
- Scid 5.2 installed as `/Applications/Scid.app`
- Python 3 available at `/usr/bin/python3`
- A readable Scid 5 database containing `.si5`, `.sg5`, and `.sn5` files

The official Scid application includes the Tcl/Tk runtime used by the helper;
no separate Tcl installation is required.

## Requirements (Windows)

- Windows 10 or 11
- Google Chrome
- Scid 5.2 for Windows, installed so its console executable can run a Tcl
  script (the executable that accepts `scid script.tcl args`, typically
  `scid.exe` in the Scid program folder)
- Python 3 on `PATH` (confirm with `py -3 --version` or `python --version`)
- A readable Scid 5 database containing `.si5`, `.sg5`, and `.sn5` files

The Scid application supplies its own Tcl/Tk runtime, so no separate Tcl
installation is required. The same four Tcl scripts run unchanged on Windows and
macOS.

### How read-only access is enforced on Windows

This project does not rely on Scid's own `sc_base isReadOnly` flag alone to keep
the database immutable. On macOS it runs Scid inside `sandbox-exec` with writes
to the database directory denied by the operating system. On Windows it runs
Scid at **Low integrity level** using Windows Mandatory Integrity Control: a
Low-integrity process can read ordinary files but cannot write them, which is
the direct analogue of the macOS deny-write. Scid is given a dedicated,
Low-integrity scratch directory for its temporary files; the database directory
is never made writable. If the low-integrity sandbox cannot be prepared, the
helper fails closed and refuses to query rather than running without enforced
read-only access. No third-party dependency is used — only the Python standard
library and the built-in Windows API.

## Linux

Linux is not supported. The extension loads in Chrome on any platform, but the
native helper only implements the enforced read-only launch on macOS and
Windows, and fails closed elsewhere. Installing Scid and a database on Linux
will not make it run.

## Installation (macOS)

### 1. Install Scid

Download the build for your Mac from the official
[Scid 5.2 download page](https://sourceforge.net/projects/scid/files/Scid/Scid%205.2/).
Use the `macos_arm64` build on Apple Silicon.

Unpack the download, move `Scid.app` into `/Applications`, then Control-click
the app in Finder and select **Open**.

If macOS reports that Scid is damaged, first check **System Settings → Privacy
& Security** for an **Open Anyway** button. If it is not available, and you
downloaded Scid from the official page above, remove the quarantine attribute
from this app only:

```bash
/usr/bin/xattr -dr com.apple.quarantine /Applications/Scid.app
open /Applications/Scid.app
```

Confirm that the required executable exists:

```bash
test -x /Applications/Scid.app/Contents/scid/scid && echo "Scid executable found"
```

### 2. Load the Chrome extension

1. Open `chrome://extensions` in Chrome.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select the `extension` directory from this repository.
5. Copy the 32-character extension ID displayed by Chrome.

### 3. Install the native helper

From the repository root, run:

```bash
scripts/install-macos.sh YOUR_EXTENSION_ID
```

Replace `YOUR_EXTENSION_ID` with the ID copied from `chrome://extensions`.
The script installs the helper for the current user and registers it with
Chrome. It does not install Scid or a chess database.

Quit Chrome completely with **Command-Q**, then reopen it.

### 4. Place the database in an accessible folder

Store the database outside macOS-protected Desktop, Documents, and Downloads
folders. A recommended location is:

```text
/Users/your-name/ChessDatabases/MyDatabase/
```

For example:

```text
/Users/your-name/ChessDatabases/MyDatabase/DatabaseName.si5
/Users/your-name/ChessDatabases/MyDatabase/DatabaseName.sg5
/Users/your-name/ChessDatabases/MyDatabase/DatabaseName.sn5
```

### 5. Configure the extension

1. Open Chrome's extensions menu and select **Lumbras & Chess Genie**.
2. Expand **Local database settings**.
3. Enter the Scid executable path:

   ```text
   /Applications/Scid.app/Contents/scid/scid
   ```

4. Enter the database base path without `.si5`, `.sg5`, or `.sn5`:

   ```text
   /Users/your-name/ChessDatabases/MyDatabase/DatabaseName
   ```

5. Click **Save and verify**. The status badge should display **Ready**.

## Installation (Windows)

### 1. Install Scid 5.2 for Windows

Download the Windows build from the official
[Scid 5.2 download page](https://sourceforge.net/projects/scid/files/Scid/Scid%205.2/)
and install or unpack it. Locate the executable that runs a Tcl script — the
one that accepts `scid script.tcl args`, usually `scid.exe` in the Scid program
folder. You will enter its full path when configuring the extension.

### 2. Install Python 3

Install Python 3 from the
[official downloads](https://www.python.org/downloads/windows/) and make sure it
is on `PATH`. Confirm it:

```bash
py -3 --version
```

### 3. Load the Chrome extension

1. Open `chrome://extensions` in Chrome.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select the `extension` directory from this repository.
5. Copy the 32-character extension ID displayed by Chrome.

### 4. Install the native helper

From the repository root, run in PowerShell:

```bash
powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1 YOUR_EXTENSION_ID
```

Replace `YOUR_EXTENSION_ID` with the ID copied from `chrome://extensions`. The
script copies the helper to `%LOCALAPPDATA%\LumbrasChessGenie\native-host`
(outside the repository, so moving the repository does not break it), renders
the native-messaging manifest, and registers it under
`HKCU\Software\Google\Chrome\NativeMessagingHosts`. It does not install Scid or
a chess database.

Fully quit Chrome — close every window, including any background apps — then
reopen it.

### 5. Configure the extension

1. Open Chrome's extensions menu and select **Lumbras & Chess Genie**.
2. Expand **Local database settings**.
3. Enter the full path to the Scid executable, for example:

   ```text
   C:\Program Files\Scid\scid.exe
   ```

4. Enter the database base path without `.si5`, `.sg5`, or `.sn5`, for example:

   ```text
   C:\Users\you\ChessDatabases\DatabaseName
   ```

5. Click **Save and verify**. The status badge should display **Ready**.

## Usage

1. Open the extension.
2. Enter either of the following in the search field:
   - a player name in Scid's `Surname, Given name` format, such as
     `Carlsen, Magnus`;
   - a numeric FIDE ID, such as `1503014`.
3. Click **Search**.
4. If several stored names match a name search, select the desired player.
   A FIDE ID search skips this step and shows the stored player name with the
   results.
5. Select the games to export. Every match is selected by default, including
   results on pages that are not shown yet; clear individual games or use
   **Select none** to choose your own.
6. Click **Download PGN** to save a `.pgn` file, or **Copy PGN** to place the
   PGN text on the clipboard.

The table shows the first 100 games so results appear quickly. **Download PGN**
and **Copy PGN** load the rest of the result set first and then export all of
it, so a player with 205 games gives a 205-game file without pressing **Load
more**. **Load more** stays available to browse further before exporting; it
lists games by number and never repeats the search, so it is fast for names and
FIDE IDs alike.

A single export is limited to 20 MB and to the newest 20,000 matches, and the
table renders at most 5,000 rows; the status line says so when a result set is
larger. Exporting a large set takes a while: about 28 seconds for a 3,934-game
player on a 10-million-game database.

Input that consists only of digits is treated as a FIDE ID of up to 12 digits;
anything else is treated as a player name. A FIDE ID must match the stored tag
completely, so partial IDs return no games. Games are found whether the player
had White or Black, and each game is listed once.

FIDE ID searches take longer than name searches because Scid scans the
`WhiteFideId` and `BlackFideId` tags of every game instead of using the name
index. On a database of about 10 million games, a FIDE ID search takes roughly
13 seconds. That cost is paid once per search: loading further games and
exporting them look up games by number and do not scan the tags again.
Everything runs against the local database; no FIDE website or other network
service is used.

## Using the games with Chess Genie

The export is ordinary PGN, so it is compatible with Chess Genie's Prepare
functionality: give it the downloaded `.pgn` file, or the PGN text placed on the
clipboard by **Copy PGN**. Preparing against a specific opponent is the usual
reason to search by FIDE ID, because an ID identifies one player even when the
database stores their name inconsistently.

Nothing about this hand-off is Chess Genie specific. The same file opens in any
chess software that reads PGN, and the extension neither uploads games nor talks
to any website.

## Troubleshooting

- **Helper unavailable:** rerun the installer for your platform
  (`scripts/install-macos.sh` or `scripts\install-windows.ps1`) with the
  extension ID currently shown by Chrome, then quit and reopen Chrome.
- **Native host has exited:** reinstall the helper, restart Chrome, and click
  **Save and verify** again.
- **Database incomplete or unreadable:** make sure the `.si5`, `.sg5`, and
  `.sn5` files are together and use their shared path without an extension.
- **Scid executable not found:** on macOS verify that
  `/Applications/Scid.app/Contents/scid/scid` exists and is executable; on
  Windows verify the full path to the Scid executable you entered.
- **Read-only sandbox unavailable (Windows):** the helper failed to launch Scid
  at Low integrity and refused to query. Make sure Scid and the database live on
  a normal local NTFS drive; some removable or network volumes do not support
  the integrity labels the sandbox relies on.
- **Python 3 not found (Windows):** ensure `py -3 --version` or
  `python --version` reports Python 3 from a normal Command Prompt, then reopen
  Chrome so it picks up the current `PATH`.
- **No games for a FIDE ID:** confirm the complete ID and that the games in the
  database carry `WhiteFideId`/`BlackFideId` tags; otherwise search by name.

## Updating or uninstalling

After updating the repository, rerun the installer so the installed native
helper receives the latest files.

On macOS:

```bash
scripts/install-macos.sh YOUR_EXTENSION_ID
```

To remove the native helper and its Chrome registration:

```bash
scripts/uninstall-macos.sh
```

Add `--remove-config` to also remove the saved Scid and database paths.

On Windows, rerun the installer to update:

```bash
powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1 YOUR_EXTENSION_ID
```

To remove the native helper and its Chrome registration:

```bash
powershell -ExecutionPolicy Bypass -File scripts\uninstall-windows.ps1
```

Add `-RemoveConfig` to also remove the saved Scid and database paths.

## Development

Run the complete automated test suite from the repository root:

```bash
npm test
```

The extension uses Chrome Manifest V3. The native helper and Scid adapter use
Python and Tcl without third-party package dependencies.

## License

The original code in this repository is licensed under the MIT License. Scid
is separate GPL-licensed software and is not included in this repository.
