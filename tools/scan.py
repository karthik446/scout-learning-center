#!/usr/bin/env python3
"""The public-material scan and the schema check of content/ (standard library only; exit 1 on any hit).

    python3 tools/scan.py                 content/ : data-free public checks + schema validation of every file
    python3 tools/scan.py --built site    site/    : the no-tracking grep over the built HTML (deploy.md section 6)

The public-repo rule (REPORT-library 3.4): nothing in content/ may hold a posting sentence, a company tied to a posting,
a count of postings, anything of a resume, or anything shaped like a master id. CI has neither postings nor master, so
only the data-free checks run here: forbidden keys at any depth, the master-id shape, the posting-count sentence
pattern, https-only addresses (no localhost). The full shingle scan stays on the machine that exports a course.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- the data-free checks (the patterns are those of gigai.scout.learning_shipped, copied, never imported) -------------
FORBIDDEN_KEYS = frozenset({
    "marker", "evidence", "missing", "corpus", "percent", "in_90d", "any_date", "examples", "company", "phrase",
    "postings_in_90d", "postings_any_date", "postings_90d", "count_in90d", "count_all", "percent_in90d", "percent_all",
    "n_in90d", "n_all", "master", "resume",
})
# The shipped scanner forbids 'phrase' because a catalog vocabulary holds posting phrases; the site's key list holds
# aliases (key 'aliases'), never 'phrase'/'phrases' fields, so the same list applies.
ID_SHAPE = re.compile(r"(?<![a-z0-9-])(?:sum|[a-z]{1,2})-[0-9a-f]{6}(?![a-z0-9])")
_NUMBER = (
    r"(?:\d+(?:[.,]\d+)*%?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
    r"|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundreds?|thousands?|dozens?|half|thirds?|quarters?|fifths?|tenths?)"
)
_GAP = r"(?:[\w'%-]+,?\s+){0,3}?"
POSTING_COUNT = re.compile(
    rf"(?i)(?<![\w.,]){_NUMBER}(?![\w])\s+{_GAP}(?:(?:job\s+)?postings?|job\s+ads?|(?:job\s+)?listings?)\b"
    rf"|\b(?:(?:job\s+)?postings|job\s+posting|job\s+ads?|job\s+listings?)\b[\s:(,-]+{_GAP}{_NUMBER}(?![\w])"
    rf"|\bnamed\s+in\s+your\s+{_GAP}postings\b|\byour\s+stored\s+postings\b"
)
N_OF_M = re.compile(r"(?i)\b\d+\s+of\s+\d+\s+(?:stored\s+)?postings\b")
URL_KEYS = frozenset({"url", "href"})
URL_OK = re.compile(r"^https://[^\s/@:]+(?::\d+)?(?:[/?#]\S*)?$")
LOCAL_HOST = re.compile(r"(?i)^https?://(?:localhost|127\.|0\.0\.0\.0|\[::1\]|10\.|192\.168\.|169\.254\.)")


def walk(obj, path="$"):
    """Yield (path, key, value) for every dict entry and (path, None, value) for every list item, at any depth."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}.{k}", k, v
            yield from walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield f"{path}[{i}]", None, v
            yield from walk(v, f"{path}[{i}]")


def public_checks(name: str, doc) -> list[str]:
    problems: list[str] = []
    for path, key, value in walk(doc):
        if key is not None and key in FORBIDDEN_KEYS:
            problems.append(f"{name}: {path}: forbidden key '{key}'")
        if isinstance(value, str):
            is_url = key in URL_KEYS
            if is_url:
                if LOCAL_HOST.match(value):
                    problems.append(f"{name}: {path}: local address {value!r}")
                elif not URL_OK.match(value):
                    problems.append(f"{name}: {path}: address is not a plain https URL: {value!r}")
                continue
            if N_OF_M.search(value):
                problems.append(f"{name}: {path}: 'N of M postings' sentence")
            m = POSTING_COUNT.search(value)
            if m:
                problems.append(f"{name}: {path}: posting-count sentence {m.group(0)!r}")
            m = ID_SHAPE.search(value)
            if m and key not in ("id", "key", "lesson", "primary_key", "parent", "tool_key", "n"):
                problems.append(f"{name}: {path}: master-id shape {m.group(0)!r}")
            m = re.search(r"(?i)\bhttp://(?!localhost\b|127\.0\.0\.1\b)\S+", value)
            if m and key not in ("code", "source"):
                problems.append(f"{name}: {path}: plain http address outside a code block: {m.group(0)!r}")
    return problems


