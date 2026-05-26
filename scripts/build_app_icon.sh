#!/usr/bin/env bash
# Build a macOS .icns app icon from frontend/static/logo.svg using the macOS
# built-ins `sips` and `iconutil` (no external deps).
#
# Output: build/Logger.icns
# Invoked automatically by scripts/build_macapp.py before PyInstaller runs.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Use the compact "lg" monogram, not the full "log(ger)" wordmark — the wordmark
# is unreadable at 16-32 px Dock/Finder sizes. The monogram is designed for icon use.
SRC_SVG="$REPO_ROOT/frontend/static/logo-icon.svg"
OUT_DIR="$REPO_ROOT/build"
ICONSET="$OUT_DIR/Logger.iconset"
ICNS="$OUT_DIR/Logger.icns"

if [[ ! -f "$SRC_SVG" ]]; then
  echo "[build_app_icon] missing source SVG: $SRC_SVG" >&2
  exit 1
fi

mkdir -p "$ICONSET"

# macOS .icns spec requires icons at these exact filenames + pixel sizes
# (see `man iconutil`):
#   icon_16x16.png        16
#   icon_16x16@2x.png     32
#   icon_32x32.png        32
#   icon_32x32@2x.png     64
#   icon_128x128.png      128
#   icon_128x128@2x.png   256
#   icon_256x256.png      256
#   icon_256x256@2x.png   512
#   icon_512x512.png      512
#   icon_512x512@2x.png   1024

render() {
  local size="$1"
  local name="$2"
  sips -s format png -z "$size" "$size" "$SRC_SVG" --out "$ICONSET/$name" >/dev/null
}

render 16   icon_16x16.png
render 32   icon_16x16@2x.png
render 32   icon_32x32.png
render 64   icon_32x32@2x.png
render 128  icon_128x128.png
render 256  icon_128x128@2x.png
render 256  icon_256x256.png
render 512  icon_256x256@2x.png
render 512  icon_512x512.png
render 1024 icon_512x512@2x.png

iconutil -c icns "$ICONSET" -o "$ICNS"
rm -rf "$ICONSET"

echo "[build_app_icon] wrote $ICNS"
