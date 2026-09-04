# Chrome extension

This directory contains the dependency-free Chrome Manifest V3 extension.

The popup communicates with the registered native helper, searches by exact
player name or by numeric FIDE ID, handles ambiguous name matches, displays
paginated games, and exports selected games. PGN can be downloaded as a `.pgn`
file or copied to the clipboard.

The helper reports every matching game number with the first page, so the popup
knows the whole result set from one search. The table renders the first 100 rows
for a fast first paint; **Download PGN** and **Copy PGN** load the remaining
rows and then export everything selected. All matches start selected;
**Select none** and the per-row checkboxes narrow the export.

Further rows are fetched with `getGames`, which returns metadata for known game
numbers in batches of 1,000 and never repeats a search, so filling the table
costs the same for a name and a FIDE ID. PGN is fetched in batches of 200.

The single search field accepts either form. Digits-only input of up to 12
digits is sent as a FIDE ID and matched exactly against the `WhiteFideId` and
`BlackFideId` tags of the local database, with White and Black games combined
and listed once each. Any other input is sent as a player name. **Load more**
repeats the original search, so a FIDE ID search keeps paging by ID. FIDE ID
searches take longer than name searches because every game's tags are scanned
rather than the name index.

Chrome Native Messaging requires an operating-system host manifest whose
`allowed_origins` entry contains the installed extension ID. From the repository
root, use `scripts/install-macos.sh` on macOS, or
`scripts\install-windows.ps1` on Windows, to install and register the native
helper for the current user.

See the repository's main `README.md` for complete requirements, installation,
configuration, and usage instructions.
