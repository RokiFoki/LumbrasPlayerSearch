# Chrome extension

This directory contains the dependency-free Chrome Manifest V3 extension.

The popup communicates with the registered native helper, searches exact
player names, handles ambiguous name matches, displays paginated games, and
exports selected games. PGN can be downloaded as a `.pgn` file or copied to
the clipboard.

Chrome Native Messaging requires an operating-system host manifest whose
`allowed_origins` entry contains the installed extension ID. Use
`scripts/install-macos.sh` from the repository root to install and register the
native helper for the current user.

See the repository's main `README.md` for complete requirements, installation,
configuration, and usage instructions.
