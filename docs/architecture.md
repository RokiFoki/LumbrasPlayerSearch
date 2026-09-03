# Architecture

```text
Chrome extension popup
        |
        | chrome.runtime.sendNativeMessage
        v
Native Messaging host
  - validates request and configured database path
  - launches/embeds the Scid adapter read-only
  - returns bounded metadata pages or selected PGNs
        |
        v
Local .si5 + .sg5 + .sn5 database

Selected PGNs -> Download PGN -> ordinary .pgn file --+
             \-> Copy PGN ----> clipboard text -------+--> generic PGN input
                                                           in ChessGenie or
                                                           another chess tool
```

## Trust boundaries

- No web page receives arbitrary filesystem access or a native-host connection.
- The extension may communicate only with its registered native host.
- The host accepts only versioned allow-listed commands.
- Database paths must resolve to a complete Scid 5 file set.
- Every opened database must report read-only before a query proceeds.
- Search returns metadata first; PGN is fetched only for a selected game.
- Responses remain below Chrome's native-message output ceiling. The working
  limit is 750 KiB per response.
- The extension has no ChessGenie host permission, content script, API token,
  or page-messaging protocol.
- No database file or exported game is uploaded by the extension. It creates a
  local PGN file or clipboard text; a later import is an ordinary user action
  in the destination application.

## Packaging decision still required

The proof uses an official Scid executable supplied by the user. A public
release must choose between locating an existing Scid installation and bundling
an appropriate Scid component. Bundling requires explicit GPL compliance and
platform-specific signing/notarization work.