# --- schemas (a small declarative spec per document type, in the spirit of check_examples.py) ---------------------------
N = type(None)


def _t(spec, value, path, out):
    """Validate ``value`` against ``spec``: a type, a tuple of types, None (any), ['x'] a list of spec, {...} an object."""
    if spec is None:  # any value
        return
    if isinstance(spec, dict):
        if not isinstance(value, dict):
            out.append(f"{path}: expected an object, got {type(value).__name__}")
            return
        for field, sub in spec.items():
            optional = field.endswith("?")
            fname = field.rstrip("?")
            if fname not in value:
                if not optional:
                    out.append(f"{path}.{fname}: missing")
                continue
            _t(sub, value[fname], f"{path}.{fname}", out)
        return
    if isinstance(spec, list):
        if not isinstance(value, list):
            out.append(f"{path}: expected a list, got {type(value).__name__}")
            return
        for i, item in enumerate(value):
            _t(spec[0], item, f"{path}[{i}]", out)
        return
    if isinstance(spec, tuple):  # any one of several specs
        for alt in spec:
            trial: list[str] = []
            _t(alt, value, path, trial)
            if not trial:
                return
        out.append(f"{path}: matches none of the allowed shapes ({type(value).__name__})")
        return
    if spec is N:
        if value is not None:
            out.append(f"{path}: expected null")
        return
    if spec is int:
        ok = isinstance(value, int) and not isinstance(value, bool)
    else:
        ok = isinstance(value, spec)
    if not ok:
        out.append(f"{path}: expected {spec.__name__}, got {type(value).__name__}")


VERIFIED = {"checked": str, "http?": int, "section_found?": (str, N), "status?": str, "note?": str}
SOURCE = {"kind": str, "title": str, "url": str, "verified?": VERIFIED}
PROVENANCE = {"generated_by": str, "generated_on": str, "reviewed_by": (str, N), "reviewed_on": (str, N)}
CHANGELOG = [{"version": int, "date": str, "change": str}]
STEP = {"n": int, "do": str, "done_when": str, "why?": str, "source": {"title": str, "url": str, "verified?": VERIFIED}}
# A design exercise (kind "design-exercise", outline section 6.1): the prompt, the numbers, the reference answer in fixed
# sections with one Mermaid diagram, the rubric by level, the two frames and the depth notes. Written by hand, not by the pipeline.
SECTIONS = [{"heading?": str, "body": str}]
EXERCISE = {
    "prompt": str,
    "constraints": SECTIONS,
    "clarifying_questions": [{"question": str, "answer": str}],
    "reference_answer": [{"id": str, "title": str, "body": SECTIONS, "diagram?": {"source": str, "legend?": str},
                          "steps?": [str], "table?": {"columns": [str], "rows": [[str]]}}],
    "rubric": {"L1": [str], "L2": [str], "L3": [str]},
    "interview_frame": [{"time": str, "text": str}],
    "design_doc_frame": [{"section": str, "text": str}],
    "depth_notes": {"L1": str, "L2": str, "L3": str},
}
EXERCISE_SECTION_IDS = ["requirements-and-estimates", "high-level-design", "data-model", "core-flow", "scaling-and-the-bottleneck",
                        "failure-modes", "trade-offs", "at-10x"]
TITLED_BODY = {"title": str, "body": str}
DIAGRAM_START = re.compile(r"^\s*(flowchart|graph)\s")

