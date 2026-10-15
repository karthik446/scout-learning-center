#!/usr/bin/env python3
"""content/ -> site/ : the static build of scout.edgelab.one (standard library only, no network, no model, no gigai).

    python3 tools/build.py [--content content] [--out site]

The output tree is deploy.md section 2. The page shell, the sidebar, the breadcrumb, the subtopic anchors, the link
audit, the glyph check and the inline-script check follow gigai.scout.learning_render (read, never imported).
Pagefind is run afterwards over site/learn/ (see README.md); its files are the only ones this build does not write.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan  # noqa: E402  (the same checks CI runs; stdlib only)

ROOT = Path(__file__).resolve().parent.parent
ORIGIN = "https://scout.edgelab.one"
GIGAI_DOCS = "https://karthik446.github.io/gigai"
MAX_HTML_BYTES = 3 * 1024 * 1024          # one page (the renderer's cap)
MAX_SITE_HTML_BYTES = 30 * 1024 * 1024    # all HTML together
MAX_FILE_BYTES = 25 * 1024 * 1024         # Cloudflare Pages: 25 MiB per file
MAX_FILES = 20000                         # Cloudflare Pages: 20,000 files per site (Pagefind roughly doubles the HTML count)
ALLOWED_EXTRA = frozenset("‘’“”–—…")
HLJS_LANGS = {"python": "python", "py": "python", "go": "go", "bash": "bash", "sh": "bash", "shell": "bash"}
GENERATED_LATER = ("/learn/pagefind/",)   # written by pagefind after this build; scan --built and lychee see them then

FOOTER_ATTRIBUTION = (
    "Lessons and practice paths on this site were written by Claude, through GigAI's generator or by hand for the Scout learning center, from public documentation "
    "and generalised job requirements; nothing here is a job posting, a company or a person. No tracking."
)
FOOTER_NO_TRACKING = "No tracking: no analytics, no cookies, no accounts, no third-party requests. Static pages built from a public library."


class BuildError(Exception):
    pass


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def domain_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url)
    return m.group(1) if m else url


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def strip_invisible(s: str) -> str:
    return "".join(ch for ch in s if ch != "﻿" and unicodedata.category(ch) != "Cf")


def clean(obj):
    """Strip invisible code points from every string of the content (the renderer's sanitation)."""
    if isinstance(obj, str):
        return strip_invisible(obj)
    if isinstance(obj, list):
        return [clean(o) for o in obj]
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    return obj


# ---------------------------------------------------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------------------------------------------------
class Library:
    def __init__(self, content: Path) -> None:
        docs, problems = scan.load_all(content)
        problems += scan.validate(docs) if not problems else []
        if problems:
            raise BuildError("content does not pass tools/scan.py:\n  " + "\n  ".join(problems[:30]))
        docs = clean(docs)
        self.site = docs["site.json"]
        self.keys = {k["key"]: k for k in docs["keys/concept-keys.json"]["keys"]}
        self.areas = docs["keys/concept-keys.json"]["areas"]
        self.lessons = {d["id"]: d for r, d in docs.items() if r.startswith("lessons/")}
        self.scenarios = {d["id"]: d for r, d in docs.items() if r.startswith("scenarios/")}
        self.practice = {d["lesson"]: d for r, d in docs.items() if r.startswith("practice/")}
        self.modules = {d["id"]: d for r, d in docs.items() if r.startswith("modules/") and r != "modules/index.json"}
        self.module_index = docs["modules/index.json"]["modules"]
        self.changelog = docs["changelog.json"]["entries"]
        self._check_provenance()
        # lesson -> (module id, position among the module's published lessons, entry); every published lesson has exactly one (scan.py)
        self.home_of: dict[str, tuple[str, int, dict]] = {}
        self.module_lessons: dict[str, list[str]] = {}
        self.planned: dict[str, dict] = {}
        for mid, m in self.modules.items():
            ids = self.module_lessons.setdefault(mid, [])
            for e in m["lessons"]:
                if e["status"] == "published":
                    ids.append(e["id"])
                    self.home_of[e["id"]] = (mid, len(ids), e)
                else:
                    self.planned[e["id"]] = e
        self.children: dict[str, list[str]] = {}
        for k in self.keys.values():
            if k["parent"]:
                self.children.setdefault(k["parent"], []).append(k["key"])
        self.lessons_by_key: dict[str, list[str]] = {}
        for lid, l in self.lessons.items():
            for k in l["keys"]:
                self.lessons_by_key.setdefault(k, []).append(lid)

    def _check_provenance(self) -> None:
        for kind, group in (("lesson", self.lessons), ("practice", self.practice)):
            for ident, d in group.items():
                p = d["provenance"]
                if not p["generated_by"].strip():
                    raise BuildError(f"{kind} {ident}: provenance.generated_by is empty; the build refuses it")
                if p["reviewed_by"] and not p["reviewed_on"]:
                    raise BuildError(f"{kind} {ident}: reviewed_by is set without a date; the build never prints 'reviewed' without one")


# ---------------------------------------------------------------------------------------------------------------------
# Page shells
# ---------------------------------------------------------------------------------------------------------------------
def a(href: str, text: str, cls: str = "") -> str:
    c = f' class="{cls}"' if cls else ""
    return f'<a href="{esc(href)}"{c}>{text}</a>'


def ext(url: str, text: str) -> str:
    return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{text}</a>'


SIM_CSS = '<link rel="stylesheet" href="/_assets/sim/sim.css">\n'
SIM_JS = "/_assets/sim/sim.js"


def head(title: str, description: str, *, code: bool = False, sim: bool = False) -> str:
    hl = (
        '<link rel="stylesheet" href="/_assets/hljs/styles/github.min.css" data-hljs-theme="light">\n'
        '<link rel="stylesheet" href="/_assets/hljs/styles/github-dark.min.css" data-hljs-theme="dark" disabled>\n'
        if code else ""
    )
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{esc(title)}</title>\n"
        f'<meta name="description" content="{esc(description)}">\n'
        '<link rel="icon" href="/_assets/favicon.svg" type="image/svg+xml">\n'
        '<script src="/_assets/theme-init.js"></script>\n'
        f'{hl}<link rel="stylesheet" href="/_assets/site.css">\n{SIM_CSS if sim else ""}</head>\n'
    )


def theme_toggle() -> str:
    return (
        '<button type="button" id="theme-toggle" class="theme-toggle" aria-label="Toggle color theme">'
        '<span class="theme-toggle-label">Light</span></button>'
    )


def footer() -> str:
    return (
        "<footer>\n<div class=\"foot-inner\">\n"
        f'<p class="muted">{esc(FOOTER_ATTRIBUTION)} Reviewed by a person only where a page says so.</p>\n'
        f'<p class="muted">{esc(FOOTER_NO_TRACKING)} &middot; {a("/", "Scout")} &middot; {a("/learn/", "Learning center")} '
        f'&middot; {a("/learn/changelog/", "Changelog")} &middot; {ext(GIGAI_DOCS, "Scout / GigAI docs")}</p>\n'
        "</div>\n</footer>\n"
    )


