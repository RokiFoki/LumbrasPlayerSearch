#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 CHROME_EXTENSION_ID" >&2
  exit 64
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
source_host="$repository_dir/native-host"
install_root="$HOME/Library/Application Support/LubrasChessGenie"
installed_host="$install_root/native-host"
launcher="$installed_host/launch.sh"
manifest_dir="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts"
manifest="$manifest_dir/app.chessgenie.local_games.json"

/bin/mkdir -p "$installed_host/scid"
/usr/bin/install -m 700 "$source_host/launch.sh" "$installed_host/launch.sh"
/usr/bin/install -m 700 "$source_host/host.py" "$installed_host/host.py"

for source_script in "$source_host"/scid/*.tcl; do
  /usr/bin/install -m 600 "$source_script" "$installed_host/scid/$(basename "$source_script")"
done

/usr/bin/python3 "$script_dir/render-native-manifest.py" \
  --extension-id "$1" \
  --launcher "$launcher" \
  --output "$manifest"

echo "Installed native helper: $installed_host"
echo "Installed native-host manifest: $manifest"
echo "Restart Chrome before testing the extension."
