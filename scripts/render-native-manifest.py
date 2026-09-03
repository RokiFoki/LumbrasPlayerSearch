#!/usr/bin/python3
"""Render a Chrome native-host manifest with validated absolute values."""

import argparse
import json
import pathlib
import re


EXTENSION_ID = re.compile(r"^[a-p]{32}$")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extension-id", required=True)
    parser.add_argument("--launcher", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if not EXTENSION_ID.fullmatch(args.extension_id):
        parser.error("extension ID must contain exactly 32 letters from a through p")

    launcher = pathlib.Path(args.launcher).expanduser().resolve()
    if not launcher.is_file():
        parser.error("launcher does not exist")

    output = pathlib.Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": "app.chessgenie.local_games",
        "description": "Read-only local Scid database search and PGN export",
        "path": str(launcher),
        "type": "stdio",
        "allowed_origins": ["chrome-extension://{}/".format(args.extension_id)],
    }
    with output.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
