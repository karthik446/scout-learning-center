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
import functools
import hashlib
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
# --- the AI engineering track: Markdown pages under content/ai-engineering (specs/BUILD-TRACK, BUILD-TRACK-D) ------------
# The 12 files are byte copies of the build guide (tools/import_build_track.py); they must render with tools/mdlite.py,
# pass the text rules above, name no workstation path, no "operator", no bead id, carry the disclaimer quote within their
# first three blocks, and every relative link must resolve to one of the 12 pages (with a heading id when it has a fragment).
BUILD_TRACK_DIR = Path("ai-engineering")
BUILD_TRACK_FILES = ("README.md", "SETUP.md", "SCHEDULE.md", *(f"week-{n}.md" for n in range(1, 10)))
DISCLAIMER = ('> *"Educational software. Not investment advice. No orders are placed; trades are hypothetical and settled from '
              'historical bars by written rules. Past results, including these, do not predict future results."*')
BEAD_ID = re.compile(r"\b(?:gigai-[a-z0-9]+\.\d+|csy\.\d+)\b")   # `gigai-core` has no .N and is a package name
OPERATOR = re.compile(r"(?<![\w/-])(?<!GPU )[Oo]perators?\b")       # "NVIDIA GPU Operator" and its URL slug are a product


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
AWS_SECTION = "building-it-on-aws"   # :2 only, optional, right after high-level-design (format v2 addendum B)
EXERCISE2_SECTION_IDS = EXERCISE_SECTION_IDS[:2] + [AWS_SECTION] + EXERCISE_SECTION_IDS[2:]
# The AWS section's shape (orchestrator #46 and #50, 2026-10-15; the split of 2026-10-15): it opens with the AWS architecture
# as one flow block or as two (a write half and a read half), the leading blocks; every later diagram block is a sequence
# diagram (the write and read paths through the services, split at their boundaries, with their failure branches); it
# carries at least one decision block (the choices as decisions, not prices) and holds at most one cost table, which comes
# last. A table is a cost table when any column header contains "monthly", "cost" or "price" (case-insensitive). Elsewhere
# in an exercise a diagram belongs in high-level-design (one flow block) or in core-flow (sequence diagrams may stand in for
# the steps block); a Mermaid flowchart or graph is refused anywhere in an exercise, as in a concept lesson. A sequence diagram
# anywhere has at most MAX_SEQUENCE_PARTICIPANTS lanes, declared or implied by its arrows: Mermaid gives each lane about
# 200 px, so five is what the 1280 lesson column holds without sideways scrolling.
AWS_COST_COLUMN = re.compile(r"(?i)monthly|cost|price")
AWS_MAX_LEADING_FLOWS = 2
MAX_SEQUENCE_PARTICIPANTS = 5
# A flow block has at most MAX_FLOW_NODES nodes: up to 12 start in the established two-lane layout, 13 to 16 on the grid of up
# to three boxes per row (tools/build.py). Measured (F2-FLOW-LIMIT, 54 synthetic graphs of 13 to 18 nodes): every graph
# routes; the 13 to 16-node ones are 736 to 1,534 px tall at the 760 px SVG width with 16 px text (the tallest earlier
# diagram is 2,090 px) and lay out in at most 36 s, the 17 and 18-node worst cases are 2,798 px and 56 s.
MAX_FLOW_NODES = 16
TITLED_BODY = {"title": str, "body": str}
FLOWCHART_START = re.compile(r"^\s*(flowchart|graph)\s")
SEQUENCE_START = re.compile(r"^\s*sequenceDiagram\s")
SEQUENCE_PARTICIPANT = re.compile(r"^\s*(?:participant|actor)\s+([^\s:]+)")
SEQUENCE_ARROW = re.compile(r"^\s*([^\s:<>+-][^\s:<>]*?)\s*(?:-->>|->>|--\)|-\)|--x|-x|-->|->)[+-]?\s*([^\s:<>+-][^\s:<>]*?)\s*:")


def sequence_participants(mermaid: str) -> set[str]:
    """The lanes of a Mermaid sequence diagram: the declared participants and actors plus the ends of every arrow."""
    names: set[str] = set()
    for line in mermaid.splitlines():
        m = SEQUENCE_PARTICIPANT.match(line)
        if m:
            names.add(m.group(1))
            continue
        m = SEQUENCE_ARROW.match(line)
        if m:
            names.update(m.groups())
    return names


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


# --- the simulator: scenario files (content/scenarios/<id>.json) and the `sim` field of a lesson (plan 7.2, 7.3) ------------
# A scenario is complete on its own: every node carries all nine base config fields (their file reader insists on them, so a
# scenario also opens in their app), no defaults are inherited. Node kinds are copied from vendor/breakscale/types.ts, never imported.
SIM_NODE_KINDS = frozenset(
    "client lb service cache db queue worker autoscaler region cdn ratelimiter breaker replica shard objectstore searchindex "
    "timeseriesdb graphdb coldstorage vectordb streambroker pubsub websocket apigateway sidecar lambda cron bulkhead retryqueue "
    "transcoder edgecompute writebehind loadshedder".split())
SIM_BASE_FIELDS = ("capacity", "serviceMs", "serviceCv", "queueLimit", "hitRate", "errorRate", "timeoutMs", "retries", "rps")
SIM_METRICS = frozenset("p50 p95 p99 goodput offered errors".split())
SIM_NODE_METRICS = frozenset("util queue arrival shed timeout hit throttled rejected breaker stale lag".split())
SIM_OPS = ("<", "<=", ">", ">=", "between")
SIM_NODE = {"id": str, "kind": str, "label": str, "x": int, "y": int, "config": None}
SIM_KNOB = {"id": str, "label": str, "node": str, "field": str, "min": (int, float), "max": (int, float), "step": (int, float),
            "default": (int, float), "unit": str}
SIM_FAULT = {"id": str, "label": str, "node": str, "kind": str}
SIM_ASSERTION = {"id": str, "knobs": None, "faults?": [str], "settle_s?": (int, float), "window_s?": (int, float), "metric": str, "op": str,
                 "value": None}
SCENARIO = {
    "schema_version": str, "id": str, "title": str, "seed": int, "warmup_s": (int, float), "window_s": (int, float),
    "scale_note": (str, N), "nodes": [SIM_NODE], "edges": [{"id": str, "from": str, "to": str, "weight": (int, float)}],
    "knobs": [SIM_KNOB], "faults?": [SIM_FAULT], "readouts": [str], "assertions": [SIM_ASSERTION],
}
SIM = {"scenario": str, "heading?": str, "caption": str, "steps": [str], "sim_claims": [{"text": str, "assertion": str}]}
GOLDEN = ROOT / "tools" / "sim" / "golden"
SCENARIO_HASHES: dict[str, str] = {}  # sha256 of each scenario file as load_all read it, to compare with its golden file
# quantity words in caption and steps that are claims like a digit is: the fraction they stand for (None: presence of a claim only)
SIM_WORDS = {"quarter": 0.25, "half": 0.5, "double": None, "doubles": None, "doubled": None, "triple": None, "ten times": None, "twice": None}
SIM_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?%?")
SIM_WORD = re.compile(r"(?i)\b(" + "|".join(sorted(SIM_WORDS, key=len, reverse=True)) + r")\b")


def _num(token: str) -> float:
    return float(token.rstrip("%").replace(",", ""))


def scenario_checks(name: str, sc: dict) -> list[str]:
    """Shape rules of one scenario file beyond the schema (the schema has already passed)."""
    out: list[str] = []
    if sc["schema_version"] != "learning-center-sim:1":
        out.append(f"{name}: schema_version must be 'learning-center-sim:1'")
    if sc["id"] != Path(name).stem or not KEBAB.match(sc["id"]):
        out.append(f"{name}: id must be kebab-case and equal the file name")
    nodes = {n["id"]: n for n in sc["nodes"]}
    if len(nodes) != len(sc["nodes"]):
        out.append(f"{name}: duplicate node id")
    for n in sc["nodes"]:
        w = f"{name}: node {n['id']}"
        if n["kind"] not in SIM_NODE_KINDS:
            out.append(f"{w}: unknown kind {n['kind']!r}")
        cfg = n["config"]
        if not isinstance(cfg, dict):
            out.append(f"{w}: config must be an object")
            continue
        for f in SIM_BASE_FIELDS:
            if not isinstance(cfg.get(f), (int, float)) or isinstance(cfg.get(f), bool):
                out.append(f"{w}: config.{f} is missing or not a number (all nine base fields are required)")
        if n["x"] < 0 or n["y"] < 0:
            out.append(f"{w}: x and y are grid positions, not negative")
    seen = set()
    for e in sc["edges"]:
        if e["id"] in seen:
            out.append(f"{name}: duplicate edge id {e['id']}")
        seen.add(e["id"])
        if e["from"] not in nodes or e["to"] not in nodes:
            out.append(f"{name}: edge {e['id']} names an unknown node")
    knobs = {k["id"]: k for k in sc["knobs"]}
    if not 1 <= len(sc["knobs"]) <= 3 or len(knobs) != len(sc["knobs"]):
        out.append(f"{name}: 1 to 3 knobs with distinct ids needed, got {len(sc['knobs'])}")
    for k in sc["knobs"]:
        w = f"{name}: knob {k['id']}"
        cfg = nodes.get(k["node"], {}).get("config", {})
        if k["node"] not in nodes:
            out.append(f"{w}: unknown node {k['node']}")
        elif not isinstance(cfg.get(k["field"]), (int, float)):
            out.append(f"{w}: node {k['node']} has no numeric config.{k['field']}")
        elif cfg[k["field"]] != k["default"]:
            out.append(f"{w}: default {k['default']} differs from the node's config.{k['field']} {cfg[k['field']]}")
        if not k["min"] <= k["default"] <= k["max"] or k["step"] <= 0:
            out.append(f"{w}: needs min <= default <= max and a positive step")
    faults = {f["id"]: f for f in sc.get("faults", [])}
    if len(faults) != len(sc.get("faults", [])):
        out.append(f"{name}: duplicate fault id")
    for f in faults.values():
        if f["node"] not in nodes or f["kind"] != "crash" or f["id"] in knobs:
            out.append(f"{name}: fault {f['id']}: must crash a known node and not reuse a knob id (kind 'crash' is the one v1 fault)")
    if not sc["readouts"]:
        out.append(f"{name}: no readouts")

    def metric_problem(m: str) -> str | None:
        base, _, node = m.partition(":")
        if node:
            return None if base in SIM_NODE_METRICS and node in nodes else f"unknown metric {m!r}"
        return None if base in SIM_METRICS else f"unknown metric {m!r}"

    for r in sc["readouts"]:
        if metric_problem(r):
            out.append(f"{name}: readout: {metric_problem(r)}")
    ids = [a["id"] for a in sc["assertions"]]
    if len(set(ids)) != len(ids) or "defaults" in ids or not all(KEBAB.match(i) for i in ids) or not ids:
        out.append(f"{name}: assertion ids must be unique kebab-case, at least one, and not 'defaults'")
    for a in sc["assertions"]:
        w = f"{name}: assertion {a['id']}"
        if metric_problem(a["metric"]):
            out.append(f"{w}: {metric_problem(a['metric'])}")
        if a["op"] not in SIM_OPS:
            out.append(f"{w}: op must be one of {SIM_OPS}")
        v = a["value"]
        if a["op"] == "between":
            if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v) and v[0] <= v[1]):
                out.append(f"{w}: 'between' needs [low, high]")
        elif not isinstance(v, (int, float)) or isinstance(v, bool):
            out.append(f"{w}: value must be a number")
        if not isinstance(a["knobs"], dict):
            out.append(f"{w}: knobs must be an object")
            continue
        for kid, val in a["knobs"].items():
            k = knobs.get(kid)
            if not k:
                out.append(f"{w}: unknown knob {kid}")
            elif not isinstance(val, (int, float)) or not k["min"] <= val <= k["max"]:
                out.append(f"{w}: knob {kid} value {val!r} is outside {k['min']}..{k['max']}")
        for fid in a.get("faults", []):
            if fid not in faults:
                out.append(f"{w}: unknown fault {fid}")
    return out


