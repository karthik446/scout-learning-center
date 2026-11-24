#!/usr/bin/env python3
"""Extract one week of the tradingresearch labs into content/ai-engineering/labs/week-N.json (standard library only).

    python3 tools/import_labs.py --from <labs repo root> --week N     write the JSON
    python3 tools/import_labs.py --check <labs repo root> --week N    exit 1 when the committed JSON differs

Reads `labs/wN/lab.toml`, every `labs/wN/exercises/*/exercise.toml` and the concept table of `labs/wN/pages/concepts.md`
in a checkout of the labs branch, nothing else (no hints, solutions, stubs, tests' text). The JSON holds per lab its id,
title, goal, chapter section numbers, unlock numbers and base tag, its exercises (id, title, effect, touched files,
folder, test file, concept ids), the concept terms and meanings, and the GitHub links it can decide: a touched file links
to the `labs` branch when it is in the checkout's HEAD tree, else to the week's start tag when the tag has it, else
nothing. The only text of its own is CONCEPT_LESSONS. build.py renders the pages from the JSON; scan.py checks it.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

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


def extract(repo: Path, week: int) -> dict:
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

    for ex_toml in sorted((folder / "exercises").glob("*/exercise.toml")):
        d = ex_toml.parent
        where = f"labs/{wk}/exercises/{d.name}/exercise.toml"
        ex = tomllib.loads(ex_toml.read_text(encoding="utf-8"))
        require(ex, ("id", "title", "effect", "lab", "concepts", "touches"), where)
        if ex["lab"] not in labs:
            raise LabsError(f"{where}: lab {ex['lab']!r} is not in lab.toml")
        if not d.name.startswith(ex["id"] + "-"):
            raise LabsError(f"{where}: folder name does not start with the id {ex['id']}")
        unknown = [c for c in ex["concepts"] if c not in concepts]
        if unknown:
            raise LabsError(f"{where}: concept id(s) not in concepts.md: {', '.join(unknown)}")
        tests = sorted(p.name for p in d.glob("test_*.py"))
        if len(tests) != 1:
            raise LabsError(f"{where}: expected one test_*.py, found {len(tests)}")
        touches = []
        for path in ex["touches"]:
            if in_tree(repo, "HEAD", path):
                url = f"{REPO}/blob/{REF}/{path}"
            elif in_tree(repo, start_tag, path):
                url = f"{REPO}/blob/{start_tag}/{path}"
            else:
                url = None
            touches.append({"path": path, "url": url})
        labs[ex["lab"]]["exercises"].append({
            "id": ex["id"], "title": ex["title"], "effect": ex["effect"], "concepts": list(ex["concepts"]),
            "touches": touches, "folder": d.name, "folder_url": f"{tree}/exercises/{d.name}",
            "test_file": tests[0], "test_url": f"{blob}/exercises/{d.name}/{tests[0]}"})
    for lid, lab in labs.items():
        if not lab["exercises"]:
            raise LabsError(f"lab {lid} has no exercises")
        lab["exercises"].sort(key=lambda e: natural(e["id"]))

    for cid, lesson in CONCEPT_LESSONS.items():
        if not (LESSONS / f"{lesson}.json").is_file():
            raise LabsError(f"CONCEPT_LESSONS: {cid} -> {lesson}: no content/lessons/{lesson}.json")
    out_concepts = [{"id": cid, **c, "url": f"{blob}/pages/concepts.md#{cid}", "lesson": CONCEPT_LESSONS.get(cid)}
                    for cid, c in concepts.items()]
    return {
        "week": week,
        "readme_url": f"{REPO}/blob/{REF}/labs/README.md",
        "labs": [labs[k] for k in sorted(labs, key=natural)],
        "concepts": out_concepts,
        "lessons_mapped": sorted(cid for cid in concepts if cid in CONCEPT_LESSONS),
    }


def dump(doc: dict) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--from", dest="src", metavar="DIR", help="the root of a labs-branch checkout")
    g.add_argument("--check", metavar="DIR", help="compare the committed JSON with what DIR yields")
    ap.add_argument("--week", type=int, required=True)
    args = ap.parse_args()
    repo = Path(args.src or args.check)
    if not (repo / "labs").is_dir():
        print(f"not a labs checkout (no labs/): {repo}", file=sys.stderr)
        return 2
    try:
        text = dump(extract(repo, args.week))
    except (LabsError, tomllib.TOMLDecodeError, OSError) as e:
        print(f"import_labs: {e}", file=sys.stderr)
        return 1
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
