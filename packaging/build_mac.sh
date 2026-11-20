#!/usr/bin/env bash
# Build the macOS app and a .dmg on this Mac (so GitHub's costlier macOS runners aren't needed).
#   usage:  packaging/build_mac.sh
# Produces:  dist/Leaderboard Setup.app   and   dist/LeaderboardKit-<version>-mac.dmg
# The app is signed only ad hoc (not by Apple), so run it from where you built it, or right-click > Open on another Mac.
set -euo pipefail
cd "$(dirname "$0")/.."

# PyInstaller supports released Python versions, so prefer a known one over whatever python3 happens to be newest.
PY=""
for c in python3.12 python3.13 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1; then PY="$(command -v "$c")"; break; fi
done
[ -n "$PY" ] || { echo "No Python 3 found. Install one (for example: brew install python@3.12)."; exit 1; }
echo "==> Using $PY ($("$PY" --version))"

VER="$("$PY" -c 'import re;print(re.search(r"\"(.+?)\"",open("cougstival_lb/__init__.py").read()).group(1))')"
APP="Leaderboard Setup"

echo "==> Setting up a build environment"
[ -d .build-venv ] || "$PY" -m venv .build-venv
.build-venv/bin/pip install -q --upgrade pip
.build-venv/bin/pip install -q -r requirements.txt pytest pyinstaller

echo "==> Running the tests"
.build-venv/bin/python -m pytest -q tests

echo "==> Building the app"
rm -rf "dist/$APP.app" build
.build-venv/bin/pyinstaller --noconfirm --windowed --name "$APP" --osx-bundle-identifier com.cougstival.leaderboard \
  --paths "$PWD" --collect-all playwright --add-data "$PWD/cougstival_lb/web:cougstival_lb/web" \
  --hidden-import tzdata --distpath dist --workpath build --specpath build packaging/app_entry.py >/dev/null
[ -d "dist/$APP.app" ] || { echo "The build did not produce the app."; exit 1; }
codesign --force --deep --sign - "dist/$APP.app" 2>&1 | tail -1 || true

echo "==> Making the disk image"
DMG="dist/LeaderboardKit-$VER-mac.dmg"
STAGE="$(mktemp -d)"
cp -R "dist/$APP.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create -quiet -volname "Leaderboard Kit" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"

echo "==> Checking the built app starts and serves the setup page"
HOME_TMP="$(mktemp -d)"
COUGSTIVAL_HOME="$HOME_TMP" PYTHONUNBUFFERED=1 "dist/$APP.app/Contents/MacOS/$APP" setup --no-browser > "$HOME_TMP/out.txt" 2>&1 &
PID=$!
URL=""
for _ in $(seq 1 40); do
  URL="$(grep -o 'http://127.0.0.1:[0-9]*' "$HOME_TMP/out.txt" 2>/dev/null | head -1 || true)"
  [ -n "$URL" ] && break
  /bin/sleep 0.5
done
if [ -n "$URL" ] && curl -s "$URL/" | grep -q "Leaderboard Setup"; then
  echo "    OK: the app serves the setup page ($URL)"
  STATUS=0
else
  echo "    FAILED: the app did not serve the setup page. Output:"; cat "$HOME_TMP/out.txt"
  STATUS=1
fi
kill "$PID" 2>/dev/null || true
rm -rf "$HOME_TMP"
[ "$STATUS" -eq 0 ] || exit 1

echo
echo "Done."
echo "  App:        $PWD/dist/$APP.app"
echo "  Disk image: $PWD/$DMG"
echo "To try the install: open the .dmg, drag the app to Applications, and open it."
