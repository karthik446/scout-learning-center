#!/bin/sh
# Build the two ES modules from src/sim with the pinned esbuild into assets/sim/ (committed, so the site builds
# without node). OUT=<dir> builds somewhere else (check.sh uses that to compare with the committed files).
# Only the pinned esbuild is fetched (npx -y esbuild@0.28.2); nothing from the vendored engine's own package.json.
set -eu
cd "$(dirname "$0")/../.."
OUT="${OUT:-assets/sim}"
ESBUILD="npx -y esbuild@0.28.2"
BANNER='/* Simulation engine: Breakscale, MIT, Copyright (c) 2026 Breakscale contributors, commit d2c876e0; vendored files listed in /_assets/sim/UPSTREAM.txt, licence in /_assets/sim/LICENSE.txt; interface by the Scout learning center. */'
mkdir -p "$OUT"
for pair in "block:sim" "engine-entry:engine"; do
  src="${pair%%:*}"; name="${pair##*:}"
  $ESBUILD "src/sim/$src.ts" --bundle --format=esm --target=es2022 --minify --legal-comments=none --banner:js="$BANNER" --log-level=warning --outfile="$OUT/$name.js"
done
cp vendor/breakscale/LICENSE "$OUT/LICENSE.txt"
cp vendor/breakscale/UPSTREAM.txt "$OUT/UPSTREAM.txt"
[ "$OUT" = "assets/sim" ] || cp assets/sim/sim.css "$OUT/sim.css"
for f in sim.js engine.js; do printf '%s: %s bytes, %s gzip\n' "$f" "$(wc -c < "$OUT/$f" | tr -d ' ')" "$(gzip -9 -c "$OUT/$f" | wc -c | tr -d ' ')"; done
