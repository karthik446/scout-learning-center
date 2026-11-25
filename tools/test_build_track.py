#!/usr/bin/env python3
"""The AI engineering track's guards (standard library only; exit 1 on any failure).

    python3 tools/test_build_track.py

Positive: the Markdown subset renders the constructs the guide uses, escapes HTML, writes external links with
target/rel, and resolves relative links the way build.py does; the labs pages (labs index with the captured session,
one page per lab with each exercise's starting code, test, real FAIL, what you write and PASS, the week page's "Labs
for this week" table, the overview line, the sidebar entries) render from content/ai-engineering/labs; the importer
extracts that data and `hidden` from a fixture labs checkout; the glossary page carries every term at #term-<id> with
the A-Z list, and a lab page links its first ATR to it once (never a fenced block, a heading or an existing link).
Negative: a workstation path, an unknown relative link and raw HTML each fail the content scan or the renderer; so do
the other constructs mdlite refuses; a labs JSON with a workstation path in a goal, a missing goal, an unknown concept
id, a solution-looking field or a section number with no chapter heading fails the scan or the build; a solution line,
a hint-2 line or an unlisted hint-1 line fails the importer (fixture), and, planted with its hash in `hidden`, the
scan and the build (copy of the real JSON); an exercise without its site keys fails the importer; an identifier planted
in a chapter that is neither a glossary term nor a not_term fails the glossary check.
"""

from __future__ import annotations

import re
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
    gloss = build.load_glossary(content)
    check(len(track) == 12, f"{len(track)} pages loaded")
    line = f'<p class="attribution">Generated by Claude through GigAI on {site["updated"]}.</p>'
    for name, page in track.items():
        url, html_text = build.render_build_track_page(content, track, page, site, gloss)
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
        check(f'<span>{build.esc(page.label)}</span></a>' in html_text, f"{name}: sidebar label {page.label!r}")
        check(len(page.label) <= 12, f"{name}: sidebar label not short: {page.label!r}")
    week1 = build.render_build_track_page(content, track, track["week-1.md"], site, gloss)[1]
    check('<td data-col="tag">week-1-start</td>' in week1, "week-1 tag column cells carry data-col=tag")
    check(">Week 2 &rarr;</a>" in week1 and "&larr; Schedule</a>" in week1, "week-1 prev/next use the short labels")