# --- the written practice pages (kind "case" and "artifact"): the generator's shapes and text checks ----------------------
# Bounds as gigai.scout.learning_case (copied, never imported): (min, max) counts.
PRACTICE_KINDS = ("tool", "case", "artifact")
SCENARIO_SENTENCES = (3, 6)
CONSTRAINTS = (3, 8)
ANSWER_SECTIONS = (5, 9)
RUBRIC = (6, 12)
MISTAKES = (3, 6)
TEMPLATE_SECTIONS = (6, 12)
CHECKLIST = (6, 12)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
# A written page cites nothing: no address in any form, no backtick, and no name that reads as a real company
# (a legal-form suffix after a capitalised word; every product and company on such a page is invented).
ANY_URL = re.compile(r"(?i)\b(?:https?|ftp)://|\bwww\.|\b[a-z0-9-]+\.(?:com|org|net|io|dev|ai|app|co|edu|gov|cloud|info)\b(?:/|\b)")
COMPANY_SHAPE = re.compile(r"\b[A-Z][\w&'-]+(?:\s+[A-Z][\w&'-]+)*,?\s+(?:Inc|LLC|Ltd|Corp|Corporation|GmbH|PLC|Plc|AG|S\.A|Co)\b\.?")


def sentences(text: str) -> list[str]:
    return [part for part in SENTENCE_END.split(text.strip()) if part.strip()]


def written_text_problems(text: str) -> list[str]:
    """Why a string may not stand on a case or artifact page (reasons only); the checks import_course.py reuses."""
    out = []
    if ANY_URL.search(text):
        out.append("holds an address")
    if "`" in text:
        out.append("holds a backtick")
    m = COMPANY_SHAPE.search(text)
    if m:
        out.append(f"holds a company-looking name {m.group(0)!r}")
    return out


def written_checks(name: str, doc: dict) -> list[str]:
    """Shape bounds and text checks of one case or artifact practice file (the schema has already passed)."""
    out: list[str] = []

    def bounded(label, items, bounds):
        if not bounds[0] <= len(items) <= bounds[1]:
            out.append(f"{name}: {label} holds {len(items)} items; {bounds[0]} to {bounds[1]} needed")

    for path, key, value in walk(doc):
        if key in URL_KEYS:
            out.append(f"{name}: {path}: a written practice page holds no address field")
        if isinstance(value, str) and key not in ("schema_version", "id", "lesson", "kind", "written_by", "generated_by", "generated_on", "reviewed_by", "reviewed_on", "date", "version"):
            out.extend(f"{name}: {path}: {why}" for why in written_text_problems(value))
    if doc["kind"] == "case":
        n = len(sentences(doc["scenario"]))
        if not SCENARIO_SENTENCES[0] <= n <= SCENARIO_SENTENCES[1]:
            out.append(f"{name}: scenario holds {n} sentences; {SCENARIO_SENTENCES[0]} to {SCENARIO_SENTENCES[1]} needed")
        bounded("constraints", doc["constraints"], CONSTRAINTS)
        bounded("reference_answer", doc["reference_answer"], ANSWER_SECTIONS)
        bounded("rubric", doc["rubric"], RUBRIC)
        bounded("common_mistakes", doc["common_mistakes"], MISTAKES)
    else:
        bounded("template", doc["template"], TEMPLATE_SECTIONS)
        bounded("review_checklist", doc["review_checklist"], CHECKLIST)
        ex = doc["reference_example"]
        if ex["written_by"] != "model":
            out.append(f"{name}: reference_example.written_by must be 'model'")
        if len(ex["sections"]) != len(doc["template"]):
            out.append(f"{name}: reference_example holds {len(ex['sections'])} sections; the template has {len(doc['template'])}")
    return out


def practice_kind(doc) -> str:
    """The kind of a practice document; a file with no kind is a tool path."""
    return doc.get("kind", "tool") if isinstance(doc, dict) else "tool"


