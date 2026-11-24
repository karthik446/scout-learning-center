#!/usr/bin/env python3
"""Extract one week of the tradingresearch labs into content/ai-engineering/labs/week-N.json (standard library only).

    python3 tools/import_labs.py --from <labs repo root> --week N     write the JSON
    python3 tools/import_labs.py --check <labs repo root> --week N    exit 1 when the committed JSON differs
    python3 tools/import_labs.py --from <repo> --week N --only-lab wNlM --out FILE
                                                                      debugging: one lab only, never into content/

Reads, in a checkout of the labs branch: `labs/wN/lab.toml`, the concept table of `labs/wN/pages/concepts.md`, and per
exercise its `exercise.toml` (id, title, effect, touches, concepts and the site keys goal, what_tested, writes,
show_tests, show_data), its captured `expected_output/fail.txt` and `pass.txt`, the `TODO(<id>)` excerpt of its stub
files, the named test functions of its test file and the first two lines of each `show_data` file; and the week's
walk-through `labs/wN/session/session.toml` with its captured output files. `solution.diff` and `hints.md` are read only
to build `hidden`: the 12-hex sha256 prefixes of the normalised lines a page must never show (the solution's added
lines, every hint from hint 2 on, and hint 1 unless the session prints it). Hashes only, never the text; the import
fails when any text it emits hashes into `hidden`. A touched file links to the `labs` branch when it is in the
checkout's HEAD tree, else to the week's start tag when the tag has it, else nothing. The only text of its own is
CONCEPT_LESSONS. build.py renders the pages from the JSON; scan.py checks it (and re-checks the leak guard).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan  # noqa: E402  (labs_line_hash, labs_leaks: the leak guard's one normaliser)

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "content" / "ai-engineering" / "labs"
LESSONS = ROOT / "content" / "lessons"
REPO = "https://github.com/karthik446/tradingresearch"
REF = "labs"   # the public branch the labs live on

# Concept id (an anchor of labs/wN/pages/concepts.md) -> a learning-center lesson that teaches it. Only lessons that exist
# under content/lessons/ and cover the concept (read from their titles and subtopics); the import fails on a missing id.
CONCEPT_LESSONS = {
    "error-analysis": "llm-agent-evaluation",          # subtopic "Error analysis and evals in the delivery loop"
    "grader": "llm-agent-evaluation",                  # subtopic "Choosing a grader"
    "code-checkable-grader": "llm-agent-evaluation",   # subtopic "Choosing a grader" (code checks versus judges)
    "llm-judge": "llm-agent-evaluation",               # subtopic "Keeping a judge honest"
    "trace": "observability-agent-traces",
    "prompt-version": "prompt-and-context-engineering",   # subtopic "Prompts as code: versions, pinned models and an eval gate"
    "adr": "design-docs-and-adrs",
    "confidence-interval": "model-evaluation-gates",   # comparisons against a baseline with confidence intervals or a bootstrap
}
CONCEPT_ROW = re.compile(r"^\[([^\]]+)\]\(#([a-z0-9_-]+)\)$")

# The site keys of exercise.toml (SPEC-LABS-PAGES contract) and their limits.
SITE_KEYS = ("goal", "what_tested", "writes", "show_tests")
GOAL_MAX, TESTED_MAX, WRITE_MAX, WRITES_N, SHOW_TESTS_N = 300, 400, 220, (2, 5), (1, 2)
START_MAX = 40     # lines of one starting-code excerpt
TEST_MAX = 30      # lines of one shown test, decorators included
AROUND = 4         # lines each side of a marker outside any top-level def/class
LANGS = {".py": "python", ".md": "markdown", ".toml": "toml", ".csv": "csv", ".txt": "text", ".json": "json", ".sh": "bash"}
HINT_SPLIT = re.compile(r"^## Hint \d+\n", re.M)   # the runner's own split (tradingresearch/lab.py _hints)


class LabsError(Exception):
    pass


def natural(s: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def cells(line: str) -> list[str]:
    """The cells of one Markdown table row; `\\|` is a literal pipe."""
    body = line.strip().removeprefix("|").removesuffix("|")
    out, cur, i = [], "", 0
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body) and body[i + 1] == "|":
            cur += "\\|"
            i += 2
            continue
        if body[i] == "|":
            out.append(cur.strip())
            cur = ""
        else:
            cur += body[i]
        i += 1
    out.append(cur.strip())
    return out


def read_concepts(path: Path) -> dict[str, dict]:
    """The `| [Term](#id) | means | ... |` rows of concepts.md -> {id: {term, meaning}}."""
    concepts: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").split("\n"):
        if not line.startswith("| ["):
            continue
        row = cells(line)
        m = CONCEPT_ROW.match(row[0])
        if not m or len(row) < 2:
            raise LabsError(f"{path.name}: a concept row is not '| [Term](#id) | means | ...': {line!r}")
        term, cid = m.groups()
        if cid in concepts:
            raise LabsError(f"{path.name}: concept {cid!r} twice")
        concepts[cid] = {"term": term, "meaning": row[1]}
    if not concepts:
        raise LabsError(f"{path.name}: no concept rows")
    return concepts


def in_tree(repo: Path, ref: str, path: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{ref}:{path}"], capture_output=True).returncode == 0


def require(table: dict, keys: tuple[str, ...], where: str) -> None:
    missing = [k for k in keys if table.get(k) in (None, "", [])]
    if missing:
        raise LabsError(f"{where}: missing {', '.join(missing)}")


def hashes(text: str, forms: bool = False) -> set[str]:
    """The leak-guard hashes of the lines of `text`; with `forms`, of each line's scan.labs_forms too."""
    return {h for line in text.split("\n") for f in (scan.labs_forms(line) if forms else (line,)) if (h := scan.labs_line_hash(f))}