def test_labs_pages() -> None:
    """The labs pages of week 1 as build.py renders them from content/: URLs, the shell, prev/next, the week table, the
    overview line, the sidebar, and no hint or solution text."""
    import json
    import build
    content = ROOT / "content"
    site = json.loads((content / "site.json").read_text(encoding="utf-8"))
    track = build.load_build_track(content)
    gloss = build.load_glossary(content)
    doc = track["week-1.md"].labs
    check(doc is not None and [lab["id"] for lab in doc["labs"]] == ["w1l1", "w1l2", "w1l3", "w1l4"], "week 1 labs not loaded")
    check(all(p.labs is None for n, p in track.items() if n not in ("week-1.md", "week-2.md", "week-3.md", "week-4.md", "week-5.md")), "labs attached to a page other than weeks 1 to 5")
    doc2 = track["week-2.md"].labs
    check(doc2 is not None and [lab["id"] for lab in doc2["labs"]] == ["w2l1", "w2l2", "w2l3", "w2l4"], "week 2 labs not loaded")
    all_pages = build.labs_pages(content, track)
    base2 = "/learn/ai-engineering/week-2/labs/"
    pages = [p for p in all_pages if "/week-1/" in p.url]
    pages2 = [p for p in all_pages if "/week-2/" in p.url]
    base = "/learn/ai-engineering/week-1/labs/"
    check([p.url for p in pages] == [base] + [f"{base}w1l{n}/" for n in range(1, 5)], f"labs urls {[p.url for p in pages]}")
    check([p.url for p in pages2] == [base2] + [f"{base2}w2l{n}/" for n in range(1, 5)], f"week 2 labs urls {[p.url for p in pages2]}")
    doc3 = track["week-3.md"].labs
    check(doc3 is not None and [lab["id"] for lab in doc3["labs"]] == ["w3l1", "w3l2", "w3l3", "w3l4"], "week 3 labs not loaded")
    base3 = "/learn/ai-engineering/week-3/labs/"
    pages3 = [p for p in all_pages if "/week-3/" in p.url]
    check([p.url for p in pages3] == [base3] + [f"{base3}w3l{n}/" for n in range(1, 5)], f"week 3 labs urls {[p.url for p in pages3]}")
    doc4 = track["week-4.md"].labs
    check(doc4 is not None and [lab["id"] for lab in doc4["labs"]] == ["w4l1", "w4l2", "w4l3", "w4l4"], "week 4 labs not loaded")
    base4 = "/learn/ai-engineering/week-4/labs/"
    pages4 = [p for p in all_pages if "/week-4/" in p.url]
    check([p.url for p in pages4] == [base4] + [f"{base4}w4l{n}/" for n in range(1, 5)], f"week 4 labs urls {[p.url for p in pages4]}")
    doc5 = track["week-5.md"].labs
    check(doc5 is not None and [lab["id"] for lab in doc5["labs"]] == ["w5l1", "w5l2", "w5l3", "w5l4"], "week 5 labs not loaded")
    base5 = "/learn/ai-engineering/week-5/labs/"
    pages5 = [p for p in all_pages if "/week-5/" in p.url]
    check([p.url for p in pages5] == [base5] + [f"{base5}w5l{n}/" for n in range(1, 5)], f"week 5 labs urls {[p.url for p in pages5]}")
    rendered = {}
    for p in pages:
        url, html_text = build.render_labs_page(track, p, site, gloss)
        rendered[url] = html_text
        main_html = html_text.split("<main data-pagefind-body", 1)[1]
        check(f"<title>{build.esc(p.title)} - AI engineering track</title>" in html_text, f"{url}: <title>")
        check(html_text.count('<blockquote class="disclaimer">') == 1, f"{url}: disclaimer count")
        check(html_text.count('class="attribution"') == 1, f"{url}: attribution count")
        check(f'<a href="{base}w1l1/" class="lesson-link' in html_text, f"{url}: the sidebar lists w1l1")
        check('<a href="/learn/ai-engineering/week-1/">Week 1</a>' in html_text.split('<nav class="breadcrumb"', 1)[1].split("</nav>", 1)[0],
              f"{url}: breadcrumb lacks the week")
        for leak in ("solution.diff", "hints.md", "/stub/", "/wrong/", "red_expect"):
            check(leak not in main_html, f"{url}: {leak!r} on the page")
    index, w1l1, w1l4 = rendered[base], rendered[f"{base}w1l1/"], rendered[f"{base}w1l4/"]
    check("&larr; Week 1</a>" in index and "Lab w1l1 &rarr;</a>" in index, "labs index prev/next")
    check("&larr; Week 1 labs</a>" in w1l1 and "Week 1 labs &rarr;</a>" in w1l4, "labs prev/next do not wrap to the index")
    check(f'href="{base}w1l1/" class="lesson-link current"' in w1l1, "w1l1 is not current in its sidebar")
    check(".venv/bin/tr lab start" in index and "git checkout labs" in index, "labs index lacks the setup or commands")
    check('href="/learn/lessons/llm-agent-evaluation/"' in rendered[f"{base}w1l3/"], "w1l3 does not link its mapped lesson")
    check("tr lab hint" in w1l1 and "never appear on this site" in w1l1, "lab page lacks the hint/solution line")
    check('href="/learn/ai-engineering/week-1/#1-setup-and-a-tour-of-the-core' in w1l1, "w1l1 does not link its chapter section")
    week1 = build.render_build_track_page(content, track, track["week-1.md"], site, gloss)[1].split("<main", 1)[1]
    week2 = build.render_build_track_page(content, track, track["week-2.md"], site, gloss)[1].split("<main", 1)[1]
    check(week1.count("Labs for this week</h2>") == 1, "week 1 has no single 'Labs for this week'")
    marks = [week1.find('<blockquote class="disclaimer">'), week1.find("Labs for this week</h2>"), week1.find('<h2 id="readings">')]
    check(all(m >= 0 for m in marks) and marks == sorted(marks), f"week 1 labs table not between disclaimer and readings {marks}")
    check(f'href="{base}"' in week1 and f'href="{base}w1l3/"' in week1, "week 1 table lacks its links")
    check(week2.count("Labs for this week</h2>") == 1 and f'href="{base2}w2l4/"' in week2, "week 2 has no labs table with its links")
    overview = build.render_build_track_page(content, track, track["README.md"], site, gloss)[1].split("<main", 1)[1]
    week3 = build.render_build_track_page(content, track, track["week-3.md"], site, gloss)[1].split("<main", 1)[1]
    check(week3.count("Labs for this week</h2>") == 1 and f'href="{base3}w3l4/"' in week3, "week 3 has no labs table with its links")
    week4 = build.render_build_track_page(content, track, track["week-4.md"], site, gloss)[1].split("<main", 1)[1]
    check(week4.count("Labs for this week</h2>") == 1 and f'href="{base4}w4l4/"' in week4, "week 4 has no labs table with its links")
    week5 = build.render_build_track_page(content, track, track["week-5.md"], site, gloss)[1].split("<main", 1)[1]
    check(week5.count("Labs for this week</h2>") == 1 and f'href="{base5}w5l4/"' in week5, "week 5 has no labs table with its links")
    check(f'<p><strong>Labs: optional, $0.</strong> <a href="{base}">Week 1</a>, <a href="{base2}">Week 2</a>, <a href="{base3}">Week 3</a>, <a href="{base4}">Week 4</a>, <a href="{base5}">Week 5</a></p>' in overview, "overview lacks the labs line")
    check(overview.find("Labs: optional") > overview.find('<blockquote class="disclaimer">'), "overview labs line before the disclaimer")
    w1l2 = rendered[f"{base}w1l2/"].split("<main data-pagefind-body", 1)[1]
    check('<h2 id="exercises">' not in w1l2 and "What you observe when green</th>" not in w1l2, "w1l2 still has the thin exercises table")
    marks = [w1l2.find(s) for s in ("w1l2.1: ", "<strong>Goal</strong>", "<strong>Starting code</strong>", "TODO(w1l2.1)",
                                     "<strong>What the check tests</strong>", "def test_", "<strong>A real FAIL</strong>",
                                     "<strong>What you write</strong>", "<strong>When green</strong>")]
    check(all(m >= 0 for m in marks) and marks == sorted(marks), f"w1l2 exercise section out of order {marks}")
    check("FAIL" in w1l2.split("A real FAIL", 1)[1] and "PASS" in w1l2.split("When green", 1)[1], "w1l2 lacks its captured FAIL or PASS")
    for ex in doc["labs"][1]["exercises"]:
        check(build.esc(ex["start_code"][0]["code"].split("\n")[0]) in w1l2, f"{ex['id']}: starting code not on the page")
        check(build.esc(ex["fail"].strip().split("\n")[0]) in w1l2, f"{ex['id']}: FAIL output not on the page")
    session = index.split("How a lab session works</h2>", 1)[-1]
    check("How a lab session works</h2>" in index and session.find("<h3") >= 0 and session.find("<h4") >= 0, "labs index lacks the session")
    outputs = [st["output"] for p in doc["session"]["parts"] for st in p["steps"] if st["output"]]
    check(bool(outputs) and all(build.esc(o.strip().split("\n")[0]) in index for o in outputs), "labs index lacks a captured session output")
    if any(st["shown"] is None for p in doc["session"]["parts"] for st in p["steps"]):
        check("applies the reference solution where you would write your own code" in index, "apply step lacks its sentence")


