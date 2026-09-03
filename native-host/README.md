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

On macOS, every Scid child process runs through `/usr/bin/sandbox-exec` with
writes denied to the database directory. The Tcl adapter additionally refuses
to continue unless Scid reports `sc_base isReadOnly` as true. Other platforms
fail closed until an equivalent enforced read-only mechanism is implemented.

## Development registration

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