SCHEMAS = {
    "lesson": {
        "schema_version": str, "id": str, "version": int, "status": str, "superseded_by": (str, N), "title": str, "area": str,
        "primary_key": str, "secondary_keys": [str], "keys": [str], "summary": str, "detail": [{"heading?": str, "body": str}],
        "in_practice": str,
        "subtopics": [{"id": str, "title": str, "body": [{"heading?": str, "body": str}]}],
        "diagram": ({"source": str}, N), "code": [{"lang": str, "code": str}], "technologies": [str], "related": [str],
        "sources": [SOURCE], "practice": (str, N), "provenance": PROVENANCE, "changelog": CHANGELOG,
        "kind?": str, "exercise?": EXERCISE,
    },
    "practice": {
        "schema_version": str, "id": str, "version": int, "lesson": str, "tool": str, "tool_key": (str, N),
        "why_this_tool": str, "alternatives": str, "setup": [STEP], "steps": [STEP], "sources": [SOURCE],
        "verified": {"checked": str, "by": str}, "provenance": PROVENANCE, "changelog": CHANGELOG, "kind?": str,
    },
    "practice-case": {
        "schema_version": str, "id": str, "version": int, "lesson": str, "kind": str, "scenario": str, "constraints": [str],
        "deliverable": str, "reference_answer": [TITLED_BODY], "rubric": [str], "common_mistakes": [str],
        "provenance": PROVENANCE, "changelog": CHANGELOG,
    },
    "practice-artifact": {
        "schema_version": str, "id": str, "version": int, "lesson": str, "kind": str, "artifact_name": str,
        "template": [{"title": str, "prompt": str}],
        "reference_example": {"situation": str, "sections": [TITLED_BODY], "written_by": str}, "review_checklist": [str],
        "provenance": PROVENANCE, "changelog": CHANGELOG,
    },
    "pathway": {
        "schema_version": str, "id": str, "version": int, "title": str, "family": str, "role_key": str,
        "titles": {"phrases": [str], "deny": [str]}, "summary": str, "shared_modules": [str],
        "modules": [{"id": str, "title": str, "intro": str}], "expectations": None, "technologies": None,
        "steps": [{"n": int, "lesson": str, "module": str, "depth": str, "why": str, "prerequisites": [str]}],
        "changelog": CHANGELOG,
    },
    "module": {
        "schema_version": str, "id": str, "version": int, "title": str, "status": str, "summary": str,
        "parts": [{"id": str, "title": str}],
        "lessons": [{"id": str, "title": str, "part": str, "part_title": str, "status": str}],
    },
    "family": {
        "schema_version": str, "id": str, "version": int, "title": str, "status": str, "summary": str,
        "roles": [{"key": str, "title": str, "pathway": str}], "shared_modules": [str],
    },
    "families": {
        "schema_version": str, "version": int,
        "families": [{"id": str, "title": str, "status": str, "summary": str}],
    },
    "redirects": {"schema_version": str, "redirects": [{"from": str, "to": str, "since": str, "reason": str}]},
    "changelog": {
        "schema_version": str,
        "entries": [{"date": str, "site_version": str, "kind": str, "id": str, "version": int, "change": str}],
    },
    "site": {
        "schema_version": str, "site_version": str, "base_url": str, "concept_keys_version": int, "built_from": str, "updated": str,
    },
    "keys": {
        "schema_version": str, "version": int, "areas": None,
        "keys": [{"key": str, "display": str, "area": str, "category": str, "technical": bool, "aliases": [str], "parent": (str, N)}],
    },
    "merge": {
        "schema_version": str, "note": str,
        "pairs": [{"a": str, "b": str, "jaccard": (int, float), "action": str, "shared_keys": [str]}],
    },
}
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
AREAS = {"ai-ml", "infra", "software", "data", "security", "delivery", "career", "domains"}


def load_all(content: Path) -> tuple[dict, list[str]]:
    """Parse every JSON file under content/; returns ({relative path: document}, parse problems)."""
    docs, problems = {}, []
    for p in sorted(content.rglob("*.json")):
        rel = p.relative_to(content).as_posix()
        try:
            docs[rel] = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001 - report any parse failure as a problem
            problems.append(f"{rel}: does not parse: {e}")
    return docs, problems