def test_glossary_page() -> None:
    """The glossary page as build.py renders it: every term once at #term-<id>, the A-Z jump list, the shell, the
    sidebar entry and the overview's line."""
    import json
    import build
    content = ROOT / "content"
    site = json.loads((content / "site.json").read_text(encoding="utf-8"))
    track = build.load_build_track(content)
    gloss = build.load_glossary(content)
    terms = json.loads((content / scan.BUILD_TRACK_DIR / scan.GLOSSARY_FILE).read_text(encoding="utf-8"))["terms"]
    url, html_text = build.render_glossary_page(track, gloss, site)
    check(url == "/learn/ai-engineering/glossary/", f"glossary url {url}")
    main_html = html_text.split("<main data-pagefind-body", 1)[1].split("</main>", 1)[0]
    check(bool(terms) and main_html.count("<dt id=") == len(terms) == main_html.count("<dd>"), f"glossary: {main_html.count('<dt id=')} entries for {len(terms)} terms")
    for t in terms:
        check(f'<dt id="term-{t["id"]}">{build.esc(t["term"])}</dt>' in main_html, f"glossary page lacks {t['id']}")
        check(build.esc(t["definition"]) in main_html, f"glossary page lacks the definition of {t['id']}")
    nav = main_html.split('aria-label="Glossary letters"', 1)[-1].split("</nav>", 1)[0]
    letters = sorted({t["term"][0].upper() for t in terms})
    check(all(f'<a href="#letter-{c.lower()}">{c}</a>' in nav and f'<h2 id="letter-{c.lower()}">' in main_html for c in letters),
          "glossary A-Z list does not reach every letter")
    check(html_text.count('<blockquote class="disclaimer">') == 1 and html_text.count('class="attribution"') == 1, "glossary disclaimer or attribution")
    check('class="lesson-link current"><span class="lesson-dot"></span><span>Glossary</span>' in html_text, "glossary is not current in its sidebar")
    check("#term-" not in main_html.split('aria-label="Glossary letters"', 1)[0], "the glossary links its own intro")
    overview = build.render_build_track_page(content, track, track["README.md"], site, gloss)[1].split("<main", 1)[1]
    check('<a href="/learn/ai-engineering/glossary/">Glossary</a>' in overview, "overview lacks the glossary line")


