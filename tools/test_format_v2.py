#!/usr/bin/env python3
"""Lesson format v2 (learning-center-lesson:2): the scan rules (one negative test per rule) and the rendered pages (standard library only, no network).

    python3 tools/test_format_v2.py                 # unittest
    python3 tools/test_format_v2.py --keep DIR      # also leave the temp content/ and the built site under DIR (for a browser check)

Two synthetic fixtures (tools/fixtures/format_v2/: one :2 concept lesson, one :2 design exercise, invented text only) are added to a temp
copy of content/ with a fixture module, then scan.py and build.py run on it. Each negative test takes the valid documents, breaks them in
exactly one way (the mutators below, one per rule) and asserts that scan.validate names that rule. Nothing is written to content/ or site/.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import build  # noqa: E402
import scan  # noqa: E402

FIXTURES = TOOLS / "fixtures" / "format_v2"
LESSON, EXERCISE = "fixture-v2-lesson", "fixture-v2-exercise"
KEEP: Path | None = None


def add_fixtures(content: Path) -> None:
    for name in (LESSON, EXERCISE):
        shutil.copy2(FIXTURES / f"{name}.json", content / "lessons" / f"{name}.json")
    module = {"schema_version": "learning-center-module:1", "id": "fixture-v2", "version": 1, "title": "Fixture module v2", "status": "planned",
              "summary": "Two synthetic lessons for the format v2 tests.", "intro": "Invented lessons used only to test the build.",
              "lessons": [{"id": LESSON, "title": "Fixture concept lesson", "status": "published"},
                          {"id": EXERCISE, "title": "Fixture design exercise", "status": "published"}],
              "changelog": [{"version": 1, "date": "2026-10-15", "change": "fixture"}]}
    (content / "modules" / "fixture-v2.json").write_text(json.dumps(module), encoding="utf-8")
    index = json.loads((content / "modules/index.json").read_text(encoding="utf-8"))
    index["modules"].append({"id": "fixture-v2", "title": module["title"], "status": "planned", "summary": module["summary"],
                             "lessons_published": 2, "lessons_planned": 0})
    (content / "modules/index.json").write_text(json.dumps(index), encoding="utf-8")


def blocks_of(doc: dict):
    """Every block dict of a fixture document, in place (to break one)."""
    for s in doc.get("subtopics", []):
        yield from s["blocks"]
    if "worked_example" in doc:
        yield from doc["worked_example"]["blocks"]
    yield from doc["in_practice"]["blocks"]
    for sec in doc.get("exercise", {}).get("reference_answer", []):
        yield from sec["blocks"]


def first(doc: dict, type_: str) -> dict:
    return next(b for b in blocks_of(doc) if b["type"] == type_)


def section(doc: dict, sid: str) -> dict:
    return next(s for s in doc["exercise"]["reference_answer"] if s["id"] == sid)


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="format-v2-"))
        cls.content = cls.tmp / "content"
        shutil.copytree(ROOT / "content", cls.content)
        add_fixtures(cls.content)
        cls.docs, parse_problems = scan.load_all(cls.content)
        assert not parse_problems, parse_problems
        cls.site = cls.tmp / "site"
        cls.built = None
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)   # cleanups run last-in first-out: the copy for --keep goes first
        if KEEP:
            cls.addClassCleanup(lambda: shutil.copytree(cls.tmp, KEEP, dirs_exist_ok=True))

    def problems_after(self, rel: str, mutate) -> list[str]:
        docs = copy.deepcopy(self.docs)
        mutate(docs[f"lessons/{rel}.json"])
        return scan.validate(docs)

    def refuses(self, rel: str, mutate, needle: str) -> None:
        problems = self.problems_after(rel, mutate)
        self.assertTrue(any(needle in p for p in problems), f"expected a problem containing {needle!r}; got {problems[:6]}")


class Valid(Fixture):
    def test_fixtures_pass_the_scan(self) -> None:
        self.assertEqual(scan.validate(copy.deepcopy(self.docs)), [])

    def test_scan_cli_on_the_fixture_tree(self) -> None:
        r = subprocess.run([sys.executable, str(TOOLS / "scan.py"), "--content", str(self.content)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_four_numbers_in_a_paragraph_pass(self) -> None:
        def m(d): first(d, "p")["text"] = "Exactly 1, 2.5 and 4% numbers, with p99 and S3 and v4 as names and 11,600 as one number."
        self.assertEqual(self.problems_after(LESSON, m), [])


class Negative(Fixture):
    # --- the blocks and the shape
    def test_unknown_block_type(self) -> None:
        self.refuses(LESSON, lambda d: first(d, "p").update(type="quote"), "block type 'quote'")

    def test_unknown_field_on_a_block(self) -> None:
        self.refuses(LESSON, lambda d: first(d, "p").update(cite=["s1"]), "unknown field 'cite'")

    def test_missing_required_field(self) -> None:
        self.refuses(LESSON, lambda d: first(d, "callout").pop("text"), "text: missing")

    def test_cites_must_be_a_list_of_strings(self) -> None:
        self.refuses(LESSON, lambda d: first(d, "p").update(cites="s1"), "expected a list")

    def test_table_row_width(self) -> None:
        self.refuses(LESSON, lambda d: first(d, "table")["rows"][0].pop(), "cells, the table has")

    def test_callout_kind(self) -> None:
        self.refuses(LESSON, lambda d: first(d, "callout").update(kind="warning"), "is not one of ('rule', 'pitfall', 'tip')")

    def test_decision_row_field_blank(self) -> None:
        self.refuses(LESSON, lambda d: first(d, "decision")["rows"][0].update(pick_when=" "), "pick_when: empty")

    def test_empty_steps(self) -> None:
        self.refuses(LESSON, lambda d: first(d, "steps").update(items=[]), "needs at least one item")

    def test_schema_version_two_needs_blocks_not_bodies(self) -> None:
        self.refuses(LESSON, lambda d: d["subtopics"][0].pop("blocks"), "blocks: missing")

    def test_legacy_code_must_be_empty(self) -> None:
        self.refuses(LESSON, lambda d: d.update(code=[{"lang": "python", "code": "x"}]), "detail and code are empty lists")

    def test_top_level_diagram_must_be_null(self) -> None:
        self.refuses(LESSON, lambda d: d.update(diagram={"source": "flowchart LR\n A --> B"}), "top-level diagram must be null")

    def test_diagram_directives(self) -> None:
        self.refuses(LESSON, lambda d: first(d, "diagram").update(mermaid="%%{init: {}}%%\nflowchart LR\n A --> B"), "no C4 syntax and no Mermaid directives")

    def test_reserved_subtopic_id(self) -> None:
        self.refuses(LESSON, lambda d: d["subtopics"][0].update(id="sources"), "reserved for a page section")

    # --- the rules of the spec
    def test_in_practice_block_without_cite(self) -> None:
        self.refuses(LESSON, lambda d: d["in_practice"]["blocks"][0].pop("cites"), "every block of in_practice cites")

    def test_in_practice_block_with_empty_cites(self) -> None:
        self.refuses(LESSON, lambda d: d["in_practice"]["blocks"][0].update(cites=[]), "every block of in_practice cites")

    def test_in_practice_block_that_cannot_cite(self) -> None:
        self.refuses(LESSON, lambda d: d["in_practice"]["blocks"].append({"type": "code", "lang": "python", "code": "x = 1"}), "cannot cite")

    def test_five_numbers_in_a_paragraph(self) -> None:
        self.refuses(LESSON, lambda d: first(d, "p").update(text="Values 1, 2, 3, 4 and 5.5 ms in one paragraph."), "holds 5 numbers")

    def test_five_numbers_in_an_exercise_paragraph(self) -> None:
        def m(d): section(d, "scaling-and-the-bottleneck")["blocks"][0]["text"] = "230 posts, 11,600 reads, 46,000 appends, 128 GB cache and 0.5 headroom."
        self.refuses(EXERCISE, m, "holds 5 numbers")

    def test_cite_to_an_unknown_source(self) -> None:
        self.refuses(LESSON, lambda d: first(d, "p").update(cites=["s99"]), "'s99' is not a source id")

    def test_source_ids_in_order(self) -> None:
        def m(d): d["sources"][0]["id"], d["sources"][1]["id"] = "s2", "s1"
        self.refuses(LESSON, m, "ids must be s1..s8 in order")

    def test_source_kind(self) -> None:
        self.refuses(LESSON, lambda d: d["sources"][0].update(kind="talk"), "kind 'talk'")

    def test_concept_lesson_needs_a_table_or_decision(self) -> None:
        def m(d):
            for blocks in [s["blocks"] for s in d["subtopics"]] + [d["worked_example"]["blocks"]]:
                blocks[:] = [b for b in blocks if b["type"] not in ("table", "decision")]
            d["subtopics"][1]["blocks"].append({"type": "p", "text": "Filler."})
        self.refuses(LESSON, m, "needs at least one table or decision block")

    def test_concept_lesson_needs_a_worked_example(self) -> None:
        self.refuses(LESSON, lambda d: d.pop("worked_example"), "needs a worked example")

    def test_worked_example_needs_steps(self) -> None:
        self.refuses(LESSON, lambda d: d["worked_example"].update(blocks=[b for b in d["worked_example"]["blocks"] if b["type"] != "steps"]),
                     "needs a title and a steps block")

    def test_choice_lesson_needs_a_decision_by_primary_key(self) -> None:
        def m(d):
            d["primary_key"], d["keys"] = "caching", ["caching", "automation"]
            for s in d["subtopics"]:
                s["blocks"] = [b for b in s["blocks"] if b["type"] != "decision"]
        self.refuses(LESSON, m, "about a choice")

    def test_choice_lesson_needs_a_decision_by_id(self) -> None:
        docs = copy.deepcopy(self.docs)
        lesson = docs.pop(f"lessons/{LESSON}.json")
        lesson["id"] = "sd-caching"
        lesson["subtopics"][2]["blocks"] = [{"type": "p", "text": "No choice table here."}]
        docs.pop("lessons/sd-caching.json")
        docs["lessons/sd-caching.json"] = lesson
        self.assertTrue(any("about a choice" in p for p in scan.validate(docs)))

    def test_aws_section_after_high_level_design(self) -> None:
        aws = {"id": "building-it-on-aws", "title": "Building it on AWS", "blocks": [
            {"type": "table", "caption": "Components", "columns": ["component", "AWS pick", "the alternative", "pick the alternative when"],
             "rows": [["store", "DynamoDB", "Aurora", "joins"]]},
            {"type": "table", "caption": "Decisions", "columns": ["fork", "choice", "why"], "rows": [["queue", "SQS", "no replay needed"]]},
            {"type": "table", "caption": "Pillars", "columns": ["pillar", "asks", "choice", "risk"], "rows": [["security", "least privilege", "IAM roles", "none"]]}]}
        def ok(d): d["exercise"]["reference_answer"].insert(2, copy.deepcopy(aws))
        self.assertEqual(self.problems_after(EXERCISE, ok), [])
        def wrong_place(d): d["exercise"]["reference_answer"].insert(3, copy.deepcopy(aws))
        self.refuses(EXERCISE, wrong_place, "right after high-level-design")
        def too_few_tables(d):
            s = copy.deepcopy(aws); s["blocks"] = s["blocks"][:2]; d["exercise"]["reference_answer"].insert(2, s)
        self.refuses(EXERCISE, too_few_tables, "at least 3 table blocks")

    def test_too_few_sources(self) -> None:
        def m(d):
            del d["sources"][7]
            for b in blocks_of(d):
                if "cites" in b:
                    b["cites"] = [c for c in b["cites"] if c != "s8"]
        self.refuses(LESSON, m, "cites 8 to 12 sources, got 7")

    def test_too_many_sources(self) -> None:
        def m(d):
            for n in range(9, 14):
                d["sources"].append({**d["sources"][0], "id": f"s{n}"})
        self.refuses(LESSON, m, "cites 8 to 12 sources, got 13")

    def test_source_not_verified_200(self) -> None:
        self.refuses(LESSON, lambda d: d["sources"][2]["verified"].update(http=404), "verified.http must be 200")

    def test_source_without_a_checked_date(self) -> None:
        self.refuses(LESSON, lambda d: d["sources"][2]["verified"].update(checked="yesterday"), "verified.http must be 200")

    def test_sim_digit_rule_still_applies(self) -> None:
        def m(d):
            d["sim"] = copy.deepcopy(self.docs["lessons/sd-caching.json"]["sim"])
            d["sim"]["caption"] = d["sim"]["caption"] + " It always lands at 47% for a reason nobody measured."
        self.refuses(LESSON, m, "not covered by a sim_claims entry")

    def test_sim_passes_on_v2(self) -> None:
        def m(d): d["sim"] = copy.deepcopy(self.docs["lessons/sd-caching.json"]["sim"])
        self.assertEqual(self.problems_after(LESSON, m), [])

    # --- the exercise rules
    def test_estimates_table_columns(self) -> None:
        self.refuses(EXERCISE, lambda d: section(d, "requirements-and-estimates")["blocks"][1].update(columns=["quantity", "per day", "per second", "peak", "note"]),
                     "needs a table block with the columns ['quantity', 'per day'")

    def test_estimates_without_a_table(self) -> None:
        self.refuses(EXERCISE, lambda d: section(d, "requirements-and-estimates").update(blocks=[{"type": "p", "text": "Words only."}]), "section requirements-and-estimates")

    def test_data_model_needs_a_table_or_code(self) -> None:
        self.refuses(EXERCISE, lambda d: section(d, "data-model").update(blocks=[{"type": "p", "text": "Words only."}]), "section data-model")

    def test_data_model_code_block_is_enough(self) -> None:
        self.assertEqual(self.problems_after(EXERCISE, lambda d: section(d, "data-model").update(blocks=[{"type": "code", "lang": "sql", "code": "create table t (id int);"}])), [])

    def test_api_table_columns(self) -> None:
        self.refuses(EXERCISE, lambda d: section(d, "data-model")["blocks"][1].update(columns=["method", "path", "body", "reply", "notes"]), "an API table has the columns")

    def test_core_flow_needs_steps(self) -> None:
        self.refuses(EXERCISE, lambda d: section(d, "core-flow").update(blocks=[{"type": "list", "items": ["a"]}]), "section core-flow: needs a steps block")

    def test_high_level_design_needs_one_diagram(self) -> None:
        self.refuses(EXERCISE, lambda d: section(d, "high-level-design").update(blocks=[{"type": "p", "text": "No picture."}]), "needs exactly one diagram block, has 0")

    def test_high_level_design_with_two_diagrams(self) -> None:
        def m(d):
            b = section(d, "high-level-design")["blocks"]
            b.append(copy.deepcopy(b[0]))
        self.refuses(EXERCISE, m, "needs exactly one diagram block, has 2")

    def test_diagram_in_another_section(self) -> None:
        def m(d): section(d, "at-10x")["blocks"].append(copy.deepcopy(section(d, "high-level-design")["blocks"][0]))
        self.refuses(EXERCISE, m, "belongs in high-level-design only")

    def test_exercise_diagram_is_a_flowchart(self) -> None:
        self.refuses(EXERCISE, lambda d: section(d, "high-level-design")["blocks"][0].update(mermaid="sequenceDiagram\n A->>B: hi"), "must be a Mermaid flowchart")

    def test_section_order(self) -> None:
        def m(d): d["exercise"]["reference_answer"].reverse()
        self.refuses(EXERCISE, m, "sections must be exactly")

    def test_constraints_block_type(self) -> None:
        self.refuses(EXERCISE, lambda d: d["exercise"].update(constraints={"type": "p", "text": "Prose."}), "exercise.constraints: a list or table block")

    def test_frame_block_type(self) -> None:
        self.refuses(EXERCISE, lambda d: d["exercise"].update(interview_frame={"type": "table", "columns": ["a"], "rows": [["b"]]}), "exercise.interview_frame")

    def test_frame_needs_three_entries(self) -> None:
        self.refuses(EXERCISE, lambda d: d["exercise"].update(design_doc_frame={"type": "list", "items": ["one", "two"]}), "at least 3 entries")

    def test_rubric_bounds(self) -> None:
        self.refuses(EXERCISE, lambda d: d["exercise"]["rubric"].update(L3=[]), "rubric has 6 lines")

    def test_clarifying_question_count(self) -> None:
        self.refuses(EXERCISE, lambda d: d["exercise"]["clarifying_questions"].pop(), "4 clarifying questions")

    def test_exercise_top_level_diagram(self) -> None:
        self.refuses(EXERCISE, lambda d: d.update(diagram={"source": "flowchart LR\n A --> B"}), "top-level diagram must be null")

    def test_exercise_sources(self) -> None:
        def m(d):
            d["sources"] = d["sources"][:2]
            for b in blocks_of(d):
                if "cites" in b:
                    b["cites"] = [c for c in b["cites"] if c in ("s1", "s2")]
        self.refuses(EXERCISE, m, "at least 3 sources")


class Pages(Fixture):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.stats = build.build(cls.content, cls.site)
        read = lambda lid: (cls.site / "learn" / "lessons" / lid / "index.html").read_text(encoding="utf-8")  # noqa: E731
        cls.lesson, cls.exercise = read(LESSON), read(EXERCISE)

    def in_order(self, page: str, marks: list[str]) -> None:
        at = [page.find(m) for m in marks]
        self.assertTrue(all(i >= 0 for i in at), dict(zip(marks, at)))
        self.assertEqual(at, sorted(at), dict(zip(marks, at)))

    def test_lesson_page_order(self) -> None:
        self.in_order(self.lesson, ["<h1>", 'class="attribution"', 'class="on-this-page"', 'id="the-idea"', 'id="the-numbers"', 'id="the-choice"', 'id="the-code"',
                                    'id="worked-example"', 'id="in-practice"', "<h2>Technologies</h2>", 'id="sources"', "<h2>Related lessons</h2>"])

    def test_lesson_has_no_read_more_box_or_old_sections(self) -> None:
        for gone in ("Read more", "sources-preview", "How it is done in practice", "<h2>Subtopics</h2>", "<h2>Diagram</h2>", "<h2>Code</h2>"):
            self.assertNotIn(gone, self.lesson)

    def test_on_this_page_lists_subtopics_worked_example_and_in_practice(self) -> None:
        otp = self.lesson.split('class="on-this-page"')[1].split("</ul>")[0]
        for t in ("The idea", "The numbers", "How to choose", "The code", "The limits", "Worked example", "In practice"):
            self.assertIn(f">{t}</a>", otp)

    def test_cite_marks_link_to_the_numbered_sources(self) -> None:
        self.assertIn('<sup class="cite"><a href="#source-s1" aria-label="Source 1">[1]</a></sup>', self.lesson)
        self.assertIn('<a href="#source-s1" aria-label="Source 1">[1]</a> <a href="#source-s3" aria-label="Source 3">[3]</a>', self.lesson)
        for n in range(1, 9):
            self.assertIn(f'<li id="source-s{n}">', self.lesson)
        self.assertLess(self.lesson.find('id="source-s1"'), self.lesson.find('id="source-s2"'))
        self.assertIn('<ol class="sources-list sources-numbered">', self.lesson)

    def test_blocks(self) -> None:
        self.assertGreaterEqual(self.lesson.count('<div class="table-scroll"'), 3)
        for kind in ("rule", "tip", "pitfall"):
            self.assertIn(f'class="callout callout-{kind}"', self.lesson)
        self.assertIn("<ol><li>an ordered item", self.lesson)
        self.assertIn("<ul><li>an unordered item", self.lesson)
        self.assertIn('<div class="steps-block"><p class="steps-title">Size it</p><ol>', self.lesson)
        self.assertIn('<table class="decision"><caption>A synthetic choice<sup class="cite"><a href="#source-s6" aria-label="Source 6">[6]</a></sup></caption><thead><tr><th scope="col">Option</th><th scope="col">Pick when</th>'
                      '<th scope="col">Avoid when</th><th scope="col">Example</th></tr></thead><tbody><tr><th scope="row">Option A</th>', self.lesson)
        self.assertIn('<pre><code class="language-python" data-lang="python">', self.lesson)
        self.assertIn('<pre class="mermaid">flowchart LR', self.lesson)
        self.assertIn("/_assets/hljs/highlight.min.js", self.lesson)
        self.assertIn("/_assets/mermaid/mermaid.min.js", self.lesson)

    def test_table_cites_print_once_in_the_caption(self) -> None:
        for page in (self.lesson, self.exercise):
            self.assertIsNone(re.search(r'</table></div>\s*<p class="cite-row">', page))
        self.assertRegex(self.lesson, r'<caption>[^<]*<sup class="cite"><a href="#source-s\d+"')

    def test_sidebar_lessons_are_a_closed_disclosure(self) -> None:
        self.assertIn('<details class="sidebar-disclosure">\n<summary>Lessons in this module</summary>', self.lesson)
        self.assertIn(".sidebar-disclosure", (self.site / "_assets" / "site.css").read_text(encoding="utf-8"))

    def test_exercise_page(self) -> None:
        ids = ["prompt", "constraints", "clarifying-questions", "reference-answer", "requirements-and-estimates", "high-level-design", "data-model", "core-flow",
               "scaling-and-the-bottleneck", "failure-modes", "trade-offs", "at-10x", "rubric", "interview-frame", "design-doc-frame", "depth", "sources", "related"]
        self.in_order(self.exercise, [f'<h{n} id="{i}"' for i, n in zip(ids, [2, 2, 2, 2] + [3] * 8 + [2] * 6)])
        self.assertEqual(self.exercise.count('<pre class="mermaid">'), 1)
        self.assertIn('<th scope="col">average per second</th>', self.exercise)
        self.assertIn("<li><strong>Question 1?</strong> Answer 1.</li>", self.exercise)
        self.assertIn('<div class="steps-block"><p class="steps-title">Sections</p>', self.exercise)
        self.assertNotIn("sources-preview", self.exercise)

    def test_exercise_lists_have_no_numbers_in_paragraphs(self) -> None:
        self.assertIn("<p>The numbers are in the table, not in this paragraph.</p>", self.exercise)

    def test_pagefind_sees_the_main_and_the_page_is_in_the_sitemap(self) -> None:
        self.assertIn("<main data-pagefind-body>", self.lesson)
        sitemap = (self.site / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn(f"/learn/lessons/{LESSON}/", sitemap)

    def test_catalog_export_titles_come_from_subtopics(self) -> None:
        out = self.tmp / "catalog.json"
        r = subprocess.run([sys.executable, str(TOOLS / "export_catalog.py"), str(out), "--content", str(self.content)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = out.read_text(encoding="utf-8")
        self.assertIn(LESSON, text)
        self.assertIn("The numbers", text)


if __name__ == "__main__":
    if "--keep" in sys.argv:
        at = sys.argv.index("--keep")
        KEEP = Path(sys.argv[at + 1]).resolve()
        del sys.argv[at:at + 2]
    unittest.main()
