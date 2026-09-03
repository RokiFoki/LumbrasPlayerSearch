# LubrasChessGenie

LubrasChessGenie is an open-source Chrome extension for searching a local Scid
5 chess database and exporting selected games as standard PGN.

## Features

- Searches for games by player name.
- Offers exact player choices when several names match a search.
- Shows matching games with date, players, ratings, result, event, and ECO.
- Loads large result sets in pages.
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

## Requirements

- macOS
- Google Chrome
- Scid 5.2 installed as `/Applications/Scid.app`
- Python 3 available at `/usr/bin/python3`
- A readable Scid 5 database containing `.si5`, `.sg5`, and `.sn5` files

The official Scid application includes the Tcl/Tk runtime used by the helper;
no separate Tcl installation is required.

## Installation

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

1. Open Chrome's extensions menu and select **LubrasChessGenie**.
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
2. Enter a player name in Scid's `Surname, Given name` format, such as
   `Carlsen, Magnus`.
3. Click **Search**.
4. If several stored names match, select the desired player.
5. Select the games to export.
6. Click **Download PGN** to save a `.pgn` file, or **Copy PGN** to place the
   PGN text on the clipboard.

The resulting PGN is a standard text format that can be opened or imported by
chess software that supports PGN.

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