def test_glossary_links() -> None:
    """First-use linking: w2l3 uses ATR in its prose many times and links only the first; no labs page links inside
    <pre>; on synthetic HTML a heading, an existing link and a fenced block stay plain, a code span links only when it is
    a whole term, and a `case` term (the ticker CAT) skips the common word. An everyday word (close) links on a lab page
    and not on a chapter page; a use inside a term's not_in phrase (can trace to) stays plain and the next use links; a
    week's readings (book titles) stay plain."""
    import json
    import build
    content = ROOT / "content"
    site = json.loads((content / "site.json").read_text(encoding="utf-8"))
    track = build.load_build_track(content)
    gloss = build.load_glossary(content)
    href = '<a href="/learn/ai-engineering/glossary/#term-atr">'
    for lp in build.labs_pages(content, track):
        main_html = build.render_labs_page(track, lp, site, gloss)[1].split("<main data-pagefind-body", 1)[1].split("</main>", 1)[0]
        check(all("/glossary/#term-" not in pre for pre in re.findall(r"<pre\b.*?</pre>", main_html, re.S)), f"{lp.url}: a glossary link inside <pre>")
        if lp.url.endswith("/w2l3/"):
            prose = re.sub(r"<pre\b.*?</pre>", "", main_html, flags=re.S)
            uses = [m.start() for m in re.finditer(r"(?<!\w)ATRs?(?!\w)", prose)]
            check(main_html.count(href) == 1, f"w2l3: {main_html.count(href)} ATR links")
            check(len(uses) >= 2 and prose[:uses[0]].endswith(href) and not prose[:uses[1]].endswith(href),
                  "w2l3: the first ATR is not the linked one, or the second is linked")
    src = ('<h2 id="atr">ATR</h2>\n<p>The ATR and the atr again, <a href="/x/">RSI</a>, <code>rsi_14</code>, <code>rsi_14 &gt; 70</code>. '
           'The cat sat; CAT rose.</p>\n<span class="code-lang">python</span><pre><code class="language-python">atr = ATR(rsi_14)</code></pre>')
    out = gloss.link(src)
    g = "/learn/ai-engineering/glossary/#term-"
    check(out.count(g + "atr") == 1 and f'The {href}ATR</a> and the atr again' in out and out.startswith('<h2 id="atr">ATR</h2>'),
          "synthetic: ATR not linked once, at its first prose use")
    check('<a href="/x/">RSI</a>' in out and f'<a href="{g}rsi"><code>rsi_14</code></a>' in out and "<code>rsi_14 &gt; 70</code>" in out,
          "synthetic: an existing link was touched, or the code spans were linked wrongly")
    check("The cat sat" in out and f'<a href="{g}cat">CAT</a> rose' in out, "synthetic: the case-sensitive ticker CAT")
    check(out.endswith('<span class="code-lang">python</span><pre><code class="language-python">atr = ATR(rsi_14)</code></pre>'), "synthetic: a fenced block was linked")
    lab_close = gloss.link("<p>Sell at the close.</p>", everyday=True)
    check(f'<a href="{g}close">close</a>' in lab_close and "#term-" not in gloss.link("<p>Sell at the close.</p>"),
          "everyday: close is not linked on a lab page, or is linked on a chapter page")
    traced = gloss.link("<p>Each number can <strong>trace</strong> to that table. A trace is one record.</p>")
    check("can <strong>trace</strong> to" in traced and f'A <a href="{g}trace">trace</a> is' in traced,
          f"not_in: the trace in 'can trace to' was linked, or the next use was not: {traced}")
    week2 = build.render_build_track_page(content, track, track["week-2.md"], site, gloss)[1]
    readings = week2.split('<div class="readings">', 1)[-1].split("</div>", 1)[0]
    check('<div class="readings">' in week2 and "Fine-Tuning" in readings and "#term-" not in readings,
          "week 2 readings: missing, or a book title is glossary-linked")