def tail_scripts(*, mermaid: bool = False, code: bool = False, extra: tuple[str, ...] = (), sim: bool = False) -> str:
    s = []
    if mermaid:
        s.append('<script src="/_assets/mermaid/mermaid.min.js"></script>')
    if code:
        s.append('<script src="/_assets/hljs/highlight.min.js"></script>')
        s += [f'<script src="/_assets/hljs/languages/{n}.min.js"></script>' for n in ("python", "go", "bash")]
    s += [f'<script src="{src}"></script>' for src in extra]
    if sim:  # the one ES module of the simulator block (same origin, no inline code)
        s.append(f'<script type="module" src="{SIM_JS}"></script>')
    s.append('<script src="/_assets/course.js" defer></script>')
    return "\n".join(s) + "\n</body>\n</html>\n"


NAV = (("/", "Scout", "scout"), ("/learn/", "Learning center", "learn"), ("/learn/modules/", "Modules", "modules"),
       ("/learn/search/", "Search", "search"))


def site_page(title: str, body: str, *, current: str = "", crumbs: list[tuple[str, str]] | None = None, description: str = "",
              brand: str = "learn", indexed: bool = True, extra_scripts: tuple[str, ...] = (), extra_head_css: bool = False) -> str:
    """A page of the site shell (landing, learning center, modules, keys, changelog, search, 404)."""
    brand_html = (
        a("/", 'Scout <span>&middot; scout.edgelab.one</span>', "brand") if brand == "scout"
        else a("/learn/", 'Learning center <span>&middot; scout.edgelab.one/learn</span>', "brand")
    )
    nav = "".join(a(h, t, "current" if c == current else "") for h, t, c in NAV)
    crumb = ""
    if crumbs:
        parts = [a(h, esc(t)) for h, t in crumbs[:-1]] + [esc(crumbs[-1][1])]
        crumb = f'<nav class="breadcrumb" aria-label="Breadcrumb">{" &rsaquo; ".join(parts)}</nav>\n'
    pf = " data-pagefind-body" if indexed else ""
    return (
        head(title, description or title)
        + '<body class="site">\n<header class="top">\n<div class="top-inner">\n'
        + f'{brand_html}\n<div class="top-right"><nav class="site" aria-label="Site">{nav}</nav>{theme_toggle()}</div>\n</div>\n</header>\n'
        + f"<main{pf}>\n{crumb}{body}\n</main>\n{footer()}"
        + tail_scripts(extra=extra_scripts)
    )


def sidebar(lib: Library, mid: str | None, current: str) -> str:
    """The product's sidebar: the module's lessons (by part when it has parts), with Practice links; `current` is a page path."""
    parts = ['<nav class="sidebar" aria-label="Module">']
    if mid is None:
        parts.append('<div class="sidebar-title">' + a("/learn/", "Learning center") + "</div>")
        parts.append("</nav>")
        return "\n".join(parts)
    m = lib.modules[mid]
    here = f"/learn/modules/{mid}/"
    parts.append(f'<div class="sidebar-title">{a(here, esc(m["title"]), "current" if current == here else "")}</div>')
    parts.append('<div class="sidebar-search"><input type="search" id="sidebar-search-input" placeholder="Filter lessons" '
                 'autocomplete="off" aria-label="Filter lessons in this module"></div>')
    parts.append('<ul class="sidebar-overview">')
    parts.append(f'<li>{a("/learn/modules/", "All modules")}</li>')
    parts.append(f'<li>{a("/learn/search/", "Search the whole site")}</li>')
    parts.append("</ul>")
    published = [e for e in m["lessons"] if e["status"] == "published"]
    groups = ([(f"{p['id']}. {p['title']}", [e for e in published if e["part"] == p["id"]]) for p in m["parts"]]
              if m.get("parts") else [("Lessons", published)])
    n = 0
    for gi, (gtitle, entries) in enumerate(groups, 1):
        if not entries:
            continue
        parts.append('<details class="toc-module" open>')
        parts.append(f'<summary data-module-title="{esc(gtitle.lower())}">{esc(gtitle)}</summary>')
        parts.append('<ul class="module-lessons">')
        for e in entries:
            n += 1
            lid = e["id"]
            href = f"/learn/lessons/{lid}/"
            title = f"{n}. {lib.lessons[lid]['title']}"
            cls = " current" if current == href else ""
            pr = ""
            if lid in lib.practice:
                ph = f"/learn/practice/{lid}/"
                pr = a(ph, "Practice", "lesson-practice-link" + (" current" if current == ph else ""))
            parts.append(
                f'<li data-lesson-title="{esc(title.lower())}"><a href="{esc(href)}" class="lesson-link{cls}">'
                f'<span class="lesson-dot"></span><span>{esc(title)}</span></a>{pr}</li>'
            )
        parts.append("</ul>\n</details>")
    parts.append("</nav>")
    return "\n".join(parts)


def lesson_shell(lib: Library, title: str, body: str, *, mid: str | None, current: str, crumbs: list[tuple[str, str]],
                 description: str, mermaid: bool = False, code: bool = False, sim: bool = False) -> str:
    parts = [a(h, esc(t)) for h, t in crumbs[:-1]] + [esc(crumbs[-1][1])]
    return (
        head(title, description, code=code, sim=sim)
        + '<body>\n<div class="shell">\n'
        + sidebar(lib, mid, current)
        + '\n<div class="page">\n<div class="page-top">\n'
        + f'<nav class="breadcrumb" aria-label="Breadcrumb">{" &rsaquo; ".join(parts)}</nav>\n{theme_toggle()}\n</div>\n'
        + f"<main data-pagefind-body>\n{body}\n</main>\n"
        + footer()
        + "</div>\n</div>\n"
        + tail_scripts(mermaid=mermaid, code=code, sim=sim)
    )


# ---------------------------------------------------------------------------------------------------------------------
# Page bodies
# ---------------------------------------------------------------------------------------------------------------------
def attribution(prov: dict) -> str:
    line = f"Generated by {esc(prov['generated_by'])} on {esc(prov['generated_on'])}"
    if prov["reviewed_by"]:
        line += f", reviewed by {esc(prov['reviewed_by'])} on {esc(prov['reviewed_on'])}"
    return f'<p class="attribution">{line}.</p>'


def render_sources(sources: list[dict]) -> str:
    items = []
    for s in sources:
        checked = ""
        v = s.get("verified")
        if v and v.get("checked"):
            checked = f' <span class="domain">checked {esc(v["checked"])}</span>'
        items.append(
            f'<li><span class="kind-badge">{esc(s["kind"])}</span>{ext(s["url"], esc(s["title"]))} '
            f'<span class="domain">({esc(domain_of(s["url"]))})</span>{checked}</li>'
        )
    return f'<ul class="sources-list">{"".join(items)}</ul>'