def golden_for(sid: str):
    """The committed golden run of a scenario (tools/sim/golden/<id>.json) or None."""
    path = GOLDEN / f"{sid}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _golden_numbers(row: dict) -> set[float]:
    """Every number the golden row shows, in the forms a sentence may quote: as is, rounded, and as a percentage."""
    vals: set[float] = set()

    def add(x) -> None:
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            return
        for v in (x, x * 100):
            for nd in (0, 1, 2):
                vals.add(round(v, nd))
            vals.add(float(int(v)))

    for v in row["metrics"].values():
        add(v)
    for v in row.get("knobs", {}).values():
        add(v)
    v = row.get("value")
    for x in (v if isinstance(v, list) else [v]):
        add(x)
    return vals


def _word_fits(word: str, row: dict) -> bool:
    frac = SIM_WORDS[word.lower()]
    if frac is None:
        return True
    return any(isinstance(v, (int, float)) and abs(v - frac) <= 0.08 for v in row["metrics"].values())


def sim_text_checks(w: str, sim: dict, sc: dict, gold: dict) -> list[str]:
    """The digit rule (plan 7.3 item 3). A sentence of caption or steps that holds a digit or a quantity word may quote only
    what the committed golden run shows: a number that is a knob setting of the scenario is an instruction and needs no claim;
    every other number or quantity word must sit inside the `text` of a sim_claims entry whose assertion passes in the golden file,
    and the number must be one that golden row shows (a metric, a knob value or a bound of that row, rounded or as a percentage)."""
    out: list[str] = []
    rows = {r["assertion"]: r for r in gold["rows"]}
    knob_values: set[float] = set()
    for k in sc["knobs"]:
        for x in (k["min"], k["max"], k["default"]):
            knob_values |= {float(x), float(x) * 100}
    for r in gold["rows"]:
        for x in r.get("knobs", {}).values():
            knob_values |= {float(x), float(x) * 100}
    claims = sim["sim_claims"]
    spoken = " ".join([sim["caption"], *sim["steps"]])
    for c in claims:
        if c["text"] not in spoken:
            out.append(f"{w}: claim {c['text']!r} does not appear in the caption or the steps")
    for c in claims:
        row = rows.get(c["assertion"])
        if c["assertion"] == "defaults" or row is None:
            out.append(f"{w}: sim_claims names assertion {c['assertion']!r}, which is not an assertion of {sc['id']}")
        elif not row["pass"]:
            out.append(f"{w}: claim {c['text']!r}: assertion {c['assertion']} FAILS in the golden run")
    texts = [sim["caption"], *sim["steps"]] + ([sim["heading"]] if "heading" in sim else [])
    for text in texts:
        for sent in sentences(text):
            mine = [c for c in claims if c["text"] and c["text"] in sent]
            rest = sent
            for c in mine:
                rest = rest.replace(c["text"], " ")
            for m in SIM_NUMBER.finditer(rest):
                if _num(m.group(0)) not in knob_values:
                    out.append(f"{w}: {m.group(0)!r} in {sent[:70]!r} is not covered by a sim_claims entry and is not a knob setting")
            for m in SIM_WORD.finditer(rest):
                out.append(f"{w}: {m.group(0)!r} in {sent[:70]!r} is not covered by a sim_claims entry")
            for c in mine:
                row = rows.get(c["assertion"])
                if row is None:
                    continue
                shown = _golden_numbers(row)
                for m in SIM_NUMBER.finditer(c["text"]):
                    n = _num(m.group(0))
                    if n not in shown and n not in knob_values:
                        out.append(f"{w}: claim {c['text']!r}: the number {m.group(0)} is not in the golden row of {c['assertion']} "
                                   f"({', '.join(f'{k}={v}' for k, v in row['metrics'].items())})")
                for m in SIM_WORD.finditer(c["text"]):
                    if not _word_fits(m.group(0), row):
                        out.append(f"{w}: claim {c['text']!r}: no metric of the golden row {c['assertion']} is near {m.group(0)!r}")
    return out


def sim_checks(lid: str, l: dict, docs: dict) -> list[str]:
    sim = l["sim"]
    w = f"lessons/{lid}: sim"
    sid = sim["scenario"]
    sc = docs.get(f"scenarios/{sid}.json")
    if sc is None:
        return [f"{w}: scenario {sid!r} has no file content/scenarios/{sid}.json"]
    gold = golden_for(sid)
    if gold is None:
        return [f"{w}: no golden run tools/sim/golden/{sid}.json (run node tools/sim/golden.mjs --write {sid})"]
    out: list[str] = []
    if gold.get("scenario_sha256") != SCENARIO_HASHES.get(sid, gold.get("scenario_sha256")):
        out.append(f"{w}: the golden run of {sid} is stale (the scenario file changed); re-run tools/sim/golden.mjs --write")
    if not sim["caption"].strip() or not sim["steps"]:
        out.append(f"{w}: caption and at least one step are required")
    out.extend(sim_text_checks(w, sim, sc, gold))
    return out


