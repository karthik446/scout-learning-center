#!/usr/bin/env python3
"""The AI engineering track's guards (standard library only; exit 1 on any failure).

    python3 tools/test_build_track.py

Positive: the Markdown subset renders the constructs the guide uses, escapes HTML, writes external links with
target/rel, and resolves relative links the way build.py does. Negative: a workstation path, an unknown relative link
and raw HTML each fail the content scan or the renderer; so do the other constructs mdlite refuses.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mdlite  # noqa: E402
import scan  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FAILURES: list[str] = []


def check(cond: bool, what: str) -> None:
    if not cond:
        FAILURES.append(what)


def render(text: str) -> mdlite.Rendered:
    return mdlite.render(text, link=lambda d: "/x/" + d, code_langs={"python": "python", "bash": "bash"})


def refused(text: str, what: str) -> None:
    try:
        render(text)
    except mdlite.MdliteError:
        return
    FAILURES.append(f"rendered instead of refusing: {what}")


def test_renderer() -> None:
    r = render("# Title *here*\n\n> *Disclaimer.*\n\n## Steps\n\nA **bold** `code <b>` line\nand a [link](week-2.md#steps) "
               "plus [ext](https://example.org/a_(b)).\n\n- one\n  - nested\n- two\n\n1. first\n2. second\n\n"
               "| H1 | H2 |\n|---|---|\n| `a\\|b` | c |\n\n```python\nprint('<')\n```\n\n```toml\nx = 1\n```\n\n"
               "```mermaid\ngraph TD; A-->B\n```\n\n---\n\nAn interval [-0.1, +0.2] and 5 * 3 and \\*literal\\*. \u2248")
    h = r.html
    check(r.title == "Title here", "title text")
    check(r.headings[0] == (1, "title-here", "Title here") and r.headings[1][1] == "steps", f"heading ids {r.headings}")
    check(r.blocks[1].kind == "quote" and "<em>Disclaimer.</em>" in r.blocks[1].html, "blockquote with emphasis")
    check("<strong>bold</strong>" in h and "<code>code &lt;b&gt;</code>" in h, "strong and escaped code span")
    check('<a href="/x/week-2.md#steps">link</a>' in h, "relative link through the resolver")
    check('<a href="https://example.org/a_(b)" target="_blank" rel="noopener noreferrer">ext</a>' in h, "external link attributes")
    check("<ul><li>one<ul><li>nested</li></ul></li><li>two</li></ul>" in h, "nested list")
    check("<ol><li>first</li><li>second</li></ol>" in h, "ordered list")
    check('<th scope="col">H1</th>' in h and '<td data-col="h1"><code>a|b</code></td>' in h and 'class="table-scroll"' in h, "table with an escaped pipe")
    check('<code class="language-python" data-lang="python">print(&#x27;&lt;&#x27;)' in h, "python fence")
    check('<span class="code-lang">toml</span><pre><code class="language-plaintext"' in h, "unknown fence language is plain code")
    check('<pre class="mermaid">graph TD; A--&gt;B</pre>' in h and r.mermaid, "mermaid fence")
    check("<hr>" in h, "rule")
    check("[-0.1, +0.2]" in h and "5 * 3" in h and "*literal*" in h, "literal brackets and asterisks")
    check("&#x2248;" in h and "\u2248" not in h, "glyphs above U+00FF as numeric references")
    check(r.links == ["week-2.md#steps", "https://example.org/a_(b)"], f"links {r.links}")


def test_refusals() -> None:
    refused("# T\n\nsee <b>bold</b>", "raw HTML")
    refused("# T\n\n<div>", "raw HTML block")
    refused("# T\n\nA &amp; B", "entity")
    refused("# T\n\n![alt](x.png)", "image")
    refused("# T\n\n_em_ text", "underscore emphasis")
    refused("# T\n\n    code", "indented code")
    refused("# T\n\nTitle\n---", "setext heading")
    refused("# T\n\nline  \nnext", "hard break")
    refused("# T\n\n| a |\n|:--|\n| b |", "alignment colon")
    refused("# T\n\n| a | b |\n|---|---|\n| only one |", "table column mismatch")
    refused("# T\n\n- item\ncontinued", "list continuation line")
    refused("# T\n\n> a\nb", "lazy blockquote continuation")
    refused("# T\n\n> > nested", "nested blockquote")
    refused("# T\n\n```python\nopen", "unclosed fence")
    refused("# T\n\n`open", "unmatched backtick")
    refused("# T\n\n**open", "unmatched strong")
    refused("# T\n\nsee https://example.org now", "bare URL")
    refused("# T\n\n[x](http://example.org)", "http link")
    refused("# T\n\n[x](mailto:a@b.c)", "mailto link")
    refused("# T\n\n[x](a.md \"title\")", "link title")
    refused("# T\n\n[x][ref]\n\n[ref]: https://example.org", "reference link")
    refused("# T\n\n# Second", "second h1")
    refused("# T\n\n\tx", "tab")
    try:
        mdlite.render("# T\n\n[x](other.md)", link=scan_link)
        FAILURES.append("rendered instead of refusing: unknown relative link")
    except mdlite.MdliteError:
        pass


def scan_link(dest: str) -> str:
    target = dest.partition("#")[0]
    if target and target not in scan.BUILD_TRACK_FILES:
        raise mdlite.MdliteError(f"unknown link {dest}")
    return dest


def test_scan(tmp: Path) -> None:
    """A copy of the real content folder: the scan passes on it, then each planted defect is reported."""
    src = ROOT / "content" / scan.BUILD_TRACK_DIR
    folder = tmp / scan.BUILD_TRACK_DIR
    shutil.copytree(src, folder)
    for name in scan.BUILD_TRACK_FILES:   # a clean baseline even while some chapters are still being written
        if not (folder / name).is_file():
            (folder / name).write_text(f"# {name[:-3]}\n\nPlaceholder for this test only.\n", encoding="utf-8")
    base = scan.build_track_checks(tmp)
    check(not base, f"baseline scan of the test copy: {base[:3]}")
    readme = (folder / "README.md").read_text(encoding="utf-8")
    plants = {
        "workstation path": "\n\nSee /Users/someone/code for the clone.\n",
        "unknown relative link": "\n\nRead [the notes](notes/extra.md) too.\n",
        "raw HTML": "\n\nA <b>bold</b> claim.\n",
        "bad fragment": "\n\nSee [setup](SETUP.md#no-such-heading).\n",
        "operator word": "\n\nThe operator runs it.\n",
        "bead id": "\n\nTracked as gigai-abc.4 and csy.12.\n",
    }
    for what, text in plants.items():
        (folder / "README.md").write_text(readme + text, encoding="utf-8")
        problems = scan.build_track_checks(tmp)
        check(bool(problems), f"scan passed with a planted {what}")
    quote = scan.DISCLAIMER + "\n"
    check(quote in readme, "README carries the disclaimer line verbatim")
    moved = readme.replace(quote, "", 1).rstrip("\n") + "\n\n" + quote   # the quote moved to the end: past the first three blocks
    (folder / "README.md").write_text(moved, encoding="utf-8")
    check(any("disclaimer" in p for p in scan.build_track_checks(tmp)), "scan passed with the disclaimer moved to the end")
    (folder / "README.md").write_text(readme.replace("Not investment advice.", "Not investment advice!", 1), encoding="utf-8")
    check(any("disclaimer" in p for p in scan.build_track_checks(tmp)), "scan passed with an altered disclaimer")
    (folder / "README.md").write_text(readme, encoding="utf-8")
    (folder / "extra.md").write_text("# Extra\n", encoding="utf-8")
    check(any("not one of the 12" in p for p in scan.build_track_checks(tmp)), "scan accepted a 13th file")


def test_pages() -> None:
    """The twelve pages as build.py renders them from content/: the attribution line under every title, the disclaimer within
    the first three blocks, a week page's order (title, What you learn, disclaimer, Readings, Build steps, chapter), the shell."""
    import json
    import build
    content = ROOT / "content"
    site = json.loads((content / "site.json").read_text(encoding="utf-8"))
    track = build.load_build_track(content)
    check(len(track) == 12, f"{len(track)} pages loaded")
    line = f'<p class="attribution">Generated by Claude through GigAI on {site["updated"]}.</p>'
    for name, page in track.items():
        url, html_text = build.render_build_track_page(content, track, page, site)
        check(url == "/learn/ai-engineering/" + ("" if name == "README.md" else name[:-3].lower() + "/"), f"{name}: url {url}")
        check(f"<title>{build.esc(page.title)} - AI engineering track</title>" in html_text, f"{name}: <title> is not the source H1")
        h1_end = html_text.find("</h1>")
        check(h1_end > 0 and html_text.find(line, h1_end) == h1_end + len("</h1>\n"), f"{name}: no attribution line right under the title")
        check(html_text.count('class="attribution"') == 1, f"{name}: attribution line count")
        check("reviewed by" not in html_text.split("<main", 1)[1].split("</h1>", 1)[1].split("<blockquote", 1)[0], f"{name}: a reviewer claim")
        check(html_text.count('<blockquote class="disclaimer">') == 1 and "data-pagefind-body" in html_text, f"{name}: disclaimer or pagefind body missing")
        main_html = html_text.split("<main", 1)[1]
        if name.startswith("week-"):
            marks = ['<blockquote class="disclaimer">', '<h2 id="readings">Readings</h2>', '<h2 id="build-steps">Build steps</h2>', "<strong>Code:</strong>"]
            if "<strong>What you learn:</strong>" in page.rendered.blocks[1].html:   # the final sources open every week with it
                marks.insert(0, "<strong>What you learn:</strong>")
            positions = [main_html.find(mk) for mk in marks]
            check(all(p >= 0 for p in positions) and positions == sorted(positions), f"{name}: order {list(zip(marks, positions))}")
            check(main_html.find("<strong>Code:</strong>") > 0 and main_html.find("<strong>Code:</strong>") > main_html.find('<h2 id="build-steps">'),
                  f"{name}: the Code line is not under Build steps")
        if name == "README.md":
            check(main_html.rfind("<h2") == main_html.find('<h2 id="track-pages">'), "overview: the contents list is not the last section")
            check(main_html.find('<div class="prevnext">') > main_html.find('<h2 id="track-pages">'), "overview: contents list is not before prev/next")
        check(f'<span>{build.esc(page.label)}</span></a></li>' in html_text, f"{name}: sidebar label {page.label!r}")
        check(len(page.label) <= 12, f"{name}: sidebar label not short: {page.label!r}")
    week1 = build.render_build_track_page(content, track, track["week-1.md"], site)[1]
    check('<td data-col="tag">week-1-start</td>' in week1, "week-1 tag column cells carry data-col=tag")
    check(">Week 2 &rarr;</a>" in week1 and "&larr; Schedule</a>" in week1, "week-1 prev/next use the short labels")


def main() -> int:
    test_renderer()
    test_refusals()
    test_pages()
    tmp = Path(tempfile.mkdtemp(prefix="btc-test-"))
    try:
        test_scan(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for f in FAILURES:
        print("  FAIL: " + f)
    print(f"test_build_track: {len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