def render_sections(items: list[dict]) -> str:
    out = []
    for sec in items:
        if sec.get("heading"):
            out.append(f"<h4>{esc(sec['heading'])}</h4>")
        out.append(f"<p>{esc(sec['body'])}</p>")
    return "\n".join(out)


def code_block(b: dict) -> str:
    lang = b["lang"]
    cls = HLJS_LANGS.get(lang.lower(), "plaintext")
    return (f'<span class="code-lang">{esc(lang)}</span>'
            f'<pre><code class="language-{cls}" data-lang="{esc(cls)}">{esc(b["code"])}</code></pre>')


SIM_FALLBACK = ("The simulation needs JavaScript; the steps above describe what it shows. "
                "Simulation engine: Breakscale (MIT, the Breakscale contributors), commit d2c876e0, vendored without its interface, analytics or link store. "
                "Nothing leaves this page.")


def render_sim(lib: Library, l: dict, level: int = 2) -> str:
    """The `sim` field of a lesson: heading, caption, the steps, and the block host the module fills in (never indexed by Pagefind)."""
    sim = l["sim"]
    sc = lib.scenarios[sim["scenario"]]
    h = f"h{level}"
    steps = "".join(f"<li>{esc(st)}</li>" for st in sim["steps"])
    note = f'<p class="muted">Scaled model: {esc(sc["scale_note"])}</p>\n' if sc.get("scale_note") else ""
    return (f'<{h} id="simulate">{esc(sim.get("heading", "Simulate it"))}</{h}>\n<p>{esc(sim["caption"])}</p>\n<ol class="sim-steps">{steps}</ol>\n'
            f'<div class="sim" data-scenario="/learn/scenarios/{esc(sc["id"])}.json" data-pagefind-ignore>{note}<p>{esc(SIM_FALLBACK)}</p></div>')


def render_lesson(lib: Library, l: dict) -> tuple[str, str]:
    lid = l["id"]
    mid, pos, _ = lib.home_of[lid]
    here = f"/learn/lessons/{lid}/"
    body = [f"<h1>{esc(l['title'])}</h1>", attribution(l["provenance"])]
    if l["status"] == "superseded":
        body.append(f'<p class="banner">This lesson is superseded by {a(f"/learn/lessons/{l["superseded_by"]}/", esc(lib.lessons[l["superseded_by"]]["title"]))}.</p>')
    # keys and module
    krow = ["Concept: " + a(f"/learn/keys/{l['primary_key']}/", esc(lib.keys[l["primary_key"]]["display"]))]
    if l["secondary_keys"]:
        krow.append("also covers " + ", ".join(a(f"/learn/keys/{k}/", esc(lib.keys[k]["display"])) for k in l["secondary_keys"]))
    line = " &middot; ".join(krow)
    line += f" &middot; Lesson {pos} of {len(lib.module_lessons[mid])} in " + a(f"/learn/modules/{mid}/", esc(lib.modules[mid]["title"]))
    body.append(f'<p class="key-line">{line} &middot; version {l["version"]}</p>')
    if lid in lib.practice:
        body.append(a(f"/learn/practice/{lid}/", "Practice this", "practice-link-button"))
    if l["subtopics"]:
        items = "".join(f'<li>{a("#" + s["id"], esc(s["title"]))}</li>' for s in l["subtopics"])
        body.append(f'<div class="on-this-page"><p class="otp-title">On this page</p><ul>{items}</ul></div>')
    body.append(f"<p>{esc(l['summary'])}</p>")
    if l["sources"]:
        body.append('<div class="sources-preview"><p class="sources-preview-title">Read more</p>' + render_sources(l["sources"][:3]) + "</div>")
    if l["detail"]:
        body.append(render_sections(l["detail"]))
    if l["in_practice"]:
        body.append("<h2>How it is done in practice</h2>")
        body.append(f"<p>{esc(l['in_practice'])}</p>")
    if "sim" in l:
        body.append(render_sim(lib, l))
    if l["technologies"]:
        tags = "".join(f"<span>{esc(t)}</span>" for t in l["technologies"])
        body.append(f'<h2>Technologies</h2>\n<div class="tech-tags">{tags}</div>')
    has_diagram = bool(l["diagram"])
    if has_diagram:
        src = esc(l["diagram"]["source"])
        body.append('<h2>Diagram</h2>\n<div class="mermaid-wrap">'
                    f'<pre class="mermaid">{src}</pre><pre class="mermaid-fallback">{src}</pre></div>')
    if l["code"]:
        body.append("<h2>Code</h2>")
        body += [code_block(b) for b in l["code"]]
    if l["subtopics"]:
        body.append("<h2>Subtopics</h2>")
        for s in l["subtopics"]:
            body.append(f'<h3 id="{esc(s["id"])}">{esc(s["title"])}</h3>')
            body.append(render_sections(s["body"]))
    body.append("<h2>Sources</h2>")
    body.append(render_sources(l["sources"]))
    if l["related"]:
        rel = "".join(f'<li>{a(f"/learn/lessons/{r}/", esc(lib.lessons[r]["title"]))}</li>' for r in l["related"])
        body.append(f'<h2>Related lessons</h2>\n<ul class="related-list">{rel}</ul>')
    if lid in lib.practice:
        body.append(a(f"/learn/practice/{lid}/", "Practice this", "practice-link-button practice-link-button-end"))
    ids = lib.module_lessons[mid]
    i = pos - 1
    prev_ = a(f"/learn/lessons/{ids[i-1]}/", esc(lib.lessons[ids[i-1]]["title"])) if i > 0 else "<span></span>"
    next_ = a(f"/learn/lessons/{ids[i+1]}/", esc(lib.lessons[ids[i+1]]["title"])) if i + 1 < len(ids) else "<span></span>"
    body.append(f'<div class="prevnext">{prev_}{next_}</div>')
    crumbs = [("/learn/", "Learning center"), (f"/learn/modules/{mid}/", lib.modules[mid]["title"]), (here, l["title"])]
    code = bool(l["code"])
    page = lesson_shell(lib, f"{l['title']} - Learning center", "\n".join(body), mid=mid, current=here, crumbs=crumbs,
                        description=l["summary"][:200], mermaid=has_diagram, code=code, sim="sim" in l)
    return here, page


# --- design exercises (kind "design-exercise"; the system design module, outline section 6) -------------------------------
def render_table(t: dict) -> str:
    head_ = "".join(f"<th>{esc(c)}</th>" for c in t["columns"])
    rows = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in t["rows"])
    return f"<table><thead><tr>{head_}</tr></thead><tbody>{rows}</tbody></table>"


def exercise_attribution(prov: dict) -> str:
    """The attribution line of a hand-written lesson names its author field verbatim (deploy.md section 2 shape, no 'through GigAI')."""
    line = f"Generated by {esc(prov['generated_by'])} on {esc(prov['generated_on'])}"
    if prov["reviewed_by"]:
        line += f", reviewed by {esc(prov['reviewed_by'])} on {esc(prov['reviewed_on'])}"
    return f'<p class="attribution">{line}.</p>'