def test_labs_refusals(tmp: Path) -> None:
    """A copy of the track with the real labs JSON: clean, then each planted defect fails the scan or the build."""
    import json
    import build
    shutil.copytree(ROOT / "content" / scan.BUILD_TRACK_DIR, tmp / scan.BUILD_TRACK_DIR)
    (tmp / "lessons").symlink_to(ROOT / "content" / "lessons", target_is_directory=True)
    path = tmp / scan.BUILD_TRACK_DIR / scan.LABS_DIR / "week-1.json"
    good = json.loads(path.read_text(encoding="utf-8"))
    check(not scan.labs_checks(tmp) and not scan.build_track_checks(tmp), f"baseline labs scan: {scan.labs_checks(tmp)[:3]}")

    def planted(change) -> dict:
        doc = json.loads(json.dumps(good))
        change(doc)
        path.write_text(json.dumps(doc), encoding="utf-8")
        return doc

    scan_plants = {
        "workstation path in a goal": (lambda d: d["labs"][0].update(goal="Clone into /Users/someone/code first."), "workstation path"),
        "missing goal": (lambda d: d["labs"][1].pop("goal"), "missing goal"),
        "unknown concept id": (lambda d: d["labs"][0]["exercises"][0]["concepts"].append("no-such-concept"), "unknown concept id"),
        "solution-looking field": (lambda d: d["labs"][0]["exercises"][0].update(solution="--- a/x\n+++ b/x"), "solution- or hint-looking"),
        "hints on a lab": (lambda d: d["labs"][2].update(hints=["look at the parser"]), "solution- or hint-looking"),
    }
    for what, (change, expect) in scan_plants.items():
        planted(change)
        problems = scan.labs_checks(tmp)
        check(any(expect in p for p in problems), f"labs scan passed with a planted {what}: {problems[:2]}")
        try:
            build.load_build_track(tmp)
            FAILURES.append(f"build loaded labs with a planted {what}")
        except build.BuildError:
            pass
    planted(lambda d: d["labs"][3].update(section=[6, 99]))
    check(not scan.labs_checks(tmp), "the section plant should pass the scan (only the build knows the chapter headings)")
    try:
        build.load_build_track(tmp)
        FAILURES.append("build loaded labs whose section 99 matches no chapter heading")
    except build.BuildError as e:
        check("section 99" in str(e), f"section error does not name the section: {e}")
    path.write_text(json.dumps(good), encoding="utf-8")


