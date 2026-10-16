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


# The module sidebar's lesson list is a <details> that is closed below the stacking breakpoint (820px, course.css) and always shown above it; no JavaScript.
SIDEBAR_CSS = """
nav.sidebar details.sidebar-disclosure > summary { cursor: pointer; font-weight: 600; padding: 0.3rem 0; }
@media (min-width: 821px) {
  /* Wide screens: the list is always shown. Only browsers that can force the closed details' content visible
     (::details-content, Chrome 131+, Safari 18.4+) hide the summary; older ones keep it as a clickable heading. */
  @supports selector(::details-content) {
    nav.sidebar details.sidebar-disclosure > summary { display: none; }
    nav.sidebar details.sidebar-disclosure::details-content { content-visibility: visible; display: block; }
  }
}
"""

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
    # closed on narrow screens (site-extra.css shows the list and hides the summary above the stacking breakpoint)
    parts.append('<details class="sidebar-disclosure">\n<summary>Lessons in this module</summary>')
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
    parts.append("</details>")
    parts.append("</nav>")
    return "\n".join(parts)


def lesson_shell(lib: Library, title: str, body: str, *, mid: str | None, current: str, crumbs: list[tuple[str, str]],
                 description: str, mermaid: bool = False, code: bool = False, sim: bool = False, flow: bool = False,
                 concept_v2: bool = False) -> str:
    parts = [a(h, esc(t)) for h, t in crumbs[:-1]] + [esc(crumbs[-1][1])]
    lesson_kind = ' data-lesson-format="concept:2"' if concept_v2 else ""
    return (
        head(title, description, code=code, sim=sim)
        .replace("</head>", '<link rel="stylesheet" href="/_assets/flow.css">\n</head>' if flow else "</head>")
        + '<body>\n<div class="shell">\n'
        + sidebar(lib, mid, current)
        + '\n<div class="page">\n<div class="page-top">\n'
        + f'<nav class="breadcrumb" aria-label="Breadcrumb">{" &rsaquo; ".join(parts)}</nav>\n{theme_toggle()}\n</div>\n'
        + f"<main data-pagefind-body{lesson_kind}>\n{body}\n</main>\n"
        + footer()
        + "</div>\n</div>\n"
        + tail_scripts(mermaid=mermaid, code=code, sim=sim, extra=("/_assets/flow.js",) if flow else ())
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


# --- lesson format v2 (learning-center-lesson:2): the block renderer, the cite marks, the numbered source list -----------------
V2 = scan.V2
CALLOUT_LABELS = {"rule": "Rule of thumb", "pitfall": "Pitfall", "tip": "Tip"}
DECISION_COLUMNS = ("Option", "Pick when", "Avoid when", "Example")
DECISION_LAST_EXERCISE = "For this design"   # an exercise's decision rows say what this design picks, not an example
LEGEND_SOURCE_ID = re.compile(r"\bs\d+\b")


class Page:
    """What the blocks of one :2 page need from the page shell: whether it holds code or a diagram, the numbered sources,
    and whether it is a design exercise (the decision table's last column reads 'For this design' there)."""

    def __init__(self, sources: list[dict], *, exercise: bool = False, accepted_flows: bool = False) -> None:
        self.number = {s["id"]: n for n, s in enumerate(sources, 1)}   # scan.py keeps ids s1..sN in order
        self.code = False
        self.diagram = False
        self.flow = False
        self.flow_count = 0
        self.exercise = exercise
        self.accepted_flows = accepted_flows


def cite_marks(pg: Page, cites: list[str] | None) -> str:
    if not cites:
        return ""
    links = " ".join(f'<a href="#source-{esc(c)}" aria-label="Source {pg.number[c]}">[{pg.number[c]}]</a>' for c in cites)
    return f'<sup class="cite">{links}</sup>'


CITE_COLUMNS = ("cite", "cites", "source", "sources")   # a table column of source ids: rendered as the linked [n] marks
SOURCE_IDS = re.compile(r"^\s*s\d+(\s*,\s*s\d+)*\s*$")


def table_html(columns: list[str], rows: list[list[str]], caption: str | None, *, first_col_head: bool = False, cites: str = "",
               pg: "Page | None" = None) -> str:
    cap = f"<caption>{esc(caption or '')}{cites}</caption>" if (caption or cites) else ""
    head_ = "".join(f'<th scope="col">{esc(c)}</th>' for c in columns)
    cite_cols = {i for i, c in enumerate(columns) if c.strip().lower() in CITE_COLUMNS} if pg is not None else set()

    def cell(i, c):
        if i in cite_cols and SOURCE_IDS.match(c):
            ids = [x.strip() for x in c.split(",")]
            if all(x in pg.number for x in ids):
                return f"<td>{cite_marks(pg, ids)}</td>"
        return f"<td>{esc(c)}</td>"

    def cells(r):
        return "".join((f'<th scope="row">{esc(c)}</th>' if i == 0 and first_col_head else cell(i, c)) for i, c in enumerate(r))
    body_ = "".join(f"<tr>{cells(r)}</tr>" for r in rows)
    label = f' aria-label="{esc(caption)}"' if caption else ' aria-label="Table"'
    cls = ' class="decision"' if first_col_head else ""
    return f'<div class="table-scroll" role="region" tabindex="0"{label}><table{cls}>{cap}<thead><tr>{head_}</tr></thead><tbody>{body_}</tbody></table></div>'


def flow_forward_edges(nodes: dict, incoming: dict) -> dict:
    """`incoming` without the edges that close a cycle (found by a depth-first walk in node order): a request and its
    reply, or a call and its callback, must not push the two boxes apart without end when ranks are assigned."""
    children = {key: [] for key in nodes}
    for key, parents in incoming.items():
        for p in parents:
            children[p].append(key)
    state, back = {}, set()

    def visit(key):
        state[key] = 1
        for child in children[key]:
            if state.get(child) == 1:
                back.add((key, child))
            elif child not in state:
                visit(child)
        state[key] = 2

    roots = [k for k in nodes if not incoming[k]]+list(nodes)
    for key in roots:
        if key not in state:
            visit(key)
    return {key: [p for p in parents if (p, key) not in back] for key, parents in incoming.items()}


def flow_request_positions(b: dict, gap: int = 32, *, accepted: bool = False, acyclic: bool = False) -> tuple[dict, list, int, float]:
    """Two-column request lanes, side branches and independent orthogonal edge tracks.

    Actor-rooted frames form stacked panels when there are independent request
    paths. Otherwise services form the main column, with stores/queues beside it.
    Titles reserve a left-hand band, leaving a clear vertical entry corridor.
    """
    import textwrap

    nodes = {n["id"]: dict(n) for n in b["nodes"]}
    groups = b.get("frames", [])
    owner = {n: f["id"] for f in groups for n in f["nodes"]}
    rooted = [f for f in groups if any(nodes[n]["kind"] == "actor" for n in f["nodes"])]
    panels = [f["nodes"] for f in rooted] if len(rooted) > 1 else [list(nodes)]
    remaining = [n for n in nodes if not any(n in p for p in panels)]
    if remaining:
        panels.append(remaining)
    panel_of = {n: i for i, panel in enumerate(panels) for n in panel}
    width, box_width = 760, 230
    for n in nodes.values():
        n["lines"] = textwrap.wrap(n["label"], 13 if n["kind"] == "decision" else 24 if n["kind"] == "queue" else 26)
        n["w"] = box_width
        n["h"] = max(38, len(n["lines"])*18 + (38 if n["kind"] == "store" else 14))
        if n["kind"] == "decision":
            n["h"] = 2*(len(n["lines"])*18+18)
    columns = {key: int(n["kind"] in ("store", "queue")) for key, n in nodes.items()}
    ranks = dict.fromkeys(nodes, 0)
    # Keep storage members of a frame together, so an unrelated regional store
    # cannot end up inside the bounding rectangle of a cache frame.
    ordered = []
    for panel in panels:
        for key in panel:
            if key in ordered:
                continue
            peers = [n for n in panel if owner.get(n) == owner.get(key) and columns[n] == columns[key]] if key in owner else [key]
            ordered.extend(n for n in peers if n not in ordered)
    incoming = {key: [] for key in nodes}
    for e in b["edges"]:
        if e.get("kind", "sync") != "reply" and panel_of[e["from"]] == panel_of[e["to"]]:
            incoming[e["to"]].append(e["from"])
    if acyclic:
        incoming = flow_forward_edges(nodes, incoming)
    reachable = {key for key, n in nodes.items() if n["kind"] == "actor" and not incoming[key]}
    if not reachable:
        reachable = set(nodes)
    if not accepted:
        for _ in nodes:
            reachable.update(e["to"] for e in b["edges"] if e["from"] in reachable)
        incoming = {key: [p for p in parents if key not in reachable or p in reachable]
                    for key, parents in incoming.items()}
    pending, placed = list(ordered), set()
    while pending:
        ready = [n for n in pending if all(p in placed for p in incoming[n])]
        key = min(ready, key=lambda n: (not accepted and n not in reachable,
                  next((i for i, e in enumerate(b["edges"]) if e["to"] == n), -1))) if ready else pending[0]
        pending.remove(key)
        parents = [p for p in incoming[key] if p in placed]
        ranks[key] = max((ranks[p] + int(columns[p] == columns[key] or nodes[key]["kind"] == "queue"
                                              or nodes[p]["kind"] == "queue") for p in parents), default=0)
        if not accepted and key not in reachable and not parents:
            ranks[key] = max((ranks[n] for n in placed), default=-1)+1
        while any(panel_of[n] == panel_of[key] and columns[n] == columns[key] and ranks[n] == ranks[key] for n in placed):
            ranks[key] += 1
        placed.add(key)
    # Frame members in a branch lane are packed as a contiguous run. Moving a
    # downstream node also moves its descendants, never a per-diagram override.
    for _ in range(len(nodes)):
        changed = False
        for frame in groups:
            members = [n for n in frame["nodes"] if columns[n] == 1]
            if not members:
                continue
            lo, hi = min(ranks[n] for n in members), max(ranks[n] for n in members)
            for key in nodes:
                if key not in members and columns[key] == 1 and panel_of[key] == panel_of[members[0]] and lo <= ranks[key] <= hi:
                    ranks[key] = hi+1
                    changed = True
            next_rank = lo
            for key in sorted(members, key=lambda n: ranks[n]):
                minimum = max((ranks[p]+int(columns[p] == columns[key] or nodes[key]["kind"] == "queue"
                                           or nodes[p]["kind"] == "queue") for p in incoming[key]), default=0)
                packed = max(next_rank, minimum)
                if packed < ranks[key]:
                    ranks[key] = packed
                    changed = True
                next_rank = ranks[key]+1
        for key in ordered:
            for parent in incoming[key]:
                delta = int(columns[parent] == columns[key] or nodes[key]["kind"] == "queue" or nodes[parent]["kind"] == "queue")
                if ranks[key] < ranks[parent]+delta and parent != key:
                    ranks[key] = ranks[parent]+delta
                    changed = True
        if not changed:
            break
    if acyclic:
        # Two boxes of one lane and rank would be drawn on top of each other: the later one is pushed down, with everything
        # it feeds. (Only for the retry: the diagrams that were drawn first time keep their ranks.)
        for _ in range(len(nodes)*len(nodes)):
            slots, clash = {}, None
            for key in ordered:
                slot = (panel_of[key], columns[key], ranks[key])
                if slot in slots:
                    clash = key
                    break
                slots[slot] = key
            if clash is None:
                break
            ranks[clash] += 1
            for _ in range(len(nodes)):
                moved = False
                for key in ordered:
                    for parent in incoming[key]:
                        delta = int(columns[parent] == columns[key] or nodes[key]["kind"] == "queue" or nodes[parent]["kind"] == "queue")
                        if parent != key and ranks[key] < ranks[parent]+delta:
                            ranks[key] = ranks[parent]+delta
                            moved = True
                if not moved:
                    break
    title_lines = {f["id"]: textwrap.wrap(f["title"], 13) for f in groups}
    title_heights = {key: len(lines)*18+8 for key, lines in title_lines.items()}
    y = max([8]+[title_heights[owner[n]]+10 for n in nodes if ranks[n] == 0 and n in owner])
    for panel in panels:
        previous_row = []
        for rank in sorted({ranks[n] for n in panel}):
            row = [n for n in panel if ranks[n] == rank]
            starts = [f for f in groups if any(n in row for n in f["nodes"]) and
                      rank == min(ranks[n] for n in f["nodes"])]
            if previous_row:
                extra_gap = 0
                for f in starts:
                    framed_before = any(n in owner and columns[n] == columns[f["nodes"][0]] for n in previous_row)
                    vertical_entry = any(n in f["nodes"] and any(columns[p] == columns[n] for p in incoming[n]) for n in row)
                    extra_gap = max(extra_gap, title_heights[f["id"]]+(24 if framed_before else 12)
                                    +(24 if vertical_entry else 0)-gap)
                y += extra_gap
            height = max(nodes[n]["h"] for n in row)
            for key in row:
                nodes[key].update(x=60+columns[key]*390, y=y+(height-nodes[key]["h"])/2)
            y += height+gap
            previous_row = row
        if len(panels) > 1:
            y += 42
    def make_frames():
        result = []
        for frame in groups:
            members = [nodes[n] for n in frame["nodes"]]
            x = min(n["x"] for n in members)-18
            right = max(n["x"]+n["w"] for n in members)+18
            title_h = title_heights[frame["id"]]
            top = min(n["y"] for n in members)-title_h
            bottom = max(n["y"]+n["h"] for n in members)+12
            result.append(dict(frame, x=x, y=top, w=right-x, h=bottom-top, lines=title_lines[frame["id"]],
                               title_box=(x+5, top+2, x+119, top+title_h-4)))
        return result

    def intersects(a, z, margin=0):
        return (max(a["x"], z["x"]) < min(a["x"]+a["w"], z["x"]+z["w"])+margin
                and max(a["y"], z["y"]) < min(a["y"]+a["h"], z["y"]+z["h"])+margin)

    frames = make_frames()
    # Disconnected members can otherwise wrap a frame around another frame or
    # an unrelated node. Pack such groups as indivisible vertical bands.
    if (any(intersects(f, other, 10) for i, f in enumerate(frames) for other in frames[i+1:])
            or any(intersects(f, n) for f in frames for key, n in nodes.items() if key not in f["nodes"])):
        bands = {}
        for key in nodes:
            bands.setdefault(owner.get(key, key), []).append(key)
        y = 8
        for band, members in sorted(bands.items(), key=lambda item: min(nodes[n]["y"] for n in item[1])):
            if band in title_heights:
                y += title_heights[band]+14
            rows = {}
            for key in members:
                n = nodes[key]
                rows.setdefault(n["y"]+n["h"]/2, []).append(key)
            for _, row in sorted(rows.items()):
                height = max(nodes[n]["h"] for n in row)
                for key in row:
                    nodes[key]["y"] = y+(height-nodes[key]["h"])/2
                y += height+gap
            y += 18
        frames = make_frames()
    return nodes, frames, width, y


def flow_concept_positions(b: dict, gap: int = 32) -> tuple[dict, list, int, float]:
    """Layer structural links, retaining feedback edges without rank inflation."""
    import textwrap

    nodes = {n["id"]: dict(n) for n in b["nodes"]}
    children = {key: [] for key in nodes}
    incoming = dict.fromkeys(nodes, 0)
    for edge in b["edges"]:
        children[edge["from"]].append(edge["to"])
        incoming[edge["to"]] += 1
    active, visited, order, parents = set(), set(), [], {key: [] for key in nodes}

    def visit(key):
        active.add(key)
        for child in children[key]:
            if child not in active:
                parents[child].append(key)
                if child not in visited:
                    visit(child)
        active.remove(key)
        visited.add(key)
        order.append(key)

    for key in sorted(nodes, key=lambda n: incoming[n] != 0):
        if key not in visited:
            visit(key)
    ranks = dict.fromkeys(nodes, 0)
    for key in reversed(order):
        ranks[key] = max((ranks[p]+1 for p in parents[key]), default=0)
    # Shared terminal consumers sit below the private branches they aggregate.
    last_rank = max(ranks.values())
    for key in nodes:
        if (not children[key] and len(set(parents[key])) > 1
                and any(len(set(parents[sibling])) < len(set(parents[key]))
                        for parent in parents[key] for sibling in children[parent])):
            ranks[key] = last_rank+1
    # Terminal feedback sources are nested by their target's rank, so returns
    # can occupy separate margin lanes rather than weaving across each other.
    returns = [key for key in nodes if children[key] and all(ranks[c] < ranks[key] for c in children[key])]
    last_rank = max(ranks.values())
    for offset, key in enumerate(sorted(returns, key=lambda n: -min(ranks[c] for c in children[n]))):
        ranks[key] = last_rank+offset
    rows = []
    for rank in sorted(set(ranks.values())):
        members = [n for n in nodes if ranks[n] == rank]
        members.sort(key=lambda n: sum(list(nodes).index(p) for p in parents[n])/max(1, len(parents[n])))
        rows.extend(members[i:i+4] for i in range(0, len(members), 4))
    width, y = 760, 28
    for row in rows:
        returning = [key for key in row if any(ranks[child] < ranks[key] for child in children[key])]
        if returning:
            row = returning[:1]+[key for key in row if key not in returning]+returning[1:]
        box_width = min(280, (width-112-40*(len(row)-1))//len(row))
        for key in row:
            n = nodes[key]
            wrap = max(10, int((box_width-28)/(16 if n["kind"] == "decision" else 8.4)))
            n["lines"] = textwrap.wrap(n["label"], wrap)
            n["w"] = box_width
            n["h"] = max(48, len(n["lines"])*18+(38 if n["kind"] == "store" else 24))
            if n["kind"] == "decision":
                n["h"] = 2*(len(n["lines"])*18+18)
        height = max(nodes[n]["h"] for n in row)
        left = (width-(box_width+40)*len(row)+40)/2
        for i, key in enumerate(row):
            nodes[key].update(x=left+i*(box_width+40), y=y+(height-nodes[key]["h"])/2)
        y += height+gap+46
    return nodes, [], width, y-gap


FLOW_LANE_NODES = 12            # the most nodes the two-lane layout places before the grid takes over
FLOW_GRID_BOX, FLOW_GRID_PITCH, FLOW_GRID_LEFT = 170, 260, 45


def flow_grid_positions(b: dict, gap: int = 32) -> tuple[dict, list, int, float]:
    """Rows of at most three boxes, for a flow of more than 12 nodes and for one the two-lane layout cannot route.

    A box stands one row below its deepest parent (edges that close a cycle do not count), a box with one parent and no
    children of its own beside that parent when its row would hold more than three. Boxes are placed row by row, in
    the slots (left, middle, right) nearest their parents' slots, a box with children towards the middle and siblings
    in the order they were written. A frame is the rectangle round its members, so a box that is not a member must not
    stand in it: while a frame still has members to come, its slots are closed to every other box (a frame of one slot
    is a stripe with the stores and queues beside it, a frame of three slots a band across the page), and a box
    that cannot be placed waits for the next row.
    """
    import itertools
    import textwrap

    nodes = {n["id"]: dict(n) for n in b["nodes"]}
    order = list(nodes)
    groups = b.get("frames", [])
    owner = {n: f["id"] for f in groups for n in f["nodes"]}
    members = {f["id"]: list(f["nodes"]) for f in groups}
    incoming = {key: [] for key in nodes}
    for e in b["edges"]:
        if e.get("kind", "sync") != "reply" and e["from"] != e["to"] and e["from"] not in incoming[e["to"]]:
            incoming[e["to"]].append(e["from"])
    incoming = flow_forward_edges(nodes, incoming)
    children = {key: [k for k in order if key in incoming[k]] for key in nodes}
    # A framed box is placed by its parents inside its frame (by all of them when it has none there), so a store that the
    # frame shares with other frames does not stretch the frame down the page.
    drivers = {key: [p for p in incoming[key] if owner.get(p) == owner[key]] or incoming[key] if key in owner else incoming[key]
               for key in nodes}
    depth = dict.fromkeys(order, 0)
    for _ in order:
        changed = False
        for key in order:
            for parent in drivers[key]:
                if depth[key] < depth[parent]+1:
                    depth[key] = depth[parent]+1
                    changed = True
        if not changed:
            break
    beside = {}
    for key in order:
        parents = incoming[key]
        if (len(parents) == 1 and not children[key] and sum(d == depth[key] for d in depth.values()) > 3
                and sum(d == depth[parents[0]] for d in depth.values()) < 3):
            beside[key] = parents[0]
            depth[key] = depth[parents[0]]

    row, slot = {}, {}
    frame_rows, frame_slots = {}, {}

    def active(fid, at):
        placed = [k for k in members[fid] if k in row]
        return bool(placed) and (len(placed) < len(members[fid]) or max(row[k] for k in placed) >= at)

    def centre(key):
        placed = [slot[p] for p in incoming[key] if p in slot]
        return sum(placed)/len(placed) if placed else 1

    def allowed(key, at):
        free = {0, 1, 2}
        for fid in members:
            if fid != owner.get(key) and active(fid, at):
                free -= set(range(frame_slots[fid][0], frame_slots[fid][1]+1))
        own = owner.get(key)
        if own in frame_slots:
            lo, hi = frame_slots[own]
            reach = set(range(lo, hi+1))
            for s in (lo-1, hi+1):
                if 0 <= s <= 2 and not any(
                        owner.get(k) != own and frame_rows[own][0] <= row[k] <= at and min(lo, s) <= slot[k] <= max(hi, s)
                        for k in row):
                    reach.add(s)
            free &= reach
        return free

    at = 0
    while len(row) < len(nodes):
        if at > 4*len(nodes):
            raise FlowLayoutSpaceError("flow: the grid cannot place every box")
        ready = [k for k in order if k not in row and depth[k] <= at
                 and all(p in row and row[p] < at for p in drivers[k] if beside.get(k) != p)]
        ready = [k for k in ready if k not in beside or beside[k] in ready or row.get(beside[k], at) < at]
        ready.sort(key=lambda k: (centre(k), order.index(k)))
        free = {k: allowed(k, at) for k in ready}
        ready = [k for k in ready if free[k]]
        while True:
            ready = [k for k in ready if k not in beside or beside[k] in ready or row.get(beside[k], at) < at]
            if len(ready) > 3:
                ready.remove(min(ready, key=lambda k: (len(free[k]), bool(children[k]), -order.index(k))))
                continue
            best = None
            for perm in itertools.permutations((0, 1, 2), len(ready)):
                if all(perm[i] in free[k] for i, k in enumerate(ready)):
                    cost = (sum(abs(s-centre(k))+(.2*abs(s-1) if children[k] else 0) for s, k in zip(perm, ready))
                            + 3*sum(perm[i] > perm[j] for i in range(len(perm)) for j in range(i+1, len(perm))))
                    if best is None or cost < best[0]:
                        best = (cost, perm)
            if best or not ready:
                break
            ready.remove(min(ready, key=lambda k: (len(free[k]), bool(children[k]), -order.index(k))))
        for key, s in zip(ready, best[1] if best else ()):
            row[key], slot[key] = at, s
            fid = owner.get(key)
            if fid:
                first, last = frame_rows.get(fid, (at, at))
                frame_rows[fid] = (min(first, at), max(last, at))
                lo, hi = frame_slots.get(fid, (s, s))
                frame_slots[fid] = (min(lo, s), max(hi, s))
        at += 1

    for n in nodes.values():
        n["lines"] = textwrap.wrap(n["label"], 13 if n["kind"] == "decision" else (24 if n["kind"] == "queue" else 26)*FLOW_GRID_BOX//230)
        n["w"] = FLOW_GRID_BOX
        n["h"] = max(38, len(n["lines"])*18 + (38 if n["kind"] == "store" else 14))
        if n["kind"] == "decision":
            n["h"] = 2*(len(n["lines"])*18+18)
    title_lines = {f["id"]: textwrap.wrap(f["title"], 13) for f in groups}
    title_heights = {key: len(lines)*18+8 for key, lines in title_lines.items()}
    used = sorted(set(row.values()))
    y = 8
    for position, at in enumerate(used):
        keys = [k for k in order if row[k] == at]
        row_y = y
        opening = [title_heights[fid] for fid in members if frame_rows.get(fid, (None,))[0] == at]
        if opening:
            row_y += max(opening)+2 if position == 0 else max(opening)+max(64, gap)-gap
        height = max(nodes[k]["h"] for k in keys)
        for key in keys:
            nodes[key].update(x=FLOW_GRID_LEFT+slot[key]*FLOW_GRID_PITCH, y=row_y+(height-nodes[key]["h"])/2)
        y = row_y+height+gap
    frames = []
    for frame in groups:
        held = [nodes[n] for n in frame["nodes"]]
        x = min(n["x"] for n in held)-38      # the title tab leaves the entry ports of a left-hand box clear
        right = max(n["x"]+n["w"] for n in held)+10
        title_h = title_heights[frame["id"]]
        top = min(n["y"] for n in held)-title_h
        bottom = max(n["y"]+n["h"] for n in held)+12
        frames.append(dict(frame, x=x, y=top, w=right-x, h=bottom-top, lines=title_lines[frame["id"]],
                           title_box=(x+5, top+2, x+119, top+title_h-4)))
    return nodes, frames, 760, y


class FlowLayoutSpaceError(BuildError):
    """The graph needs more room, without changing authored content."""


def flow_layout(b: dict, *, accepted: bool = False) -> dict:
    """The deterministic geometry, retrying with more row gap until every route and label has room.

    Plans, in order: the established two-lane layout; the grid (rows of up to three boxes); the grid with the arrows
    routed last to first (a different crowd in the corridors); the grid where a label that finds no room may be cut to
    its step number; the two-lane layout again with the edges that close a cycle left out of the ranking and no two
    boxes on one spot. A diagram the first plan draws never reaches the others, so no earlier diagram changes. A flow
    of more than 12 nodes (none before) is placed on the grid first, then in the two lanes."""
    plans = (["lanes"] if accepted else ["lanes", "grid", "grid-reversed", "grid-numbers", "retry"]
             if len(b["nodes"]) <= FLOW_LANE_NODES else ["grid", "grid-reversed", "grid-numbers", "retry"])
    for position, plan in enumerate(plans):
        for gap in (32, 48, 64, 96, 128, 192):
            try:
                return flow_geometry(b, gap, accepted=accepted, plan=plan)
            except FlowLayoutSpaceError:
                if gap == 192 and position == len(plans)-1:
                    raise


def flow_geometry(b: dict, gap: int, *, accepted: bool = False, plan: str = "lanes") -> dict:
    import heapq
    import textwrap

    grid = plan in ("grid", "grid-reversed", "grid-numbers")
    concept = all(e.get("kind") == "link" for e in b["edges"]) and not b.get("frames")
    nodes, frames, width, y = (flow_concept_positions(b, gap) if concept else
                               flow_grid_positions(b, gap) if grid else
                               flow_request_positions(b, gap, accepted=accepted, acyclic=plan == "retry"))
    obstacles = [(n["x"]-5, n["y"]-5, n["x"]+n["w"]+5, n["y"]+n["h"]+5) for n in nodes.values()]
    obstacles += [f["title_box"] for f in frames]
    borders = [(f["x"], f["y"], f["x"]+f["w"], f["y"]+f["h"]) for f in frames]
    sides = []
    attachments = {}
    feedback = {}
    predecessors = {key: {e["from"] for e in b["edges"] if e["to"] == key} for key in nodes}
    successors = {key: {e["to"] for e in b["edges"] if e["from"] == key} for key in nodes}
    for i, edge in enumerate(b["edges"]):
        a, z = nodes[edge["from"]], nodes[edge["to"]]
        if concept and a["y"] > z["y"]:
            side = "left" if a["x"]+a["w"]/2 <= width/2 else "right"
            feedback[i] = (side, None)
            pair = (side, side)
        elif (concept and a["x"]+a["w"]/2 != z["x"]+z["w"]/2
              and not successors[edge["to"]] and len(predecessors[edge["to"]]) > 1
              and any(len(predecessors[child]) < len(predecessors[edge["to"]]) for child in successors[edge["from"]])
              and sum(e["from"] == edge["from"] and e["to"] == edge["to"] for e in b["edges"]) == 1):
            # A shared fan-in must not cut across a sibling's private path.
            side = "left" if a["x"]+a["w"]/2 < z["x"]+z["w"]/2 else "right"
            pair = (side, side)
        elif concept and a["y"] != z["y"]:
            pair = ("bottom", "top")
        elif grid:
            # Rows of the grid: a box in another row is entered from its top (below) or bottom (above); a box that does not
            # stand under (over) the source is left through the source's side; a box in the same row is joined side to side.
            beside = "left" if z["x"]+z["w"] <= a["x"] else "right" if z["x"] >= a["x"]+a["w"] else None
            if z["y"] >= a["y"]+a["h"]:
                pair = (beside or "bottom", "top")
            elif a["y"] >= z["y"]+z["h"]:
                pair = (beside or "top", "bottom")
            else:
                pair = ("right", "left") if a["x"] < z["x"] else ("left", "right")
        elif a["x"] == z["x"]:
            pair = ("bottom", "top") if a["y"] < z["y"] else ("top", "bottom")
        elif abs(a["y"]+a["h"]/2-z["y"]-z["h"]/2) < 2:
            pair = ("right", "left") if a["x"] < z["x"] else ("left", "right")
        elif a["x"] < z["x"]:
            pair = ("right", "left")
        else:
            pair = ("bottom", "top") if a["y"] < z["y"] else ("left", "right")
        sides.append(pair)
        for key, side, role in ((edge["from"], pair[0], "start"), (edge["to"], pair[1], "end")):
            attachments.setdefault((key, side), []).append((i, role))
    for side in ("left", "right"):
        returning = sorted((i for i, (s, _) in feedback.items() if s == side),
                           key=lambda i: -abs(nodes[b["edges"][i]["from"]]["y"]-nodes[b["edges"][i]["to"]]["y"]))
        for lane_index, i in enumerate(returning):
            feedback[i] = (side, 8+14*lane_index if side == "left" else width-8-14*lane_index)
    if not accepted:
        for (key, side), peers in attachments.items():
            def opposite(ref):
                edge, role = b["edges"][ref[0]], ref[1]
                other = nodes[edge["to"] if role == "start" else edge["from"]]
                return (other["x"]+other["w"]/2 if side in ("top", "bottom") else other["y"]+other["h"]/2, ref[0])
            peers.sort(key=opposite)

    def vertical_port(n, side, x):
        offset = x-n["x"]-n["w"]/2
        inset = abs(offset)*n["h"]/n["w"] if n["kind"] == "decision" else 0
        return (x, n["y"]+(n["h"]-inset if side == "bottom" else inset))

    def port(key, side, ref):
        n = nodes[key]
        peers = attachments[(key, side)]
        offset = (peers.index(ref)-(len(peers)-1)/2)*14
        if side in ("top", "bottom"):
            return vertical_port(n, side, n["x"]+n["w"]/2+offset)
        inset = abs(offset)*n["w"]/n["h"] if n["kind"] == "decision" else 0
        return (n["x"]+(n["w"]-inset if side == "right" else inset), n["y"]+n["h"]/2+offset)

    def crosses(a, z, c, d):
        if a[0] == z[0] and c[1] == d[1]:
            return min(c[0], d[0]) <= a[0] <= max(c[0], d[0]) and min(a[1], z[1]) <= c[1] <= max(a[1], z[1])
        if a[1] == z[1] and c[0] == d[0]:
            return min(c[1], d[1]) <= a[1] <= max(c[1], d[1]) and min(a[0], z[0]) <= c[0] <= max(a[0], z[0])
        return False

    def overlap(a, z, c, d):
        if a[0] == z[0] == c[0] == d[0]:
            return max(0, min(max(a[1], z[1]), max(c[1], d[1]))-max(min(a[1], z[1]), min(c[1], d[1])))
        if a[1] == z[1] == c[1] == d[1]:
            return max(0, min(max(a[0], z[0]), max(c[0], d[0]))-max(min(a[0], z[0]), min(c[0], d[0])))
        return 0

    def outside(key, point, side, ref):
        n = nodes[key]
        distance = 10 if accepted or side in ("top", "bottom") else 10+6*attachments[(key, side)].index(ref)
        if side in ("top", "bottom"):
            return (point[0], n["y"]+(n["h"]+distance if side == "bottom" else -distance))
        return (n["x"]+(n["w"]+distance if side == "right" else -distance), point[1])

    endpoints = []
    for i, edge in enumerate(b["edges"]):
        start_side, end_side = sides[i]
        start_port = port(edge["from"], start_side, (i, "start"))
        end_port = port(edge["to"], end_side, (i, "end"))
        source, destination = nodes[edge["from"]], nodes[edge["to"]]
        if (concept and start_side in ("top", "bottom") and end_side in ("top", "bottom")
                and source["x"]+source["w"]/2 == destination["x"]+destination["w"]/2):
            if len(attachments[(edge["to"], end_side)]) == 1:
                end_port = vertical_port(destination, end_side, start_port[0])
            elif len(attachments[(edge["from"], start_side)]) == 1:
                start_port = vertical_port(source, start_side, end_port[0])
        if (start_side in ("left", "right") and end_side in ("left", "right")
                and abs(source["y"]+source["h"]/2-destination["y"]-destination["h"]/2) < 2
                and len(attachments[(edge["to"], end_side)]) == 1):
            end_port = (end_port[0], start_port[1])
        start = outside(edge["from"], start_port, start_side, (i, "start"))
        end = outside(edge["to"], end_port, end_side, (i, "end"))
        endpoints.append((start_port, end_port, start, end))
    # Reserve every future port, not only edges already drawn. This prevents a
    # later endpoint from landing exactly on an earlier elbow (a false junction).
    port_reservations = [] if accepted else [
        (i, (min(p[0], o[0])-5, min(p[1], o[1])-5, max(p[0], o[0])+5, max(p[1], o[1])+5))
        for i, (a, z, start, end) in enumerate(endpoints) for p, o in ((a, start), (z, end))]

    labels = []
    edge_ids = {edge["id"]: i for i, edge in enumerate(b["edges"]) if "id" in edge}
    stepped = {edge_ids[step["edge"]] if isinstance(step["edge"], str) else step["edge"] for step in b.get("steps", [])}
    label_obstacles = (list(obstacles) if accepted else [
        (n["x"]-26, n["y"]-26, n["x"]+n["w"]+26, n["y"]+n["h"]+26) for n in nodes.values()])
    label_obstacles += [(f["x"]-4, f["y"]-4, f["x"]+f["w"]+4, f["title_box"][3]+4) for f in frames]
    label_obstacles += [rect for l, t, r, bot in borders for rect in
                        ((l-4, t-4, l+4, bot+4), (r-4, t-4, r+4, bot+4), (l-4, bot-4, r+4, bot+4))]
    label_obstacles_tight = [(n["x"]-8, n["y"]-8, n["x"]+n["w"]+8, n["y"]+n["h"]+8) for n in nodes.values()] + label_obstacles[len(nodes):]

    def nearest(rect, path):
        return min(max(rect[0]-max(a[0], z[0]), min(a[0], z[0])-rect[2], 0) +
                   max(rect[1]-max(a[1], z[1]), min(a[1], z[1])-rect[3], 0) for a, z in zip(path, path[1:]))

    def place_label(i, route):
        edge = b["edges"][i]
        short = edge.get("short") or (edge["label"] if concept else " ".join(edge["label"].split()[:3]))
        if not short:
            return
        text = f"{i+1} · {short}" if i in stepped else short
        candidates = []
        # On the grid a label that finds no room with the usual clearance round the boxes gets a second try with less, but
        # only once the row gap is wide (128 or more): a smaller gap grows first, so the diagram keeps its air.
        for tight in ((False, True) if grid and gap >= 128 else (False,)):
            avoid = (label_obstacles_tight if tight else label_obstacles)+[item["box"] for item in labels]
            if not accepted:
                reach = 8 if tight else 16
                avoid += [(p[0]-reach, p[1]-reach, p[0]+reach, p[1]+reach)
                          for j, endpoint in enumerate(endpoints) if j != i for p in endpoint[2:]]
            alternatives = [[text], textwrap.wrap(text, 12)]
            if not accepted:
                alternatives.append(textwrap.wrap(text, 8, break_long_words=False, break_on_hyphens=False))
            if plan == "grid-numbers" and tight and i in stepped:
                # Last resort on the grid, in the tight pass: the step number alone (the words stay in Exact calls).
                alternatives.append([str(i+1)])
            for lines in alternatives:
                tw, th = max(map(len, lines))*8.2, len(lines)*18
                for a, z in zip(route, route[1:]):
                    length = abs(a[0]-z[0])+abs(a[1]-z[1])
                    if length < 16:
                        continue
                    for fraction in (j/40 for j in range(4, 37)):
                        cx, cy = a[0]+(z[0]-a[0])*fraction, a[1]+(z[1]-a[1])*fraction
                        positions = [(cx+10, cy-th/2, 0), (cx-tw-10, cy-th/2, 0)] if a[0] == z[0] else [(cx-tw/2, cy-th-6, 0), (cx-tw/2, cy+7, 0)]
                        if grid:
                            # A crowded grid may leave no room beside the line: the label may stand a little further off (up to
                            # 30 px more), nearest first, and later arrows then keep clear of it by that much.
                            spread = range(10, 50, 10)
                            positions = ([(cx+d, cy-th/2, d-10) for d in spread] + [(cx-tw-d, cy-th/2, d-10) for d in spread] if a[0] == z[0] else
                                         [(cx-tw/2, cy-th-d+4, d-10) for d in spread] + [(cx-tw/2, cy+d-3, d-10) for d in spread])
                        for lx, ly, away in positions:
                            rect = (lx-3, ly-2, lx+tw+3, ly+th+2)
                            if rect[0] < 4 or rect[2] > width-4 or rect[1] < 0 or (grid and rect[3] > y-18):
                                continue
                            if any(max(rect[0], l) < min(rect[2], r) and max(rect[1], t) < min(rect[3], bot)
                                   for l, t, r, bot in avoid):
                                continue
                            if any(abs(i-item["edge"]) == 1 and max(rect[0], item["box"][0]) < min(rect[2], item["box"][2])
                                   and max(rect[1]-item["box"][3], item["box"][1]-rect[3]) < 10 for item in labels):
                                continue
                            if any((rect[0] < a[0] < rect[2] and max(min(a[1], z[1]), rect[1]) < min(max(a[1], z[1]), rect[3]))
                                   if a[0] == z[0] else (rect[1] < a[1] < rect[3] and max(min(a[0], z[0]), rect[0]) < min(max(a[0], z[0]), rect[2]))
                                   for a, z in segments):
                                continue
                            if not accepted:
                                def distance_to(rect, path):
                                    return min(max(rect[0]-max(a[0], z[0]), min(a[0], z[0])-rect[2], 0) +
                                               max(rect[1]-max(a[1], z[1]), min(a[1], z[1])-rect[3], 0)
                                               for a, z in zip(path, path[1:]))
                                own_distance = distance_to(rect, route)
                                if any(distance_to(rect, other) <= own_distance+3 for j, other in indexed_routes.items() if j != i):
                                    continue
                            anchor = ("end" if lx < cx else "start") if a[0] == z[0] else "middle"
                            number_only = grid and lines == [str(i+1)] and text != lines[0]
                            candidates.append((len(lines)*100+(350 if number_only else 0)+abs(fraction-.5)*30-length/100+away,
                                               lx, ly, rect, lines, anchor))
            if candidates:
                break
        if not candidates:
            raise FlowLayoutSpaceError(f"flow: no clear space for edge label {text!r}")
        _, lx, ly, rect, lines, anchor = min(candidates)
        item = dict(edge=i, text=text, lines=lines, x=lx, y=ly+15, box=rect)
        if not accepted:
            item["anchor"] = anchor
            item["x"] = rect[2]-3 if anchor == "end" else (rect[0]+rect[2])/2 if anchor == "middle" else lx
        labels.append(item)

    segments, routes, indexed_routes = [], [], {}
    route_order = sorted(range(len(b["edges"])), key=lambda i: (
        i in feedback, nodes[b["edges"][i]["from"]]["y"],
        -abs(nodes[b["edges"][i]["to"]]["y"]-nodes[b["edges"][i]["from"]]["y"]),
        -abs(nodes[b["edges"][i]["to"]]["x"]-nodes[b["edges"][i]["from"]]["x"]), i)) if concept else (
            range(len(b["edges"])-1, -1, -1) if plan == "grid-reversed" else range(len(b["edges"])))
    for i in route_order:
        edge = b["edges"][i]
        source, destination = nodes[edge["from"]], nodes[edge["to"]]
        start_port, end_port, start, end = endpoints[i]
        route_obstacles = obstacles+[box for j, box in port_reservations if j != i]
        lane = feedback[i][1] if i in feedback else None
        xs = sorted({12, width-12, start[0], end[0]} | ({lane} if lane is not None else set()) |
                    {v for l, t, r, bot in route_obstacles for v in (l-10, r+10)} |
                    {p[0]+d for route in routes for p in route for d in ((-120, 120) if not accepted and not concept else (-14, 14))})
        ys = sorted({8, y-8, start[1], end[1]} |
                    {v for l, t, r, bot in route_obstacles for v in (t-10, bot+10)} |
                    {p[1]+d for route in routes for p in route for d in ((-36, 36) if not accepted and not concept else (-14, 14))})
        xs = [v for v in xs if 8 <= v <= width-8]
        ys = [v for v in ys if 4 <= v <= y]

        def clear(a, z):
            if a[0] == z[0]:
                hit = any(l < a[0] < r and max(min(a[1], z[1]), t) < min(max(a[1], z[1]), bot) for l, t, r, bot in route_obstacles)
            else:
                hit = any(t < a[1] < bot and max(min(a[0], z[0]), l) < min(max(a[0], z[0]), r) for l, t, r, bot in route_obstacles)
            if hit or any(overlap(a, z, c, d) > 0 for c, d in segments):
                return False
            return not any(overlap(a, z, c, d) > 0 for l, t, r, bot in borders
                           for c, d in (((l,t),(r,t)), ((r,t),(r,bot)), ((r,bot),(l,bot)), ((l,bot),(l,t))))

        origin = (xs.index(start[0]), ys.index(start[1]), 0, 2 if lane is None else 0)
        target = (xs.index(end[0]), ys.index(end[1]))
        todo, distances, previous = [(0, origin)], {origin: 0}, {}
        goal = None
        while todo:
            distance, here = heapq.heappop(todo)
            if distance != distances[here]:
                continue
            ix, iy, direction, phase = here
            if (ix, iy) == target and phase == 2:
                goal = here
                break
            for nx, ny, axis in ((ix-1, iy, 1), (ix+1, iy, 1), (ix, iy-1, 2), (ix, iy+1, 2)):
                if not (0 <= nx < len(xs) and 0 <= ny < len(ys)):
                    continue
                a, z = (xs[ix], ys[iy]), (xs[nx], ys[ny])
                if not clear(a, z):
                    continue
                next_phase = phase
                if phase == 0 and axis == 2:
                    continue
                if phase == 0 and z[0] == lane:
                    next_phase = 1
                if phase == 1:
                    if a[1] == end[1]:
                        next_phase = 2
                    elif axis == 1 or abs(z[1]-end[1]) >= abs(a[1]-end[1]):
                        continue
                cost = distance+abs(a[0]-z[0])+abs(a[1]-z[1])+(30 if direction and direction != axis else 0)
                if not accepted:
                    cost += 180*sum(crosses(a, z, c, d) for c, d in segments)
                if not accepted and not concept:
                    # Closely parallel calls leave no side on which a label can
                    # belong to its own edge. Prefer a clear corridor up front.
                    along, across = (1, 0) if axis == 2 else (0, 1)
                    spacing = 110 if axis == 2 else 36
                    for c, d in segments:
                        separation = abs(a[across]-c[across])
                        if c[across] == d[across] and separation < spacing:
                            shared = max(0, min(max(a[along], z[along]), max(c[along], d[along]))
                                         - max(min(a[along], z[along]), min(c[along], d[along])))
                            cost += shared*(spacing-separation)/spacing*4
                # Fan out near the source, leaving the middle link room for its label.
                if concept and source["y"] < destination["y"] and start[0] != end[0] and axis == 2 and a[0] == start[0]:
                    cost += abs(a[1]-z[1])*.001
                point = (nx, ny, axis, next_phase)
                if cost < distances.get(point, float("inf")):
                    distances[point], previous[point] = cost, here
                    heapq.heappush(todo, (cost, point))
        if goal is None:
            raise FlowLayoutSpaceError(f"flow: cannot route edge {i} without sharing a track")
        route, here = [], goal
        while True:
            route.append((xs[here[0]], ys[here[1]]))
            if here == origin:
                break
            here = previous[here]
        points = [start_port]+list(reversed(route))+[end_port]
        compact = []
        for point in points:
            if compact and point == compact[-1]:
                continue
            if len(compact) > 1 and ((compact[-2][0] == compact[-1][0] == point[0]) or
                                     (compact[-2][1] == compact[-1][1] == point[1])):
                compact[-1] = point
            else:
                compact.append(point)
        routes.append(compact)
        indexed_routes[i] = compact
        segments.extend(zip(compact, compact[1:]))
        if not accepted:
            before = len(labels)
            place_label(i, compact)
            if len(labels) > before:
                l, t, r, bot = labels[-1]["box"]
                # A label that stands off its own arrow keeps later arrows farther from it than that arrow is.
                margin = max(12, nearest(labels[-1]["box"], compact)+4) if grid else 12
                obstacles.append((l-margin, t-margin, r+margin, bot+margin))
    if grid:
        # Safety net: a label with a foreign arrow nearer than its own is placed again, now that every arrow is known.
        for item in list(labels):
            own = nearest(item["box"], indexed_routes[item["edge"]])
            if any(nearest(item["box"], other) <= own+3 for j, other in indexed_routes.items() if j != item["edge"]):
                labels.remove(item)
                place_label(item["edge"], indexed_routes[item["edge"]])
    routes = [indexed_routes[i] for i in range(len(b["edges"]))]
    if accepted:
        label_order = sorted(range(len(routes)), key=lambda i: sum(abs(a[0]-z[0])+abs(a[1]-z[1]) for a, z in zip(routes[i], routes[i][1:])))
        for i in label_order:
            place_label(i, routes[i])
    result = dict(nodes=nodes, frames=frames, routes=routes, labels=labels, width=width, height=y-18)
    if not accepted:
        result["bridges"] = flow_bridges(routes)
    return result

def flow_bridges(routes: list) -> list:
    """Give every residual crossing a quiet overpass on its roomiest segment."""
    crossings = {}
    for i, route in enumerate(routes):
        for j, other in enumerate(routes[:i]):
            for si, (a, z) in enumerate(zip(route, route[1:])):
                for sj, (c, d) in enumerate(zip(other, other[1:])):
                    if (a[0] == z[0]) == (c[0] == d[0]):
                        continue
                    h, v = ((a, z), (c, d)) if a[1] == z[1] else ((c, d), (a, z))
                    x, y = v[0][0], h[0][1]
                    if not (min(h[0][0], h[1][0]) <= x <= max(h[0][0], h[1][0])
                            and min(v[0][1], v[1][1]) <= y <= max(v[0][1], v[1][1])):
                        continue
                    choices = []
                    for edge, segment, start, end in ((i, si, a, z), (j, sj, c, d)):
                        distance = abs(x-start[0])+abs(y-start[1])
                        clearance = min(distance, abs(x-end[0])+abs(y-end[1]))
                        choices.append((clearance, edge, segment, distance))
                    clearance, edge, segment, distance = max(choices)
                    if clearance < 4:
                        raise FlowLayoutSpaceError("flow: crossing needs room for an overpass")
                    crossings.setdefault((edge, segment), []).append((distance, (i, j, x, y)))
    bridges = []
    for (edge, segment), points in sorted(crossings.items()):
        a, z = routes[edge][segment:segment+2]
        length = abs(z[0]-a[0])+abs(z[1]-a[1])
        dx, dy = (z[0]-a[0])/length, (z[1]-a[1])/length
        groups = []
        for distance, crossing in sorted(points):
            left, right = distance-4, distance+4
            if groups and left <= groups[-1][1]+2:
                groups[-1][1] = max(groups[-1][1], right)
                groups[-1][2].append(crossing)
            else:
                groups.append([left, right, [crossing]])
        for left, right, covered in groups:
            middle = (left+right)/2
            bridges.append(dict(edge=edge, segment=segment,
                                start=(a[0]+left*dx, a[1]+left*dy),
                                control=(a[0]+middle*dx+(8 if dy else 0),
                                         a[1]+middle*dy-(8 if dx else 0)),
                                end=(a[0]+right*dx, a[1]+right*dy), crossings=covered))
    return bridges



def render_flow(b: dict, ident: str, *, accepted: bool = False) -> str:
    g = flow_layout(b, accepted=accepted)
    interactive = bool(b.get("steps"))
    out = [f'<section class="flow" data-interactive="{str(interactive).lower()}" aria-label="Architecture walkthrough" id="{ident}">',
           f'<svg class="flow-svg" viewBox="0 0 {g["width"]} {g["height"]}" role="img" aria-labelledby="{ident}-title">',
           f'<title id="{ident}-title">Architecture; see {"Exact calls for the numbered arrows" if interactive else "Connections for the relationships"} below.</title>',
           f'<defs><marker id="{ident}-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z"/></marker></defs>']

    def label(lines, x, y, css="", anchor=None, edge=None):
        attrs = f' text-anchor="{anchor}" data-edge="{edge}"' if anchor else ""
        return f'<text class="{css}" x="{x}" y="{y}"{attrs}>' + "".join(
            f'<tspan x="{x}" dy="{0 if i == 0 else 18}">{esc(line)}</tspan>' for i, line in enumerate(lines)) + '</text>'

    for f in g["frames"]:
        out.append(f'<g class="flow-frame" data-frame="{esc(f["id"])}"><rect x="{f["x"]}" y="{f["y"]}" width="{f["w"]}" height="{f["h"]}" rx="8"/>'
                   + label(f["lines"], f["x"]+8, f["y"]+17) + '</g>')
    for i, (edge, route) in enumerate(zip(b["edges"], g["routes"])):
        d = f"M {route[0][0]},{route[0][1]}"
        for segment, end in enumerate(route[1:]):
            for bridge in g.get("bridges", []):
                if (bridge["edge"], bridge["segment"]) == (i, segment):
                    a, c, z = bridge["start"], bridge["control"], bridge["end"]
                    d += f" L {a[0]},{a[1]} Q {c[0]},{c[1]} {z[0]},{z[1]}"
            d += f" L {end[0]},{end[1]}"
        out.append(f'<path class="flow-edge" data-edge="{i}" data-from="{esc(edge["from"])}" data-to="{esc(edge["to"])}" '
                   f'data-kind="{esc(edge.get("kind", "sync"))}" data-dashed="{str(edge.get("dashed", False)).lower()}" d="{d}" marker-end="url(#{ident}-arrow)"><title>{esc(edge["label"])}</title></path>')
    # Paint overpasses last so an earlier edge can pass above a later edge.
    for bridge in g.get("bridges", []):
        i = bridge["edge"]
        a, c, z = bridge["start"], bridge["control"], bridge["end"]
        d = f"M {a[0]},{a[1]} Q {c[0]},{c[1]} {z[0]},{z[1]}"
        out.append(f'<path class="flow-bridge-clearance" d="{d}"/>'
                   f'<path class="flow-bridge" data-edge="{i}" d="{d}"/>')
    for key, n in g["nodes"].items():
        x, y, w, h = n["x"], n["y"], n["w"], n["h"]
        out.append(f'<g class="flow-node" data-node="{esc(key)}" data-kind="{n["kind"]}">')
        if n["kind"] == "store":
            out.append(f'<path d="M{x},{y+9} a{w/2},9 0 0 1 {w},0 v{h-18} a{w/2},9 0 0 1 {-w},0 Z M{x},{y+9} a{w/2},9 0 0 0 {w},0"/>')
        elif n["kind"] == "decision":
            out.append(f'<path d="M{x+w/2},{y} L{x+w},{y+h/2} L{x+w/2},{y+h} L{x},{y+h/2} Z"/>')
        else:
            out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4"/>')
            if n["kind"] == "queue":
                out.append(f'<path d="M{x+7},{y} v{h} M{x+w-7},{y} v{h}"/>')
        baseline = y+(h-len(n["lines"])*18)/2+(18 if n["kind"] == "store" else 14)
        out.append(label(n["lines"], x+w/2, baseline, "flow-label") + '</g>')
    for item in g["labels"]:
        out.append(label(item["lines"], item["x"], item["y"], "flow-edge-label", item.get("anchor"), item["edge"]))
    if not interactive:
        out.append('</svg><details class="flow-connections"><summary>Connections</summary><ul>')
        for edge in b["edges"]:
            source, target = g["nodes"][edge["from"]]["label"], g["nodes"][edge["to"]]["label"]
            text = f'{source} to {target}' + (f': {edge["label"]}' if edge["label"] else '')
            out.append(f'<li>{esc(text)}</li>')
        out.append('</ul></details><noscript>This is a static diagram. Connections lists every relationship.</noscript></section>')
        return "".join(out)
    out += ['<circle class="flow-packet hidden" r="6"/>', '<circle class="flow-queued hidden" r="6"/>', '</svg>',
            '<div class="flow-controls">' + "".join(f'<button type="button" data-action="{action}">{text}</button>' for action, text in
            (("previous", "Back"), ("next", "Next"), ("play", "Play"), ("reset", "Reset"))) + '</div>',
            '<p class="flow-caption" aria-live="polite" aria-atomic="true"></p><p class="flow-mode muted"></p>',
            '<details class="flow-calls"><summary>Exact calls</summary><ol>']
    for step in b["steps"]:
        edge = step["edge"]
        if isinstance(edge, str):
            edge = next(i for i, e in enumerate(b["edges"]) if e.get("id") == edge)
        out.append(f'<li data-edge="{edge}" data-caption="{esc(step["caption"])}" value="{edge+1}"><strong>{esc(b["edges"][edge]["label"])}</strong><br>{esc(step["caption"])}</li>')
    out += ['</ol></details><noscript>Motion is optional. Read the numbered arrows and expand Exact calls for the request order.</noscript></section>']
    return "".join(out)


def render_block(pg: Page, b: dict) -> str:
    t = b["type"]
    cites = cite_marks(pg, b.get("cites"))
    row = f'<p class="cite-row">{cites}</p>' if cites else ""
    if t == "p":
        return f"<p>{esc(b['text'])}{cites}</p>"
    if t == "list":
        tag = "ol" if b.get("ordered") else "ul"
        return f"<{tag}>" + "".join(f"<li>{esc(i)}</li>" for i in b["items"]) + f"</{tag}>{row}"
    if t == "table":
        return table_html(b["columns"], b["rows"], b.get("caption"), cites=cites, pg=pg)
    if t == "code":
        pg.code = True
        cap = f'<p class="muted block-caption">{esc(b["caption"])}</p>' if b.get("caption") else ""
        return cap + code_block(b)
    if t == "callout":
        return (f'<aside class="callout callout-{esc(b["kind"])}"><p><strong class="callout-label">{CALLOUT_LABELS[b["kind"]]}.</strong> '
                f'{esc(b["text"])}{cites}</p></aside>')
    if t == "steps":
        title = f'<p class="steps-title">{esc(b["title"])}</p>' if b.get("title") else ""
        return f'<div class="steps-block">{title}<ol>' + "".join(f"<li>{esc(i)}</li>" for i in b["items"]) + f"</ol>{row}</div>"
    if t == "decision":
        rows = [[r["option"], r["pick_when"], r["avoid_when"], r.get("example", "")] for r in b["rows"]]
        columns = list(DECISION_COLUMNS[:3]) + [DECISION_LAST_EXERCISE if pg.exercise else DECISION_COLUMNS[3]]
        return table_html(columns, rows, b.get("caption"), first_col_head=True, cites=cites)
    if t == "flow":
        pg.flow = True
        pg.flow_count += 1
        return render_flow(b, f"flow-{pg.flow_count}", accepted=pg.accepted_flows and pg.flow_count <= 3) + legend_html(pg, b)
    if t == "diagram":
        pg.diagram = True
        src = esc(b["mermaid"])
        style = ' data-diagram-style="sequence"' if scan.SEQUENCE_START.match(b["mermaid"]) else ""
        return f'<div class="mermaid-wrap"{style}><pre class="mermaid">{src}</pre><pre class="mermaid-fallback">{src}</pre></div>{legend_html(pg, b)}'
    raise BuildError(f"unknown block type {t!r}")


def legend_html(pg: Page, b: dict) -> str:
    """A diagram's legend. A source id in the legend text that is one of the block's cites (the 's12, s25' form a cite column
    uses) renders as that source's linked mark, next to the fact it backs; cites the legend does not name follow at the end."""
    legend, cites = b.get("legend") or "", list(b.get("cites") or [])
    if not legend and not cites:
        return ""
    inline: set[str] = set()

    def mark(m: re.Match) -> str:
        sid = m.group(0)
        if sid in cites and sid in pg.number:
            inline.add(sid)
            return cite_marks(pg, [sid])
        return sid
    text = LEGEND_SOURCE_ID.sub(mark, esc(legend))
    return f'<p class="muted diagram-legend">{text}{cite_marks(pg, [c for c in cites if c not in inline])}</p>'


def render_blocks(pg: Page, blocks) -> str:
    """Blocks, or one block (an exercise field may hold either), as HTML."""
    return "\n".join(render_block(pg, b) for b in scan.as_blocks(blocks))


def render_sources_v2(sources: list[dict]) -> str:
    """The numbered source list (ids s1..sN in order): the cite marks of the page link to each item's id."""
    items = []
    for s in sources:
        v = s.get("verified")
        checked = f' <span class="domain">checked {esc(v["checked"])}</span>' if v and v.get("checked") else ""
        items.append(
            f'<li id="source-{esc(s["id"])}"><span class="kind-badge">{esc(s["kind"])}</span>{ext(s["url"], esc(s["title"]))} '
            f'<span class="domain">({esc(domain_of(s["url"]))})</span>{checked}</li>'
        )
    return f'<ol class="sources-list sources-numbered">{"".join(items)}</ol>'


def render_lesson_v2(lib: Library, l: dict) -> tuple[str, str]:
    """Page order of a :2 lesson: title and attribution, summary, on this page; the teaching (subtopics); the worked example;
    in practice (cited); simulator; technologies, sources, related lessons, the practice link. No 'Read more' box above the teaching."""
    lid = l["id"]
    mid, pos, _ = lib.home_of[lid]
    here = f"/learn/lessons/{lid}/"
    pg = Page(l["sources"])
    body = [f"<h1>{esc(l['title'])}</h1>", attribution(l["provenance"])]
    if l["status"] == "superseded":
        body.append(f'<p class="banner">This lesson is superseded by {a(f"/learn/lessons/{l["superseded_by"]}/", esc(lib.lessons[l["superseded_by"]]["title"]))}.</p>')
    krow = ["Concept: " + a(f"/learn/keys/{l['primary_key']}/", esc(lib.keys[l["primary_key"]]["display"]))]
    if l["secondary_keys"]:
        krow.append("also covers " + ", ".join(a(f"/learn/keys/{k}/", esc(lib.keys[k]["display"])) for k in l["secondary_keys"]))
    line = " &middot; ".join(krow)
    line += f" &middot; Lesson {pos} of {len(lib.module_lessons[mid])} in " + a(f"/learn/modules/{mid}/", esc(lib.modules[mid]["title"]))
    body.append(f'<p class="key-line">{line} &middot; version {l["version"]}</p>')
    body.append(f"<p>{esc(l['summary'])}</p>")
    has_practice_blocks = bool(l["in_practice"]["blocks"])
    otp = [(s["id"], s["title"]) for s in l["subtopics"]]
    if "worked_example" in l:
        otp.append(("worked-example", "Worked example"))
    if has_practice_blocks:
        otp.append(("in-practice", "In practice"))
    body.append('<div class="on-this-page"><p class="otp-title">On this page</p><ul>'
                + "".join(f'<li>{a("#" + i, esc(t))}</li>' for i, t in otp) + "</ul></div>")
    for s in l["subtopics"]:
        body.append(f'<h2 id="{esc(s["id"])}">{esc(s["title"])}</h2>')
        body.append(render_blocks(pg, s["blocks"]))
    if "worked_example" in l:
        we = l["worked_example"]
        body.append(f'<h2 id="worked-example">Worked example</h2>\n<h3>{esc(we["title"])}</h3>')
        body.append(render_blocks(pg, we["blocks"]))
    if has_practice_blocks:
        body.append('<h2 id="in-practice">In practice</h2>')
        body.append(render_blocks(pg, l["in_practice"]["blocks"]))
    if "sim" in l:
        body.append(render_sim(lib, l))
    if l["technologies"]:
        tags = "".join(f"<span>{esc(t)}</span>" for t in l["technologies"])
        body.append(f'<h2>Technologies</h2>\n<div class="tech-tags">{tags}</div>')
    body.append('<h2 id="sources">Sources</h2>')
    body.append(render_sources_v2(l["sources"]))
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
    page = lesson_shell(lib, f"{l['title']} - Learning center", "\n".join(body), mid=mid, current=here, crumbs=crumbs,
                        description=l["summary"][:200], mermaid=pg.diagram, code=pg.code, sim="sim" in l, flow=pg.flow, concept_v2=True)
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


def render_exercise_v2(lib: Library, l: dict) -> tuple[str, str]:
    """A :2 design exercise page: the same eight sections and order as :1, every section through the block renderer."""
    lid, ex = l["id"], l["exercise"]
    here = f"/learn/lessons/{lid}/"
    mid, _, entry = lib.home_of[lid]
    mod_here = f"/learn/modules/{mid}/"
    # The operator accepted these three diagrams pixel-for-pixel before the
    # routing revision. Only those blocks retain the pinned placement.
    pg = Page(l["sources"], exercise=True, accepted_flows=lid == "sd-ex-news-feed")
    body = [f"<h1>{esc(l['title'])}</h1>", exercise_attribution(l["provenance"])]
    krow = ["Concept: " + a(f"/learn/keys/{l['primary_key']}/", esc(lib.keys[l["primary_key"]]["display"]))]
    if l["secondary_keys"]:
        krow.append("also covers " + ", ".join(a(f"/learn/keys/{k}/", esc(lib.keys[k]["display"])) for k in l["secondary_keys"]))
    mod = lib.modules[mid]
    if entry.get("part"):
        part_title = next(p["title"] for p in mod["parts"] if p["id"] == entry["part"])
        krow.append(f"Part {esc(entry['part'])} ({esc(part_title)}) of the " + a(mod_here, esc(mod["title"]) + " module"))
    body.append(f'<p class="key-line">{" &middot; ".join(krow)} &middot; design exercise &middot; version {l["version"]}</p>')
    has_practice_blocks = bool(l["in_practice"]["blocks"])
    otp = [("prompt", "The prompt"), ("constraints", "Constraints and numbers"), ("clarifying-questions", "Clarifying questions worth asking"),
           ("reference-answer", "Reference answer")] + [(sec["id"], sec["title"]) for sec in ex["reference_answer"]] + [
           ("rubric", "Self-check rubric"), ("interview-frame", "The 45-minute interview frame"), ("design-doc-frame", "The design-doc frame"),
           ("depth", "Depth notes")] + ([("in-practice", "In practice")] if has_practice_blocks else []) + [("sources", "Sources"), ("related", "Related lessons")]
    if "sim" in l:
        otp.insert(otp.index(("rubric", "Self-check rubric")), ("simulate", l["sim"].get("heading", "Simulate it")))
    body.append('<div class="on-this-page"><p class="otp-title">On this page</p><ul>' + "".join(f'<li>{a("#" + i, esc(t))}</li>' for i, t in otp) + "</ul></div>")
    body.append(f"<p>{esc(l['summary'])}</p>")
    body.append('<p class="muted">Attempt the design from the prompt, the constraints and the questions before reading the reference answer.</p>')
    body.append(f'<h2 id="prompt">The prompt</h2>\n<p>{esc(ex["prompt"])}</p>')
    body.append('<h2 id="constraints">Constraints and numbers</h2>\n' + render_blocks(pg, ex["constraints"]))
    body.append('<h2 id="clarifying-questions">Clarifying questions worth asking</h2>\n<ul>'
                + "".join(f'<li><strong>{esc(q["q"])}</strong> {esc(q["a"])}</li>' for q in ex["clarifying_questions"]) + "</ul>")
    body.append('<h2 id="reference-answer">Reference answer</h2>')
    for sec in ex["reference_answer"]:
        body.append(f'<h3 id="{esc(sec["id"])}">{esc(sec["title"])}</h3>')
        body.append(render_blocks(pg, sec["blocks"]))
        if sec["id"] == "scaling-and-the-bottleneck" and "sim" in l:
            body.append(render_sim(lib, l, level=3))
    body.append('<h2 id="rubric">Self-check rubric</h2>\n<p class="muted">Read, not scored: find the level your answer reached.</p>')
    for lvl, name in (("L1", "L1, mid-level: applies"), ("L2", "L2, senior: chooses with numbers and defends"), ("L3", "L3, staff: sets the constraint and judges")):
        body.append(f"<h3>{esc(name)}</h3><ul>" + "".join(f"<li>{esc(x)}</li>" for x in ex["rubric"][lvl]) + "</ul>")
    body.append('<h2 id="interview-frame">The 45-minute interview frame</h2>\n' + render_blocks(pg, ex["interview_frame"]))
    body.append('<h2 id="design-doc-frame">The design-doc frame</h2>\n' + render_blocks(pg, ex["design_doc_frame"]))
    body.append('<h2 id="depth">Depth notes</h2>\n<ul>' + "".join(f'<li><strong>{lvl}.</strong> {esc(ex["depth_notes"][lvl])}</li>' for lvl in ("L1", "L2", "L3")) + "</ul>")
    if has_practice_blocks:
        body.append('<h2 id="in-practice">In practice</h2>\n' + render_blocks(pg, l["in_practice"]["blocks"]))
    body.append('<h2 id="sources">Sources</h2>')
    body.append(render_sources_v2(l["sources"]))
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
                        description=l["summary"][:200], mermaid=pg.diagram, code=pg.code, sim="sim" in l, flow=pg.flow)
    return here, page


def render_lesson_page(lib: Library, l: dict) -> tuple[str, str]:
    """The renderer for one lesson file: by schema version, then by kind."""
    exercise = l.get("kind") == "design-exercise"
    if l["schema_version"] == V2:
        return render_exercise_v2(lib, l) if exercise else render_lesson_v2(lib, l)
    return render_exercise(lib, l) if exercise else render_lesson(lib, l)


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
            # Count the common site sheet, not optional same-origin component/theme sheets.
            if (am.get("rel") == "stylesheet" and am["href"] != "/_assets/flow.css"
                    and not am["href"].startswith(("/_assets/hljs/", "/_assets/sim/", "/learn/pagefind/"))):
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
    pages += [render_lesson_page(lib, l) for l in lib.lessons.values()]
    pages += [render_practice(lib, p) for p in lib.practice.values()]
    pages += [render_key(lib, k) for k in lib.keys.values()]
    for url, text in pages:
        write(out, url, text, written)
    # assets, once, at the root (shared by / and /learn/)
    assets = out / "_assets"
    assets.mkdir()
    (assets / "site.css").write_text((ROOT / "assets/course.css").read_text(encoding="utf-8") + "\n" + (ROOT / "assets/site-extra.css").read_text(encoding="utf-8") + SIDEBAR_CSS, encoding="utf-8")
    for name in ("course.js", "theme-init.js", "search.js", "favicon.svg", "flow.js", "flow.css"):
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