def render_exercise(lib: Library, l: dict) -> tuple[str, str]:
    """A design exercise page: prompt, constraints, clarifying questions, the reference answer in its fixed sections (one
    Mermaid flowchart), the rubric by level, the interview and design-doc frames, depth notes, sources, related lessons."""
    lid, ex = l["id"], l["exercise"]
    here = f"/learn/lessons/{lid}/"
    mid, _, entry = lib.home_of[lid]
    mod_here = f"/learn/modules/{mid}/"
    body = [f"<h1>{esc(l['title'])}</h1>", exercise_attribution(l["provenance"])]
    krow = ["Concept: " + a(f"/learn/keys/{l['primary_key']}/", esc(lib.keys[l["primary_key"]]["display"]))]
    if l["secondary_keys"]:
        krow.append("also covers " + ", ".join(a(f"/learn/keys/{k}/", esc(lib.keys[k]["display"])) for k in l["secondary_keys"]))
    mod = lib.modules[mid]
    if entry.get("part"):
        part_title = next(p["title"] for p in mod["parts"] if p["id"] == entry["part"])
        krow.append(f"Part {esc(entry['part'])} ({esc(part_title)}) of the " + a(mod_here, esc(mod["title"]) + " module"))
    body.append(f'<p class="key-line">{" &middot; ".join(krow)} &middot; design exercise &middot; version {l["version"]}</p>')
    otp = [("prompt", "The prompt"), ("constraints", "Constraints and numbers"), ("clarifying-questions", "Clarifying questions worth asking"),
           ("reference-answer", "Reference answer")] + [(sec["id"], sec["title"]) for sec in ex["reference_answer"]] + [
           ("rubric", "Self-check rubric"), ("interview-frame", "The 45-minute interview frame"), ("design-doc-frame", "The design-doc frame"),
           ("depth", "Depth notes"), ("sources", "Sources"), ("related", "Related lessons")]
    if "sim" in l:
        otp.insert(otp.index(("rubric", "Self-check rubric")), ("simulate", l["sim"].get("heading", "Simulate it")))
    body.append('<div class="on-this-page"><p class="otp-title">On this page</p><ul>' + "".join(f'<li>{a("#" + i, esc(t))}</li>' for i, t in otp) + "</ul></div>")
    body.append(f"<p>{esc(l['summary'])}</p>")
    body.append('<p class="muted">Attempt the design from the prompt, the constraints and the questions before reading the reference answer.</p>')
    body.append(f'<h2 id="prompt">The prompt</h2>\n<p>{esc(ex["prompt"])}</p>')
    body.append('<h2 id="constraints">Constraints and numbers</h2>\n' + render_sections(ex["constraints"]))
    body.append('<h2 id="clarifying-questions">Clarifying questions worth asking</h2>\n<ul>'
                + "".join(f'<li><strong>{esc(q["question"])}</strong> {esc(q["answer"])}</li>' for q in ex["clarifying_questions"]) + "</ul>")
    body.append('<h2 id="reference-answer">Reference answer</h2>')
    has_diagram = False
    for sec in ex["reference_answer"]:
        body.append(f'<h3 id="{esc(sec["id"])}">{esc(sec["title"])}</h3>')
        body.append(render_sections(sec["body"]))
        if sec.get("steps"):
            body.append("<ol>" + "".join(f"<li>{esc(st)}</li>" for st in sec["steps"]) + "</ol>")
        if sec.get("diagram"):
            has_diagram = True
            src = esc(sec["diagram"]["source"])
            body.append(f'<div class="mermaid-wrap"><pre class="mermaid">{src}</pre><pre class="mermaid-fallback">{src}</pre></div>')
            if sec["diagram"].get("legend"):
                body.append(f'<p class="muted">{esc(sec["diagram"]["legend"])}</p>')
        if sec.get("table"):
            body.append(render_table(sec["table"]))
        if sec["id"] == "scaling-and-the-bottleneck" and "sim" in l:
            body.append(render_sim(lib, l, level=3))
    body.append('<h2 id="rubric">Self-check rubric</h2>\n<p class="muted">Read, not scored: find the level your answer reached.</p>')
    for lvl, name in (("L1", "L1, mid-level: applies"), ("L2", "L2, senior: chooses with numbers and defends"), ("L3", "L3, staff: sets the constraint and judges")):
        body.append(f"<h3>{esc(name)}</h3><ul>" + "".join(f"<li>{esc(x)}</li>" for x in ex["rubric"][lvl]) + "</ul>")
    body.append('<h2 id="interview-frame">The 45-minute interview frame</h2>\n<ul>'
                + "".join(f'<li><strong>{esc(f["time"])}</strong> {esc(f["text"])}</li>' for f in ex["interview_frame"]) + "</ul>")
    body.append('<h2 id="design-doc-frame">The design-doc frame</h2>\n<ul>'
                + "".join(f'<li><strong>{esc(f["section"])}.</strong> {esc(f["text"])}</li>' for f in ex["design_doc_frame"]) + "</ul>")
    body.append('<h2 id="depth">Depth notes</h2>\n<ul>' + "".join(f'<li><strong>{lvl}.</strong> {esc(ex["depth_notes"][lvl])}</li>' for lvl in ("L1", "L2", "L3")) + "</ul>")
    body.append('<h2 id="sources">Sources</h2>')
    body.append(render_sources(l["sources"]))
    if l["related"]:
        items = []
        for r in l["related"]:
            if r in lib.lessons:
                items.append(f'<li>{a(f"/learn/lessons/{r}/", esc(lib.lessons[r]["title"]))}</li>')
            else:  # an outlined system design lesson without a page yet: named, not linked
                items.append(f'<li>{esc(lib.planned[r]["title"])} <code>{esc(r)}</code> <span class="status">planned</span></li>')
        body.append(f'<h2 id="related">Related lessons</h2>\n<ul class="related-list">{"".join(items)}</ul>')
    crumbs = [("/learn/", "Learning center"), (mod_here, mod["title"]), (here, l["title"])]
    page = lesson_shell(lib, f"{l['title']} - Learning center", "\n".join(body), mid=mid, current=here, crumbs=crumbs,
                        description=l["summary"][:200], mermaid=has_diagram, code=False, sim="sim" in l)
    return here, page


def render_practice_steps(steps: list[dict]) -> str:
    items = []
    for st in sorted(steps, key=lambda s: s["n"]):
        src = st["source"]
        v = src.get("verified") or {}
        chk = f", checked {esc(v['checked'])}" if v.get("checked") else ""
        parts = [f'<p class="practice-step-title"><span class="path-number">{st["n"]}.</span> {esc(st["do"])}</p>']
        if st.get("why"):
            parts.append(f'<p class="practice-step-why">{esc(st["why"])}</p>')
        parts.append(f'<p class="practice-step-source">Explained in: {ext(src["url"], esc(src["title"]) + " (" + esc(domain_of(src["url"])) + ")")}{chk}</p>')
        if st["done_when"]:
            parts.append(f'<p class="practice-step-done">Done when: {esc(st["done_when"])}</p>')
        items.append(f"<li>{''.join(parts)}</li>")
    return f'<ul class="practice-steps">{"".join(items)}</ul>'


