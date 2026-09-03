# Native messaging protocol

All messages use Chrome's native-messaging framing: a four-byte native-endian
unsigned length followed by UTF-8 JSON.

Every request contains:

```json
{
  "protocolVersion": 1,
  "id": "request-uuid",
  "command": "searchPlayer"
}
```

The native host accepts `hello`, `status`, `configure`, `searchPlayer`, and
`getPgn`. It does not accept URLs, web origins, upload commands, or arbitrary
shell commands.

## `configure`

Configuration is stored by the native host, not in browser storage:

```json
{
  "protocolVersion": 1,
  "id": "request-uuid",
  "command": "configure",
  "payload": {
    "scidExecutable": "/Applications/Scid.app/Contents/scid/scid",
    "databaseBase": "/absolute/path/without-extension"
  }
}
```

## `searchPlayer`

Request fields:

```json
{
  "protocolVersion": 1,
  "id": "request-uuid",
  "command": "searchPlayer",
  "payload": {
    "player": "Carlsen, Magnus",
    "limit": 100,
    "cursor": 0
  }
}
```

The response contains bounded game metadata, not PGN bodies:

```json
{
  "protocolVersion": 1,
  "id": "request-uuid",
  "ok": true,
  "total": 3934,
  "selectedPlayer": "Carlsen, Magnus",
  "games": [],
  "nextCursor": null
}
```

If the query is not an exact stored player name, the host returns a bounded
`candidates` list with `requiresPlayerChoice: true`; it does not silently choose
a namesake.

## `getPgn`

The request identifies selected Scid game numbers and returns bounded PGN
chunks. The host must reject any response that would exceed 750 KiB. The
extension combines the chunks and creates a local `.pgn` file through Chrome's
Downloads API or an explicit clipboard action; it does not forward PGN to a
website.

## Errors

Errors return `ok: false` with a stable code and safe message. Unexpected
filesystem paths, stack traces, and raw subprocess output are not exposed in
the extension UI.
