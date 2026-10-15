#!/usr/bin/env python3
"""Import a pipeline course's export into one module of content/ (standard library only, no model call).

    python3 tools/import_course.py --module ID --export DIR [--date YYYY-MM-DD] [--replace]

Reads the export folder written by gigai's tools/learning_export_shipped.py (course.json, catalog.json, paths/*.json) and
writes content/lessons, content/practice, flips the entries of content/modules/<ID>.json to published and updates that
module's row (status and counts) in content/modules/index.json. Nothing else is written: there is no pathway, no family,
no key list and no merge-candidates file any more. Every concept id of a lesson must be a key of the site's own
content/keys/concept-keys.json; an unknown id is refused.

A practice path has a ``kind``: ``tool`` (also when missing; the steps cited into one tool's documentation), ``case`` or
``artifact`` (the written pages of gigai.scout.learning_case). A case or artifact file is written with its kind and its
fields unchanged; an unknown kind, an unknown field, or a text with an address, a backtick or a company-looking name is refused.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan  # noqa: E402  (the checks of the public scan: reused for the written pages, never copied)

ROOT = Path(__file__).resolve().parent.parent
FALLBACK_DATE = "2026-10-12"
IMPORT_DATE = "2026-10-12"
# 'N of M postings' sentences and the sentences of a personal course that speak of one machine's postings.
# The keys a written page holds (gigai.scout.learning_shipped._CASE_PATH_KEYS / _ARTIFACT_PATH_KEYS).
WRITTEN_KEYS = {
    "case": ("concept", "kind", "scenario", "constraints", "deliverable", "reference_answer", "rubric", "common_mistakes"),
    "artifact": ("concept", "kind", "artifact_name", "template", "reference_example", "review_checklist"),
}
POSTING_COUNT = re.compile(
    r"\b\d+\s+of\s+\d+\s+(?:stored\s+)?postings\b|\bnamed in your\b|\byour (?:own |stored |own stored )?postings\b", re.IGNORECASE
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def strip_count_sentences(text: str) -> str:
    """Drop every sentence that carries a posting-count phrase."""
    if not text or not POSTING_COUNT.search(text):
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(s for s in sentences if not POSTING_COUNT.search(s))


def map_ids(course: str, ids: list[str], kmap: dict, where: str) -> list[str]:
    out: list[str] = []
    for i in ids:
        if (course, i) not in kmap:
            raise SystemExit(f"refused: {where}: concept id '{i}' maps to no key (course {course})")
        k = kmap[(course, i)]
        if k not in out:
            out.append(k)
    return out


def written_page(lid: str, path: dict) -> dict:
    """The fields of a case or artifact path as they are stored; refuses an unknown key or a text the scan would refuse."""
    kind = path["kind"]
    extra = sorted(set(path) - set(WRITTEN_KEYS[kind]))
    missing = sorted(set(WRITTEN_KEYS[kind]) - set(path))
    if extra or missing:
        raise SystemExit(f"refused: practice {lid}: a {kind} page has unknown keys {extra} / lacks {missing}")
    if path["concept"] != lid:
        raise SystemExit(f"refused: practice {lid}: concept is {path['concept']!r}")
    fields = {k: v for k, v in path.items() if k not in ("concept",)}
    for where, key, value in scan.walk(fields):
        if key in scan.URL_KEYS:
            raise SystemExit(f"refused: practice {lid}: {where}: a {kind} page holds no address field")
        if isinstance(value, str) and key != "kind":
            for why in scan.written_text_problems(value):
                raise SystemExit(f"refused: practice {lid}: {where}: {why}")
    return fields


def path_dates(path: dict) -> list[str]:
    dates = [s["source"]["verified"]["checked"] for k in ("setup", "steps") for s in path.get(k, []) if s.get("source", {}).get("verified")]
    dates += [s["verified"]["checked"] for s in path.get("sources", []) if s.get("verified")]
    return dates


def write_lesson(content: Path, lesson: dict, path: dict | None, mapped: list[str], key_by: dict, cat_entry: dict, *,
                 generated_by: str, generated_on: str | None, import_date: str, change: str, practice_change: str,
                 verified_by: str) -> int:
    """Write content/lessons/<id>.json and, when ``path`` is given, content/practice/<id>.json (tool, case or artifact).

    ``generated_on`` ``None`` takes the newest link-check date of the practice path (the shipped courses' rule), else
    the given date (a pipeline run). Returns 1 when a practice file was written, else 0.
    """
    lid = lesson["id"]
    if not mapped:
        raise SystemExit(f"refused: lesson {lid} has no key")
    primary, secondary = mapped[0], mapped[1:]
    if path is not None and path.get("kind", "tool") not in ("tool", "case", "artifact"):
        raise SystemExit(f"refused: practice {lid}: unknown kind {path.get('kind')!r}")
    dates = path_dates(path) if path else []
    if generated_on is None:
        generated_on = max(dates) if dates else FALLBACK_DATE
    prov = {"generated_by": generated_by, "generated_on": generated_on, "reviewed_by": None, "reviewed_on": None}
    if [s["id"] for s in lesson["subtopics"]] != [s["id"] for s in cat_entry["subtopics"]]:
        raise SystemExit(f"refused: lesson {lid}: course and catalog subtopic ids differ")
    out = {
        "schema_version": "learning-center-lesson:1",
        "id": lid,
        "version": 1,
        "status": "published",
        "superseded_by": None,
        "title": lesson["title"],
        "area": key_by[primary]["area"],
        "primary_key": primary,
        "secondary_keys": secondary,
        "keys": mapped,
        "summary": lesson["summary"],
        "detail": lesson.get("detail", []),
        "in_practice": lesson.get("in_practice", ""),
        "subtopics": lesson["subtopics"],
        "diagram": lesson.get("diagram") or None,
        "code": lesson.get("code", []),
        "technologies": lesson.get("technologies", []),
        "related": lesson.get("related", []),
        "sources": lesson.get("sources", []),
        "practice": f"practice/{lid}" if path else None,
        "provenance": prov,
        "changelog": [{"version": 1, "date": import_date, "change": change}],
    }
    dump(content / f"lessons/{lid}.json", out)
    if not path:
        return 0
    if path.get("kind", "tool") != "tool":
        pr = {
            "schema_version": "learning-center-practice:1",
            "id": f"practice/{lid}",
            "version": 1,
            "lesson": lid,
            **written_page(lid, path),
            "provenance": prov,
            "changelog": [{"version": 1, "date": import_date, "change": practice_change}],
        }
        dump(content / f"practice/{lid}.json", pr)
        return 1
    for field in ("why_this_tool", "alternatives", "tool"):
        path[field] = strip_count_sentences(path.get(field) or "")
        if POSTING_COUNT.search(path[field]):
            raise SystemExit(f"refused: practice {lid}: {field} still speaks of postings")
    tool = path.get("tool", "")
    tool_key = next((k["key"] for k in key_by.values() if tool and k["display"].lower() == tool.lower()), None)
    if not dates:
        raise SystemExit(f"refused: practice {lid}: a tool path with no link-check date")
    pr = {
        "schema_version": "learning-center-practice:1",
        "id": f"practice/{lid}",
        "version": 1,
        "lesson": lid,
        "tool": tool,
        "tool_key": tool_key,
        "why_this_tool": path.get("why_this_tool", ""),
        "alternatives": path.get("alternatives", ""),
        "setup": path.get("setup", []),
        "steps": path.get("steps", []),
        "sources": path.get("sources", []),
        "verified": {"checked": max(dates), "by": verified_by},
        "provenance": prov,
        "changelog": [{"version": 1, "date": import_date, "change": change}],
    }
    if "kind" in path:
        pr["kind"] = path["kind"]
    dump(content / f"practice/{lid}.json", pr)
    return 1


def import_module(args) -> int:
    """``--module ID --export DIR``: a pipeline course exported by gigai's tools/learning_export_shipped.py, whose lesson
    ids are entries of content/modules/<ID>.json, imported as published lessons of that module.

    Every concept id must be a key of the site's own content/keys/concept-keys.json (replace that file first when the run
    added keys). The module's entries flip to published; no key list is written. The hand-written entries of the module (sd-ex-*) are never touched: an export may only carry ids the
    module lists, and a lesson file that already exists is refused unless --replace is given.
    """
    content: Path = args.content
    export: Path = args.export
    if export is None:
        raise SystemExit("refused: --module needs --export DIR (the export folder: course.json, catalog.json, paths/)")
    module_file = content / f"modules/{args.module}.json"
    if not module_file.exists():
        raise SystemExit(f"refused: {module_file} does not exist")
    module = load(module_file)
    entries = {l["id"]: l for l in module["lessons"]}
    keys = load(content / "keys/concept-keys.json")
    if keys.get("schema_version") != "learning-center-concept-keys:1":
        raise SystemExit("refused: content/keys/concept-keys.json is not the site's public key list")
    key_by = {k["key"]: k for k in keys["keys"]}
    kmap = {(args.module, k): k for k in key_by}
    course = load(export / "course.json")
    catalog = load(export / "catalog.json")
    paths = {p.stem: load(p) for p in sorted((export / "paths").glob("*.json"))}
    cat_by = {l["id"]: l for l in catalog["lessons"]}
    ids = [lesson["id"] for m in course["modules"] for lesson in m["concepts"]]
    if len(set(ids)) != len(ids):
        raise SystemExit("refused: a lesson id appears twice in the export")
    for lid in ids:
        if lid not in entries:
            raise SystemExit(f"refused: lesson {lid} is not an entry of module {args.module}")
        if (content / f"lessons/{lid}.json").exists() and not args.replace:
            raise SystemExit(f"refused: content/lessons/{lid}.json exists; pass --replace to overwrite it")
        if lid not in cat_by:
            raise SystemExit(f"refused: lesson {lid} is not in the export's catalog")
    for lid in cat_by:
        if lid not in ids:
            raise SystemExit(f"refused: catalog lesson {lid} is not in the course")
    for lesson in (lesson for m in course["modules"] for lesson in m["concepts"]):
        for r in lesson.get("related", []):
            if r not in ids:
                raise SystemExit(f"refused: lesson {lesson['id']} relates to {r}, which this export does not hold")
    n_lessons = n_practice = 0
    for lesson in (lesson for m in course["modules"] for lesson in m["concepts"]):
        lid = lesson["id"]
        mapped = map_ids(args.module, lesson.get("concept_keys", []), kmap, f"lesson {lid}")
        n_practice += write_lesson(
            content, lesson, paths.get(lid), mapped, key_by, cat_by[lid],
            generated_by=args.generated_by, generated_on=args.date, import_date=args.date,
            change=f"generated by the gigai learning pipeline from tools/curricula/{args.module}.json and imported into module {args.module}",
            practice_change=f"generated by the gigai learning pipeline for module {args.module}",
            verified_by=MODULE_VERIFIED_BY,
        )
        n_lessons += 1
        entries[lid]["status"] = "published"
    n_pub = sum(1 for l in module["lessons"] if l["status"] == "published")
    if n_pub:
        module["status"] = "published"
    dump(module_file, module)
    index_file = content / "modules/index.json"   # the index row carries the counts and the status; keep it in step
    index = load(index_file)
    for row in index["modules"]:
        if row["id"] == args.module:
            row.update(status=module["status"], lessons_published=n_pub, lessons_planned=len(module["lessons"]) - n_pub)
    dump(index_file, index)
    print(f"module {args.module}: lessons {n_lessons} practice {n_practice}; module entries published {n_pub} of {len(module['lessons'])}")
    return 0


MODULE_GENERATED_BY = "Claude through GigAI (karthik446/gigai-learning-center 4c0cb514)"
MODULE_VERIFIED_BY = "gigai learning pipeline link check (karthik446/gigai-learning-center 4c0cb514)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--content", type=Path, default=ROOT / "content")
    ap.add_argument("--module", required=True, help="import a pipeline course's export folder as published lessons of content/modules/<ID>.json (with --export)")
    ap.add_argument("--export", type=Path, help="--module: the export folder written by gigai's tools/learning_export_shipped.py")
    ap.add_argument("--generated-by", default=MODULE_GENERATED_BY, help="--module: provenance.generated_by of every lesson and practice file")
    ap.add_argument("--date", default=IMPORT_DATE, help="--module: provenance.generated_on and the changelog date")
    ap.add_argument("--replace", action="store_true", help="--module: overwrite a lesson file that already exists")
    args = ap.parse_args()
    return import_module(args)


if __name__ == "__main__":
    sys.exit(main())