FIXTURE = {   # a one-lab, two-exercise labs checkout for the importer (paths under its root)
    "labs/w1/lab.toml": 'base = "week-1-start"\n[unlock]\nhints = [2, 5]\nsolution = 10\n[labs.w1l1]\ntitle = "Fixture lab"\n'
                        'page = "pages/w1l1.md"\ngoal = "Practise the fixture loop."\nsection = [1]\n',
    "labs/w1/pages/concepts.md": "| Term | Means |\n|---|---|\n| [Error analysis](#error-analysis) | reading failures by hand |\n",
    "labs/w1/pages/w1l1.md": "# Lab w1l1\n",
    "labs/w1/exercises/w1l1.1-count/exercise.toml":
        'id = "w1l1.1"\ntitle = "Count the labels"\neffect = "The counts print."\nlab = "w1l1"\nconcepts = ["error-analysis"]\n'
        'touches = ["src/app.py", "data/rows.csv"]\ngoal = "Count how many rows carry each label."\n'
        'what_tested = "The check feeds three rows and expects the per-label totals."\n'
        'writes = ["The body of `count`: a total per label.", "A dict as the return value."]\n'
        'show_tests = ["test_counts"]\nshow_data = ["data/rows.csv"]\n',
    "labs/w1/exercises/w1l1.1-count/stub/src/app.py":
        'import csv\n\n\ndef load(path):\n    return list(csv.DictReader(open(path)))\n\n\ndef count(rows):\n'
        '    # TODO(w1l1.1): count the rows per label\n    return {}\n',
    "labs/w1/exercises/w1l1.1-count/stub/data/rows.csv": "label,text\nok,first row\nbad,second row\n",
    "labs/w1/exercises/w1l1.1-count/test_count.py":
        'from app import count\n\n\ndef test_counts():\n    rows = [{"label": "ok"}, {"label": "ok"}, {"label": "bad"}]\n'
        '    assert count(rows) == {"ok": 2, "bad": 1}\n\n\ndef test_empty():\n    assert count([]) == {}\n',
    "labs/w1/exercises/w1l1.1-count/solution.diff":
        '--- a/src/app.py\n+++ b/src/app.py\n@@ -8,3 +8,3 @@\n def count(rows):\n-    # TODO(w1l1.1): count the rows per label\n'
        '-    return {}\n+    totals = collections.Counter(r["label"] for r in rows)\n+    return dict(totals)\n',
    "labs/w1/exercises/w1l1.1-count/hints.md":
        "## Hint 1\nThink about grouping rows by their label value.\nEach label maps to how many rows carry it.\n"
        "## Hint 2\nA collections.Counter over the label column does it.\n",
    "labs/w1/exercises/w1l1.1-count/expected_output/fail.txt": "FAIL w1l1.1 test_counts\nassert {} == {'ok': 2, 'bad': 1}\n",
    "labs/w1/exercises/w1l1.1-count/expected_output/pass.txt": "PASS w1l1.1 (2 tests)\n",
    "labs/w1/exercises/w1l1.2-report/exercise.toml":
        'id = "w1l1.2"\ntitle = "Report the counts"\neffect = "One line per label prints."\nlab = "w1l1"\nconcepts = ["error-analysis"]\n'
        'touches = ["src/app.py"]\ngoal = "Print one line per label."\nwhat_tested = "The check captures the printed report."\n'
        'writes = ["A loop over the totals.", "One print per label."]\nshow_tests = ["test_report"]\n',
    "labs/w1/exercises/w1l1.2-report/stub/src/app.py":
        'import collections\n\n\ndef count(rows):\n    totals = collections.Counter(r["label"] for r in rows)\n    return dict(totals)\n\n\n'
        'def report(rows):\n    totals = collections.Counter(r["label"] for r in rows)\n    # TODO(w1l1.2): print one line per label\n    pass\n',
    "labs/w1/exercises/w1l1.2-report/test_report.py":
        'from app import report\n\n\ndef test_report(capsys):\n    report([{"label": "ok"}])\n    assert capsys.readouterr().out == "ok 1\\n"\n',
    "labs/w1/exercises/w1l1.2-report/solution.diff":
        '--- a/src/app.py\n+++ b/src/app.py\n@@ -11,2 +11,3 @@\n-    pass\n+    for label, n in sorted(totals.items()):\n'
        '+        print(label, n)\n',
    "labs/w1/exercises/w1l1.2-report/hints.md": "## Hint 1\nLoop over the totals you already have.\n## Hint 2\nsorted(totals.items()) gives a stable order.\n",
    "labs/w1/exercises/w1l1.2-report/expected_output/fail.txt": "FAIL w1l1.2 test_report\nassert '' == 'ok 1'\n",
    "labs/w1/exercises/w1l1.2-report/expected_output/pass.txt": "PASS w1l1.2 (1 test)\n",
    "labs/w1/session/session.toml":
        'diagram = """\nstart -> verify (FAIL) -> write -> verify (PASS) -> next\n"""\n[[part]]\nid = "start"\ntitle = "Start the lab"\n'
        'intro = "Begin from a clean clone."\n[[part.step]]\ntitle = "Start"\nrun = ".venv/bin/tr lab start w1l1"\noutput = "01-start.txt"\n'
        'explain = "The runner installs the stub."\n[[part.step]]\ntitle = "Read hint 1"\nrun = ".venv/bin/tr lab hint"\n'
        'output = "02-hint.txt"\nexplain = "Hint 1 is an idea, not code."\n[[part.step]]\ntitle = "Write the code"\napply = "solution"\n'
        '[[part.step]]\ntitle = "Look at the tree"\nrun = "git status --short"\nexplain = "Nothing printed: the tree is clean."\n',
    "labs/w1/session/01-start.txt": "Installed w1l1.1: Count the labels\n",
    "labs/w1/session/02-hint.txt": "Hint 1 of 2:\nThink about grouping rows by their label value.\n",
}