def site_key_problems(ex: dict) -> list[str]:
    """The missing or over-limit site keys of one exercise.toml."""
    out = [k for k in SITE_KEYS if ex.get(k) in (None, "", [])]
    if isinstance(ex.get("goal"), str) and len(ex["goal"]) > GOAL_MAX:
        out.append(f"goal over {GOAL_MAX} chars")
    if isinstance(ex.get("what_tested"), str) and len(ex["what_tested"]) > TESTED_MAX:
        out.append(f"what_tested over {TESTED_MAX} chars")
    w = ex.get("writes")
    if w and (not isinstance(w, list) or not WRITES_N[0] <= len(w) <= WRITES_N[1]
              or not all(isinstance(s, str) and s.strip() and len(s) <= WRITE_MAX for s in w)):
        out.append(f"writes must list {WRITES_N[0]} to {WRITES_N[1]} texts of at most {WRITE_MAX} chars")
    t = ex.get("show_tests")
    if t and (not isinstance(t, list) or not SHOW_TESTS_N[0] <= len(t) <= SHOW_TESTS_N[1] or not all(isinstance(s, str) for s in t)):
        out.append(f"show_tests must name {SHOW_TESTS_N[0]} or {SHOW_TESTS_N[1]} test functions")
    d = ex.get("show_data", [])
    if not isinstance(d, list) or not all(isinstance(s, str) for s in d):
        out.append("show_data must list repo-relative paths")
    return out


def top_blocks(src: str) -> list[tuple[int, int]]:
    """1-based (first, last) line of each top-level def/class: from its first decorator to its last indented line."""
    lines = src.split("\n")
    out = []
    for node in ast.parse(src).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = min([d.lineno for d in node.decorator_list] + [node.lineno])
            last = node.end_lineno or node.lineno
            while last < len(lines) and (not lines[last].strip() or lines[last][:1].isspace()):
                last += 1   # a trailing comment of the body belongs to it
            while not lines[last - 1].strip():
                last -= 1
            out.append((first, last))
    return out


