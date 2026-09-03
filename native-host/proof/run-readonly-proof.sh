#!/bin/sh
set -eu

if [ "$#" -ne 3 ]; then
  echo "Usage: $0 SCID_EXECUTABLE DATABASE_BASE PLAYER_QUERY" >&2
  exit 64
fi

scid_executable=$1
database_base=$2
player_query=$3
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
proof_dir=$(mktemp -d "${TMPDIR:-/tmp}/lubras-chess-genie-proof.XXXXXX")
output_pgn="$proof_dir/first-match.proof.pgn"
before_state="$proof_dir/database-before.txt"
after_state="$proof_dir/database-after.txt"
proof_log="$proof_dir/proof.log"

for extension in si5 sg5 sn5; do
  database_file="$database_base.$extension"
  if [ ! -r "$database_file" ]; then
    echo "Missing or unreadable database file: $database_file" >&2
    exit 66
  fi
done

database_state() {
  for extension in si5 sg5 sn5; do
    database_file="$database_base.$extension"
    stat -f '%N|%z|%m' "$database_file"
    shasum -a 256 "$database_file"
  done
}

database_state > "$before_state"
"$scid_executable" "$script_dir/query-player.tcl" \
  "$database_base" "$player_query" "$output_pgn" | tee "$proof_log"
database_state > "$after_state"

if ! cmp -s "$before_state" "$after_state"; then
  echo "FAILED: database files changed during the proof." >&2
  diff -u "$before_state" "$after_state" >&2 || true
  exit 1
fi

echo "database_unchanged=1" | tee -a "$proof_log"
echo "proof_directory=$proof_dir"
