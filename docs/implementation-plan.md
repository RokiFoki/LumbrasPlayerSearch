# Implementation plan

## Fixed locations

- Local database during development:
  `$HOME/ChessDatabases/LumbrasGigabase_OTB_si5/LumbrasGigaBase_OTB.{si5,sg5,sn5}`
- Standalone open-source repository: `$HOME/Desktop/LubrasChessGenie`
- Installed native helper (macOS):
  `$HOME/Library/Application Support/LubrasChessGenie/native-host`
- Installed native helper (Windows):
  `%LOCALAPPDATA%\LumbrasChessGenie\native-host`
- ChessGenie source remains separate and does not receive local database code,
  extension detection, or an extension messaging bridge.

## Phase 1 — Proven database adapter

- [x] Confirm the three-file Scid 5 database set.
- [x] Run official Scid 5.2 from a temporary directory without installing it.
- [x] Confirm bundled Tcl 9.0.4 removes the need for Tcl 8.6.
- [x] Open the database read-only and inspect its game count.
- [x] Search an exact player name through Scid's header index.
- [x] Export one selected match as PGN.
- [x] Verify database hashes, sizes, and timestamps are unchanged.
- [x] Preserve a repeatable proof script in this repository.

## Phase 2 — Native Messaging host

- [x] Choose Python 3.9+ standard library for the macOS development host.
- [x] Implement four-byte framed JSON input/output.
- [x] Validate protocol version, command, path, player, cursor, and limits.
- [x] Add `searchPlayer` with candidate selection and newest-first pagination.
- [x] Add bounded `getPgn` export for selected games.
- [x] Enforce macOS write denial and require Scid's read-only flag.
- [x] Enforce timeouts and a 750 KiB response cap.
- [x] Add structured errors and mock/contract tests.
- [ ] Add integration tests using a tiny redistributable Scid
  fixture database.

## Phase 3 — Host registration and packaging

- [x] Create the macOS native-host manifest renderer.
- [x] Register only the supplied extension ID in `allowed_origins`.
- [x] Build per-user macOS install/uninstall scripts with explicit execution.
- [x] Install the runnable helper outside macOS-protected Desktop and Documents
  folders.
- [x] Create Windows native-host registration and enforced read-only access.
  `scripts/install-windows.ps1` copies the helper to
  `%LOCALAPPDATA%\LumbrasChessGenie\native-host`, renders the manifest with the
  shared `render-native-manifest.py`, and registers it under
  `HKCU\Software\Google\Chrome\NativeMessagingHosts`. Read-only access is
  enforced by launching Scid at Low integrity level (Windows Mandatory
  Integrity Control), the analogue of the macOS sandbox deny-write;
  `host.py._run()` fails closed if the low-integrity sandbox is unavailable.
- [ ] Decide whether to discover a user-installed Scid or bundle a component.
- [ ] If bundling Scid, satisfy GPL notice/source obligations.
- [ ] Sign/notarize macOS artifacts and sign Windows artifacts.

## Phase 4 — Extension game picker

- [x] Create a valid Manifest V3 popup and native-message request scaffold.
- [x] Add database and Scid executable onboarding.
- [x] Render newest-first paginated game metadata and selection controls.
- [x] Fetch PGN only after the user selects games.
- [x] Add clear native-host missing/configuration states.
- [x] Combine selected PGNs into a sensibly named `.pgn` download.
- [x] Add an explicit Copy PGN action for generic paste-based importers.
- [x] Add no content script or website host permissions.
- [ ] Add optional date, color, result, event, and ECO search filters.

## Phase 5 — Source-agnostic PGN handoff

- [x] Preview the exact games and require an explicit Export PGN action.
- [ ] Verify the resulting file can be selected or dropped into ChessGenie's
  generic PGN importer without any ChessGenie extension-specific code.
- [ ] Verify copied PGN works with a generic Paste PGN input if ChessGenie adds
  one independently of this extension.
- [ ] Verify the same file opens in another standard PGN-capable tool.
- [ ] Add an end-to-end test from local search to downloaded PGN.

## Phase 6 — Open-source release

- [ ] Add CI for lint, unit tests, extension-manifest validation, and packaging.
- [ ] Add contributor, security, and privacy documentation.
- [ ] Publish reproducible release artifacts and checksums.
- [ ] Complete database-license and Scid-GPL review before public distribution.
