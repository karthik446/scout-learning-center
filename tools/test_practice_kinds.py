#!/usr/bin/env python3
"""The case and artifact practice pages, end to end on a temp copy of content/ (standard library only, no network).

    python3 tools/test_practice_kinds.py            # unittest
    python3 tools/test_practice_kinds.py --keep DIR # also leave the temp content/ and the built site under DIR (for a browser check)

Two synthetic fixtures (tools/fixtures/, invented names only) are imported through import_course.py --module into a temp copy of
content/ (with a fixture module file listing them, so each sits in exactly one module), then scan.py, build.py and
export_catalog.py run on it. Nothing is written to content/ or site/.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
FIXTURES = TOOLS / "fixtures" / "gigai"
COURSE = "src/gigai/scout/data/learning/shipped/fixture-course"
MODEL_LINE = "Written by a model for this lesson, not by a person"
KEEP: Path | None = None


def run(*args: str | Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=ROOT)


def with_fixture_module(content: Path) -> None:
    """The fixture module: two planned entries (the import flips them to published) and a row in modules/index.json."""
    entries = [{"id": "fixture-case-lesson", "title": "Fixture lesson with a case exercise", "status": "planned"},
               {"id": "fixture-artifact-lesson", "title": "Fixture lesson with an artifact exercise", "status": "planned"}]
    module = {"schema_version": "learning-center-module:2", "id": "fixture-course", "version": 1, "title": "Fixture module", "status": "planned",
              "summary": "Two synthetic lessons for the page tests.", "intro": "Invented lessons used only to test the build.", "lessons": entries,
              "changelog": [{"version": 1, "date": "2026-10-14", "change": "fixture"}]}
    (content / "modules/fixture-course.json").write_text(json.dumps(module), encoding="utf-8")
    index = json.loads((content / "modules/index.json").read_text(encoding="utf-8"))
    index["modules"].append({"id": "fixture-course", "title": module["title"], "status": "planned", "summary": module["summary"],
                             "lessons_published": 0, "lessons_planned": 2})
    (content / "modules/index.json").write_text(json.dumps(index), encoding="utf-8")


def import_into(content: Path, export: Path) -> subprocess.CompletedProcess:
    return run(TOOLS / "import_course.py", "--content", content, "--module", "fixture-course", "--export", export / COURSE)


class Imported(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="practice-kinds-"))
        cls.content = cls.tmp / "content"
        shutil.copytree(ROOT / "content", cls.content)
        with_fixture_module(cls.content)
        cls.imp = import_into(cls.content, FIXTURES)
        cls.scan = run(TOOLS / "scan.py", "--content", cls.content)
        cls.site = cls.tmp / "site"
        cls.build = run(TOOLS / "build.py", "--content", cls.content, "--out", cls.site)
        cls.catalog_path = cls.tmp / "catalog.json"
        cls.export = run(TOOLS / "export_catalog.py", cls.catalog_path, "--content", cls.content)

    @classmethod
    def tearDownClass(cls) -> None:
        if KEEP:
            shutil.copytree(cls.tmp, KEEP, dirs_exist_ok=True)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def page(self, lid: str) -> str:
        return (self.site / "learn/practice" / lid / "index.html").read_text(encoding="utf-8")

    def test_steps_ran(self) -> None:
        self.assertEqual(self.imp.returncode, 0, self.imp.stdout + self.imp.stderr)
        self.assertEqual(self.scan.returncode, 0, self.scan.stdout + self.scan.stderr)
        self.assertEqual(self.build.returncode, 0, self.build.stdout + self.build.stderr)
        self.assertEqual(self.export.returncode, 0, self.export.stdout + self.export.stderr)

    def test_fixture_lessons_sit_in_one_module(self) -> None:
        module = json.loads((self.content / "modules/fixture-course.json").read_text(encoding="utf-8"))
        self.assertEqual([e["status"] for e in module["lessons"]], ["published", "published"])
        index = {r["id"]: r for r in json.loads((self.content / "modules/index.json").read_text(encoding="utf-8"))["modules"]}
        self.assertEqual((index["fixture-course"]["status"], index["fixture-course"]["lessons_published"]), ("published", 2))
        page = (self.site / "learn/modules/fixture-course/index.html").read_text(encoding="utf-8")
        self.assertIn("Fixture lesson with a case exercise", page)
        lesson = (self.site / "learn/lessons/fixture-case-lesson/index.html").read_text(encoding="utf-8")
        self.assertIn("Lesson 1 of 2 in", lesson)
        self.assertIn("Learning center</a> &rsaquo; <a href=\"/learn/modules/fixture-course/\">Fixture module</a>", lesson)

    def test_a_lesson_in_two_modules_is_refused(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="practice-kinds-twice-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        content = tmp / "content"
        shutil.copytree(self.content, content)
        path = content / "modules/software-foundations.json"
        module = json.loads(path.read_text(encoding="utf-8"))
        module["lessons"].append({"id": "fixture-case-lesson", "status": "published"})
        path.write_text(json.dumps(module), encoding="utf-8")
        result = run(TOOLS / "scan.py", "--content", content)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one", result.stdout)

    def test_exported_catalog_shape(self) -> None:
        cat = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        self.assertEqual(cat["schema_version"], "scout-learning-catalog:3")
        self.assertEqual(sorted(cat), ["catalog_version", "concept_keys_version", "keys", "lessons", "modules", "schema_version", "site"])
        self.assertEqual(sorted(cat["site"]), ["base_url", "lessons_path", "modules_path", "practice_path", "site_version"])
        self.assertEqual(cat["modules"][-1]["id"], "fixture-course")
        self.assertEqual(cat["modules"][-1]["lessons"], ["fixture-case-lesson", "fixture-artifact-lesson"])
        by_id = {l["id"]: l for l in cat["lessons"]}
        case = by_id["fixture-case-lesson"]
        self.assertEqual(sorted(case), ["concept_keys", "has_practice", "id", "module", "practice_kind", "subtopics", "title"])
        self.assertEqual((case["module"], case["practice_kind"], case["has_practice"]), ("fixture-course", "case", True))
        self.assertEqual(case["concept_keys"], ["system-design"])
        self.assertEqual(case["subtopics"], [{"id": "the-idea", "title": "The idea"}])
        self.assertEqual(by_id["fixture-artifact-lesson"]["practice_kind"], "artifact")
        self.assertEqual(by_id["mcp-servers"]["practice_kind"], "tool")
        self.assertIsNone(by_id["sd-numbers"]["practice_kind"])
        # the real content plus the two fixture lessons and the one fixture module (counts come from content/, not literals)
        published = sum(1 for f in (ROOT / "content" / "lessons").glob("*.json") if json.loads(f.read_text())["status"] == "published")
        module_files = sum(1 for f in (ROOT / "content" / "modules").glob("*.json") if f.name != "index.json")
        key_count = len(json.loads((ROOT / "content" / "keys" / "concept-keys.json").read_text())["keys"])
        self.assertEqual(len(cat["lessons"]), published + 2)
        self.assertEqual(len(cat["modules"]), module_files + 1)
        self.assertEqual(len(cat["keys"]), key_count)
        self.assertEqual(sorted(cat["keys"][0]), ["aliases", "area", "category", "display", "key", "technical"])
        flat = json.dumps(cat)
        for word in ("expectations", "role_key", "postings", "sequence", '"summary"', '"detail"'):
            self.assertNotIn(word, flat)
        self.assertEqual([m["order"] for m in cat["modules"]], list(range(1, len(cat["modules"]) + 1)))

    def test_content_files_keep_kind_and_fields(self) -> None:
        for lid, kind in (("fixture-case-lesson", "case"), ("fixture-artifact-lesson", "artifact")):
            stored = json.loads((self.content / "practice" / f"{lid}.json").read_text(encoding="utf-8"))
            source = json.loads((FIXTURES / COURSE / "paths" / f"{lid}.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["kind"], kind)
            for key, value in source.items():
                if key != "concept":
                    self.assertEqual(stored[key], value, key)
            self.assertEqual(stored["lesson"], lid)

    def test_case_page(self) -> None:
        html = self.page("fixture-case-lesson")
        for text in ("Case exercise: Fixture lesson with a case exercise", "Scenario", "Constraints and numbers", "Deliverable",
                     "Reference answer", "Check your answer", "Common mistakes", MODEL_LINE, "Generated by Claude through GigAI",
                     "Restate the problem", "Names the resize workers"):
            self.assertIn(text, html)
        self.assertNotIn("Done when", html)
        self.assertEqual(html.count("path-number"), 6)  # the rubric is a tick list of six

    def test_artifact_page(self) -> None:
        html = self.page("fixture-artifact-lesson")
        for text in ("Write a launch runbook: Fixture lesson with an artifact exercise", "Template", "Example, filled in",
                     "Review checklist", MODEL_LINE, "Situation (made up):", "Generated by Claude through GigAI", "When it goes wrong"):
            self.assertIn(text, html)
        self.assertNotIn("Done when", html)
        self.assertEqual(html.count("path-number"), 6)

    def test_pages_link_back_and_lesson_links_here(self) -> None:
        self.assertIn('href="/learn/lessons/fixture-case-lesson/"', self.page("fixture-case-lesson"))
        lesson = (self.site / "learn/lessons/fixture-case-lesson/index.html").read_text(encoding="utf-8")
        self.assertIn('href="/learn/practice/fixture-case-lesson/"', lesson)

    def test_a_tool_page_is_unchanged_in_shape(self) -> None:
        html = self.page("mcp-servers")
        self.assertIn("Done when", html)
        self.assertNotIn(MODEL_LINE, html)


class Refusals(unittest.TestCase):
    """import_course.py refuses what the generator never writes; scan.py refuses it in a content file."""

    def imported(self, lid: str, edit) -> subprocess.CompletedProcess:
        tmp = Path(tempfile.mkdtemp(prefix="practice-kinds-refuse-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        gigai = tmp / "gigai"
        shutil.copytree(FIXTURES, gigai)
        target = gigai / COURSE / "paths" / f"{lid}.json"
        data = json.loads(target.read_text(encoding="utf-8"))
        edit(data)
        target.write_text(json.dumps(data), encoding="utf-8")
        shutil.copytree(ROOT / "content", tmp / "content")
        with_fixture_module(tmp / "content")
        return import_into(tmp / "content", gigai)

    def refused(self, lid: str, edit, needle: str) -> None:
        result = self.imported(lid, edit)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(needle, result.stdout + result.stderr)

    def test_unknown_kind(self) -> None:
        self.refused("fixture-case-lesson", lambda d: d.update(kind="quiz"), "unknown kind")

    def test_url(self) -> None:
        self.refused("fixture-case-lesson", lambda d: d.update(deliverable="See https://example.org/guide for the format."), "address")

    def test_bare_domain(self) -> None:
        self.refused("fixture-case-lesson", lambda d: d.update(deliverable="Use the format on example.com please."), "address")

    def test_backtick(self) -> None:
        self.refused("fixture-case-lesson", lambda d: d["constraints"].__setitem__(0, "Run `make test` first."), "backtick")

    def test_company_shape(self) -> None:
        self.refused("fixture-artifact-lesson", lambda d: d["review_checklist"].__setitem__(0, "Check it against the Acme Widgets Inc style."), "company")

    def test_unknown_field(self) -> None:
        self.refused("fixture-artifact-lesson", lambda d: d.update(steps=[]), "unknown keys")

    def test_missing_kind_is_a_tool_path(self) -> None:
        # A tool path with no kind keeps today's shape: the case fixture without its kind has no tool fields, so a tool path
        # is expected and its steps are read; the importer must not mistake it for a written page.
        result = self.imported("fixture-case-lesson", lambda d: d.pop("kind"))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("unknown kind", result.stdout + result.stderr)


class ScanSchema(unittest.TestCase):
    """scan.py: per-kind schema, the generator's bounds, no address anywhere, written_by == 'model'."""

    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(TOOLS))
        import scan  # noqa: PLC0415

        cls.scan = scan
        base = FIXTURES / COURSE / "paths"
        prov = {"generated_by": "Claude through GigAI", "generated_on": "2026-10-12", "reviewed_by": None, "reviewed_on": None}
        head = {"schema_version": "learning-center-practice:1", "version": 1, "provenance": prov,
                "changelog": [{"version": 1, "date": "2026-10-12", "change": "x"}]}
        cls.case = {**head, "id": "practice/c", "lesson": "c", **{k: v for k, v in json.loads((base / "fixture-case-lesson.json").read_text()).items() if k != "concept"}}
        cls.art = {**head, "id": "practice/a", "lesson": "a", **{k: v for k, v in json.loads((base / "fixture-artifact-lesson.json").read_text()).items() if k != "concept"}}

    def problems(self, doc: dict) -> list[str]:
        name = "practice/x.json"
        kind = self.scan.practice_kind(doc)
        errs: list[str] = []
        self.scan._t(self.scan.SCHEMAS["practice-" + kind], doc, "$", errs)
        return errs or self.scan.written_checks(name, doc)

    def test_fixtures_pass(self) -> None:
        self.assertEqual(self.problems(self.case), [])
        self.assertEqual(self.problems(self.art), [])

    def test_bounds(self) -> None:
        for edit, needle in (
            (lambda d: d.update(constraints=d["constraints"][:2]), "constraints"),
            (lambda d: d.update(rubric=d["rubric"][:5]), "rubric"),
            (lambda d: d.update(common_mistakes=d["common_mistakes"] * 3), "common_mistakes"),
            (lambda d: d.update(reference_answer=d["reference_answer"][:4]), "reference_answer"),
            (lambda d: d.update(scenario="One sentence only."), "scenario"),
        ):
            doc = copy.deepcopy(self.case)
            edit(doc)
            self.assertTrue(any(needle in p for p in self.problems(doc)), needle)
        for edit, needle in (
            (lambda d: d.update(template=d["template"][:5]), "template"),
            (lambda d: d.update(review_checklist=d["review_checklist"][:5]), "review_checklist"),
            (lambda d: d["reference_example"].update(written_by="person"), "written_by"),
        ):
            doc = copy.deepcopy(self.art)
            edit(doc)
            self.assertTrue(any(needle in p for p in self.problems(doc)), needle)

    def test_no_address_anywhere(self) -> None:
        doc = copy.deepcopy(self.art)
        doc["reference_example"]["sections"][0]["body"] += " Read https://example.org/x for more."
        self.assertTrue(any("address" in p for p in self.problems(doc)))
        doc = copy.deepcopy(self.case)
        doc["sources"] = [{"url": "https://example.org/x"}]
        self.assertTrue(any("address field" in p for p in self.scan.written_checks("x", doc)))


if __name__ == "__main__":
    if "--keep" in sys.argv:
        at = sys.argv.index("--keep")
        KEEP = Path(sys.argv[at + 1]).resolve()
        del sys.argv[at:at + 2]
    unittest.main(verbosity=2)
