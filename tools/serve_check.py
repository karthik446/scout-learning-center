#!/usr/bin/env python3
"""Serve site/ on 127.0.0.1 with the exact response headers of site/_headers (standard library only).

    python3 tools/serve_check.py [--site site] [--port 18765] [--frames]

What it mimics of Cloudflare Pages: every rule of _headers whose path pattern matches the request path applies, in file
order; a header named twice is joined with ', ' (the documented behaviour); a rule with a host in its pattern
(https://:project.pages.dev/*) never matches 127.0.0.1; a directory answers with its index.html; an unknown path answers 404
with /404.html. .wasm is served as application/wasm.

--frames is for the 390 px screenshots only (macOS Chrome will not open a window narrower than 500 px, so the page is shown in
an iframe of a wrapper page served on port+1): it rewrites `frame-ancestors 'none'` to the wrapper's origin and drops
X-Frame-Options, nothing else. Every other run, and the Pagefind proof, uses the headers untouched.
"""

from __future__ import annotations

import argparse
import fnmatch
import mimetypes
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

TYPES = {".wasm": "application/wasm", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".html": "text/html; charset=utf-8", ".json": "application/json", ".svg": "image/svg+xml", ".xml": "application/xml",
         ".txt": "text/plain; charset=utf-8", ".pf_fragment": "application/octet-stream", ".pf_index": "application/octet-stream",
         ".pf_meta": "application/octet-stream", ".pf_facet": "application/octet-stream"}


def parse_headers(text: str) -> list[tuple[str, list[tuple[str, str]]]]:
    rules: list[tuple[str, list[tuple[str, str]]]] = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            rules.append((line.strip(), []))
        else:
            name, _, value = line.strip().partition(":")
            rules[-1][1].append((name.strip(), value.strip()))
    return rules


def matches(pattern: str, path: str) -> bool:
    if "://" in pattern or pattern.startswith(":"):
        return False  # host-specific rule: not for 127.0.0.1
    return fnmatch.fnmatchcase(path, pattern.replace("*", "*"))  # '*' is a splat (matches '/' too)


def headers_for(rules, path: str, frames: str | None) -> list[tuple[str, str]]:
    merged: dict[str, tuple[str, list[str]]] = {}
    for pattern, hs in rules:
        if matches(pattern, path):
            for name, value in hs:
                key = name.lower()
                merged.setdefault(key, (name, []))[1].append(value)
    out = []
    for key, (name, values) in merged.items():
        value = ", ".join(values)
        if frames:
            if key == "x-frame-options":
                continue
            if key == "content-security-policy":
                value = value.replace("frame-ancestors 'none'", f"frame-ancestors {frames}")
        out.append((name, value))
    return out


def make_handler(site: Path, rules, frames: str | None):
    class H(BaseHTTPRequestHandler):
        server_version = "scout-serve-check"

        def log_message(self, fmt, *args):  # one line per request on stderr: the request log
            sys.stderr.write(f"[serve] {self.address_string()} {fmt % args}\n")

        def do_GET(self):  # noqa: N802
            path = unquote(urlparse(self.path).path)
            target = (site / path.lstrip("/")).resolve()
            status = 200
            if site.resolve() not in target.parents and target != site.resolve():
                target, status = site / "404.html", 404
            elif target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                target, status = site / "404.html", 404
            body = target.read_bytes() if target.is_file() else b"not found"
            ctype = TYPES.get(target.suffix) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for name, value in headers_for(rules, path, frames):
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        do_HEAD = do_GET  # noqa: N815

    return H


def make_wrapper(main_port: int):
    class W(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def do_GET(self):  # noqa: N802
            q = parse_qs(urlparse(self.path).query)
            src = q.get("src", ["/"])[0]
            w = int(q.get("w", ["390"])[0])
            h = int(q.get("h", ["1600"])[0])
            if not re.match(r"^/[A-Za-z0-9_./?=&%-]*$", src):
                self.send_error(400)
                return
            page = (f'<!doctype html><meta charset="utf-8"><title>wrapper</title><body style="margin:0;background:#888">'
                    f'<iframe src="http://127.0.0.1:{main_port}{src}" width="{w}" height="{h}" style="border:0;background:#fff;display:block"></iframe>').encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

    return W


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", type=Path, default=Path(__file__).resolve().parent.parent / "site")
    ap.add_argument("--port", type=int, default=18765)
    ap.add_argument("--frames", action="store_true", help="390 px screenshots only: allow the wrapper page on port+1 to frame the site")
    args = ap.parse_args()
    site = args.site.resolve()
    rules = parse_headers((site / "_headers").read_text(encoding="utf-8"))
    frames = f"http://127.0.0.1:{args.port + 1}" if args.frames else None
    main_srv = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(site, rules, frames))
    if args.frames:
        wrap = ThreadingHTTPServer(("127.0.0.1", args.port + 1), make_wrapper(args.port))
        threading.Thread(target=wrap.serve_forever, daemon=True).start()
    print(f"serving {site} on http://127.0.0.1:{args.port}/ ({'frames allowed for ' + frames if frames else 'headers exactly as _headers'})", flush=True)
    try:
        main_srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
