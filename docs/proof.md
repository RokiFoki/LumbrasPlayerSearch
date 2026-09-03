# Read-only feasibility proof

## Outcome

The approach works against the real Lumbra Scid 5 database without converting
it to PGN and without installing Tcl separately.

Proof environment:

- Scid: `5.2.202603`, official macOS ARM64 build
- Bundled Tcl: `9.0.4`
- Database format: Scid 5 (`.si5`, `.sg5`, `.sn5`)
- Database games: `10,355,488`
- Query: exact stored name `Carlsen, Magnus`
- Matches: `3,934`
- First match exported: game `2,119`, valid PGN, `558` bytes
- Open time: `936 ms`
- Indexed header search: `210 ms`
- PGN export: `1 ms`
- Total measured inside Scid: `1,147 ms`
- Scid read-only flag: `1`

Before and after the proof, all three database files had identical byte sizes,
modification timestamps, and SHA-256 hashes:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `.si5` | 579,907,328 | `b8f41cb590b3afb1d3c5dfddc5e7516d296833dc13812214fde8ee6cdc62c4cd` |
| `.sg5` | 2,134,472,163 | `5472780c16ddc428888036759f018189f47fac9f2f6ce4f22b59df5ab158d41a` |
| `.sn5` | 15,247,957 | `7c76f36e017a90a0ef2f2fd33582b34e13ac769fbf2ca1e46c9c9f878f16e4c4` |

The common modification timestamp remained `2026-07-08 14:45:38 +0200`.

## What this proves

- The local Scid 5 database is directly searchable; a multi-gigabyte PGN export
  is unnecessary.
- Player-name filtering uses Scid's indexed header search and is fast enough for
  an interactive extension workflow.
- Individual matching games can be materialized as standard PGN for ChessGenie.
- The official prebuilt Scid application supplies the required runtime, so this
  proof does not depend on a system Tcl installation.
- The database can remain immutable throughout search and export.

## Scope limits

This proves the database adapter, not the complete Chrome Native Messaging
host, installer, result picker, or ChessGenie page integration. Those are the
next implementation stages.

The proof does not redistribute the database or the exported game.