# --- lesson format v2 (learning-center-lesson:2): typed blocks, numbered sources, cites (SPEC-format-v2-system-design.md section 1) ---
V2 = "learning-center-lesson:2"
SOURCE_KINDS_V2 = ("doc", "article", "book", "paper", "repo", "tutorial")
SOURCE_V2 = {"id": str, "title": str, "url": str, "kind": str, "verified?": VERIFIED}
BLOCK_SPECS = {
    "p": {"type": str, "text": str, "cites?": [str]},
    "list": {"type": str, "items": [str], "ordered?": bool, "cites?": [str]},
    "table": {"type": str, "caption?": str, "columns": [str], "rows": [[str]], "cites?": [str]},
    "code": {"type": str, "lang": str, "code": str, "caption?": str},
    "callout": {"type": str, "kind": str, "text": str, "cites?": [str]},
    "steps": {"type": str, "title?": str, "items": [str], "cites?": [str]},
    "decision": {"type": str, "caption?": str, "rows": [{"option": str, "pick_when": str, "avoid_when": str, "example?": str}], "cites?": [str]},
    "diagram": {"type": str, "mermaid": str, "legend?": str, "cites?": [str]},   # the legend names the source ids its arrows rest on
    "flow": {"type": str, "nodes": [{"id": str, "label": str, "kind": str}],
             "frames?": [{"id": str, "title": str, "nodes": [str]}],
             "edges": [{"id?": str, "from": str, "to": str, "kind?": str, "label": str, "short?": str, "dashed?": bool}],
             "steps?": [{"edge": (int, str), "caption": str}], "legend?": str, "cites?": [str]},
}
CALLOUT_KINDS = ("rule", "pitfall", "tip")
CITING_BLOCKS = frozenset(t for t, spec in BLOCK_SPECS.items() if "cites?" in spec)
# A block carries its own text fields; the strings below must not be blank.
BLOCK_TEXT_FIELDS = {"p": ("text",), "callout": ("text",), "code": ("code",), "diagram": ("mermaid",)}
LESSON_V2 = {
    "schema_version": str, "id": str, "version": int, "status": str, "superseded_by": (str, N), "title": str, "area": str,
    "primary_key": str, "secondary_keys": [str], "keys": [str], "summary": str, "detail": [None], "in_practice": {"blocks": [None]},
    "subtopics": [{"id": str, "title": str, "blocks": [None]}], "worked_example?": {"title": str, "blocks": [None]},
    "diagram": ({"source": str}, N), "code": [None], "technologies": [str], "related": [str],
    "sources": [SOURCE_V2], "practice": (str, N), "provenance": PROVENANCE, "changelog": CHANGELOG,
    "kind?": str, "exercise?": {
        "prompt": str, "constraints": None, "clarifying_questions": [{"q": str, "a": str}],
        "reference_answer": [{"id": str, "title": str, "blocks": [None]}], "rubric": {"L1": [str], "L2": [str], "L3": [str]},
        "interview_frame": None, "design_doc_frame": None, "depth_notes": {"L1": str, "L2": str, "L3": str},
    }, "sim?": SIM,
}
# lessons whose job is a choice carry a decision block (ids, and primary keys of any lesson)
DECISION_LESSON_IDS = frozenset("sd-storage-engines sd-queues-streams sd-caching sd-consistency-consensus sd-replication-partitioning sd-load-balancing".split())
DECISION_KEYS = frozenset("storage-engines message-queues caching consistency replication load-balancing".split())
MAX_NUMBERS_IN_P = 4   # a p, a table cell or a decision cell with more numbers than this is refused; steps items are exempt
CITE_COLUMNS = frozenset({"cite", "cites", "source", "sources"})   # a table column of source ids, rendered as linked marks
# integers (with thousands commas) and decimals; a digit run glued to a letter before it (p99, S3, v4) is a name, not a number
V2_NUMBER = re.compile(r"(?<![\w.])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
RESERVED_IDS_V2 = frozenset({"worked-example", "in-practice", "sources", "related", "technologies", "simulate", "prompt", "constraints",
                             "clarifying-questions", "reference-answer", "rubric", "interview-frame", "design-doc-frame", "depth"})
EST_COLUMNS = ["quantity", "per day", "average per second", "peak per second", "note"]
DATA_COLUMNS = ["entity", "fields", "key or partition", "notes"]
API_COLUMNS = ["method", "path", "request", "response", "notes"]


SCHEMAS = {
    "lesson": {
        "schema_version": str, "id": str, "version": int, "status": str, "superseded_by": (str, N), "title": str, "area": str,
        "primary_key": str, "secondary_keys": [str], "keys": [str], "summary": str, "detail": [{"heading?": str, "body": str}],
        "in_practice": str,
        "subtopics": [{"id": str, "title": str, "body": [{"heading?": str, "body": str}]}],
        "diagram": ({"source": str}, N), "code": [{"lang": str, "code": str}], "technologies": [str], "related": [str],
        "sources": [SOURCE], "practice": (str, N), "provenance": PROVENANCE, "changelog": CHANGELOG,
        "kind?": str, "exercise?": EXERCISE, "sim?": SIM,
    },
    "lesson2": LESSON_V2,
    "scenario": SCENARIO,
    "sim-staging": {"lesson": str, "sim": SIM},
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
    "module": {
        "schema_version": str, "id": str, "version": int, "title": str, "status": str, "summary": str, "intro?": str,
        "parts?": [{"id": str, "title": str}],
        "lessons": [{"id": str, "title?": str, "part?": str, "part_title?": str, "status": str}],
        "changelog?": CHANGELOG,
    },
    "modules-index": {
        "schema_version": str,
        "modules": [{"id": str, "title": str, "status": str, "summary": str, "lessons_published": int, "lessons_planned": int}],
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
            if rel.startswith("scenarios/"):
                SCENARIO_HASHES[p.stem] = hashlib.sha256(p.read_bytes()).hexdigest()
        except Exception as e:  # noqa: BLE001 - report any parse failure as a problem
            problems.append(f"{rel}: does not parse: {e}")
    return docs, problems


def kind_of(rel: str) -> str | None:
    if rel.startswith("lessons/"):
        return "lesson"
    if rel.startswith("scenarios/"):
        return "scenario"
    if rel.startswith("sim-staging/"):  # the `sim` field of a lesson that is not in this tree yet, for the coordinator to apply
        return "sim-staging"
    if rel.startswith("practice/"):
        return "practice"
    if rel == "modules/index.json":
        return "modules-index"
    if rel.startswith("modules/"):
        return "module"
    return {"redirects.json": "redirects", "changelog.json": "changelog", "site.json": "site",
            "keys/concept-keys.json": "keys", "merge-candidates.json": "merge"}.get(rel)


ENTRY_FORBIDDEN = ("home", "why", "depth")   # no cross-references: a lesson sits in exactly one module


def module_checks(docs: dict, lessons: dict, modules: dict) -> list[str]:
    """The module rules: ids and parts, published entries have a published lesson file and planned ones have none,
    every published lesson is listed in exactly one module, modules/index.json lists every module file once with matching counts."""
    out: list[str] = []
    homes: dict[str, list[str]] = {}
    for mid, m in modules.items():
        w = f"modules/{mid}.json"
        if not KEBAB.match(mid):
            out.append(f"{w}: id is not kebab-case")
        if m["status"] not in ("planned", "published"):
            out.append(f"{w}: bad status {m['status']!r}")
        if m.get("changelog") and m["changelog"][-1]["version"] != m["version"]:
            out.append(f"{w}: version does not match the last changelog entry")
        part_ids = [p["id"] for p in m.get("parts", [])]
        if len(set(part_ids)) != len(part_ids):
            out.append(f"{w}: duplicate part id")
        seen: set[str] = set()
        for e in m["lessons"]:
            eid = e["id"]
            if eid in seen:
                out.append(f"{w}: lists {eid} twice")
            seen.add(eid)
            for f in ENTRY_FORBIDDEN:
                if f in e:
                    out.append(f"{w}: entry {eid} has a {f!r} field (no cross-references, no why or depth)")
            if e["status"] not in ("planned", "published"):
                out.append(f"{w}: entry {eid} has bad status {e['status']!r}")
            elif e["status"] == "planned":
                if eid in lessons:
                    out.append(f"{w}: {eid} is planned but a lesson file exists")
                if not e.get("title", "").strip():
                    out.append(f"{w}: planned entry {eid} needs a title")
            else:
                if eid not in lessons or lessons[eid]["status"] != "published":
                    out.append(f"{w}: {eid} is published but no published lesson file exists")
                homes.setdefault(eid, []).append(mid)
            if part_ids:
                if e.get("part") not in part_ids:
                    out.append(f"{w}: entry {eid} names part {e.get('part')!r}, not one of {part_ids}")
            elif "part" in e or "part_title" in e:
                out.append(f"{w}: entry {eid} names a part but the module has none")
    for lid, l in lessons.items():
        if l["status"] == "published" and len(homes.get(lid, [])) != 1:
            out.append(f"lessons/{lid}: listed in {len(homes.get(lid, []))} modules ({', '.join(homes.get(lid, [])) or 'none'}); a published lesson sits in exactly one")
    rows = docs["modules/index.json"]["modules"]
    listed = [r["id"] for r in rows]
    if len(set(listed)) != len(listed):
        out.append("modules/index.json: duplicate module id")
    for mid in modules:
        if mid not in listed:
            out.append(f"modules/index.json: module {mid} is not listed")
    for r in rows:
        m = modules.get(r["id"])
        if m is None:
            out.append(f"modules/index.json: {r['id']} has no file modules/{r['id']}.json")
            continue
        for f in ("title", "status", "summary"):
            if r[f] != m[f]:
                out.append(f"modules/index.json: {r['id']} {f} differs from the module file")
        pub = sum(1 for e in m["lessons"] if e["status"] == "published")
        if (r["lessons_published"], r["lessons_planned"]) != (pub, len(m["lessons"]) - pub):
            out.append(f"modules/index.json: {r['id']} counts {r['lessons_published']}/{r['lessons_planned']} do not match the file ({pub}/{len(m['lessons']) - pub})")
    return out


def validate(docs: dict) -> list[str]:
    out: list[str] = []
    for rel, doc in docs.items():
        if rel.startswith(f"{BUILD_TRACK_DIR.as_posix()}/{LABS_DIR}/"):   # the track's labs JSON: labs_checks
            continue
        if rel == f"{BUILD_TRACK_DIR.as_posix()}/{GLOSSARY_FILE}":   # the track's glossary: glossary_checks
            continue
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
        v2 = kind == "lesson" and isinstance(doc, dict) and doc.get("schema_version") == V2
        _t(SCHEMAS["lesson2" if v2 else kind], doc, "$", errs)
        out.extend(f"{rel}: {e}" for e in errs)
        out.extend(public_checks(rel, doc))
        if v2 and not errs:
            out.extend(f"{rel}: {e}" for e in lesson2_checks(doc))
        if kind in ("practice-case", "practice-artifact") and not errs:
            out.extend(written_checks(rel, doc))
        if kind == "scenario" and not errs:
            out.extend(scenario_checks(rel, doc))
        if kind == "sim-staging" and not errs:
            if Path(rel).stem != doc["lesson"]:
                out.append(f"{rel}: file name does not match lesson {doc['lesson']}")
            out.extend(sim_checks(doc["lesson"], doc, docs))
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
    modules = {d["id"]: d for r, d in docs.items() if r.startswith("modules/") and r != "modules/index.json"}
    planned_ids = {e["id"] for m in modules.values() for e in m["lessons"] if e["status"] == "planned"}
    for rel, d in docs.items():
        if rel.startswith(("lessons/", "practice/", "modules/")) and rel != "modules/index.json" and Path(rel).stem != (d["id"].split("/")[-1]):
            out.append(f"{rel}: file name does not match id {d['id']}")
    for lid, l in lessons.items():
        w = f"lessons/{lid}"
        if not KEBAB.match(lid):
            out.append(f"{w}: id is not kebab-case")
        if l["status"] not in ("draft", "published", "superseded"):
            out.append(f"{w}: bad status {l['status']!r}")
        if l["status"] == "superseded" and l["superseded_by"] not in lessons:
            out.append(f"{w}: superseded_by names an unknown lesson")
        elif l["status"] == "superseded" and lessons[l["superseded_by"]]["status"] != "published":
            out.append(f"{w}: superseded_by names a lesson that is not published")
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
        if "sim" in l:
            out.extend(sim_checks(lid, l, docs))
        for r in l["related"]:
            if r not in lessons and not (ex and r in planned_ids):
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
    out.extend(module_checks(docs, lessons, modules))
    for r in docs["redirects.json"]["redirects"]:
        out.append(f"redirects.json: no redirects are kept (the old URLs simply stop existing): {r['from']}")
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
    if l["schema_version"] == V2:
        return exercise2_checks(l)
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
        if not FLOWCHART_START.match(sec["diagram"]["source"]):
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


# --- the :2 checks: blocks, cites, the 4-number rule, the concept-lesson and exercise rules ----------------------------------
def as_blocks(v) -> list:
    """An exercise field that holds blocks may be one block or a list of blocks."""
    return [v] if isinstance(v, dict) else v if isinstance(v, list) else []


def flow_problems(b: dict, path: str) -> list[str]:
    out = []
    ids = [n["id"] for n in b["nodes"]]
    known = set(ids)
    if not 1 <= len(ids) <= MAX_FLOW_NODES:
        out.append(f"{path}: a flow needs 1 to {MAX_FLOW_NODES} nodes; split a larger architecture")
    if len(known) != len(ids) or any(not n.strip() for n in ids):
        out.append(f"{path}: node ids must be unique and non-empty")
    for n in b["nodes"]:
        if not n["label"].strip():
            out.append(f"{path}: node labels must be non-empty")
        if n["kind"] not in ("service", "store", "queue", "actor", "decision"):
            out.append(f"{path}: invalid node kind {n['kind']!r}")
        if set(n) - {"id", "label", "kind"}:
            out.append(f"{path}: nodes accept only id, label and kind (no coordinates)")
    edge_ids = [e["id"] for e in b["edges"] if "id" in e]
    if len(edge_ids) != len(set(edge_ids)) or any(not i.strip() for i in edge_ids):
        out.append(f"{path}: edge ids must be unique and non-empty")
    for e in b["edges"]:
        if e["from"] not in known or e["to"] not in known:
            out.append(f"{path}: edges must reference existing nodes")
        if not e["label"].strip() and e.get("kind", "sync") != "link":
            out.append(f"{path}: edge labels must be non-empty unless the edge is a non-temporal link")
        if e.get("kind", "sync") not in ("sync", "async", "reply", "link"):
            out.append(f"{path}: invalid edge kind {e['kind']!r}")
        if "short" in e and (not e["short"].strip() or "\n" in e["short"] or "\r" in e["short"]):
            out.append(f"{path}: short labels must be non-empty single lines")
        if "dashed" in e and e.get("kind", "sync") != "link":
            out.append(f"{path}: dashed styling is only for non-temporal links")
        if set(e) - {"id", "from", "to", "kind", "label", "short", "dashed"}:
            out.append(f"{path}: edges accept only id, from, to, kind, label, short and dashed")
    used = set()
    for step in b.get("steps", []):
        ref = step["edge"]
        index = next((i for i, e in enumerate(b["edges"]) if e.get("id") == ref), -1) if isinstance(ref, str) else ref
        if isinstance(index, bool) or not 0 <= index < len(b["edges"]):
            out.append(f"{path}: steps must reference existing edges")
        else:
            used.add(index)
        if not step["caption"].strip() or "\n" in step["caption"] or "\r" in step["caption"]:
            out.append(f"{path}: step captions must be non-empty single lines")
        if set(step) - {"edge", "caption"}:
            out.append(f"{path}: steps accept only edge and caption")
    required_steps = {i for i, edge in enumerate(b["edges"]) if edge.get("kind", "sync") != "link"}
    if not b["edges"] or not required_steps <= used:
        out.append(f"{path}: every edge needs a step unless it is a non-temporal link")
    held, frame_ids = set(), set()
    for frame in b.get("frames", []):
        if not frame["id"].strip() or frame["id"] in frame_ids or frame["id"] in known:
            out.append(f"{path}: frame ids must be unique, non-empty and distinct from nodes")
        frame_ids.add(frame["id"])
        if not frame["title"].strip():
            out.append(f"{path}: frame titles must be non-empty")
        members = frame["nodes"]
        if not members or any(n not in known for n in members):
            out.append(f"{path}: frames must hold existing nodes, never nested frames")
        if len(set(members)) != len(members) or held.intersection(members):
            out.append(f"{path}: frames must not overlap")
        held.update(members)
        if set(frame) - {"id", "title", "nodes"}:
            out.append(f"{path}: frames accept only id, title and nodes; no nesting or coordinates")
    for source in re.findall(r"\bs[1-9]\d*\b", b.get("legend", "")):
        if source not in b.get("cites", []):
            out.append(f"{path}: legend source {source} must resolve to the block's cites")
    return out


def block_problems(b, path: str) -> list[str]:
    if not isinstance(b, dict):
        return [f"{path}: a block is an object, got {type(b).__name__}"]
    t = b.get("type")
    if t not in BLOCK_SPECS:
        return [f"{path}: block type {t!r} is not one of {sorted(BLOCK_SPECS)}"]
    spec = BLOCK_SPECS[t]
    out: list[str] = []
    _t(spec, b, path, out)
    if out:
        return out
    known = {k.rstrip("?") for k in spec}
    out += [f"{path}: unknown field {k!r} on a {t} block" for k in b if k not in known]
    for f in BLOCK_TEXT_FIELDS.get(t, ()):
        if not b[f].strip():
            out.append(f"{path}.{f}: empty")
    if t in ("list", "steps") and (not b["items"] or not all(i.strip() for i in b["items"])):
        out.append(f"{path}.items: needs at least one item and no blank item")
    if t == "table":
        if not b["columns"] or not b["rows"]:
            out.append(f"{path}: a table needs columns and rows")
        out += [f"{path}.rows[{i}]: {len(r)} cells, the table has {len(b['columns'])} columns" for i, r in enumerate(b["rows"]) if len(r) != len(b["columns"])]
    if t == "callout" and b["kind"] not in CALLOUT_KINDS:
        out.append(f"{path}.kind: {b['kind']!r} is not one of {CALLOUT_KINDS}")
    if t == "decision":
        if not b["rows"]:
            out.append(f"{path}: a decision block needs rows")
        for i, r in enumerate(b["rows"]):
            out += [f"{path}.rows[{i}].{f}: empty" for f in ("option", "pick_when", "avoid_when") if not r[f].strip()]
    if t == "diagram" and (re.search(r"(?i)^\s*C4", b["mermaid"]) or "%%{" in b["mermaid"]):
        out.append(f"{path}: no C4 syntax and no Mermaid directives in a diagram")
    if t == "flow":
        out += flow_problems(b, path)
    return out


def v2_blocks(l: dict):
    """Yield (path, region, block) for every block of a :2 lesson; region is 'subtopic', 'worked_example', 'in_practice' or 'exercise:<part>'."""
    for i, s in enumerate(l["subtopics"]):
        for j, b in enumerate(s["blocks"]):
            yield f"$.subtopics[{i}].blocks[{j}]", "subtopic", b
    if "worked_example" in l:
        for j, b in enumerate(l["worked_example"]["blocks"]):
            yield f"$.worked_example.blocks[{j}]", "worked_example", b
    for j, b in enumerate(l["in_practice"]["blocks"]):
        yield f"$.in_practice.blocks[{j}]", "in_practice", b
    ex = l.get("exercise")
    if ex:
        for i, sec in enumerate(ex["reference_answer"]):
            for j, b in enumerate(sec["blocks"]):
                yield f"$.exercise.reference_answer[{i}].blocks[{j}]", f"exercise:{sec['id']}", b
        for f in ("constraints", "interview_frame", "design_doc_frame"):
            for j, b in enumerate(as_blocks(ex[f])):
                yield f"$.exercise.{f}[{j}]", f"exercise:{f}", b


def lesson2_checks(l: dict) -> list[str]:
    """Every :2 rule that needs only this one file (the schema has already passed). Refuses, never warns."""
    out: list[str] = []
    if l["detail"] or l["code"]:
        out.append("$: detail and code are empty lists in :2 (the teaching and the code live in blocks)")
    if l["diagram"] is not None:
        out.append("$.diagram: a :2 lesson places its diagram in a diagram block of the subtopic it explains; the top-level diagram must be null")
    ids = [s["id"] for s in l["sources"]]
    if ids != [f"s{n}" for n in range(1, len(ids) + 1)]:
        out.append(f"$.sources: ids must be s1..s{len(ids)} in order, got {ids}")
    for s in l["sources"]:
        if s["kind"] not in SOURCE_KINDS_V2:
            out.append(f"$.sources.{s['id']}: kind {s['kind']!r} is not one of {SOURCE_KINDS_V2}")
    for s in l["subtopics"]:
        if s["id"] in RESERVED_IDS_V2:
            out.append(f"$.subtopics.{s['id']}: id is reserved for a page section")
    exercise = l.get("kind") == "design-exercise"
    known = set(ids)
    blocks = []
    for path, region, b in v2_blocks(l):
        bp = block_problems(b, path)
        out += bp
        if bp:
            continue
        blocks.append((path, region, b))
        t = b["type"]
        cites = b.get("cites", [])
        out += [f"{path}.cites: {c!r} is not a source id of this lesson" for c in cites if c not in known]
        if region == "in_practice":
            if t not in CITING_BLOCKS:
                out.append(f"{path}: a {t} block cannot cite, so it cannot stand in 'in practice'")
            elif not cites:
                out.append(f"{path}: every block of in_practice cites at least one source (a claim with nothing to cite is cut)")
        if t == "p":
            n = len(V2_NUMBER.findall(b["text"]))
            if n > MAX_NUMBERS_IN_P:
                out.append(f"{path}: a paragraph holds {n} numbers (at most {MAX_NUMBERS_IN_P}); put them in a table or steps block")
        if t == "table":
            for ci, col in enumerate(b["columns"]):
                if col.strip().lower() in CITE_COLUMNS:
                    for ri, r in enumerate(b["rows"]):
                        ids = [x.strip() for x in r[ci].split(",")] if ci < len(r) else []
                        if not ids or not all(re.fullmatch(r"s\d+", x) and x in known for x in ids):
                            out.append(f"{path}.rows[{ri}]: the {col!r} column holds source ids of this lesson (s1, s2 ...), got {r[ci]!r}")
            cite_cols = {ci for ci, col in enumerate(b["columns"]) if col.strip().lower() in CITE_COLUMNS}
            for ri, r in enumerate(b["rows"]):
                for ci, cell in enumerate(r):
                    n = 0 if ci in cite_cols else len(V2_NUMBER.findall(cell))
                    if n > MAX_NUMBERS_IN_P:
                        out.append(f"{path}.rows[{ri}]: a table cell holds {n} numbers (at most {MAX_NUMBERS_IN_P}), the same as a paragraph; "
                                   "split the row or move the arithmetic to a steps block")
        if t == "decision":
            for ri, r in enumerate(b["rows"]):
                for field, cell in r.items():
                    n = len(V2_NUMBER.findall(cell))
                    if n > MAX_NUMBERS_IN_P:
                        out.append(f"{path}.rows[{ri}].{field}: a decision cell holds {n} numbers (at most {MAX_NUMBERS_IN_P}), the same as a paragraph; "
                                   "split the row or move the arithmetic to a steps block")
        if t == "diagram" and FLOWCHART_START.match(b["mermaid"]):
            what = "exercise architecture diagrams" if exercise else "concept flowcharts"
            out.append(f"{path}: {what} must use a flow block; Mermaid remains for sequence diagrams")
        elif t == "diagram" and exercise and not SEQUENCE_START.match(b["mermaid"]):
            out.append(f"{path}: the diagram must be a Mermaid sequence diagram (starts with 'sequenceDiagram'); an architecture diagram is a flow block")
        if t == "diagram" and SEQUENCE_START.match(b["mermaid"]):
            n = len(sequence_participants(b["mermaid"]))
            if n > MAX_SEQUENCE_PARTICIPANTS:
                out.append(f"{path}: a sequence diagram has {n} participants (at most {MAX_SEQUENCE_PARTICIPANTS}, declared or implied by its arrows); "
                           "split it at a boundary of the flow so it fits the 1280 column without sideways scrolling")
    if not exercise:
        types = {b["type"] for _, _, b in blocks}
        if not types & {"table", "decision"}:
            out.append("$: a concept lesson needs at least one table or decision block")
        we = l.get("worked_example")
        if we is None:
            out.append("$.worked_example: a concept lesson needs a worked example")
        elif not we["title"].strip() or not any(b.get("type") == "steps" for b in we["blocks"]):
            out.append("$.worked_example: needs a title and a steps block (the real numbers go there)")
        if (l["id"] in DECISION_LESSON_IDS or l["primary_key"] in DECISION_KEYS) and "decision" not in types:
            out.append("$: a lesson about a choice (storage, queues, caching, consistency, replication, load balancing) needs a decision block")
        if not 8 <= len(l["sources"]) <= 12:
            out.append(f"$.sources: a concept lesson cites 8 to 12 sources, got {len(l['sources'])}")
        for s in l["sources"]:
            v = s.get("verified") or {}
            if v.get("http") != 200 or not DATE.match(str(v.get("checked", ""))):
                out.append(f"$.sources.{s['id']}: verified.http must be 200 with a checked date (YYYY-MM-DD)")
    else:
        for s in l["sources"]:
            v = s.get("verified")
            if v and "checked" in v and not DATE.match(v["checked"]):
                out.append(f"$.sources.{s['id']}: verified.checked is not a date")
    return out


def exercise2_checks(l: dict) -> list[str]:
    """The :2 design-exercise rules: eight sections in order and their blocks, one diagram, rubric, questions, frames, sources."""
    out: list[str] = []
    ex = l["exercise"]
    if not l["summary"].strip() or not ex["prompt"].strip():
        out.append("summary and exercise.prompt must not be empty")
    secs = ex["reference_answer"]
    ids = [sec["id"] for sec in secs]
    if ids not in (EXERCISE_SECTION_IDS, EXERCISE2_SECTION_IDS):
        out.append(f"reference_answer sections must be exactly {EXERCISE_SECTION_IDS} in that order, "
                   f"optionally with {AWS_SECTION!r} right after high-level-design; got {ids}")
    for sec in secs:
        sid, bl = sec["id"], [b for b in sec["blocks"] if isinstance(b, dict)]
        tables = [b for b in bl if b.get("type") == "table"]
        if sid == AWS_SECTION:
            first = bl[0].get("type") if bl else "missing"
            if first not in ("diagram", "flow"):
                out.append(f"section {sid}: must start with a flow block (the AWS architecture, mirroring the high-level-design one); "
                           f"the first block is {first!r}")
            elif first != "flow":
                out.append(f"section {sid}: must start with a flow block (the AWS architecture); a sequence diagram comes after it")
            lead = 0   # the architecture: one flow block, or its write half and read half
            while lead < min(len(bl), AWS_MAX_LEADING_FLOWS) and bl[lead].get("type") == "flow":
                lead += 1
            for i, b in enumerate(bl[lead:], lead):
                if b.get("type") == "flow" or (b.get("type") == "diagram" and not SEQUENCE_START.match(b["mermaid"])):
                    out.append(f"section {sid}: a later diagram (block {i}) must be a sequence diagram (the paths through the services); "
                               f"the architecture flow block, or its write and read halves, comes first only")
            if not any(b.get("type") == "decision" for b in bl):
                out.append(f"section {sid}: needs at least one decision block (the choices as decisions: option, pick when, avoid when, for this design)")
            cost_tables = [t for t in tables if any(AWS_COST_COLUMN.search(c) for c in t["columns"])]
            if len(cost_tables) > 1:
                out.append(f"section {sid}: at most one cost table (a column header containing monthly, cost or price), has {len(cost_tables)}; "
                           f"cost comes last and small, the per-fork price tables go")
        if sid == "requirements-and-estimates" and not any(t["columns"] == EST_COLUMNS for t in tables):
            out.append(f"section {sid}: needs a table block with the columns {EST_COLUMNS}")
        if sid == "data-model" and not (any(t["columns"] == DATA_COLUMNS for t in tables) or any(b.get("type") == "code" for b in bl)):
            out.append(f"section {sid}: needs a table block with the columns {DATA_COLUMNS} or a code block")
        diagrams = [b for b in bl if b.get("type") in ("diagram", "flow")]
        if sid == "core-flow":
            if not any(b.get("type") == "steps" for b in bl) and not any(SEQUENCE_START.match(b.get("mermaid", "")) for b in diagrams):
                out.append(f"section {sid}: needs a steps block or a sequence diagram")
            for b in diagrams:
                if not SEQUENCE_START.match(b.get("mermaid", "")):
                    out.append(f"section {sid}: a diagram here is a sequence diagram (the flow, request by request); the flow block is high-level-design's")
        n_diagrams = len(diagrams)
        if sid == "high-level-design":
            if n_diagrams != 1:
                out.append(f"section {sid}: needs exactly one diagram block, has {n_diagrams}")
            elif diagrams[0].get("type") != "flow":
                out.append(f"section {sid}: the diagram must be a flow block (the architecture); Mermaid remains for sequence diagrams")
        if sid not in ("high-level-design", AWS_SECTION, "core-flow") and n_diagrams:
            out.append(f"section {sid}: a diagram block belongs in high-level-design only (or in {AWS_SECTION}, or a sequence diagram in core-flow)")
        for t in tables:
            if t["columns"][:1] == ["method"] and t["columns"] != API_COLUMNS:
                out.append(f"section {sid}: an API table has the columns {API_COLUMNS}, got {t['columns']}")
    for f, allowed in (("constraints", ("list", "table")), ("interview_frame", ("list", "steps")), ("design_doc_frame", ("list", "steps"))):
        bl = as_blocks(ex[f])
        if not bl or any(not isinstance(b, dict) or b.get("type") not in allowed for b in bl):
            out.append(f"exercise.{f}: a {' or '.join(allowed)} block (or a list of them) is required")
    n = sum(len(ex["rubric"][k]) for k in ("L1", "L2", "L3"))
    if not 8 <= n <= 12:
        out.append(f"rubric has {n} lines; 8 to 12 required")
    if not 5 <= len(ex["clarifying_questions"]) <= 8:
        out.append(f"{len(ex['clarifying_questions'])} clarifying questions; 5 to 8 required")
    if len(l["sources"]) < 3:
        out.append("a design exercise cites at least 3 sources")
    for f in ("interview_frame", "design_doc_frame"):
        items = sum(len(b.get("items", [])) for b in as_blocks(ex[f]) if isinstance(b, dict))
        if items < 3:
            out.append(f"exercise.{f}: at least 3 entries needed, got {items}")
    return out


SCRIPT_BODY = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S | re.I)


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
        # Cookie CODE, not cookie prose: a lesson may teach the Set-Cookie header; only a script that touches
        # document.cookie or the cookieStore API is a problem (the response headers are checked once below).
        for body in SCRIPT_BODY.findall(text):
            if "document.cookie" in body or "cookieStore" in body:
                problems.append(f"{rel}: cookie code in a script")
                break
    headers = site / "_headers"
    if headers.is_file() and "set-cookie" in headers.read_text(encoding="utf-8", errors="ignore").lower():
        problems.append("_headers: a Set-Cookie header is set")
    for p in sorted(site.rglob("*.css")):
        if p.stat().st_size and CSS_URL.search(p.read_text(encoding="utf-8", errors="ignore")):
            # a font or image from another origin; @import is not used by any shipped sheet
            problems.append(f"{p.relative_to(site).as_posix()}: CSS url()/@import to another origin")
    return problems


def build_track_checks(content: Path) -> list[str]:
    import mdlite  # noqa: E402  (tools/ is the script directory; stdlib only)
    folder = content / BUILD_TRACK_DIR
    if not folder.is_dir():
        return [f"{BUILD_TRACK_DIR}: folder is missing"]
    problems: list[str] = []
    # labs/ holds the generated labs JSON (labs_checks) and glossary.json the hand-written glossary (glossary_checks);
    # everything else must be one of the 12 copies
    present = sorted(p.name for p in folder.iterdir()
                     if not p.name.startswith(".") and not (p.name == LABS_DIR and p.is_dir()) and p.name != GLOSSARY_FILE)
    problems += [f"{BUILD_TRACK_DIR}/{n}: missing" for n in BUILD_TRACK_FILES if n not in present]
    problems += [f"{BUILD_TRACK_DIR}/{n}: not one of the 12 AI engineering track files" for n in present if n not in BUILD_TRACK_FILES]
    pages: dict[str, mdlite.Rendered] = {}
    for name in BUILD_TRACK_FILES:
        path = folder / name
        if not path.is_file():
            continue
        label = f"{BUILD_TRACK_DIR}/{name}"
        text = path.read_text(encoding="utf-8")
        problems += public_checks(label, {"text": text})
        for pattern, what in ((re.compile(r"/Users/"), "workstation path"), (OPERATOR, "the word 'operator'"), (BEAD_ID, "bead id")):
            for m in pattern.finditer(text):
                problems.append(f"{label}: line {text.count(chr(10), 0, m.start()) + 1}: {what} {m.group(0)!r}")
        try:
            pages[name] = mdlite.render(text, link=lambda dest: dest)
        except mdlite.MdliteError as e:
            problems.append(f"{label}: {e}")
            continue
        if disclaimer_index(pages[name].blocks) is None:
            problems.append(f"{label}: the disclaimer quote is not within the first three blocks")
    for name, page in pages.items():
        ids = {ident for _, ident, _ in page.headings}
        for dest in page.links:
            if dest.startswith("https://"):
                continue
            target, _, fragment = dest.partition("#")
            if target == "":
                target_ids = ids
            elif target in pages:
                target_ids = {ident for _, ident, _ in pages[target].headings}
            else:
                problems.append(f"{BUILD_TRACK_DIR}/{name}: link {dest!r} does not point at an AI engineering track page")
                continue
            if fragment and fragment not in target_ids:
                problems.append(f"{BUILD_TRACK_DIR}/{name}: link {dest!r}: no heading with that id")
    return problems


# --- the labs of the track: content/ai-engineering/labs/week-N.json (tools/import_labs.py; build.py renders the pages) ----
# Extracted data only: the keys below and nothing else. What a page shows of an exercise is its stub excerpt, chosen
# tests, captured FAIL/PASS output and authored words; `hidden` holds the sha256 prefixes of every solution and
# unshown hint line, and no shown line may hash into it (labs_leaks, here and in build.py on the generated Markdown).
LABS_DIR = "labs"
LABS_FILE = re.compile(r"^week-([1-9])\.json$")
LABS_REPO = "https://github.com/karthik446/tradingresearch/"
LABS_KEYS = {
    "week": {"week", "readme_url", "labs", "concepts", "lessons_mapped", "session", "hidden"},
    "lab": {"id", "title", "goal", "section", "unlock", "base", "page_url", "exercises"},
    "unlock": {"hints", "solution"},
    "exercise": {"id", "title", "effect", "concepts", "touches", "folder", "folder_url", "test_file", "test_url",
                 "goal", "what_tested", "writes", "start_code", "tests", "data", "fail", "pass"},
    "touch": {"path", "url"},
    "concept": {"id", "term", "meaning", "url", "lesson"},
    "start_code": {"path", "url", "lines", "code", "lang"},
    "test": {"name", "code"},
    "data": {"path", "header_and_row"},
    "session": {"diagram", "parts"},
    "part": {"id", "title", "intro", "steps"},
    "step": {"title", "shown", "output", "explain"},
}
LABS_HIDDEN_KEY = re.compile(r"(?i)solution|hint|stub|wrong|red_expect|check|observe|diff|fixture|origin")
LABS_HIDDEN_TEXT = re.compile(r"solution\.diff|hints\.md|/stub/|/wrong/")   # the captured FAIL block is page content
LABS_HASH = re.compile(r"^[0-9a-f]{12}$")
LABS_LINE_MIN = 12   # shorter normalised lines are too common to hide
LABS_MD_PREFIX = re.compile(r"^(?:#{1,6} +|- +|\d{1,3}\. +|> *)+")
LABS_MD_ESCAPE = re.compile(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~])")


def labs_line_hash(line: str) -> str | None:
    """The leak guard's hash of one line: the stripped, whitespace-collapsed text's sha256, first 12 hex; None if short."""
    norm = " ".join(line.split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:12] if len(norm) >= LABS_LINE_MIN else None


def labs_forms(line: str) -> set[str]:
    """A line of generated Markdown and the forms data text may hide in: backslash escapes and code-span backticks
    removed, a list, heading or quote prefix dropped (build.py's md_plain/md_prose)."""
    unescaped = LABS_MD_ESCAPE.sub(r"\1", line)
    forms: set[str] = set()
    for f in (line, unescaped, unescaped.replace("`", "")):
        forms |= {f, LABS_MD_PREFIX.sub("", f)}
    return forms


def labs_leaks(text: str, hidden: set[str], *, markdown: bool = False) -> list[str]:
    """The lines of `text` that hash into `hidden`; with `markdown`, in any of their labs_forms."""
    return [line for line in text.split("\n")
            if any(labs_line_hash(f) in hidden for f in (labs_forms(line) if markdown else (line,)))]


TRACK_GLYPHS_EXTRA = frozenset("\u2018\u2019\u201c\u201d\u2013\u2014\u2026")   # build.py ALLOWED_EXTRA


def track_text_problems(label: str, text: str) -> list[str]:
    """The public-text rules of the track for generated text: no workstation path, no 'operator', no bead id, the glyph policy."""
    problems = []
    for pattern, what in ((re.compile(r"/Users/"), "workstation path"), (OPERATOR, "the word 'operator'"), (BEAD_ID, "bead id")):
        problems += [f"{label}: {what} {m.group(0)!r}" for m in pattern.finditer(text)]
    bad = sorted({ch for ch in text if ord(ch) >= 128 and ch not in TRACK_GLYPHS_EXTRA and not 0xA0 <= ord(ch) <= 0xFF})
    if bad:
        problems.append(f"{label}: glyph(s) outside the policy {', '.join(f'U+{ord(c):04X}' for c in bad)}")
    return problems


def labs_checks(content: Path) -> list[str]:
    """Every content/ai-engineering/labs/week-N.json: its shape, ids, links, concept ids, lessons and public text."""
    import mdlite  # noqa: E402
    folder = content / BUILD_TRACK_DIR / LABS_DIR
    if not folder.is_dir():
        return []
    problems: list[str] = []
    for path in sorted(folder.iterdir()):
        label = f"{BUILD_TRACK_DIR}/{LABS_DIR}/{path.name}"
        m = LABS_FILE.match(path.name)
        if not m or not path.is_file():
            problems.append(f"{label}: not a week-N.json")
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            problems.append(f"{label}: unreadable: {e}")
            continue
        problems += labs_doc_problems(label, int(m.group(1)), doc, content, mdlite)
    return problems


def labs_doc_problems(label: str, week: int, doc, content: Path, mdlite) -> list[str]:
    problems: list[str] = []

    def shape(obj, kind: str, where: str) -> bool:
        if not isinstance(obj, dict):
            problems.append(f"{label}: {where}: not an object")
            return False
        for k in sorted(set(obj) - LABS_KEYS[kind]):
            what = "a solution- or hint-looking field" if LABS_HIDDEN_KEY.search(k) else "an unexpected field"
            problems.append(f"{label}: {where}: {what} {k!r}")
        for k in sorted(LABS_KEYS[kind] - set(obj)):
            problems.append(f"{label}: {where}: missing {k}")
        return True

    def no_relative(dest: str) -> str:
        raise mdlite.MdliteError(f"relative link {dest!r}")

    def text(obj, key, where: str, *, markdown: bool = False) -> None:
        """A one-line field; plain text (build.py escapes it) unless `markdown` (a cell of concepts.md, the track's subset)."""
        v = obj[key] if isinstance(obj, list) else obj.get(key)
        if not isinstance(v, str) or not v.strip():
            problems.append(f"{label}: {where}: missing {key}")
            return
        if "\n" in v:
            problems.append(f"{label}: {where}.{key}: more than one line")
        if markdown:
            try:
                mdlite.render("# x\n\n" + v + "\n", link=no_relative)
            except mdlite.MdliteError as e:
                problems.append(f"{label}: {where}.{key}: {e}")

    def block(v, where: str, nullable: bool = False) -> None:
        """A verbatim block (code or captured output): build.py fences it, so no line may close the fence."""
        if v is None and nullable:
            return
        if not isinstance(v, str) or not v.strip():
            problems.append(f"{label}: {where}: missing or empty")
        elif any(mdlite.FENCE_CLOSE.match(line) for line in v.split("\n")):
            problems.append(f"{label}: {where}: a line would close the code fence")

    def url(v, where: str, nullable: bool = False) -> None:
        if v is None and nullable:
            return
        if not isinstance(v, str) or not v.startswith(LABS_REPO) or not URL_OK.match(v):
            problems.append(f"{label}: {where}: not a link into {LABS_REPO}: {v!r}")

    if not shape(doc, "week", "$"):
        return problems
    if doc.get("week") != week:
        problems.append(f"{label}: week {doc.get('week')!r} does not match the file name")
    url(doc.get("readme_url"), "readme_url")
    concepts = {c["id"]: c for c in doc["concepts"] if isinstance(c, dict) and isinstance(c.get("id"), str)} \
        if isinstance(doc.get("concepts"), list) else {}
    for cid, c in concepts.items():
        where = f"concepts.{cid}"
        if not re.fullmatch(r"[a-z0-9_-]+", cid):
            problems.append(f"{label}: {where}: concept id is not an anchor")
        if not shape(c, "concept", where):
            continue
        text(c, "term", where)
        text(c, "meaning", where, markdown=True)
        url(c.get("url"), f"{where}.url")
        lesson = c.get("lesson")
        if lesson is not None and not (isinstance(lesson, str) and (content / "lessons" / f"{lesson}.json").is_file()):
            problems.append(f"{label}: {where}: lesson {lesson!r} does not exist under content/lessons/")
    if doc.get("lessons_mapped") != sorted(cid for cid, c in concepts.items() if isinstance(c, dict) and c.get("lesson")):
        problems.append(f"{label}: lessons_mapped does not list exactly the concepts with a lesson")
    labs = doc.get("labs")
    if not isinstance(labs, list) or not labs:
        problems.append(f"{label}: no labs")
        labs = []
    lab_ids: set[str] = set()
    ex_ids: set[str] = set()
    for i, lab in enumerate(labs):
        where = f"labs[{i}]"
        if not shape(lab, "lab", where):
            continue
        lid = lab.get("id")
        if not isinstance(lid, str) or not re.fullmatch(rf"w{week}l\d+", lid) or lid in lab_ids:
            problems.append(f"{label}: {where}: id {lid!r} is not a new w{week}lM")
            lid = f"w{week}l?"
        lab_ids.add(lid)
        where = f"labs.{lid}"
        text(lab, "title", where)
        text(lab, "goal", where)
        sec = lab.get("section")
        if not isinstance(sec, list) or not sec or not all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in sec):
            problems.append(f"{label}: {where}: section must list chapter section numbers")
        un = lab.get("unlock")
        if shape(un, "unlock", f"{where}.unlock"):
            h, s = un.get("hints"), un.get("solution")
            if not (isinstance(h, list) and h and all(isinstance(n, int) and n > 0 for n in h) and h == sorted(h) and isinstance(s, int) and s > 0):
                problems.append(f"{label}: {where}.unlock: hints must be rising positive numbers and solution a positive number")
        if lab.get("base") is not None and not (isinstance(lab["base"], str) and re.fullmatch(r"week-\d+-start", lab["base"])):
            problems.append(f"{label}: {where}: base {lab['base']!r} is not a week-N-start tag")
        url(lab.get("page_url"), f"{where}.page_url")
        exercises = lab.get("exercises")
        if not isinstance(exercises, list) or not exercises:
            problems.append(f"{label}: {where}: no exercises")
            continue
        for j, ex in enumerate(exercises):
            ew = f"{where}.exercises[{j}]"
            if not shape(ex, "exercise", ew):
                continue
            eid = ex.get("id")
            if not isinstance(eid, str) or not re.fullmatch(rf"{re.escape(lid)}\.\d+", eid) or eid in ex_ids:
                problems.append(f"{label}: {ew}: id {eid!r} is not a new {lid}.N")
            ex_ids.add(str(eid))
            text(ex, "title", ew)
            text(ex, "effect", ew)
            for cid in ex.get("concepts") if isinstance(ex.get("concepts"), list) else []:
                if cid not in concepts:
                    problems.append(f"{label}: {ew}: unknown concept id {cid!r}")
            if not isinstance(ex.get("folder"), str) or not ex["folder"].startswith(f"{eid}-"):
                problems.append(f"{label}: {ew}: folder {ex.get('folder')!r} does not start with the id")
            if not isinstance(ex.get("test_file"), str) or not re.fullmatch(r"test_\w+\.py", ex["test_file"]):
                problems.append(f"{label}: {ew}: test_file {ex.get('test_file')!r}")
            url(ex.get("folder_url"), f"{ew}.folder_url")
            url(ex.get("test_url"), f"{ew}.test_url")
            text(ex, "goal", ew)
            text(ex, "what_tested", ew)
            writes = ex.get("writes")
            if not isinstance(writes, list) or not 2 <= len(writes) <= 5:
                problems.append(f"{label}: {ew}: writes must list 2 to 5 texts")
            else:
                for k in range(len(writes)):
                    text(writes, k, f"{ew}.writes")
            for key in ("fail", "pass"):
                block(ex.get(key), f"{ew}.{key}")
            starts = ex.get("start_code")
            if not isinstance(starts, list) or not starts:
                problems.append(f"{label}: {ew}: no start_code")
                starts = []
            paths = {t.get("path") for t in ex.get("touches") or [] if isinstance(t, dict)}
            for k, s in enumerate(starts):
                sw = f"{ew}.start_code[{k}]"
                if not shape(s, "start_code", sw):
                    continue
                if s.get("path") not in paths:
                    problems.append(f"{label}: {sw}: path {s.get('path')!r} is not a touched file")
                url(s.get("url"), f"{sw}.url", nullable=True)
                ln = s.get("lines")
                code = s.get("code")
                if not (isinstance(ln, list) and len(ln) == 2 and all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in ln)
                        and ln[0] <= ln[1] <= ln[0] + 39 and isinstance(code, str) and code.count("\n") == ln[1] - ln[0]):
                    problems.append(f"{label}: {sw}: lines must be [first, last] of at most 40 lines matching the code")
                if not isinstance(code, str) or f"TODO({eid})" not in code:
                    problems.append(f"{label}: {sw}: code does not hold the TODO({eid}) marker")
                block(code, f"{sw}.code")
                if not isinstance(s.get("lang"), str) or not re.fullmatch(r"[a-z]+", s["lang"]):
                    problems.append(f"{label}: {sw}: lang {s.get('lang')!r}")
            tests = ex.get("tests")
            if not isinstance(tests, list) or not 1 <= len(tests) <= 2:
                problems.append(f"{label}: {ew}: tests must hold 1 or 2 test functions")
                tests = []
            for k, t in enumerate(tests):
                if shape(t, "test", f"{ew}.tests[{k}]"):
                    if not isinstance(t.get("name"), str) or not re.fullmatch(r"test_\w+", t["name"]) \
                            or not isinstance(t.get("code"), str) or f"def {t['name']}(" not in t["code"] or t["code"].count("\n") >= 30:
                        problems.append(f"{label}: {ew}.tests[{k}]: not a test function of at most 30 lines")
                    block(t.get("code"), f"{ew}.tests[{k}].code")
            data = ex.get("data")
            if not isinstance(data, list):
                problems.append(f"{label}: {ew}: data is not a list")
                data = []
            for k, d in enumerate(data):
                if shape(d, "data", f"{ew}.data[{k}]"):
                    if not isinstance(d.get("path"), str) or d["path"] not in paths:
                        problems.append(f"{label}: {ew}.data[{k}]: path {d.get('path')!r} is not a touched file")
                    if not isinstance(d.get("header_and_row"), str) or d["header_and_row"].count("\n") > 1:
                        problems.append(f"{label}: {ew}.data[{k}]: header_and_row is not at most two lines")
                    block(d.get("header_and_row"), f"{ew}.data[{k}].header_and_row")
            touches = ex.get("touches")
            if not isinstance(touches, list) or not touches:
                problems.append(f"{label}: {ew}: no touched files")
                continue
            for k, t in enumerate(touches):
                if shape(t, "touch", f"{ew}.touches[{k}]"):
                    if not isinstance(t.get("path"), str) or not re.fullmatch(r"[\w./-]+", t["path"]) or ".." in t["path"]:
                        problems.append(f"{label}: {ew}.touches[{k}]: path {t.get('path')!r}")
                    url(t.get("url"), f"{ew}.touches[{k}].url", nullable=True)
    session = doc.get("session")
    if shape(session, "session", "session"):
        block(session.get("diagram"), "session.diagram")
        parts = session.get("parts")
        if not isinstance(parts, list) or not parts:
            problems.append(f"{label}: session: no parts")
            parts = []
        for i, part in enumerate(parts):
            pw = f"session.parts[{i}]"
            if not shape(part, "part", pw):
                continue
            if not isinstance(part.get("id"), str) or not re.fullmatch(r"[a-z0-9-]+", part["id"]):
                problems.append(f"{label}: {pw}: id {part.get('id')!r}")
            text(part, "title", pw)
            if part.get("intro") is not None and not (isinstance(part["intro"], str) and part["intro"].strip()):
                problems.append(f"{label}: {pw}: intro is neither text nor null")
            steps = part.get("steps")
            if not isinstance(steps, list) or not steps:
                problems.append(f"{label}: {pw}: no steps")
                steps = []
            for j, st in enumerate(steps):
                sw = f"{pw}.steps[{j}]"
                if not shape(st, "step", sw):
                    continue
                text(st, "title", sw)
                block(st.get("shown"), f"{sw}.shown", nullable=True)
                block(st.get("output"), f"{sw}.output", nullable=True)
                if st.get("shown") is None and st.get("output") is not None:
                    problems.append(f"{label}: {sw}: an applied step (no command shown) has output")
                ex_text = st.get("explain")
                if not isinstance(ex_text, str) or (st.get("shown") is not None and not ex_text.strip()):
                    problems.append(f"{label}: {sw}: missing explain")
    hidden = doc.get("hidden")
    if not isinstance(hidden, list) or not hidden or not all(isinstance(h, str) and LABS_HASH.match(h) for h in hidden) \
            or hidden != sorted(set(hidden)):
        problems.append(f"{label}: hidden must be a sorted list of distinct 12-hex hashes")
        hidden = []
    hidden_set = set(hidden)
    problems += public_checks(label, doc)
    for where, key, v in walk(doc):
        if isinstance(v, str):
            problems += track_text_problems(f"{label}: {where}", v)
            if LABS_HIDDEN_TEXT.search(v):
                problems.append(f"{label}: {where}: hint, solution or stub text {LABS_HIDDEN_TEXT.search(v).group(0)!r}")
            if not where.startswith("$.hidden") and key not in URL_KEYS:
                problems += [f"{label}: {where}: a solution or hint line {line.strip()[:60]!r}"
                             for line in labs_leaks(v, hidden_set, markdown=True)]
    return problems