def kind_of(rel: str) -> str | None:
    if rel.startswith("lessons/"):
        return "lesson"
    if rel.startswith("practice/"):
        return "practice"
    if rel.startswith("pathways/"):
        return "pathway"
    if rel.startswith("modules/"):
        return "module"
    if rel == "families/index.json":
        return "families"
    if rel.startswith("families/"):
        return "family"
    return {"redirects.json": "redirects", "changelog.json": "changelog", "site.json": "site",
            "keys/concept-keys.json": "keys", "merge-candidates.json": "merge"}.get(rel)


def validate(docs: dict) -> list[str]:
    out: list[str] = []
    for rel, doc in docs.items():
        kind = kind_of(rel)
        if kind is None:
            out.append(f"{rel}: not a known content file")
            continue
        errs: list[str] = []
        if kind == "practice":
            pk = practice_kind(doc)
            if pk not in PRACTICE_KINDS:
                out.append(f"{rel}: unknown practice kind {pk!r}")
                continue
            kind = "practice" if pk == "tool" else f"practice-{pk}"
        _t(SCHEMAS[kind], doc, "$", errs)
        out.extend(f"{rel}: {e}" for e in errs)
        out.extend(public_checks(rel, doc))
        if kind in ("practice-case", "practice-artifact") and not errs:
            out.extend(written_checks(rel, doc))
    if out:
        return out  # reference checks need well-formed documents

    keys = {k["key"]: k for k in docs["keys/concept-keys.json"]["keys"]}
    if len(keys) != len(docs["keys/concept-keys.json"]["keys"]):
        out.append("keys: duplicate key")
    alias_owner: dict[str, str] = {}
    for k in keys.values():
        if not KEBAB.match(k["key"]) or not 2 <= len(k["key"]) <= 48:
            out.append(f"keys: bad key id {k['key']!r}")
        if k["area"] not in AREAS:
            out.append(f"keys: {k['key']}: unknown area {k['area']!r}")
        if k["parent"] and k["parent"] not in keys:
            out.append(f"keys: {k['key']}: unknown parent {k['parent']}")
        for a in k["aliases"]:
            if alias_owner.setdefault(a, k["key"]) != k["key"]:
                out.append(f"keys: alias {a!r} owned by {alias_owner[a]} and {k['key']}")

    lessons = {d["id"]: d for r, d in docs.items() if r.startswith("lessons/")}
    practice = {d["lesson"]: d for r, d in docs.items() if r.startswith("practice/")}
    sd_ids = {l["id"] for l in docs["modules/system-design.json"]["lessons"]}
    for rel, d in docs.items():
        if rel.startswith(("lessons/", "practice/", "pathways/")) and Path(rel).stem != (d["id"].split("/")[-1]):
            out.append(f"{rel}: file name does not match id {d['id']}")
    for lid, l in lessons.items():
        w = f"lessons/{lid}"
        if not KEBAB.match(lid):
            out.append(f"{w}: id is not kebab-case")
        if l["status"] not in ("draft", "published", "superseded"):
            out.append(f"{w}: bad status {l['status']!r}")
        if l["status"] == "superseded" and l["superseded_by"] not in lessons:
            out.append(f"{w}: superseded_by names an unknown lesson")
        if l["version"] < 1 or l["changelog"][-1]["version"] != l["version"]:
            out.append(f"{w}: version does not match the last changelog entry")
        p = l["provenance"]
        if not p["generated_by"].strip() or not DATE.match(p["generated_on"]):
            out.append(f"{w}: provenance.generated_by is empty or generated_on is not a date")
        if p["reviewed_by"] and not (p["reviewed_on"] and DATE.match(p["reviewed_on"])):
            out.append(f"{w}: reviewed_by is set without a reviewed_on date")
        if (p["reviewed_on"] or p["reviewed_by"] is None) and p["reviewed_by"] is None and p["reviewed_on"]:
            out.append(f"{w}: reviewed_on is set without reviewed_by")
        if not l["keys"] or l["keys"][0] != l["primary_key"] or l["keys"][1:] != l["secondary_keys"]:
            out.append(f"{w}: keys must be [primary_key] + secondary_keys")
        for k in l["keys"]:
            if k not in keys:
                out.append(f"{w}: unknown key {k}")
        if l["area"] != keys.get(l["primary_key"], {}).get("area"):
            out.append(f"{w}: area differs from the primary key's area")
        ids = [s["id"] for s in l["subtopics"]]
        if len(set(ids)) != len(ids) or not all(KEBAB.match(i) for i in ids):
            out.append(f"{w}: subtopic ids must be unique kebab-case")
        ex = l.get("kind") == "design-exercise"
        if "kind" in l and not ex:
            out.append(f"{w}: unknown kind {l['kind']!r}")
        if not l["subtopics"] and not ex:
            out.append(f"{w}: no subtopics")
        if ex:
            out.extend(f"{w}: {e}" for e in exercise_checks(l))
        for r in l["related"]:
            if r not in lessons and not (ex and r in sd_ids):
                out.append(f"{w}: related names unknown lesson {r}")
        if (l["practice"] is None) != (lid not in practice):
            out.append(f"{w}: 'practice' pointer and practice file disagree")
        elif l["practice"] and l["practice"] != practice[lid]["id"]:
            out.append(f"{w}: practice pointer {l['practice']} != {practice[lid]['id']}")
    for lid, pr in practice.items():
        w = f"practice/{lid}"
        if lid not in lessons:
            out.append(f"{w}: lesson does not exist")
        if not pr["provenance"]["generated_by"].strip():
            out.append(f"{w}: provenance.generated_by is empty")
        if practice_kind(pr) != "tool":
            continue
        if len(pr["steps"]) < 6:
            out.append(f"{w}: fewer than 6 steps")
        if pr["tool_key"] and pr["tool_key"] not in keys:
            out.append(f"{w}: unknown tool_key")
        for s in pr["setup"] + pr["steps"]:
            if not s["source"].get("verified", {}).get("checked"):
                out.append(f"{w}: step {s['n']} has no verified.checked date")
    seen_in_pathway: set[str] = set()
    pathways = {d["id"]: d for r, d in docs.items() if r.startswith("pathways/")}
    families = {d["id"]: d for r, d in docs.items() if r.startswith("families/") and r != "families/index.json"}
    for pid, pw in pathways.items():
        w = f"pathways/{pid}"
        if pw["family"] not in families:
            out.append(f"{w}: unknown family {pw['family']}")
        mods = {m["title"] for m in pw["modules"]}
        seen = set()
        for i, s in enumerate(pw["steps"], 1):
            if s["n"] != i:
                out.append(f"{w}: step numbers are not 1..N in order")
            if s["lesson"] not in lessons:
                out.append(f"{w}: step {s['n']} names unknown lesson {s['lesson']}")
            if s["lesson"] in seen:
                out.append(f"{w}: lists lesson {s['lesson']} twice")
            seen.add(s["lesson"])
            if s["module"] not in mods:
                out.append(f"{w}: step {s['n']} module {s['module']!r} is not a module of the pathway")
            if s["depth"] not in ("L1", "L2", "L3"):
                out.append(f"{w}: step {s['n']} bad depth")
            if not s["why"].strip():
                out.append(f"{w}: step {s['n']} has no 'why'")
            for pre in s["prerequisites"]:
                if pre not in sd_ids:
                    out.append(f"{w}: step {s['n']} prerequisite {pre} is not an sd- lesson")
        for grp in ("expectations", "technologies"):
            for g, ks in pw[grp].items():
                for k in ks:
                    if k not in keys:
                        out.append(f"{w}: {grp}.{g} names unknown key {k}")
        for m in pw["shared_modules"]:
            if f"modules/{m}.json" not in docs:
                out.append(f"{w}: unknown shared module {m}")
        seen_in_pathway |= seen
    for fid, fam in families.items():
        for r in fam["roles"]:
            if r["pathway"] not in pathways:
                out.append(f"families/{fid}: role {r['key']} names unknown pathway {r['pathway']}")
    index_ids = [f["id"] for f in docs["families/index.json"]["families"]]
    for fid in families:
        if fid not in index_ids:
            out.append(f"families/index.json: published family {fid} is not listed")
    for f in docs["families/index.json"]["families"]:
        if (f["status"] == "published") != (f["id"] in families):
            out.append(f"families/index.json: {f['id']} status {f['status']} does not match its file")
    mod = docs["modules/system-design.json"]
    if len(mod["lessons"]) != 40 or any(l["status"] not in ("planned", "published") or not l["id"].startswith("sd-") for l in mod["lessons"]):
        out.append("modules/system-design.json: expected 40 sd- lessons, each planned or published")
    if len({l["id"] for l in mod["lessons"]}) != len(mod["lessons"]):
        out.append("modules/system-design.json: duplicate lesson id")
    for l in mod["lessons"]:
        if l["status"] == "planned" and l["id"] in lessons:
            out.append(f"modules/system-design.json: {l['id']} is planned but a lesson file exists")
        if l["status"] == "published" and (l["id"] not in lessons or lessons[l["id"]]["status"] != "published"):
            out.append(f"modules/system-design.json: {l['id']} is published but no published lesson file exists")
    for r in docs["redirects.json"]["redirects"]:
        m = re.match(r"^/learn/lessons/([a-z0-9-]+)/$", r["to"])
        if not m or m.group(1) not in lessons:
            out.append(f"redirects.json: redirect to an unknown lesson {r['to']}")
    ids = {l for l in lessons}
    for p in docs["merge-candidates.json"]["pairs"]:
        if p["a"] not in ids or p["b"] not in ids:
            out.append(f"merge-candidates.json: unknown lesson in {p['a']}/{p['b']}")
    site = docs["site.json"]
    if site["base_url"] != "https://scout.edgelab.one/learn" or site["concept_keys_version"] != docs["keys/concept-keys.json"]["version"]:
        out.append("site.json: base_url or concept_keys_version does not match")
    for e in docs["changelog.json"]["entries"]:
        if not DATE.match(e["date"]):
            out.append("changelog.json: bad date")
    return out


