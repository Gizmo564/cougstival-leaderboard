#!/usr/bin/env bash
# Build a .deb from a PyInstaller folder.   usage: packaging/build_deb.sh <pyinstaller-dist-folder> <version> [out-dir]
set -euo pipefail
SRC="$1"; VER="$2"; OUT="${3:-.}"
ROOT="$(mktemp -d)"
PKG="$ROOT/cougstival-leaderboard_${VER}_amd64"
mkdir -p "$PKG/DEBIAN" "$PKG/opt" "$PKG/usr/bin" "$PKG/usr/share/applications"
cp -r "$SRC" "$PKG/opt/cougstival-lb"
ln -s /opt/cougstival-lb/cougstival-lb "$PKG/usr/bin/cougstival-lb"

cat > "$PKG/usr/share/applications/cougstival-leaderboard.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Leaderboard Setup
Comment=Set up and run an event leaderboard
Exec=cougstival-lb setup
Terminal=false
Categories=Utility;
DESK

# Libraries the headless Chromium needs (names differ between Ubuntu 22.04 and 24.04, hence the alternatives).
cat > "$PKG/DEBIAN/control" <<CTL
Package: cougstival-leaderboard
Version: ${VER}
Section: utils
Priority: optional
Architecture: amd64
Depends: git, openssh-client, libnss3, libnspr4, libdbus-1-3, libdrm2, libgbm1, libxcb1, libxkbcommon0, libx11-6, libxcomposite1, libxdamage1, libxext6, libxfixes3, libxrandr2, libcairo2, libpango-1.0-0, libasound2t64 | libasound2, libatk1.0-0t64 | libatk1.0-0, libatk-bridge2.0-0t64 | libatk-bridge2.0-0, libatspi2.0-0t64 | libatspi2.0-0, libcups2t64 | libcups2, libglib2.0-0t64 | libglib2.0-0, fonts-liberation
Maintainer: Leaderboard Kit <noreply@example.com>
Description: Per-day leaderboards for Goosechase events
 A setup app and scheduler that read a Goosechase experience and publish daily
 and total leaderboards to GitHub Pages or the local network.
CTL

mkdir -p "$OUT"
dpkg-deb --root-owner-group --build "$PKG" "$OUT/cougstival-leaderboard_${VER}_amd64.deb"