# --- the glossary of the track: content/ai-engineering/glossary.json (hand-written; build.py renders it at
# /learn/ai-engineering/glossary/ and links each term's first use on a week page and on a labs page) ---------------------
# Each entry: id (kebab), term, aliases, a one-to-three-sentence definition, optional example, see (other ids), case
# (true: link only the exact case, for acronyms), everyday_word (true: the term is also a common English word, so a week
# page links only its aliases; a lab page, where the trading sense dominates, links the word too) and not_in (phrases,
# any case, inside which a use is another sense and is not linked: "can trace to"). Every term the chapters and labs use
# is defined or set aside in not_terms with a reason. The candidates, from the prose of content/ai-engineering/*.md
# (outside fenced code, link targets dropped) and the prose fields of labs/week-N.json: a code span that is one
# identifier with an underscore or a digit suffix (`sma_200`, `p95`), a snake_case name written bare (sma_200), an
# ALLCAPS word of 2-6 letters outside code (ATR), its plural (ATRs, checked as ATR), capitals with a number (ATR14, P5),
# and every lab concept's term. One passes as a term or an alias (any case), a not_terms token (any case) or a full
# match of a not_terms pattern; a not_terms entry that no candidate uses is stale and fails too.
GLOSSARY_FILE = "glossary.json"
GLOSSARY_FIX = "add it to content/ai-engineering/glossary.json terms, or to not_terms with a why"
GLOSSARY_TERM = {"id": str, "term": str, "aliases": [str], "definition": str, "example?": str, "see?": [str],
                 "case?": bool, "everyday_word?": bool, "not_in?": [str]}
