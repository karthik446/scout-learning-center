#!/usr/bin/env python3
"""Verify vendor/breakscale/*.ts against the sha256 lines of UPSTREAM.txt.

A file listed under [sha256 of each patched file ...] is compared with that hash, every other
file with its as-copied hash. Exit 1 on any drift: a changed, missing or unlisted file.
"""
import hashlib
import re
import sys
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[2] / "vendor" / "breakscale"
LINE = re.compile(r"^([0-9a-f]{64})  (\S+)$")


def parse(text: str) -> tuple[dict[str, str], dict[str, str]]:
    copied: dict[str, str] = {}
    patched: dict[str, str] = {}
    cur = None
    for raw in text.splitlines():
        if raw.startswith("[sha256 of each file exactly as copied"):
            cur = copied
        elif raw.startswith("[sha256 of each patched file"):
            cur = patched
        else:
            m = LINE.match(raw)
            if m and cur is not None:
                cur[m.group(2)] = m.group(1)
    return copied, patched


def main() -> int:
    copied, patched = parse((VENDOR / "UPSTREAM.txt").read_text())
    errors = []
    if len(copied) != 12:
        errors.append(f"UPSTREAM.txt lists {len(copied)} files, expected 12")
    for name, want_copied in sorted(copied.items()):
        want = patched.get(name, want_copied)
        path = VENDOR / name
        if not path.is_file():
            errors.append(f"missing: {name}")
            continue
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != want:
            errors.append(f"drift: {name} is {got}, UPSTREAM.txt says {want}")
    for name in patched:
        if name not in copied:
            errors.append(f"patched file not in the as-copied list: {name}")
    on_disk = {p.name for p in VENDOR.glob("*.ts")}
    for name in sorted(on_disk - set(copied)):
        errors.append(f"unlisted file: {name}")
    patches = (VENDOR / "PATCHES.md").read_text()
    for name, h in patched.items():
        if h not in patches:
            errors.append(f"PATCHES.md does not record the patched hash of {name}")
    if not (VENDOR / "LICENSE").is_file():
        errors.append("missing: LICENSE")
    for e in errors:
        print("check_vendor:", e, file=sys.stderr)
    if errors:
        return 1
    print(f"check_vendor: {len(copied)} files ok ({len(patched)} patched), LICENSE present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
