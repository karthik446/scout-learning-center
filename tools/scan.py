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
