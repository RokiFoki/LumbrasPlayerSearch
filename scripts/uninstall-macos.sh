#!/bin/sh
set -eu

manifest="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts/app.chessgenie.local_games.json"
install_root="$HOME/Library/Application Support/LubrasChessGenie"
installed_host="$install_root/native-host"
config="$install_root/config.json"

if [ -f "$manifest" ]; then
  rm -f "$manifest"
  echo "Removed native-host manifest."
fi

if [ -d "$installed_host" ]; then
  rm -rf "$installed_host"
  echo "Removed installed native helper."
fi

if [ "${1:-}" = "--remove-config" ] && [ -f "$config" ]; then
  rm -f "$config"
  echo "Removed native-host configuration."
fi
