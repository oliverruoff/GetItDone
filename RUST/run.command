#!/bin/sh
set -eu
cd "$(dirname "$0")"
exe="releases/macos/GetItDone.app/Contents/MacOS/GetItDone"
if [ ! -x "$exe" ]; then
  ./scripts/package-macos.sh
elif [ Cargo.toml -nt "$exe" ] || [ Cargo.lock -nt "$exe" ] || [ scripts/Info.plist -nt "$exe" ] || [ -n "$(find src -type f -newer "$exe" -print -quit)" ]; then
  ./scripts/package-macos.sh
fi
open releases/macos/GetItDone.app