GLOSSARY_TERM_KEYS = {k.rstrip("?") for k in GLOSSARY_TERM}
GLOSSARY_NOT_TERM = ({"token": str, "why": str}, {"pattern": str, "why": str})
GLOSSARY_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
GLOSSARY_PROSE_KEYS = frozenset({"title", "goal", "effect", "what_tested", "writes", "term", "meaning", "intro", "explain"})
GLOSSARY_FENCE = re.compile(r"^\s*(?:```|~~~)")
GLOSSARY_CODE_SPAN = re.compile(r"`([^`\n]+)`")
GLOSSARY_LINK_DEST = re.compile(r"\]\([^)\s]*\)|<https://[^>\s]*>")
GLOSSARY_CODE_IDENT = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+|[A-Za-z]+[0-9]+")
GLOSSARY_BARE_IDENT = re.compile(r"(?<![\w/.<>@$\\-])[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+(?![\w/(<>-]|\.\w)")
GLOSSARY_CAPS = re.compile(r"(?<!\w)[A-Z]{2,6}(?!\w|\.[A-Za-z])")
GLOSSARY_CAPS_PLURAL = re.compile(r"(?<!\w)([A-Z]{2,6})s(?!\w|\.[A-Za-z])")
GLOSSARY_CAPS_NUMBER = re.compile(r"(?<![\w/.<>@$\\-])[A-Z]{1,6}[0-9]+(?![\w-]|\.\w)")


