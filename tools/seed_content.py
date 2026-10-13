#!/usr/bin/env python3
"""One-off: the hand-kept content files of site 2026.10.1 (system design module, families, redirects, changelog, site.json).

The 40 system design lesson keys and titles come from docs/learning-center/system-design-outline.md section 2 of the
orchestrator repository (public design text, read only); in M1 they are PLANNED entries, no lesson pages exist.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTLINE = Path("/Users/kar/orca/workspaces/gigai/orchestrator/docs/learning-center/system-design-outline.md")
PARTS = {
    "A": "Foundations",
    "B": "Patterns",
    "C": "Design exercises",
    "D": "Real-world practice",
}


def dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    text = OUTLINE.read_text(encoding="utf-8")
    lessons = []
    for m in re.finditer(r"^\*\*([A-D])(\d+)\. (.+?)\*\* \(`(sd-[a-z0-9-]+)`\)", text, re.M):
        part, n, title, key = m.groups()
        lessons.append({"id": key, "title": title.strip(), "part": part, "part_title": PARTS[part], "status": "planned"})
    if len(lessons) != 40 or len({l["id"] for l in lessons}) != 40:
        raise SystemExit(f"expected 40 distinct sd- lessons, found {len(lessons)}")
    c = ROOT / "content"
    dump(c / "modules/system-design.json", {
        "schema_version": "learning-center-module:1",
        "id": "system-design",
        "version": 1,
        "title": "System design",
        "status": "planned",
        "summary": "The mechanisms every design is built from, taught as trade-offs with numbers, plus classic and AI-era design exercises and the real-world practice of design docs, postmortems and migrations. Shared by every engineering pathway.",
        "parts": [{"id": k, "title": v} for k, v in PARTS.items()],
        "lessons": lessons,
    })
    dump(c / "families/software-engineering.json", {
        "schema_version": "learning-center-family:1",
        "id": "software-engineering",
        "version": 1,
        "title": "Software engineering",
        "status": "published",
        "summary": "Backend, platform, ML platform and AI delivery roles. Concept lessons plus practice paths you can run.",
        "roles": [
            {"key": "mlops-ml-platform-engineer", "title": "MLOps / ML platform engineer", "pathway": "mlops-ml-platform-engineer"},
            {"key": "ai-forward-deployed-engineer", "title": "AI forward deployed engineer", "pathway": "ai-forward-deployed-engineer"},
        ],
        "shared_modules": ["system-design"],
    })
    planned = [
        ("product-management", "Product management", "Discovery, prioritisation, roadmaps and the artifacts a product manager is expected to produce."),
        ("engineering-management", "Engineering management", "Hiring, delivery, team health and technical judgement, from team lead to director."),
        ("qa-test", "QA and test", "Test strategy, automation, quality gates and the plans and reports the role produces."),
        ("erp", "ERP systems", "SAP, Oracle, NetSuite and Workday functional and technical roles, with the vendors' own sandboxes."),
        ("salesforce", "Salesforce", "Admin, developer and consultant roles, structured around Trailhead and the certification paths."),
    ]
    dump(c / "families/index.json", {
        "schema_version": "learning-center-families:1",
        "version": 1,
        "families": [{"id": "software-engineering", "title": "Software engineering", "status": "published",
                      "summary": "Backend, platform, ML platform and AI delivery roles. Concept lessons plus practice paths you can run."}]
        + [{"id": i, "title": t, "status": "planned", "summary": s} for i, t, s in planned],
    })
    dump(c / "redirects.json", {"schema_version": "learning-center-redirects:1", "redirects": []})
    dump(c / "changelog.json", {
        "schema_version": "learning-center-changelog:1",
        "entries": [{
            "date": "2026-10-12", "site_version": "2026.10.1", "kind": "site", "id": "site", "version": 1,
            "change": "import of the two shipped courses (MLOps / ML platform engineer, AI forward deployed engineer) from gigai 0.1.11.10: 69 lessons, 62 practice paths, 2 pathways, 230 concept keys; system design module listed as planned",
        }],
    })
    dump(c / "site.json", {
        "schema_version": "learning-center-site:1",
        "site_version": "2026.10.1",
        "base_url": "https://scout.edgelab.one/learn",
        "concept_keys_version": 1,
        "built_from": "gigai 12241e91",
        "updated": "2026-10-12",
    })
    print("system design lessons", len(lessons))
    return 0


if __name__ == "__main__":
    sys.exit(main())