MODEL_WRITTEN_NOTE = "Written by a model for this lesson, not by a person: read it as one way to do it, not the only one."


def written_list(lines: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{esc(line)}</li>" for line in lines) + "</ul>"


def tick_list(lines: list[str]) -> str:
    """A list the reader ticks mentally: a plain [ ] in front of every line (no script, no form control)."""
    return '<ul class="practice-steps">' + "".join(
        f'<li><p class="practice-step-title"><span class="path-number">[&nbsp;]</span> {esc(line)}</p></li>' for line in lines) + "</ul>"


def written_sections(sections: list[dict], text_key: str) -> str:
    return "".join(f"<h3>{esc(s['title'])}</h3><p>{esc(s[text_key])}</p>" for s in sections)


def written_body(l: dict, pr: dict) -> list[str]:
    """The page body of a case or artifact practice (the product's variants, gigai.scout.learning_render.render_case_page and
    render_artifact_page): sections, a tick list, the model line, the attribution; no tool, no steps, no 'Done when'."""
    h2 = '<h2 class="practice-section-title">{}</h2>'.format
    if pr["kind"] == "case":
        return [
            f"<h1>Case exercise: {esc(l['title'])}</h1>", attribution(pr["provenance"]),
            '<p class="practice-lead">A case, not a tool: attempt it on paper before you open the reference answer.</p>',
            h2("Scenario"), f"<p>{esc(pr['scenario'])}</p>",
            h2("Constraints and numbers"), written_list(pr["constraints"]),
            h2("Deliverable"), f"<p>{esc(pr['deliverable'])}</p>",
            h2("Reference answer"), f'<p class="muted">{esc(MODEL_WRITTEN_NOTE)}</p>',
            "<details><summary>Show the reference answer</summary>", written_sections(pr["reference_answer"], "body"), "</details>",
            h2("Check your answer"),
            '<p class="muted">Read each line and tick it in your head: your answer either does it or it does not.</p>',
            tick_list(pr["rubric"]),
            h2("Common mistakes"), written_list(pr["common_mistakes"]),
        ]
    ex = pr["reference_example"]
    return [
        f"<h1>Write a {esc(pr['artifact_name'])}: {esc(l['title'])}</h1>", attribution(pr["provenance"]),
        '<p class="practice-lead">An artifact, not a tool: fill the template for a case of your own, then review it against the checklist.</p>',
        h2("Template"), written_sections(pr["template"], "prompt"),
        h2("Example, filled in"), f'<p class="muted">{esc(MODEL_WRITTEN_NOTE)}</p>',
        f"<p><strong>Situation (made up):</strong> {esc(ex['situation'])}</p>",
        "<details><summary>Show the filled example</summary>", written_sections(ex["sections"], "body"), "</details>",
        h2("Review checklist"), tick_list(pr["review_checklist"]),
    ]


def render_practice(lib: Library, pr: dict) -> tuple[str, str]:
    lid = pr["lesson"]
    l = lib.lessons[lid]
    mid = lib.home_of[lid][0]
    here = f"/learn/practice/{lid}/"
    if pr.get("kind", "tool") != "tool":
        body = written_body(l, pr)
        body.append(f'<p class="practice-back-link">{a(f"/learn/lessons/{lid}/", "Back to " + esc(l["title"]))}</p>')
        crumbs = [("/learn/", "Learning center"), (f"/learn/modules/{mid}/", lib.modules[mid]["title"]),
                  (f"/learn/lessons/{lid}/", l["title"]), (here, "Practice")]
        what = "Case exercise" if pr["kind"] == "case" else "Artifact exercise"
        page = lesson_shell(lib, f"{what}: {l['title']} - Learning center", "\n".join(body), mid=mid, current=here, crumbs=crumbs,
                            description=f"{what} for {l['title']}, written by a model for this lesson.")
        return here, page
    body = [f"<h1>Practice: {esc(l['title'])}</h1>", attribution(pr["provenance"])]
    lead = []
    if pr["tool"]:
        lead.append("Main tool: " + (a(f"/learn/keys/{pr['tool_key']}/", esc(pr["tool"])) if pr["tool_key"] else esc(pr["tool"])))
    if pr["why_this_tool"]:
        lead.append(esc(pr["why_this_tool"]))
    if pr["alternatives"]:
        lead.append("Alternatives: " + esc(pr["alternatives"]))
    if lead:
        body.append(f'<p class="practice-lead">{" &middot; ".join(lead)}</p>')
    body.append(f'<p class="key-line">Every step links into the tool\'s own documentation; links were checked on {esc(pr["verified"]["checked"])} &middot; version {pr["version"]}</p>')
    if pr["setup"]:
        body.append('<h2 class="practice-section-title">Setup (one time)</h2>')
        body.append(render_practice_steps(pr["setup"]))
    body.append('<h2 class="practice-section-title">Steps</h2>')
    body.append(render_practice_steps(pr["steps"]))
    body.append(f'<p class="practice-back-link">{a(f"/learn/lessons/{lid}/", "Back to " + esc(l["title"]))}</p>')
    crumbs = [("/learn/", "Learning center"), (f"/learn/modules/{mid}/", lib.modules[mid]["title"]),
              (f"/learn/lessons/{lid}/", l["title"]), (here, "Practice")]
    page = lesson_shell(lib, f"Practice: {l['title']} - Learning center", "\n".join(body), mid=mid, current=here, crumbs=crumbs,
                        description=f"Hands-on practice path for {l['title']}: {pr['tool']}.")
    return here, page


def key_chips(lib: Library, keys: list[str]) -> str:
    return '<ul class="chips">' + "".join(f'<li>{a(f"/learn/keys/{k}/", esc(lib.keys[k]["display"]))}</li>' for k in keys) + "</ul>"


def first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]


def module_counts(lib: Library, row: dict) -> str:
    m = lib.modules[row["id"]]
    total = len(m["lessons"])
    pub = row["lessons_published"]
    n_prac = sum(1 for lid in lib.module_lessons[row["id"]] if lid in lib.practice)
    chips = [f"{pub} lessons" if pub == total else f"{pub} of {total} lessons published"]
    if n_prac:
        chips.append(f"{n_prac} practice paths")
    return '<ul class="chips">' + "".join(f"<li>{esc(c)}</li>" for c in chips) + "</ul>"


def module_cards(lib: Library) -> str:
    """One card per module of modules/index.json, in index order."""
    out = ['<ul class="cards">']
    for row in lib.module_index:
        out.append(f'<li class="card"><h3>{a(f"/learn/modules/{row["id"]}/", esc(row["title"]))}</h3><p>{esc(row["summary"])}</p>'
                   f"{module_counts(lib, row)}</li>")
    out.append("</ul>")
    return "\n".join(out)