# --- the no-tracking grep over the built HTML (deploy.md section 6) -------------------------------------------------------
class _Scan(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.problems: list[str] = []
        self.inline_script = False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        for k, v in a.items():
            if k.startswith("on"):
                self.problems.append(f"inline event handler {k}=")
        if tag == "script":
            src = a.get("src")
            if src is None:
                self.problems.append("inline <script>")
            elif re.match(r"(?i)^(?:https?:)?//", src):
                self.problems.append(f"script from another origin: {src}")
        if tag == "link" and re.match(r"(?i)^(?:https?:)?//", a.get("href", "")):
            self.problems.append(f"<link> to another origin: {a['href']}")
        if tag in ("iframe", "frame", "embed", "object", "audio", "video", "source", "img", "form"):
            if tag in ("iframe", "frame", "embed", "object"):
                self.problems.append(f"<{tag}> is not allowed")
            for k in ("src", "srcset", "data", "action"):
                if re.match(r"(?i)^(?:https?:)?//", a.get(k, "")):
                    self.problems.append(f"<{tag} {k}> to another origin: {a[k]}")
        if tag == "meta" and a.get("http-equiv", "").lower() == "refresh" and re.search(r"(?i)url=\s*(?:https?:)?//", a.get("content", "")):
            self.problems.append("meta refresh to another origin")
        if tag == "base":
            self.problems.append("<base> is not allowed")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


CSS_URL = re.compile(r"(?i)url\(\s*['\"]?(?:https?:)?//|@import")
TRACKERS = re.compile(r"(?i)google-analytics|googletagmanager|gtag\(|plausible\.io|cloudflareinsights|static\.cloudflareinsights|beacon\.min\.js|fbq\(|hotjar|segment\.com|matomo|piwik|mixpanel|sentry\.io|doubleclick")


def exercise_checks(l: dict) -> list[str]:
    """The rules of a design exercise beyond its shape: the eight sections in order, one flowchart, 8 to 12 rubric lines, 3+ sources."""
    out: list[str] = []
    if "exercise" not in l:
        return ["kind is design-exercise but there is no 'exercise' object"]
    ex = l["exercise"]
    if not l["summary"].strip() or not ex["prompt"].strip():
        out.append("summary and exercise.prompt must not be empty")
    ids = [sec["id"] for sec in ex["reference_answer"]]
    if ids != EXERCISE_SECTION_IDS:
        out.append(f"reference_answer sections must be exactly {EXERCISE_SECTION_IDS} in that order, got {ids}")
    diagrams = [sec for sec in ex["reference_answer"] if sec.get("diagram")]
    if len(diagrams) != 1 or diagrams[0]["id"] != "high-level-design":
        out.append("exactly one diagram, in the high-level-design section")
    for sec in diagrams:
        if not DIAGRAM_START.match(sec["diagram"]["source"]):
            out.append("the diagram must be a Mermaid flowchart (source starts with 'flowchart' or 'graph')")
        if re.search(r"(?i)^\s*C4", sec["diagram"]["source"]) or "%%{" in sec["diagram"]["source"]:
            out.append("no C4 syntax and no Mermaid directives in a diagram")
    for sec in ex["reference_answer"]:
        t = sec.get("table")
        if t and any(len(r) != len(t["columns"]) for r in t["rows"]):
            out.append(f"section {sec['id']}: every table row must have {len(t['columns'])} cells")
    if l["diagram"] is not None:
        out.append("a design exercise carries its diagram inside the reference answer, not in 'diagram'")
    n = sum(len(ex["rubric"][k]) for k in ("L1", "L2", "L3"))
    if not 8 <= n <= 12:
        out.append(f"rubric has {n} lines; 8 to 12 required")
    if not 5 <= len(ex["clarifying_questions"]) <= 8:
        out.append(f"{len(ex['clarifying_questions'])} clarifying questions; 5 to 8 required")
    if len(l["sources"]) < 3:
        out.append("a design exercise cites at least 3 sources")
    if len(ex["interview_frame"]) < 3 or len(ex["design_doc_frame"]) < 3:
        out.append("both frames need at least 3 entries")
    return out


def scan_built(site: Path) -> list[str]:
    problems: list[str] = []
    pages = sorted(site.rglob("*.html"))
    if not pages:
        return [f"{site}: no HTML files"]
    for p in pages:
        rel = p.relative_to(site).as_posix()
        text = p.read_text(encoding="utf-8")
        s = _Scan()
        s.feed(text)
        problems.extend(f"{rel}: {m}" for m in sorted(set(s.problems)))
        if TRACKERS.search(text):
            problems.append(f"{rel}: analytics or tracker string {TRACKERS.search(text).group(0)!r}")
        if CSS_URL.search(text):
            problems.append(f"{rel}: CSS url()/@import to another origin")
        if "set-cookie" in text.lower() or "document.cookie" in text.lower():
            problems.append(f"{rel}: cookie code")
    for p in sorted(site.rglob("*.css")):
        if p.stat().st_size and CSS_URL.search(p.read_text(encoding="utf-8", errors="ignore")):
            # a font or image from another origin; @import is not used by any shipped sheet
            problems.append(f"{p.relative_to(site).as_posix()}: CSS url()/@import to another origin")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--content", type=Path, default=ROOT / "content")
    ap.add_argument("--built", type=Path, help="scan a built site folder instead of content/")
    args = ap.parse_args()
    if args.built:
        problems = scan_built(args.built)
        label = f"built site {args.built}: {len(list(args.built.rglob('*.html')))} HTML files"
    else:
        docs, problems = load_all(args.content)
        problems += validate(docs) if not problems else []
        label = f"content {args.content}: {len(docs)} files"
    for p in problems[:200]:
        print("  " + p)
    print(f"scan: {label}; {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
