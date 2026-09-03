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

The native host accepts `hello`, `status`, `configure`, `searchPlayer`,
`searchFideId`, `getGames`, and `getPgn`. It does not accept URLs, web origins,
upload commands, or arbitrary shell commands.

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
  "gameNumbers": [],
  "nextCursor": null
}
```

`games` holds one page of metadata. `gameNumbers` is sent only with the first
page (`cursor` 0) and lists every matching game number in the same newest-first
order, bounded to 20,000, so the caller can export beyond the page it renders.
Later pages return it empty.

If the query is not an exact stored player name, the host returns a bounded
`candidates` list with `requiresPlayerChoice: true`; it does not silently choose
a namesake.

## `searchFideId`

Request fields:

```json
{
  "protocolVersion": 1,
  "id": "request-uuid",
  "command": "searchFideId",
  "payload": {
    "fideId": "1503014",
    "limit": 100,
    "cursor": 0
  }
}
```

`fideId` must be a string of 1–12 ASCII digits; leading zeros are dropped and
an all-zero value is rejected with `INVALID_FIDE_ID`. `limit` and `cursor` use
the same bounds as `searchPlayer`. The host searches the `WhiteFideId` and
`BlackFideId` extra tags of the local database for the complete identifier,
merges both sides without duplicates, and orders games newest first.

The response has the same shape as `searchPlayer`, including the first-page
`gameNumbers` result set, with `selectedPlayer` set to
the name most often stored beside the identifier and `fideId` echoing the
normalized value. `candidates` is always empty and `requiresPlayerChoice`
always `false`; `playerNotFound` is `true` when no game carries the ID:

```json
{
  "protocolVersion": 1,
  "id": "request-uuid",
  "ok": true,
  "total": 3934,
  "selectedPlayer": "Carlsen, Magnus",
  "fideId": "1503014",
  "games": [],
  "candidates": [],
  "requiresPlayerChoice": false,
  "playerNotFound": false,
  "nextCursor": 100
}
```

Each page repeats the tag scan, so `cursor` must be paired with the same
`fideId`. The scan takes longer than an indexed name search; the host allows it
120 seconds instead of 30.

## `getGames`

Returns bounded metadata for game numbers the caller already has, so a client
can fill in the rest of a result set without repeating a search:

```json
{
  "protocolVersion": 1,
  "id": "request-uuid",
  "command": "getGames",
  "payload": { "gameNumbers": [10344015, 10314728] }
}
```

`gameNumbers` must be a non-empty list of at most 1,000 distinct positive
integers. The response carries a `games` array in the requested order, with the
same fields as a search page. The host rejects a reply that does not cover every
requested game.

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