def render_home(lib: Library) -> tuple[str, str]:
    body = [
        "<h1>Learn what the job asks for</h1>",
        '<p class="muted">A library of lessons and hands-on practice paths, keyed by concept and grouped in topic modules. '
        "Scout builds your own pathway from them on your computer. "
        "Everything here is public and generalised: no job postings, no companies, no personal data.</p>",
        '<form class="search" role="search" action="/learn/search/" method="get">'
        '<label for="q" hidden>Search lessons</label>'
        '<input id="q" name="q" type="search" placeholder="Search lessons, concepts, technologies" autocomplete="off">'
        '<button type="submit">Search</button></form>',
        '<p class="muted">Search runs in your browser from a prebuilt index. Nothing you type leaves this page.</p>',
        f'<h2>{a("/learn/modules/", "Modules")}</h2>', module_cards(lib),
        "<h2>How this library works</h2>",
        "<p>Lessons are keyed by concept. A module is one topic's lessons in teaching order; every lesson sits in exactly one module. "
        f"Links to outside documentation are re-checked every week. Site version {esc(lib.site['site_version'])}; see the {a('/learn/changelog/', 'changelog')}.</p>",
    ]
    return "/learn/", site_page("Learning center", "\n".join(body), current="learn", description="A public library of lessons and practice paths, grouped in topic modules and organised by concept. Static pages, no tracking.")


def render_modules_index(lib: Library) -> tuple[str, str]:
    n = sum(r["lessons_published"] for r in lib.module_index)
    body = ["<h1>Modules</h1>",
            f'<p class="muted">{len(lib.module_index)} topic modules, {n} lessons. A module lists one topic\'s lessons in teaching order; every lesson sits in exactly one module.</p>',
            module_cards(lib)]
    return "/learn/modules/", site_page("Modules - Learning center", "\n".join(body), current="modules",
                                        crumbs=[("/learn/", "Learning center"), ("/learn/modules/", "Modules")],
                                        description="The topic modules of the learning center and their lessons.")


def render_module(lib: Library, m: dict) -> tuple[str, str]:
    here = f"/learn/modules/{m['id']}/"
    n_all = len(m["lessons"])
    n_pub = sum(1 for e in m["lessons"] if e["status"] == "published")
    body = [f"<h1>{esc(m['title'])}</h1>"]
    if n_pub == 0:
        body.append(f'<p class="banner">Planned. These {n_all} lessons are outlined and not yet written; none of them has a page.</p>')
    elif n_pub < n_all:
        body.append(f'<p class="banner">In progress. {n_pub} of these {n_all} lessons are published; the other {n_all - n_pub} are outlined and not yet written.</p>')
    body.append(f"<p>{esc(m['summary'])}</p>")
    if m.get("intro"):
        body.append(f"<p>{esc(m['intro'])}</p>")

    def entry(e: dict) -> str:
        if e["status"] == "published":
            lid = e["id"]
            pr = f' &middot; {a(f"/learn/practice/{lid}/", "Practice")}' if lid in lib.practice else ""
            return (f'<li>{a(f"/learn/lessons/{lid}/", esc(lib.lessons[lid]["title"]))}{pr}'
                    f'<p class="muted">{esc(first_sentence(lib.lessons[lid]["summary"]))}</p></li>')
        return f'<li>{esc(e["title"])}<code>{esc(e["id"])}</code> <span class="status">planned</span></li>'
    if m.get("parts"):
        for part in m["parts"]:
            ls = [e for e in m["lessons"] if e["part"] == part["id"]]
            body.append(f"<h2>Part {esc(part['id'])}. {esc(part['title'])} ({len(ls)} lessons)</h2>")
            body.append('<ul class="planned-list">' + "".join(entry(e) for e in ls) + "</ul>")
    else:
        body.append(f"<h2>Lessons ({n_all})</h2>")
        body.append('<ul class="planned-list">' + "".join(entry(e) for e in m["lessons"]) + "</ul>")
    if m.get("changelog"):
        body.append("<h2>Changes</h2>")
        body.append("<ul>" + "".join(f"<li>Version {c['version']}, {esc(c['date'])}: {esc(c['change'])}</li>" for c in m["changelog"]) + "</ul>")
    return here, site_page(f"{m['title']} - Learning center", "\n".join(body), current="modules",
                           crumbs=[("/learn/", "Learning center"), ("/learn/modules/", "Modules"), (here, m["title"])], description=m["summary"][:200])


def render_key(lib: Library, k: dict) -> tuple[str, str]:
    key = k["key"]
    here = f"/learn/keys/{key}/"
    body = [f"<h1>{esc(k['display'])}</h1>",
            f'<p class="status">{esc(key)} &middot; {esc(lib.areas[k["area"]])} &middot; {esc(k["category"])}</p>']
    if k["aliases"]:
        body.append(f'<p class="muted">Also known as: {esc(", ".join(k["aliases"]))}.</p>')
    if k["parent"]:
        body.append(f'<p>Part of: {a(f"/learn/keys/{k["parent"]}/", esc(lib.keys[k["parent"]]["display"]))}</p>')
    kids = sorted(lib.children.get(key, []))
    if kids:
        body.append("<h2>Narrower concepts</h2>" + key_chips(lib, kids))
    prim = [l for l in lib.lessons_by_key.get(key, []) if lib.lessons[l]["primary_key"] == key]
    also = [l for l in lib.lessons_by_key.get(key, []) if l not in prim]
    def lesson_list(ids):
        return "<ul>" + "".join(
            f'<li>{a(f"/learn/lessons/{i}/", esc(lib.lessons[i]["title"]))} &middot; module '
            f'{a(f"/learn/modules/{lib.home_of[i][0]}/", esc(lib.modules[lib.home_of[i][0]]["title"]))}</li>' for i in sorted(ids)) + "</ul>"
    if prim:
        body.append("<h2>The lesson for this</h2>" + lesson_list(prim))
    if also:
        body.append("<h2>Also covered in</h2>" + lesson_list(also))
    prac = [p["lesson"] for p in lib.practice.values() if p.get("tool_key") == key]
    if prac:
        body.append("<h2>Practice paths with this tool</h2><ul>" + "".join(f'<li>{a(f"/learn/practice/{i}/", esc("Practice: " + lib.lessons[i]["title"]))}</li>' for i in sorted(prac)) + "</ul>")
    if not (prim or also or prac):
        body.append('<p class="muted">No lesson uses this concept yet.</p>')
    return here, site_page(f"{k['display']} - Learning center", "\n".join(body), current="learn",
                           crumbs=[("/learn/", "Learning center"), (here, k["display"])],
                           description=f"{k['display']}: where this concept appears in the learning center.")


