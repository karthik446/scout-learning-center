#!/usr/bin/env python3
"""Copy the build guide of the AI engineering track into content/ai-engineering, byte for byte.

    python3 tools/import_build_track.py --from <build-guide dir>     copy the 12 files in
    python3 tools/import_build_track.py --check <build-guide dir>    exit 1 when any copy differs from its source

The 12 files are README.md, SETUP.md, SCHEDULE.md and week-1.md to week-9.md; nothing else in the source directory is
read, and the copies are never edited here (build.py renders them, scan.py checks them).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "content" / "ai-engineering"
FILES = ["README.md", "SETUP.md", "SCHEDULE.md"] + [f"week-{n}.md" for n in range(1, 10)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--from", dest="src", metavar="DIR", help="copy the files from DIR")
    g.add_argument("--check", metavar="DIR", help="compare the copies with the files in DIR")
    args = ap.parse_args()
    src = Path(args.src or args.check)
    if not src.is_dir():
        print(f"not a directory: {src}", file=sys.stderr)
        return 2
    problems: list[str] = []
    if args.src:
        DEST.mkdir(parents=True, exist_ok=True)
        for name in FILES:
            s = src / name
            if not s.is_file():
                problems.append(f"missing in source: {name}")
                continue
            (DEST / name).write_bytes(s.read_bytes())
            print(f"copied {name}")
    else:
        for name in FILES:
            s, d = src / name, DEST / name
            if not s.is_file():
                problems.append(f"missing in source: {name}")
            elif not d.is_file():
                problems.append(f"missing copy: {d.relative_to(ROOT)}")
            elif s.read_bytes() != d.read_bytes():
                problems.append(f"differs from source: {name}")
        extra = sorted(p.name for p in DEST.glob("*") if p.name not in FILES) if DEST.is_dir() else []
        problems += [f"unexpected file in {DEST.relative_to(ROOT)}: {n}" for n in extra]
    for p in problems:
        print(p, file=sys.stderr)
    if not problems:
        print(f"{len(FILES)} files {'copied' if args.src else 'match'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
