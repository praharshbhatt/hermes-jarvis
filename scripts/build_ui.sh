#!/bin/sh
# Build the web UI (webui/, Next.js) into a static export and copy it to src/hermes_jarvis/static/app/, where the Python
# service serves it. The export is committed, so `pip install .` from a clone needs no Node. Run this after changing webui/.
#
#   scripts/build_ui.sh             install dependencies from the lockfile, build, copy
#   scripts/build_ui.sh --fast      skip `npm ci` (dependencies already installed)
#
# Needs Node 20.9 or newer.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/src/hermes_jarvis/static/app"

command -v node >/dev/null 2>&1 || { echo "error: Node.js 20.9+ is required to build the UI" >&2; exit 1; }
node -e 'const [a,b]=process.versions.node.split(".").map(Number); if (a<20||(a===20&&b<9)) { console.error("error: Node 20.9+ needed, found "+process.version); process.exit(1) }'

cd "$ROOT/webui"
if [ "${1:-}" != "--fast" ]; then
  npm ci --no-audit --no-fund
fi
npm run build

rm -rf "$DEST"
mkdir -p "$DEST"
cp -R out/. "$DEST/"
# drop what the service never serves (Next's own 404 page); keep the small .txt payloads client-side navigation uses
rm -rf "$DEST/404" "$DEST/404.html" "$DEST/_not-found" 2>/dev/null || true
echo "UI copied to ${DEST#"$ROOT"/} ($(du -sk "$DEST" | cut -f1) KB)"