def glossary_prose_lines(text: str):
    """(line number, line) of Markdown outside fenced code blocks, link targets dropped."""
    fenced = False
    for n, line in enumerate(text.split("\n"), 1):
        if GLOSSARY_FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            yield n, GLOSSARY_LINK_DEST.sub("]", line)


def glossary_candidates(content: Path) -> dict[str, dict[str, tuple[str, str, str]]]:
    """{file label: {casefolded candidate: (the candidate, as first written, where)}} over the chapters and the labs
    JSON. A plural ALLCAPS word is the candidate of its singular; where is `line N`, or the JSON path of a labs field
    with the lab and exercise ids (`labs[w1l3].exercises[w1l3.5].goal`)."""
    folder = content / BUILD_TRACK_DIR
    out: dict[str, dict[str, tuple[str, str, str]]] = {}

    def prose(label: str, text: str, where: str | None) -> None:
        found = out.setdefault(label, {})
        for n, line in glossary_prose_lines(text):
            at = where or f"line {n}"
            for m in GLOSSARY_CODE_SPAN.finditer(line):
                if GLOSSARY_CODE_IDENT.fullmatch(m.group(1).strip()):
                    found.setdefault(m.group(1).strip().casefold(), (m.group(1).strip(), m.group(1).strip(), at))
            rest = LABS_MD_ESCAPE.sub(r"\1", GLOSSARY_CODE_SPAN.sub(" ", line))
            for rx in (GLOSSARY_BARE_IDENT, GLOSSARY_CAPS, GLOSSARY_CAPS_NUMBER):
                for m in rx.finditer(rest):
                    found.setdefault(m.group(0).casefold(), (m.group(0), m.group(0), at))
            for m in GLOSSARY_CAPS_PLURAL.finditer(rest):
                found.setdefault(m.group(1).casefold(), (m.group(1), m.group(0), at))

    def strings(obj, path: str, key=None):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield from strings(v, f"{path}.{k}" if path else k, k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                ident = v.get("id") if isinstance(v, dict) else None
                yield from strings(v, f"{path}[{ident if isinstance(ident, str) else i}]", key)
        elif isinstance(obj, str) and key in GLOSSARY_PROSE_KEYS:
            yield key, path, obj

    for path in sorted(folder.glob("*.md")):
        prose(f"{BUILD_TRACK_DIR}/{path.name}", path.read_text(encoding="utf-8"), None)
    for path in sorted((folder / LABS_DIR).glob("week-*.json")):
        label = f"{BUILD_TRACK_DIR}/{LABS_DIR}/{path.name}"
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue   # labs_checks reports it
        for key, where, text in strings(doc, ""):
            prose(label, text, where)
            if key == "term":
                out[label].setdefault(text.strip().casefold(), (text.strip(), text.strip(), where))
    return out


GLOSSARY_ALIAS_GLYPHS = {0x3BA: None}   # kappa: an alias matches the chapters' spelling (Cohen's kappa as a Greek letter); mdlite.esc writes it as &#x3BA;


def glossary_alias_text(where: str, text: str) -> str:
    """The text the public-text rules see: an alias without the chapter letters it may hold."""
    return text.translate(GLOSSARY_ALIAS_GLYPHS) if ".aliases[" in where else text


def glossary_doc_problems(label: str, doc) -> list[str]:
    """The glossary file itself: shape, ids, alphabetical order, one entry per phrase, reasons, public text."""
    errs: list[str] = []
    _t({"terms": [GLOSSARY_TERM], "not_terms": [GLOSSARY_NOT_TERM]}, doc, "$", errs)
    if errs:
        return [f"{label}: {e}" for e in errs]
    problems = [f"{label}: unknown top-level key {k!r}" for k in sorted(set(doc) - {"terms", "not_terms"})]
    problems += public_checks(label, doc)
    problems += [p for where, _, v in walk(doc) if isinstance(v, str)
                 for p in track_text_problems(f"{label}: {where}", glossary_alias_text(where, v))]
    terms, ids, phrases = doc["terms"], set(), {}
    for i, t in enumerate(terms):
        where = f"{label}: terms[{i}] {t['term']!r}"
        problems += [f"{where}: unknown key {k!r}" for k in sorted(set(t) - GLOSSARY_TERM_KEYS)]
        if not GLOSSARY_ID.match(t["id"]):
            problems.append(f"{where}: id {t['id']!r} is not kebab-case")
        if t["id"] in ids:
            problems.append(f"{where}: duplicate id {t['id']!r}")
        ids.add(t["id"])
        if not re.match(r"[A-Za-z]", t["term"]):
            problems.append(f"{where}: a term starts with a letter (the A-Z list)")
        if not t["definition"].strip() or not t.get("example", "x").strip():
            problems.append(f"{where}: empty definition or example")
        if t.get("everyday_word") and not t["aliases"]:
            problems.append(f"{where}: an everyday word links only through its aliases, and it has none")
        for ph in (t["term"], *t["aliases"]):
            if not ph.strip() or ph != ph.strip():
                problems.append(f"{where}: empty or padded phrase {ph!r}")
            elif ph.casefold() in phrases:
                problems.append(f"{where}: {ph!r} is already a phrase of {phrases[ph.casefold()]!r}")
            phrases[ph.casefold()] = t["id"]
        own = [ph.casefold() for ph in (t["term"], *t["aliases"])]
        problems += [f"{where}: not_in {ctx!r} holds none of the term's phrases" for ctx in t.get("not_in", [])
                     if not any(re.search(rf"(?<!\w){re.escape(ph)}(?!\w)", ctx.casefold()) for ph in own)]
    problems += [f"{label}: terms are not in alphabetical order (first out of place: {b['term']!r})"
                 for a_, b in zip(terms, terms[1:]) if a_["term"].casefold() > b["term"].casefold()][:1]
    for t in terms:
        problems += [f"{label}: {t['id']}: see {s!r} is not another term's id" for s in t.get("see", []) if s not in ids or s == t["id"]]
    seen: set[str] = set()
    for i, n in enumerate(doc["not_terms"]):
        what = n.get("token", n.get("pattern"))
        where = f"{label}: not_terms[{i}] {what!r}"
        if set(n) not in ({"token", "why"}, {"pattern", "why"}):
            problems.append(f"{where}: keys are token or pattern, and why")
        if not n["why"].strip() or not what.strip():
            problems.append(f"{where}: empty token, pattern or reason")
        if what.casefold() in seen:
            problems.append(f"{where}: listed twice")
        seen.add(what.casefold())
        if "token" in n and what.casefold() in phrases:
            problems.append(f"{where}: is also a glossary phrase of {phrases[what.casefold()]!r}")
        if "pattern" in n:
            try:
                re.compile(what)
            except re.error as e:
                problems.append(f"{where}: not a regular expression: {e}")
    return problems


def glossary_checks(content: Path) -> list[str]:
    """content/ai-engineering/glossary.json, and every candidate term of the chapters and labs (see above) against it."""
    if not (content / BUILD_TRACK_DIR).is_dir():
        return []   # build_track_checks reports the folder
    label = f"{BUILD_TRACK_DIR}/{GLOSSARY_FILE}"
    try:
        doc = json.loads((content / BUILD_TRACK_DIR / GLOSSARY_FILE).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"{label}: missing"]
    except (OSError, ValueError) as e:
        return [f"{label}: unreadable: {e}"]
    problems = glossary_doc_problems(label, doc)
    if problems:
        return problems
    known = {ph.casefold() for t in doc["terms"] for ph in (t["term"], *t["aliases"])}
    tokens = {n["token"].casefold(): n["token"] for n in doc["not_terms"] if "token" in n}
    patterns = {n["pattern"]: re.compile(n["pattern"]) for n in doc["not_terms"] if "pattern" in n}
    used: set[str] = set()
    for file, found in glossary_candidates(content).items():
        for fold, (token, written, where) in sorted(found.items()):
            if fold in known:
                continue
            hit = fold if fold in tokens else next((p for p, rx in patterns.items() if rx.fullmatch(token)), None)
            if hit is None:
                shown = repr(token) if token == written else f"{token!r} (written {written!r})"
                problems.append(f"{file} ({where}): {shown} is not in the glossary or not_terms; {GLOSSARY_FIX}")
            else:
                used.add(hit)
    problems += [f"{label}: not_terms {tok!r} is used by no chapter or lab (remove it)" for fold, tok in tokens.items() if fold not in used]
    problems += [f"{label}: not_terms pattern {p!r} matches no candidate (remove it)" for p in patterns if p not in used]
    return problems


def disclaimer_index(blocks) -> int | None:
    """The index of the disclaimer quote among a page's first three blocks (mdlite Block list), or None."""
    for i, b in enumerate(blocks[:3]):
        if b.kind == "quote" and b.html == disclaimer_html():
            return i
    return None


@functools.cache
def disclaimer_html() -> str:
    import mdlite  # noqa: E402
    return mdlite.render("# x\n\n" + DISCLAIMER + "\n", link=lambda dest: dest).blocks[1].html


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
        problems += build_track_checks(args.content) + labs_checks(args.content) + glossary_checks(args.content)
        label = f"content {args.content}: {len(docs)} files"
    for p in problems[:200]:
        print("  " + p)
    print(f"scan: {label}; {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