def test_import_labs(tmp: Path) -> None:
    """The importer on a fixture checkout: the page data it extracts, `hidden`, and the leaks and gaps it refuses."""
    import import_labs
    for rel, text in FIXTURE.items():
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp / rel).write_text(text, encoding="utf-8")
    h = scan.labs_line_hash
    doc = import_labs.extract(tmp, 1)
    ex1, ex2 = doc["labs"][0]["exercises"]
    check(ex1["start_code"] == [{"path": "src/app.py", "url": None, "lines": [8, 10], "lang": "python",
                                 "code": "def count(rows):\n    # TODO(w1l1.1): count the rows per label\n    return {}"}],
          f"w1l1.1 start_code {ex1['start_code']}")
    check(ex1["data"] == [{"path": "data/rows.csv", "header_and_row": "label,text\nok,first row"}], f"w1l1.1 data {ex1['data']}")
    check([t["name"] for t in ex1["tests"]] == ["test_counts"] and ex1["tests"][0]["code"].startswith("def test_counts():"), "w1l1.1 tests")
    check(ex1["fail"].startswith("FAIL w1l1.1") and ex1["pass"].startswith("PASS w1l1.1"), "w1l1.1 captures")
    check(ex2["start_code"][0]["lines"] == [11, 12] and "Counter" not in ex2["start_code"][0]["code"],
          f"w1l1.2 start_code keeps w1l1.1's answer: {ex2['start_code']}")
    steps = doc["session"]["parts"][0]["steps"]
    check([(s["shown"] is None, s["output"] is None) for s in steps] == [(False, False), (False, False), (True, True), (False, True)],
          "session: apply step without command and output, silent run without output")
    hidden = set(doc["hidden"])
    for line, want in (('totals = collections.Counter(r["label"] for r in rows)', True), ("print(label, n)", True),
                       ("A collections.Counter over the label column does it.", True),
                       ("Each label maps to how many rows carry it.", True),
                       ("Think about grouping rows by their label value.", False), ("return dict(totals)", True)):
        check((h(line) in hidden) == want, f"hidden {'lacks' if want else 'holds'} {line!r}")
    toml = tmp / "labs/w1/exercises/w1l1.1-count/exercise.toml"
    good = toml.read_text(encoding="utf-8")
    for what, old, new in (("a solution line in writes", '"A dict as the return value."', '"return dict(totals)"'),
                           ("a hint-2 line in what_tested", "The check feeds three rows and expects the per-label totals.",
                            "A collections.Counter over the label column does it."),
                           ("an unlisted hint-1 line in goal", "Count how many rows carry each label.",
                            "Each label maps to how many rows carry it.")):
        toml.write_text(good.replace(old, new), encoding="utf-8")
        try:
            import_labs.extract(tmp, 1)
            FAILURES.append(f"importer accepted {what}")
        except import_labs.LabsError as e:
            check("would reach a page" in str(e), f"{what}: wrong error {e}")
    toml.write_text(good.replace('goal = "Count how many rows carry each label."\n', ""), encoding="utf-8")
    try:
        import_labs.extract(tmp, 1)
        FAILURES.append("importer accepted an exercise without goal")
    except import_labs.LabsError as e:
        check("w1l1.1 (goal)" in str(e), f"missing-key error does not list the key: {e}")
    toml.write_text(good, encoding="utf-8")
    only = import_labs.extract(tmp, 1, only_lab="w1l1")
    check([lab["id"] for lab in only["labs"]] == ["w1l1"], "--only-lab")


def test_labs_leaks(tmp: Path) -> None:
    """A copy of the real week-1 JSON: a solution line, a hint-2 line and an unlisted hint-1 line planted (text on a page,
    its hash in `hidden`) each fail the scan and the build; the build's own guard catches them in escaped Markdown."""
    import json
    import build
    shutil.copytree(ROOT / "content" / scan.BUILD_TRACK_DIR, tmp / scan.BUILD_TRACK_DIR)
    (tmp / "lessons").symlink_to(ROOT / "content" / "lessons", target_is_directory=True)
    path = tmp / scan.BUILD_TRACK_DIR / scan.LABS_DIR / "week-1.json"
    good = json.loads(path.read_text(encoding="utf-8"))
    plants = {
        "solution line in a goal": ("    totals = collections.Counter(r['label'] for r in rows)",
                                    lambda d, t: d["labs"][0]["exercises"][0].update(goal=t.strip())),
        "hint-2 line in a session explain": ("Use a Counter over the label column of each row.",
                                             lambda d, t: d["session"]["parts"][0]["steps"][0].update(explain=t)),
        "unlisted hint-1 line in a FAIL block": ("Think about which rows share one label value.",
                                                 lambda d, t: d["labs"][1]["exercises"][0].update(fail=d["labs"][1]["exercises"][0]["fail"] + t + "\n")),
    }
    for what, (text, change) in plants.items():
        doc = json.loads(json.dumps(good))
        change(doc, text)
        doc["hidden"] = sorted(set(doc["hidden"]) | {scan.labs_line_hash(text)})
        path.write_text(json.dumps(doc), encoding="utf-8")
        problems = scan.labs_checks(tmp)
        check(any("a solution or hint line" in p for p in problems), f"labs scan passed with a planted {what}: {problems[:2]}")
        try:
            build.load_build_track(tmp)
            FAILURES.append(f"build loaded labs with a planted {what}")
        except build.BuildError:
            pass
        try:
            build.render_labs_md("leak", f"# x\n\n- {build.md_prose(text.strip())}\n", {}, {scan.labs_line_hash(text)})
            FAILURES.append(f"build rendered a page with a planted {what}")
        except build.BuildError as e:
            check("a solution or hint line" in str(e), f"build leak error: {e}")
    path.write_text(json.dumps(good), encoding="utf-8")