def render_changelog(lib: Library) -> tuple[str, str]:
    rows = "".join(
        f"<tr><td>{esc(e['date'])}</td><td>{esc(e['site_version'])}</td><td>{esc(e['kind'])} {esc(e['id'])} v{e['version']}</td><td>{esc(e['change'])}</td></tr>"
        for e in sorted(lib.changelog, key=lambda e: (e["date"], e["site_version"]), reverse=True)
    )
    body = ["<h1>Changelog</h1>", f'<p class="muted">Site version {esc(lib.site["site_version"])}, concept keys version {lib.site["concept_keys_version"]}, '
            f'built from {esc(lib.site["built_from"])}.</p>',
            f"<table><thead><tr><th>Date</th><th>Site</th><th>What</th><th>Change</th></tr></thead><tbody>{rows}</tbody></table>"]
    return "/learn/changelog/", site_page("Changelog - Learning center", "\n".join(body), current="learn", indexed=False,
                                          crumbs=[("/learn/", "Learning center"), ("/learn/changelog/", "Changelog")], description="Every change of the learning center.")


def render_search(lib: Library) -> tuple[str, str]:
    body = [
        "<h1>Search</h1>",
        '<form class="search" role="search" action="/learn/search/" method="get"><label for="search-q" hidden>Search</label>'
        '<input id="search-q" name="q" type="search" placeholder="Search lessons, concepts, technologies" autocomplete="off">'
        '<button type="submit">Search</button></form>',
        '<p id="result-count" aria-live="polite"></p>',
        '<div id="search"></div>',
        '<p class="muted">The index is built when the site is built and runs in your browser; nothing you type leaves this page.</p>',
    ]
    page = site_page("Search - Learning center", "\n".join(body), current="search", indexed=False,
                     crumbs=[("/learn/", "Learning center"), ("/learn/search/", "Search")], description="Search the learning center.",
                     extra_scripts=("/learn/pagefind/pagefind-ui.js", "/_assets/search.js"))
    page = page.replace('<link rel="stylesheet" href="/_assets/site.css">', '<link rel="stylesheet" href="/_assets/site.css">\n<link rel="stylesheet" href="/learn/pagefind/pagefind-ui.css">')
    return "/learn/search/", page


def render_landing(lib: Library) -> tuple[str, str]:
    body = [
        "<h1>Scout</h1>",
        '<p class="muted">Scout is a job search assistant that runs on your own machine: it follows company job boards, assesses postings against your resume, '
        "drafts answers and tailors a resume, and keeps everything local. It is part of GigAI, which is free and open source.</p>",
        '<ul class="cards">',
        f'<li class="card"><h3>{ext(GIGAI_DOCS, "Scout / GigAI")}</h3><p>Install, documentation and the source. Runs with your own model subscription; '
        "nothing of yours leaves your machine except the model calls you approve.</p>"
        '<ul class="chips"><li>Install</li><li>Docs</li><li>Source</li></ul></li>',
        f'<li class="card module"><h3>{a("/learn/", "Learning center")}</h3><p>Public lessons and hands-on practice paths, keyed by concept and grouped in topic modules. '
        "Scout builds your own pathway from them on your computer.</p>"
        '<ul class="chips"><li>Topic modules</li><li>Practice paths</li><li>No account needed</li></ul></li>',
        "</ul>",
    ]
    return "/", site_page("Scout", "\n".join(body), current="scout", brand="scout", indexed=False,
                          description="Scout: a job search assistant that runs on your own machine, and a public learning center. Static pages, no tracking.")


def render_404(lib: Library) -> tuple[str, str]:
    body = [
        "<h1>Page not found</h1>",
        "<p>There is no page at this address. Lessons, practice paths and modules live under "
        f'{a("/learn/", "the learning center")}; try the search:</p>',
        '<form class="search" role="search" action="/learn/search/" method="get"><label for="q" hidden>Search</label>'
        '<input id="q" name="q" type="search" placeholder="Search lessons, concepts, technologies" autocomplete="off">'
        '<button type="submit">Search</button></form>',
    ]
    return "404.html", site_page("Page not found", "\n".join(body), indexed=False, description="Page not found.")


# ---------------------------------------------------------------------------------------------------------------------
# Output, checks
# ---------------------------------------------------------------------------------------------------------------------
class Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.refs: list[tuple[str, str, str | None]] = []  # (tag, path, fragment)
        self.ids: set[str] = set()
        self.dup_ids: set[str] = set()
        self.external: list[tuple[str, bool]] = []
        self.inline_scripts = 0
        self.on_attrs: list[str] = []
        self.stylesheets = 0
        self.scenarios: list[str] = []

    def handle_starttag(self, tag, attrs):
        am = {k: (v or "") for k, v in attrs}
        for n in am:
            if n.lower().startswith("on"):
                self.on_attrs.append(n.lower())
        if am.get("data-scenario"):
            self.scenarios.append(am["data-scenario"])
        if am.get("id"):
            if am["id"] in self.ids:
                self.dup_ids.add(am["id"])
            self.ids.add(am["id"])
        if tag == "a" and am.get("href"):
            h = am["href"]
            if h.startswith(("http://", "https://")):
                self.external.append((h, am.get("target") == "_blank" and "noopener" in am.get("rel", "")))
            elif h.startswith(("mailto:", "javascript:", "data:")):
                self.refs.append((tag, h, "!bad"))
            else:
                p, _, f = h.partition("#")
                self.refs.append((tag, p, f or None))
        elif tag == "script":
            if "src" not in am:
                self.inline_scripts += 1
            else:
                self.refs.append((tag, am["src"], None))
        elif tag == "link" and am.get("href"):
            # the site's own sheet is the one stylesheet; the shipped highlighter's theme sheets (code pages) and
            # Pagefind's UI sheet (search page) and the simulator block's sheet are third-party files of the same origin and not counted
            if am.get("rel") == "stylesheet" and not am["href"].startswith(("/_assets/hljs/", "/_assets/sim/", "/learn/pagefind/")):
                self.stylesheets += 1
            self.refs.append((tag, am["href"], None))
        elif tag == "form" and am.get("action"):
            self.refs.append((tag, am["action"].partition("?")[0], None))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def resolve(page_url: str, ref: str) -> str:
    """Page URL (/x/y/) and a reference -> an absolute path."""
    if ref.startswith("/"):
        return ref
    base = page_url if page_url.endswith("/") else page_url.rsplit("/", 1)[0] + "/"
    parts = (base + ref).split("/")
    out: list[str] = []
    for p in parts:
        if p == "..":
            if out:
                out.pop()
        elif p and p != ".":
            out.append(p)
    return "/" + "/".join(out)


def file_for(site: Path, path: str) -> Path | None:
    rel = path.lstrip("/")
    cand = site / rel
    if path.endswith("/") or rel == "":
        cand = site / rel / "index.html"
    return cand if cand.is_file() else None


