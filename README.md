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

## Requirements

- macOS
- Google Chrome
- Scid 5.2 installed as `/Applications/Scid.app`
- Python 3 available at `/usr/bin/python3`
- A readable Scid 5 database containing `.si5`, `.sg5`, and `.sn5` files

The official Scid application includes the Tcl/Tk runtime used by the helper;
no separate Tcl installation is required.

## Windows and Linux

The extension does not work on Windows or Linux yet, and there is no installer
for either. Do not install Scid and a database expecting it to run.

The extension itself loads in Chrome on any platform, but it is only a front end
for the native helper, and the helper refuses to run anywhere except macOS. It
opens the database through `/usr/bin/sandbox-exec` with writes to the database
directory denied, and fails closed rather than querying without that protection.
On another platform every search returns:

```text
This build currently supports enforced read-only access on macOS only.
```

Windows support needs three things that do not exist yet:

- registration under `HKCU\Software\Google\Chrome\NativeMessagingHosts`,
  instead of the per-user manifest directory used by macOS;
- a launcher for the helper, since `native-host/launch.sh` is a shell script,
  and a Python 3 interpreter on `PATH`, since macOS relies on
  `/usr/bin/python3`;
- an enforced read-only mechanism equivalent to the macOS sandbox.

The third is the real blocker. Scid's own `sc_base isReadOnly` check already
runs on every platform, but this project deliberately does not rely on the
database application alone to keep the database immutable.

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

- **Helper unavailable:** rerun `scripts/install-macos.sh` with the extension ID
  currently shown by Chrome, then quit and reopen Chrome.
- **Native host has exited:** reinstall the helper, restart Chrome, and click
  **Save and verify** again.
- **Database incomplete or unreadable:** make sure the `.si5`, `.sg5`, and
  `.sn5` files are together and use their shared path without an extension.
- **Scid executable not found:** verify that
  `/Applications/Scid.app/Contents/scid/scid` exists and is executable.
- **Database on Desktop:** move the complete database directory to a location
  such as `~/ChessDatabases` and update the configured base path.
- **No games for a FIDE ID:** confirm the complete ID and that the games in the
  database carry `WhiteFideId`/`BlackFideId` tags; otherwise search by name.

## Updating or uninstalling

After updating the repository, rerun the installer so the installed native
helper receives the latest files:

```bash
scripts/install-macos.sh YOUR_EXTENSION_ID
```

To remove the native helper and its Chrome registration:

```bash
scripts/uninstall-macos.sh
```

Add `--remove-config` to also remove the saved Scid and database paths.

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
