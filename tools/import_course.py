#!/usr/bin/env python3
"""One-off import of the shipped gigai courses into content/ (standard library only, no model call).

Reads, never imports, the public package data of a released gigai:
    <gigai>/src/gigai/scout/data/learning/shipped/<role>/{catalog.json,course.json,paths/*.json}
and writes content/lessons, content/practice, content/pathways, content/keys, content/merge-candidates.json.
Every concept id of a lesson is mapped through the key list's id map (former_ids included); an unknown id is refused.

A practice path has a ``kind``: ``tool`` (also when missing; the steps cited into one tool's documentation), ``case`` or
``artifact`` (the written pages of gigai.scout.learning_case). A case or artifact file is written with its kind and its
fields unchanged; an unknown kind, an unknown field, or a text with an address, a backtick or a company-looking name is refused.
``--keys`` may also be the site's public key list (schema ``learning-center-concept-keys:1``): a concept id equal to one of its
keys then maps to that key, which lets a later course be added to an existing content/.
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
DEFAULT_GIGAI = Path("/Users/kar/orca/workspaces/gigai/gigai-v0.1.11.10")
DEFAULT_KEYS = Path("/Users/kar/orca/workspaces/gigai/orchestrator/research/learning-center/library/concept-keys-v0.json")
COURSES = ("mlops-ml-platform-engineer", "ai-forward-deployed-engineer")
GENERATED_BY = "Claude through GigAI 0.1.11.10"
FALLBACK_DATE = "2026-10-12"
IMPORT_DATE = "2026-10-12"
SITE_VERSION = "2026.10.1"
FAMILY = "software-engineering"
# A lesson with no mapped key at all gets one by decision of record (REPORT-library 2.1).
PRIMARY_OVERRIDE = {"design-docs-and-adrs": "design-and-code-reviews"}
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


def first_sentence(text: str) -> str:
    text = " ".join(text.split())
    m = re.search(r"(?<=[.!?])\s", text)
    return text[: m.start()] if m else text


def strip_count_sentences(text: str) -> str:
    """Drop every sentence that carries a posting-count phrase."""
    if not text or not POSTING_COUNT.search(text):
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(s for s in sentences if not POSTING_COUNT.search(s))


def key_map(keys: dict) -> dict[tuple[str, str], str]:
    m: dict[tuple[str, str], str] = {}
    for k in keys["keys"]:
        for course, ids in k.get("ids_in_course", {}).items():
            for i in ids:
                m[(course, i)] = k["key"]
        for course, ids in k.get("former_ids", {}).items():
            for i in ids:
                m[(course, i)] = k["key"]
    return m


def public_keys(seed: dict, kmap: dict) -> dict:
    """The key list as the site publishes it: the seed's analysis fields (counts, merge reasons, the raw
    phrase-under-different-ids table, which course used a key) stay in the spike; the public file keeps what a
    lesson, a pathway or a later import needs."""
    out = []
    for k in seed["keys"]:
        former = {c: [i for i in ids if i != k["key"]] for c, ids in k.get("former_ids", {}).items()}
        former = {c: ids for c, ids in former.items() if ids}
        e = {f: k[f] for f in ("key", "display", "area", "category", "technical", "aliases", "parent")}
        e["former_ids"] = former
        if k.get("category_note"):
            e["category_note"] = k["category_note"]
        out.append(e)
    # the public file must map every old id exactly as the seed did
    check = {(c, i): e["key"] for e in out for c, ids in e["former_ids"].items() for i in ids}
    check.update({("*", e["key"]): e["key"] for e in out})
    for (c, i), key in kmap.items():
        if i != key and check.get((c, i)) != key:
            raise SystemExit(f"refused: public key list loses the mapping {c}:{i} -> {key}")
    return {"schema_version": "learning-center-concept-keys:1", "version": int(seed.get("version", 1)), "areas": seed["areas"], "keys": out}


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


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


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
    added keys). The module's entries flip to published; no pathway, no family, no key list and no merge candidates are
    written. The hand-written entries of the module (sd-ex-*) are never touched: an export may only carry ids the
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
    dump(module_file, module)
    n_pub = sum(1 for l in module["lessons"] if l["status"] == "published")
    print(f"module {args.module}: lessons {n_lessons} practice {n_practice}; module entries published {n_pub} of {len(module['lessons'])}")
    return 0


MODULE_GENERATED_BY = "Claude through GigAI (karthik446/gigai-learning-center 4c0cb514)"
MODULE_VERIFIED_BY = "gigai learning pipeline link check (karthik446/gigai-learning-center 4c0cb514)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gigai", type=Path, default=DEFAULT_GIGAI)
    ap.add_argument("--keys", type=Path, default=DEFAULT_KEYS)
    ap.add_argument("--content", type=Path, default=ROOT / "content")
    ap.add_argument("--courses", nargs="+", default=list(COURSES), help="course folder names under the shipped folder")
    ap.add_argument("--module", help="import a pipeline course's export folder as published lessons of content/modules/<ID>.json (with --export)")
    ap.add_argument("--export", type=Path, help="--module: the export folder written by gigai's tools/learning_export_shipped.py")
    ap.add_argument("--generated-by", default=MODULE_GENERATED_BY, help="--module: provenance.generated_by of every lesson and practice file")
    ap.add_argument("--date", default=IMPORT_DATE, help="--module: provenance.generated_on and the changelog date")
    ap.add_argument("--replace", action="store_true", help="--module: overwrite a lesson file that already exists")
    args = ap.parse_args()
    if args.module:
        return import_module(args)
    shipped = args.gigai / "src/gigai/scout/data/learning/shipped"
    content: Path = args.content

    keys = load(args.keys)
    public_list = keys.get("schema_version") == "learning-center-concept-keys:1"
    kmap = key_map(keys)  # built from the full seed file (ids_in_course and former_ids), before the analysis fields go
    keys = public_keys(keys, kmap)
    key_by = {k["key"]: k for k in keys["keys"]}
    dump(content / "keys/concept-keys.json", keys)

    lesson_keys: dict[str, tuple[str, set[str], str]] = {}  # lesson id -> (course, keys, title)
    seen_lessons: dict[str, str] = {}
    pathways = []
    n_lessons = n_practice = 0
    for course_id in args.courses:
        if public_list:
            kmap.update({(course_id, k["key"]): k["key"] for k in keys["keys"] if (course_id, k["key"]) not in kmap})
        folder = shipped / course_id
        course = load(folder / "course.json")
        catalog = load(folder / "catalog.json")
        paths = {p.stem: load(p) for p in sorted((folder / "paths").glob("*.json"))}
        cat_by = {l["id"]: l for l in catalog["lessons"]}
        steps = []
        module_list = []
        n = 0
        for module in course["modules"]:
            module_list.append({"id": module["id"], "title": module["title"], "intro": module.get("intro", "")})
            for lesson in module["concepts"]:
                lid = lesson["id"]
                if lid in seen_lessons:
                    raise SystemExit(f"refused: lesson id {lid} appears in {seen_lessons[lid]} and {course_id}")
                seen_lessons[lid] = course_id
                mapped = map_ids(course_id, lesson.get("concept_keys", []), kmap, f"lesson {lid}")
                if lid in PRIMARY_OVERRIDE:
                    pk = PRIMARY_OVERRIDE[lid]
                    if pk not in key_by:
                        raise SystemExit(f"refused: override key {pk} is not in the key list")
                    mapped = [pk] + [k for k in mapped if k != pk]
                wrote_practice = write_lesson(
                    content, lesson, paths.get(lid), mapped, key_by, cat_by[lid],
                    generated_by=GENERATED_BY, generated_on=None, import_date=IMPORT_DATE,
                    change="imported from the gigai 0.1.11.10 shipped course " + course_id,
                    practice_change="imported from the gigai shipped course " + course_id,
                    verified_by="gigai 0.1.11.10 release-time link check",
                )
                n_lessons += 1
                n_practice += wrote_practice
                lesson_keys[lid] = (course_id, set(mapped), lesson["title"])
                n += 1
                steps.append({
                    "n": n, "lesson": lid, "module": module["title"], "depth": "L2",
                    "why": first_sentence(lesson["summary"]), "prerequisites": [],
                })
        for lid, l in ((l["id"], l) for l in catalog["lessons"]):
            if lid not in seen_lessons:
                raise SystemExit(f"refused: catalog lesson {lid} is not in the course")
        exp = {g: [map_ids(course_id, [i["id"]], kmap, f"expectations {g}")[0] for i in items] for g, items in course.get("expectations", {}).items()}
        tech = {g: [map_ids(course_id, [i["id"]], kmap, f"technologies {g}")[0] for i in items] for g, items in course.get("technologies", {}).items()}
        pathways.append({
            "schema_version": "learning-center-pathway:1",
            "id": course_id,
            "version": 1,
            "title": course["role"],
            "family": FAMILY,
            "role_key": course_id,
            "titles": catalog["titles"],
            "summary": f"A curated sequence over the library for a {course['role']}: {len(steps)} lessons in {len(module_list)} modules, from the foundations of the role to its advanced topics.",
            "shared_modules": ["system-design"],
            "modules": module_list,
            "expectations": exp,
            "technologies": tech,
            "steps": steps,
            "changelog": [{"version": 1, "date": IMPORT_DATE, "change": "re-expressed the gigai 0.1.11.10 shipped course as references into the library"}],
        })
    for p in pathways:
        dump(content / f"pathways/{p['id']}.json", p)

    # near-duplicate pairs across the two courses: written for a later merge, nothing is merged in M1
    cands = []
    ids = sorted(lesson_keys)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if lesson_keys[a][0] == lesson_keys[b][0]:
                continue
            j = jaccard(lesson_keys[a][1], lesson_keys[b][1])
            if j >= 0.33:
                cands.append((j, a, b))
    cands.sort(key=lambda t: (-t[0], t[1], t[2]))
    dump(content / "merge-candidates.json", {
        "schema_version": "learning-center-merge-candidates:1",
        "note": "Pairs of lessons from different courses whose merged-key Jaccard is at least 0.33. Pairs at 0.5 or more are merge candidates; none was merged in site 2026.10.1, both originals are published.",
        "pairs": [{"a": a, "b": b, "jaccard": round(j, 2), "action": "merge candidate" if j >= 0.5 else "link as related",
                   "shared_keys": sorted(lesson_keys[a][1] & lesson_keys[b][1])} for j, a, b in cands],
    })
    print(f"lessons {n_lessons} practice {n_practice} pathways {len(pathways)} keys {len(keys['keys'])} "
          f"merge candidates {sum(1 for j, *_ in cands if j >= 0.5)} (of {len(cands)} pairs >= 0.33)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
