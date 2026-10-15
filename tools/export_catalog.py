#!/usr/bin/env python3
"""content/ -> the library catalog scout-learning-catalog:3 (standard library only, no network, no model, no gigai).

    python3 tools/export_catalog.py OUT.json [--content content]

One file for the whole library: the modules in index order with their published lessons in module order, each lesson with its
module, concept keys (primary first), subtopic ids and titles and its practice kind, the shared concept keys with their aliases,
and the site block. No role, no sequence, no expectations or technologies, no posting counts, no text bodies.

The file is validated against tools/catalog3.schema.json before it is written, and nothing is written when tools/scan.py has
problems with content/. gigai keeps its own copy of the catalog; this site's CI only runs the export once as a check.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan  # noqa: E402  (the same checks CI runs)

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = Path(__file__).resolve().parent / "catalog3.schema.json"
SCHEMA_VERSION = "scout-learning-catalog:3"


def check(schema: dict, value, path: str = "$") -> list[str]:
    """The subset of JSON Schema the catalog schema uses: const, enum, type, required, properties, additionalProperties,
    items, minItems, minLength, minimum, pattern."""
    out: list[str] = []
    if "const" in schema and value != schema["const"]:
        return [f"{path}: expected {schema['const']!r}, got {value!r}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}: {value!r} is not one of {schema['enum']}"]
    t = schema.get("type")
    if t:
        ok = {"object": isinstance(value, dict), "array": isinstance(value, list), "string": isinstance(value, str),
              "boolean": isinstance(value, bool), "integer": isinstance(value, int) and not isinstance(value, bool)}[t]
        if not ok:
            return [f"{path}: expected {t}, got {type(value).__name__}"]
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for r in schema.get("required", []):
            if r not in value:
                out.append(f"{path}.{r}: missing")
        if schema.get("additionalProperties") is False:
            out += [f"{path}.{k}: not allowed" for k in value if k not in props]
        for k, sub in props.items():
            if k in value:
                out += check(sub, value[k], f"{path}.{k}")
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            out.append(f"{path}: fewer than {schema['minItems']} items")
        for i, item in enumerate(value):
            out += check(schema.get("items", {}), item, f"{path}[{i}]")
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            out.append(f"{path}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            out.append(f"{path}: {value!r} does not match {schema['pattern']}")
    elif isinstance(value, int) and not isinstance(value, bool) and value < schema.get("minimum", value):
        out.append(f"{path}: below {schema['minimum']}")
    return out


def build_catalog(content: Path) -> dict:
    docs, problems = scan.load_all(content)
    problems += scan.validate(docs) if not problems else []
    if problems:
        raise SystemExit("export_catalog: content does not pass tools/scan.py:\n  " + "\n  ".join(problems[:30]))
    site = docs["site.json"]
    keys_doc = docs["keys/concept-keys.json"]
    lessons = {d["id"]: d for r, d in docs.items() if r.startswith("lessons/")}
    practice = {d["lesson"]: d for r, d in docs.items() if r.startswith("practice/")}
    modules = {d["id"]: d for r, d in docs.items() if r.startswith("modules/") and r != "modules/index.json"}
    mods, out_lessons = [], []
    for order, row in enumerate(docs["modules/index.json"]["modules"], 1):
        ids = [e["id"] for e in modules[row["id"]]["lessons"] if e["status"] == "published"]
        mods.append({"id": row["id"], "title": row["title"], "order": order, "lessons": ids})
        for lid in ids:
            l = lessons[lid]
            out_lessons.append({
                "id": lid, "title": l["title"], "module": row["id"], "concept_keys": list(l["keys"]),
                "subtopics": [{"id": s["id"], "title": s["title"]} for s in l["subtopics"]],
                "has_practice": lid in practice,
                "practice_kind": scan.practice_kind(practice[lid]) if lid in practice else None,
            })
    keys = [{"key": k["key"], "display": k["display"], "area": k["area"], "category": k["category"],
             "technical": k["technical"], "aliases": list(k["aliases"])} for k in keys_doc["keys"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "catalog_version": f"{site['site_version']}+keys{keys_doc['version']}",
        "concept_keys_version": keys_doc["version"],
        "site": {"base_url": site["base_url"], "site_version": site["site_version"], "lessons_path": "lessons",
                 "practice_path": "practice", "modules_path": "modules"},
        "modules": mods,
        "lessons": out_lessons,
        "keys": keys,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path, help="where to write the catalog (a path given on the command line; never inside content/)")
    ap.add_argument("--content", type=Path, default=ROOT / "content")
    args = ap.parse_args()
    cat = build_catalog(args.content)
    problems = check(json.loads(SCHEMA.read_text(encoding="utf-8")), cat)
    ids = [l["id"] for l in cat["lessons"]]
    if len(set(ids)) != len(ids):
        problems.append("a lesson is listed in two modules")
    known = {k["key"] for k in cat["keys"]}
    problems += [f"lesson {l['id']}: unknown key {k}" for l in cat["lessons"] for k in l["concept_keys"] if k not in known]
    if problems:
        raise SystemExit("export_catalog: the catalog does not validate:\n  " + "\n  ".join(problems[:30]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(cat, indent=1, ensure_ascii=False) + "\n"
    args.out.write_text(text, encoding="utf-8")
    print(f"export_catalog: {args.out}: lessons {len(cat['lessons'])}, modules {len(cat['modules'])}, keys {len(cat['keys'])}, "
          f"{len(text.encode('utf-8'))} bytes, {cat['catalog_version']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