def audit(site: Path) -> list[str]:
    problems: list[str] = []
    pages = sorted(site.rglob("*.html"))
    info: dict[str, Collector] = {}
    for p in pages:
        rel = p.relative_to(site).as_posix()
        url = "/" + rel[: -len("index.html")] if rel.endswith("index.html") else "/" + rel
        c = Collector()
        c.feed(p.read_text(encoding="utf-8"))
        info[url] = c
    for url, c in info.items():
        if c.inline_scripts:
            problems.append(f"{url}: {c.inline_scripts} inline <script> block(s)")
        for n in sorted(set(c.on_attrs)):
            problems.append(f"{url}: {n}= attribute")
        for d in sorted(c.dup_ids):
            problems.append(f"{url}: duplicate id {d!r}")
        for href, ok in c.external:
            if not ok:
                problems.append(f"{url}: external link {href} without target=_blank rel=noopener")
            if not href.startswith("https://"):
                problems.append(f"{url}: external link {href} is not https")
        for sc in c.scenarios:
            if not (site / sc.lstrip("/")).is_file():
                problems.append(f"{url}: data-scenario {sc} does not exist in the built site")
        if c.scenarios and not any(ref == SIM_JS for _, ref, _ in c.refs):
            problems.append(f"{url}: a simulator block without the module script {SIM_JS}")
        if c.stylesheets != 1:
            problems.append(f"{url}: {c.stylesheets} site stylesheets (expected one)")
        for tag, ref, frag in c.refs:
            if frag == "!bad":
                problems.append(f"{url}: forbidden link scheme {ref}")
                continue
            if re.match(r"(?i)^(?:https?:)?//", ref):
                problems.append(f"{url}: <{tag}> points to another origin: {ref}")
                continue
            target = resolve(url, ref) if ref else url
            if target.startswith(GENERATED_LATER):
                continue
            if tag in ("a", "form") and target.endswith("/") or target.endswith(".html"):
                tkey = target[: -len("index.html")] if target.endswith("/index.html") else target
                if tkey not in info:
                    problems.append(f"{url}: <{tag}> target {ref or '#' + (frag or '')} does not resolve to a page")
                    continue
                if frag and frag not in info[tkey].ids:
                    problems.append(f"{url}: anchor #{frag} does not resolve to an id in {tkey}")
            elif file_for(site, target) is None and not (site / target.lstrip("/")).is_file():
                problems.append(f"{url}: <{tag}> file {ref} does not exist")
    return sorted(p for p in problems if p)


def glyph_check(site: Path) -> list[str]:
    problems = []
    for p in sorted(site.rglob("*.html")):
        bad = sorted({ch for ch in p.read_text(encoding="utf-8")
                      if ord(ch) >= 128 and ch not in ALLOWED_EXTRA and not 0xA0 <= ord(ch) <= 0xFF})
        if bad:
            problems.append(f"{p.relative_to(site).as_posix()}: disallowed glyph(s) {', '.join(f'U+{ord(c):04X}' for c in bad[:8])}")
    return problems


def write(site: Path, url: str, text: str, written: dict[str, int]) -> None:
    if url == "404.html":
        path = site / "404.html"
    else:
        path = site / url.lstrip("/") / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    if len(data) > MAX_HTML_BYTES:
        raise BuildError(f"{url}: {len(data)} bytes exceeds the page cap")
    path.write_bytes(data)
    written[url] = len(data)


def sitemap(lib: Library, urls: list[str]) -> str:
    last = {}
    for lid, l in lib.lessons.items():
        last[f"/learn/lessons/{lid}/"] = l["changelog"][-1]["date"]
    for lid, pr in lib.practice.items():
        last[f"/learn/practice/{lid}/"] = pr["changelog"][-1]["date"]
    for mid, m in lib.modules.items():
        if m.get("changelog"):
            last[f"/learn/modules/{mid}/"] = m["changelog"][-1]["date"]
    default = lib.site["updated"]
    rows = "".join(f"<url><loc>{ORIGIN}{esc(u)}</loc><lastmod>{last.get(u, default)}</lastmod></url>\n" for u in sorted(urls))
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{rows}</urlset>\n'


def build(content: Path, out: Path) -> dict:
    lib = Library(content)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    written: dict[str, int] = {}
    pages: list[tuple[str, str]] = [render_landing(lib), render_home(lib), render_modules_index(lib), render_changelog(lib),
                                    render_search(lib), render_404(lib)]
    pages += [render_module(lib, m) for m in lib.modules.values()]
    pages += [render_exercise(lib, l) if l.get("kind") == "design-exercise" else render_lesson(lib, l) for l in lib.lessons.values()]
    pages += [render_practice(lib, p) for p in lib.practice.values()]
    pages += [render_key(lib, k) for k in lib.keys.values()]
    for url, text in pages:
        write(out, url, text, written)
    # assets, once, at the root (shared by / and /learn/)
    assets = out / "_assets"
    assets.mkdir()
    (assets / "site.css").write_text((ROOT / "assets/course.css").read_text(encoding="utf-8") + "\n" + (ROOT / "assets/site-extra.css").read_text(encoding="utf-8"), encoding="utf-8")
    for name in ("course.js", "theme-init.js", "search.js", "favicon.svg"):
        shutil.copy2(ROOT / "assets" / name, assets / name)
    for d in ("mermaid", "hljs"):
        shutil.copytree(ROOT / "assets" / d, assets / d)
    # the simulator: the block, its sheet and the licence travel together; engine.js (for the headless runner only) stays in the repo
    (assets / "sim").mkdir()
    for name in ("sim.js", "sim.css", "LICENSE.txt", "UPSTREAM.txt"):
        shutil.copy2(ROOT / "assets" / "sim" / name, assets / "sim" / name)
    if lib.scenarios:
        (out / "learn" / "scenarios").mkdir(parents=True, exist_ok=True)
        for sid in lib.scenarios:
            shutil.copy2(content / "scenarios" / f"{sid}.json", out / "learn" / "scenarios" / f"{sid}.json")
    for f in (ROOT / "static").iterdir():
        shutil.copy2(f, out / f.name)
    urls = [u for u in written if u != "404.html"]
    (out / "sitemap.xml").write_text(sitemap(lib, urls), encoding="utf-8")

    problems = glyph_check(out) + audit(out) + scan.scan_built(out)
    total_html = sum(p.stat().st_size for p in out.rglob("*.html"))
    files = [p for p in out.rglob("*") if p.is_file()]
    if total_html > MAX_SITE_HTML_BYTES:
        problems.append(f"HTML total {total_html} bytes exceeds the cap {MAX_SITE_HTML_BYTES}")
    if len(files) > MAX_FILES:
        problems.append(f"{len(files)} files exceed {MAX_FILES}")
    for p in files:
        if p.stat().st_size > MAX_FILE_BYTES:
            problems.append(f"{p.relative_to(out)}: larger than 25 MiB")
    if problems:
        raise BuildError("build checks failed:\n  " + "\n  ".join(problems[:60]))
    kinds = {"lessons": len(lib.lessons), "practice": len(lib.practice), "modules": len(lib.modules),
             "keys": len(lib.keys), "html pages": len(written), "files": len(files), "html bytes": total_html}
    return kinds


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--content", type=Path, default=ROOT / "content")
    ap.add_argument("--out", type=Path, default=ROOT / "site")
    args = ap.parse_args()
    try:
        k = build(args.content, args.out)
    except BuildError as e:
        print(f"build: FAILED: {e}", file=sys.stderr)
        return 1
    print("build: ok; " + ", ".join(f"{n} {v}" for n, v in k.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
