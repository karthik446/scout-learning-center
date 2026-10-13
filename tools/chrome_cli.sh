#!/bin/sh
# The brief's plain command-line runs, for the record (tools/chrome_check.py is the full check):
#   1280 px: --screenshot with --enable-logging=stderr, headers exactly as _headers (serve_check on 18765)
#   390 px : the same page inside an iframe of the wrapper page (serve_check --frames on 18770, wrapper on 18771)
#   search : --dump-dom of /learn/search/?q=kubernetes
# Usage: tools/chrome_cli.sh [outdir]   (needs site/ built and pagefind run)
cd "$(dirname "$0")/.." || exit 1
OUT="${1:-verify/cli}"; mkdir -p "$OUT"
CH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
python3 tools/serve_check.py --port 18765 >"$OUT/serve-1280.log" 2>&1 & S1=$!
python3 tools/serve_check.py --port 18770 --frames >"$OUT/serve-390.log" 2>&1 & S2=$!
sleep 1
run() { # name url width height extra...
  rn=$1; u=$2; w=$3; h=$4; shift 4
  P=$(mktemp -d)
  "$CH" --headless=new --disable-gpu --no-first-run --user-data-dir="$P" --enable-logging=stderr --v=0 \
    --window-size="$w,$h" --virtual-time-budget=8000 --screenshot="$OUT/$rn.png" "$@" "$u" 2>"$OUT/$rn.stderr.log" >/dev/null
  rm -rf "$P"
}
for pair in landing:/ learn-home:/learn/ family:/learn/families/software-engineering/ pathway:/learn/pathways/mlops-ml-platform-engineer/ \
            lesson:/learn/lessons/mlflow-experiment-tracking/ practice:/learn/practice/mlflow-experiment-tracking/ search:/learn/search/?q=kubernetes notfound:/nope/; do
  n=${pair%%:*}; p=${pair#*:}
  run "$n-1280" "http://127.0.0.1:18765$p" 1280 1400
  run "$n-390" "http://127.0.0.1:18771/wrap?w=390&h=1400&src=$p" 500 1400
done
P=$(mktemp -d)
"$CH" --headless=new --disable-gpu --no-first-run --user-data-dir="$P" --enable-logging=stderr --v=0 --virtual-time-budget=15000 --dump-dom \
  "http://127.0.0.1:18765/learn/search/?q=kubernetes" >"$OUT/search-dump-dom.html" 2>"$OUT/search-dump-dom.stderr.log"
rm -rf "$P"
kill $S1 $S2 2>/dev/null
echo "CSP 'Refused' lines: $(cat "$OUT"/*.stderr.log | grep -c 'Refused to')"
echo "console lines: $(cat "$OUT"/*.stderr.log | grep -c 'CONSOLE')"