def test_glossary_scan(tmp: Path) -> None:
    """A copy of the real track: the glossary check is clean, then a candidate planted in week-1.md (or a labs goal)
    that is neither a term nor a not_term fails it with the reviewer's message, naming the line or the labs field: a
    code-span identifier, capitals with a number (EMA50), a plural (EMAs, checked as EMA) and a finance constant
    (STOP_ATR_MULT, in code and bare); a not_term that is also a term fails too."""
    import json
    folder = tmp / scan.BUILD_TRACK_DIR
    shutil.copytree(ROOT / "content" / scan.BUILD_TRACK_DIR, folder)
    base = scan.glossary_checks(tmp)
    check(not base, f"baseline glossary check of the test copy: {base[:3]}")
    week1 = folder / "week-1.md"
    text = week1.read_text(encoding="utf-8")
    line = len(text.split("\n")) + 1
    plants = {"The new `zz_new_feature` column.": "'zz_new_feature'", "A bare EMA50 cross.": "'EMA50'",
              "Two EMAs cross.": "'EMA' (written 'EMAs')", "The `STOP_ATR_MULT` knob.": "'STOP_ATR_MULT'",
              "The STOP_ATR_MULT knob.": "'STOP_ATR_MULT'"}
    for plant, shown in plants.items():
        week1.write_text(text + f"\n{plant}\n", encoding="utf-8")
        problems = scan.glossary_checks(tmp)
        want = f"{scan.BUILD_TRACK_DIR}/week-1.md (line {line}): {shown} is not in the glossary or not_terms; {scan.GLOSSARY_FIX}"
        check(want in problems, f"planted {plant!r} passed the glossary check, or its message changed: {problems[:3]}")
    week1.write_text(text, encoding="utf-8")
    labs = folder / scan.LABS_DIR / "week-1.json"
    good = labs.read_text(encoding="utf-8")
    doc = json.loads(good)
    doc["labs"][0]["exercises"][0]["goal"] += " Plus EMA50."
    labs.write_text(json.dumps(doc), encoding="utf-8")
    where = f"{scan.BUILD_TRACK_DIR}/{scan.LABS_DIR}/week-1.json (labs[{doc['labs'][0]['id']}].exercises[{doc['labs'][0]['exercises'][0]['id']}].goal): 'EMA50'"
    check(any(p.startswith(where) for p in scan.glossary_checks(tmp)), "a planted labs goal is not reported at its lab and exercise")
    labs.write_text(good, encoding="utf-8")
    path = folder / scan.GLOSSARY_FILE
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["not_terms"].append({"token": "ATR", "why": "Allowlisted instead of defined."})
    path.write_text(json.dumps(doc), encoding="utf-8")
    check(any("'ATR'" in p and "also a glossary phrase" in p for p in scan.glossary_checks(tmp)), "a finance term allowlisted in not_terms passed")


def main() -> int:
    test_renderer()
    test_refusals()
    test_pages()
    test_labs_pages()
    test_glossary_page()
    test_glossary_links()
    tmp = Path(tempfile.mkdtemp(prefix="btc-test-"))
    try:
        test_scan(tmp / "scan")
        test_labs_refusals(tmp / "labs")
        test_import_labs(tmp / "import")
        test_labs_leaks(tmp / "leaks")
        test_glossary_scan(tmp / "glossary")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for f in FAILURES:
        print("  FAIL: " + f)
    print(f"test_build_track: {len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
