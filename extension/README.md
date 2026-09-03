# Chrome extension

This directory contains the dependency-free Chrome Manifest V3 extension.

The popup communicates with the registered native helper, searches by exact
player name or by numeric FIDE ID, handles ambiguous name matches, displays
paginated games, and exports selected games. PGN can be downloaded as a `.pgn`
file or copied to the clipboard.

The single search field accepts either form. Digits-only input of up to 12
digits is sent as a FIDE ID and matched exactly against the `WhiteFideId` and
`BlackFideId` tags of the local database, with White and Black games combined
and listed once each. Any other input is sent as a player name. **Load more**
repeats the original search, so a FIDE ID search keeps paging by ID. FIDE ID
searches take longer than name searches because every game's tags are scanned
rather than the name index.

Chrome Native Messaging requires an operating-system host manifest whose
`allowed_origins` entry contains the installed extension ID. Use
`scripts/install-macos.sh` from the repository root to install and register the
native helper for the current user.

See the repository's main `README.md` for complete requirements, installation,
configuration, and usage instructions.