def excerpts(path: str, src: str, eid: str, hidden: set[str], where: str) -> list[tuple[int, int]]:
    """The 1-based line spans of the starting code an exercise shows of one stub file (empty: no marker)."""
    lines = src.split("\n")
    marker = re.compile(r"(?:#|<!--|//)\s*TODO\(" + re.escape(eid) + r"\)")
    marks = [i + 1 for i, line in enumerate(lines) if marker.search(line)]
    if not marks:
        return []
    blocks = top_blocks(src) if path.endswith(".py") else []
    groups: dict[tuple[int, int], list[int]] = {}
    for m in marks:
        blk = next(((a, b) for a, b in blocks if a <= m <= b), (max(1, m - AROUND), min(len(lines), m + AROUND)))
        groups.setdefault(blk, []).append(m)
    spans = []
    for (a, b), ms in groups.items():
        lo, hi = min(ms), max(ms)
        if b - a + 1 > START_MAX:   # a 40-line window round the markers, inside the block
            start = lo if hi - lo + 1 >= START_MAX else max(a, min(lo - (START_MAX - (hi - lo + 1)) // 2, b - START_MAX + 1))
            a, b = start, min(b, start + START_MAX - 1)
            hi = min(hi, b)
        # A later stub holds the reference code of the earlier exercises: keep the largest window round the markers in
        # which no line hashes into `hidden`.
        dirty = [i for i in range(a, b + 1) if scan.labs_leaks(lines[i - 1], hidden, markdown=True)]
        if any(lo <= i <= hi for i in dirty):
            raise LabsError(f"{where}: {path}: hidden line {dirty[0]} between the TODO({eid}) markers")
        a = max([i + 1 for i in dirty if i < lo] + [a])
        b = min([i - 1 for i in dirty if i > hi] + [b])
        while a < lo and not lines[a - 1].strip():
            a += 1
        while b > hi and not lines[b - 1].strip():
            b -= 1
        spans.append((a, b))
    return sorted(spans)


def test_sources(src: str, names: list[str], where: str) -> list[dict]:
    """The source of each named module-level `def test_...` (decorators included)."""
    lines = src.split("\n")
    found = {n.name: n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}
    out = []
    for name in names:
        node = found.get(name)
        if node is None:
            raise LabsError(f"{where}: show_tests: no module-level def {name}")
        first = min([d.lineno for d in node.decorator_list] + [node.lineno])
        last = node.end_lineno or node.lineno
        if last - first + 1 > TEST_MAX:
            raise LabsError(f"{where}: show_tests: {name} has {last - first + 1} lines (at most {TEST_MAX})")
        out.append({"name": name, "code": "\n".join(lines[first - 1:last])})
    return out


def start_files(ex_dirs: list[Path], k: int, touches: list[str]) -> dict[str, Path]:
    """Each touched file as the learner starts exercise k: its stub copy, else (no stub/: the learner keeps their own file)
    the copy in the nearest earlier exercise's stub of the week."""
    out = {}
    for path in touches:
        for d in reversed(ex_dirs[:k + 1]):
            if (d / "stub" / path).is_file():
                out[path] = d / "stub" / path
                break
    return out


def read_session(folder: Path, wk: str) -> dict:
    sdir = folder / "session"
    where = f"labs/{wk}/session/session.toml"
    if not (sdir / "session.toml").is_file():
        raise LabsError(f"no {where}")
    spec = tomllib.loads((sdir / "session.toml").read_text(encoding="utf-8"))
    require(spec, ("diagram", "part"), where)
    parts = []
    for i, part in enumerate(spec["part"]):
        pw = f"{where} part[{i}]"
        require(part, ("id", "title", "step"), pw)
        steps = []
        for j, st in enumerate(part["step"]):
            sw = f"{pw} step[{j}]"
            require(st, ("title",), sw)
            if "apply" in st:
                if st["apply"] != "solution" or "run" in st or "output" in st:
                    raise LabsError(f"{sw}: an apply step is `apply = \"solution\"` alone, with no run or output")
                shown = output = None
            elif "run" in st:
                require(st, ("explain",), sw)
                shown = st.get("shown") or st["run"]
                output = None
                if st.get("output"):
                    name = st["output"]
                    if "/" in name or not (sdir / name).is_file():
                        raise LabsError(f"{sw}: output file {name!r} is not in labs/{wk}/session/")
                    output = (sdir / name).read_text(encoding="utf-8")
            else:
                raise LabsError(f"{sw}: neither run nor apply")
            steps.append({"title": st["title"], "shown": shown, "output": output, "explain": st.get("explain", "")})
        parts.append({"id": part["id"], "title": part["title"], "intro": part.get("intro") or None, "steps": steps})
    return {"diagram": spec["diagram"].strip("\n"), "parts": parts}


def emitted_leaks(doc: dict, hidden: set[str]) -> list[str]:
    """Every emitted text line that hashes into `hidden` (the JSON's own hidden list and its links excluded)."""
    out = []
    for where, key, v in scan.walk(doc):
        if isinstance(v, str) and not where.startswith("$.hidden") and key not in scan.URL_KEYS:
            out += [f"{where}: {line.strip()[:60]!r}" for line in scan.labs_leaks(v, hidden, markdown=True)]
    return out


def extract(repo: Path, week: int, only_lab: str | None = None) -> dict:
    wk = f"w{week}"
    folder = repo / "labs" / wk
    lab_toml = folder / "lab.toml"
    if not lab_toml.is_file():
        raise LabsError(f"no {lab_toml.relative_to(repo)}")
    spec = tomllib.loads(lab_toml.read_text(encoding="utf-8"))
    base = spec.get("base")
    start_tag = f"week-{week}-start"
    default_unlock = spec.get("unlock") or {}
    require(default_unlock, ("hints", "solution"), f"labs/{wk}/lab.toml [unlock]")
    concepts = read_concepts(folder / "pages" / "concepts.md")
    tree = f"{REPO}/tree/{REF}/labs/{wk}"
    blob = f"{REPO}/blob/{REF}/labs/{wk}"

    labs: dict[str, dict] = {}
    for lid, lab in (spec.get("labs") or {}).items():
        where = f"labs/{wk}/lab.toml [labs.{lid}]"
        if not re.fullmatch(rf"{wk}l\d+", lid):
            raise LabsError(f"{where}: id is not {wk}lM")
        require(lab, ("title", "page", "goal", "section"), where)
        if not all(isinstance(n, int) for n in lab["section"]):
            raise LabsError(f"{where}: section must list chapter section numbers")
        if not (folder / lab["page"]).is_file():
            raise LabsError(f"{where}: page {lab['page']} does not exist")
        unlock = {**default_unlock, **(lab.get("unlock") or {})}
        labs[lid] = {"id": lid, "title": lab["title"], "goal": lab["goal"], "section": list(lab["section"]),
                     "unlock": {"hints": list(unlock["hints"]), "solution": unlock["solution"]}, "base": base,
                     "page_url": f"{blob}/{lab['page']}", "exercises": []}
    if not labs:
        raise LabsError(f"labs/{wk}/lab.toml: no [labs.*] tables")
    if only_lab is not None and only_lab not in labs:
        raise LabsError(f"--only-lab {only_lab}: not a lab of labs/{wk}/lab.toml")

    # Pass 1: every exercise of the week, in chain order (hidden spans the week: a later stub holds earlier answers).
    loaded = []
    for ex_toml in sorted((folder / "exercises").glob("*/exercise.toml"), key=lambda p: natural(p.parent.name)):
        d = ex_toml.parent
        where = f"labs/{wk}/exercises/{d.name}/exercise.toml"
        ex = tomllib.loads(ex_toml.read_text(encoding="utf-8"))
        require(ex, ("id", "title", "effect", "lab", "concepts", "touches"), where)
        if ex["lab"] not in labs:
            raise LabsError(f"{where}: lab {ex['lab']!r} is not in lab.toml")
        if not d.name.startswith(ex["id"] + "-"):
            raise LabsError(f"{where}: folder name does not start with the id {ex['id']}")
        loaded.append((d, where, ex))
    dirs = [d for d, _, _ in loaded]
    included = [only_lab is None or ex["lab"] == only_lab for _, _, ex in loaded]

    missing = []
    for (d, _, ex), inc in zip(loaded, included):
        if inc:
            probs = site_key_problems(ex) + [f"expected_output/{n}" for n in ("fail.txt", "pass.txt") if not (d / "expected_output" / n).is_file()]
            if probs:
                missing.append(f"{ex['id']} ({', '.join(probs)})")
    if missing:
        raise LabsError(f"labs/{wk}: exercises lack the site keys or captures (SPEC-LABS-PAGES contract): " + "; ".join(missing))

    session = read_session(folder, wk)
    printed = set().union(*(hashes(st["output"]) for p in session["parts"] for st in p["steps"] if st["output"]))

    hidden: set[str] = set()
    shown_tests: list[list[dict]] = []
    for k, ((d, where, ex), inc) in enumerate(zip(loaded, included)):
        tests = sorted(p.name for p in d.glob("test_*.py"))
        if len(tests) != 1:
            raise LabsError(f"{where}: expected one test_*.py, found {len(tests)}")
        src = (d / tests[0]).read_text(encoding="utf-8")
        shown = test_sources(src, list(ex.get("show_tests") or []), where) if inc else []
        shown_tests.append(shown)
        keep = set().union(*(hashes(t["code"], forms=True) for t in shown),
                           *(hashes(p.read_text(encoding="utf-8"), forms=True) for p in start_files(dirs, k, ex["touches"]).values()))
        diff = d / "solution.diff"
        if diff.is_file():
            added = "\n".join(l[1:] for l in diff.read_text(encoding="utf-8").split("\n") if l.startswith("+") and not l.startswith("+++"))
            hidden |= hashes(added) - keep
        hint_file = d / "hints.md"
        if hint_file.is_file():
            # Hints are Markdown: each line is hidden in every form a page could show it in (scan.labs_forms); a line of
            # hint 1 that the session prints is shown on purpose.
            hints = HINT_SPLIT.split(hint_file.read_text(encoding="utf-8"))[1:]
            for n, h in enumerate(hints):
                hidden |= set().union(*(hashes(line, forms=True) for line in h.split("\n")
                                        if n > 0 or scan.labs_line_hash(line) not in printed))

    # Pass 2: the JSON of the included exercises.
    for k, ((d, where, ex), inc) in enumerate(zip(loaded, included)):
        if not inc:
            continue
        unknown = [c for c in ex["concepts"] if c not in concepts]
        if unknown:
            raise LabsError(f"{where}: concept id(s) not in concepts.md: {', '.join(unknown)}")
        test_file = next(p.name for p in d.glob("test_*.py"))
        touches = []
        for path in ex["touches"]:
            if in_tree(repo, "HEAD", path):
                url = f"{REPO}/blob/{REF}/{path}"
            elif in_tree(repo, start_tag, path):
                url = f"{REPO}/blob/{start_tag}/{path}"
            else:
                url = None
            touches.append({"path": path, "url": url})
        start_code = []
        for t in touches:
            f = start_files(dirs, k, [t["path"]]).get(t["path"])
            if f is None:
                continue
            src = f.read_text(encoding="utf-8")
            lines = src.split("\n")
            for a, b in excerpts(t["path"], src, ex["id"], hidden, where):
                start_code.append({"path": t["path"], "url": t["url"], "lines": [a, b], "code": "\n".join(lines[a - 1:b]),
                                   "lang": LANGS.get(Path(t["path"]).suffix, "text")})
        if not start_code:
            raise LabsError(f"{where}: no TODO({ex['id']}) marker in the stub of any touched file ({', '.join(ex['touches'])})")
        data = []
        for path in ex.get("show_data", []):
            f = d / "stub" / path
            if not f.is_file():
                raise LabsError(f"{where}: show_data {path}: not in the exercise's stub/")
            data.append({"path": path, "header_and_row": "\n".join(f.read_text(encoding="utf-8").split("\n")[:2])})
        out = d / "expected_output"
        labs[ex["lab"]]["exercises"].append({
            "id": ex["id"], "title": ex["title"], "effect": ex["effect"], "concepts": list(ex["concepts"]),
            "touches": touches, "folder": d.name, "folder_url": f"{tree}/exercises/{d.name}",
            "test_file": test_file, "test_url": f"{blob}/exercises/{d.name}/{test_file}",
            "goal": ex["goal"], "what_tested": ex["what_tested"], "writes": list(ex["writes"]), "start_code": start_code,
            "tests": shown_tests[k], "data": data,
            "fail": (out / "fail.txt").read_text(encoding="utf-8"), "pass": (out / "pass.txt").read_text(encoding="utf-8")})
    if only_lab is not None:
        labs = {only_lab: labs[only_lab]}
    for lid, lab in labs.items():
        if not lab["exercises"]:
            raise LabsError(f"lab {lid} has no exercises")
        lab["exercises"].sort(key=lambda e: natural(e["id"]))

    for cid, lesson in CONCEPT_LESSONS.items():
        if not (LESSONS / f"{lesson}.json").is_file():
            raise LabsError(f"CONCEPT_LESSONS: {cid} -> {lesson}: no content/lessons/{lesson}.json")
    out_concepts = [{"id": cid, **c, "url": f"{blob}/pages/concepts.md#{cid}", "lesson": CONCEPT_LESSONS.get(cid)}
                    for cid, c in concepts.items()]
    doc = {
        "week": week,
        "readme_url": f"{REPO}/blob/{REF}/labs/README.md",
        "labs": [labs[k] for k in sorted(labs, key=natural)],
        "concepts": out_concepts,
        "lessons_mapped": sorted(cid for cid in concepts if cid in CONCEPT_LESSONS),
        "session": session,
        "hidden": sorted(hidden),
    }
    leaks = emitted_leaks(doc, hidden)
    if leaks:
        raise LabsError("a solution or hint line would reach a page:\n  " + "\n  ".join(leaks[:20]))
    return doc


def dump(doc: dict) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--from", dest="src", metavar="DIR", help="the root of a labs-branch checkout")
    g.add_argument("--check", metavar="DIR", help="compare the committed JSON with what DIR yields")
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--only-lab", metavar="ID", help="debugging: one lab only; needs --out (never content/)")
    ap.add_argument("--out", type=Path, metavar="FILE", help="with --only-lab: where to write the JSON")
    args = ap.parse_args()
    if args.only_lab and (not args.src or not args.out or args.out.resolve().is_relative_to(DEST.resolve())):
        print("--only-lab needs --from and an --out FILE outside content/ai-engineering/labs/", file=sys.stderr)
        return 2
    if args.out and not args.only_lab:
        print("--out is for --only-lab only", file=sys.stderr)
        return 2
    repo = Path(args.src or args.check)
    if not (repo / "labs").is_dir():
        print(f"not a labs checkout (no labs/): {repo}", file=sys.stderr)
        return 2
    try:
        text = dump(extract(repo, args.week, args.only_lab))
    except (LabsError, tomllib.TOMLDecodeError, SyntaxError, OSError) as e:
        print(f"import_labs: {e}", file=sys.stderr)
        return 1
    if args.only_lab:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out} (only {args.only_lab}; debugging, not site data)")
        return 0
    dest = DEST / f"week-{args.week}.json"
    if args.src:
        DEST.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        print(f"wrote {dest.relative_to(ROOT)}")
        return 0
    if not dest.is_file():
        print(f"missing: {dest.relative_to(ROOT)}", file=sys.stderr)
        return 1
    if dest.read_text(encoding="utf-8") != text:
        print(f"differs from the labs checkout: {dest.relative_to(ROOT)} (run --from)", file=sys.stderr)
        return 1
    print(f"{dest.relative_to(ROOT)} matches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
