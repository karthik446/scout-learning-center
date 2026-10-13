#!/bin/sh
# Everything the simulator needs to be trusted, in one command; exit 1 on the first problem.
#  1. vendored engine files match UPSTREAM.txt (the patched file its patched hash)
#  2. the committed assets/sim/{sim,engine}.js equal a fresh build with the pinned esbuild
#  3. node --test: closed forms (M/M/1, M/M/4, Kingman, Little) and conservation / bounds
#  4. golden runs of every scenario equal the committed tools/sim/golden/*.json and every assertion passes
# Needs node and, for step 2, `npx -y esbuild@0.28.2` (the only package it fetches).
set -eu
cd "$(dirname "$0")/../.."
echo "== vendor hashes"; python3 -I tools/sim/check_vendor.py
echo "== committed build equals a fresh build"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
OUT="$tmp" sh tools/sim/build.sh >/dev/null
for f in sim.js engine.js LICENSE.txt UPSTREAM.txt; do
  cmp -s "$tmp/$f" "assets/sim/$f" || { echo "assets/sim/$f differs from a fresh build: run tools/sim/build.sh and commit it" >&2; exit 1; }
done
echo "ok"
echo "== node tests"; node --test tools/sim/*.test.mjs
echo "== golden runs"; node tools/sim/golden.mjs --check
echo "sim checks green"
