#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
cargo build --release --target aarch64-apple-darwin
bundle="releases/macos/GetItDone.app"
mkdir -p "$bundle/Contents/MacOS" "$bundle/Contents/Resources"
cp target/aarch64-apple-darwin/release/getitdone "$bundle/Contents/MacOS/GetItDone"
cp scripts/Info.plist "$bundle/Contents/Info.plist"
codesign --force --deep --sign - "$bundle"
cp target/aarch64-apple-darwin/release/getitdone releases/macos/GetItDone
