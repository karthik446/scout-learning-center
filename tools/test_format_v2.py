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

    def test_five_numbers_in_a_table_cell(self) -> None:
        def m(d): first(d, "table")["rows"][0][0] = "14 nodes at $0.3496 an hour for 730 hours is $3,573, about 128 GB"
        self.refuses(LESSON, m, "a table cell holds 5 numbers (at most 4), the same as a paragraph")
        def dm(d):
            d["subtopics"][0]["blocks"].append({"type": "decision", "caption": "c", "rows": [
                {"option": "Aurora", "pick_when": "1 writer, 2 readers, 4 ACUs, 730 hours and $700.80 a month", "avoid_when": "key lookups"}]})
        self.refuses(LESSON, dm, "a decision cell holds 5 numbers (at most 4), the same as a paragraph")

    def test_four_numbers_in_a_table_cell_pass(self) -> None:
        def m(d): first(d, "table")["rows"][0][0] = "14 nodes at $0.3496 an hour for 730 hours is about $3,570"
        self.assertEqual(self.problems_after(LESSON, m), [])

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

    # The AWS section (orchestrator #46, #50): the architecture flowchart first, sequence diagrams after it (the paths), a decision
    # block, at most one cost table.
    SEQUENCE = "sequenceDiagram\n  autonumber\n  participant C as client\n  participant S as service\n  C->>S: POST\n  S-->>C: 201\n  opt network failure\n    C->>S: retry with the same id\n  end"
    AWS = {"id": "building-it-on-aws", "title": "Building it on AWS", "blocks": [
        {"type": "diagram", "mermaid": "flowchart TB\n  C[client] -->|HTTPS, sync| ALB[Application Load Balancer]\n  ALB -->|HTTP, sync| S[ECS on Fargate]\n  S -->|PutItem, sync| D[(DynamoDB)]",
         "legend": "The neutral boxes, one AWS service each."},
        {"type": "steps", "title": "The write path", "items": ["The client calls the ALB over HTTPS, sync; it retries with backoff.", "The service writes with PutItem, sync."]},
        {"type": "diagram", "mermaid": SEQUENCE, "legend": "The write path. Sources: the retry s1, the write s2.", "cites": ["s1", "s2"]},
        {"type": "p", "text": "The retry carries the same id, so the second write is a no-op."},
        {"type": "list", "items": ["Identity: one task role per service.", "Public: the ALB only."]},
        {"type": "decision", "caption": "Store", "rows": [{"option": "DynamoDB", "pick_when": "key lookups", "avoid_when": "joins", "example": "For this design: chosen, every read is a key lookup."}]},
        {"type": "table", "caption": "Pillars", "columns": ["pillar", "asks", "choice", "risk"], "rows": [["security", "least privilege", "IAM roles", "none"]]},
        {"type": "table", "caption": "Cost", "columns": ["component", "AWS service", "monthly at 10M daily active users", "monthly at 100M daily active users"],
         "rows": [["store", "DynamoDB", "about $300", "about $3,000"]]},
        {"type": "p", "text": "The store dominates."}]}

    def with_aws(self, mutate=None, at: int = 2):
        def m(d):
            s = copy.deepcopy(self.AWS)
            if mutate:
                mutate(s)
            d["exercise"]["reference_answer"].insert(at, s)
        return m

    def test_aws_section_after_high_level_design(self) -> None:
        self.assertEqual(self.problems_after(EXERCISE, self.with_aws()), [])
        self.refuses(EXERCISE, self.with_aws(at=3), "right after high-level-design")

    def test_aws_section_without_a_leading_diagram(self) -> None:
        def drop(s): s["blocks"] = s["blocks"][1:]
        self.refuses(EXERCISE, self.with_aws(drop), "section building-it-on-aws: must start with a diagram block")
        def later(s): s["blocks"] = s["blocks"][1:2] + s["blocks"][:1] + s["blocks"][2:]
        self.refuses(EXERCISE, self.with_aws(later), "must start with a diagram block (the AWS architecture, mirroring the high-level-design one); the first block is 'steps'")

    def test_aws_section_starts_with_the_flowchart_not_a_sequence(self) -> None:
        def seq_first(s): s["blocks"][0] = copy.deepcopy(s["blocks"][2])
        self.refuses(EXERCISE, self.with_aws(seq_first), "section building-it-on-aws: must start with a flowchart (the AWS architecture); a sequence diagram comes after it")

    def test_aws_section_later_diagrams_are_sequence_diagrams(self) -> None:
        def flowchart_again(s): s["blocks"].append(copy.deepcopy(s["blocks"][0]))
        self.refuses(EXERCISE, self.with_aws(flowchart_again), "a later diagram (block 9) must be a sequence diagram (the paths through the services)")
        def two_sequences(s): s["blocks"].insert(4, copy.deepcopy(s["blocks"][2]))
        self.assertEqual(self.problems_after(EXERCISE, self.with_aws(two_sequences)), [])

    # The split (2026-10-15): the architecture may come as two leading flowcharts (write half, read half); a third is a later diagram.
    def test_aws_section_two_leading_flowcharts(self) -> None:
        def two_halves(s): s["blocks"].insert(1, copy.deepcopy(s["blocks"][0]))
        self.assertEqual(self.problems_after(EXERCISE, self.with_aws(two_halves)), [])
        def three(s): s["blocks"][1:1] = [copy.deepcopy(s["blocks"][0]), copy.deepcopy(s["blocks"][0])]
        self.refuses(EXERCISE, self.with_aws(three), "a later diagram (block 2) must be a sequence diagram")
        def flowchart_after_a_sequence(s): s["blocks"].insert(3, copy.deepcopy(s["blocks"][0]))
        self.refuses(EXERCISE, self.with_aws(flowchart_after_a_sequence), "a later diagram (block 3) must be a sequence diagram")

    # A sequence diagram has at most five lanes, declared or implied by its arrows (five is what the 1280 column holds).
    def test_sequence_diagram_participants(self) -> None:
        five = "sequenceDiagram\n  autonumber\n  participant A\n  participant B as Bee\n  actor C\n  participant D\n  participant E\n  A->>B: x\n  B-->>A: y\n  C-)D: z\n  D-xE: w"
        self.assertEqual(scan.sequence_participants(five), {"A", "B", "C", "D", "E"})
        self.assertEqual(scan.sequence_participants(five + "\n  E->>+F: f\n  F-->>-E: g"), {"A", "B", "C", "D", "E", "F"})
        def ok(d): section(d, "core-flow")["blocks"] = [{"type": "diagram", "mermaid": five}]
        self.assertEqual(self.problems_after(EXERCISE, ok), [])
        def six_declared(d): section(d, "core-flow")["blocks"] = [{"type": "diagram", "mermaid": five.replace("  participant E\n", "  participant E\n  participant F\n")}]
        self.refuses(EXERCISE, six_declared, "a sequence diagram has 6 participants (at most 5, declared or implied by its arrows)")
        def six_implied(d): section(d, "core-flow")["blocks"] = [{"type": "diagram", "mermaid": five + "\n  E->>F: implied"}]
        self.refuses(EXERCISE, six_implied, "a sequence diagram has 6 participants (at most 5")
        def in_aws(s): s["blocks"][2]["mermaid"] = five + "\n  E->>F: implied"
        self.refuses(EXERCISE, self.with_aws(in_aws), "a sequence diagram has 6 participants")
        def in_a_concept_lesson(d): first(d, "diagram").update(mermaid=five + "\n  E->>F: implied")
        self.refuses(LESSON, in_a_concept_lesson, "a sequence diagram has 6 participants")

    # The news-feed exercise as shipped (version 9): the two flowchart halves first, the write path in three parts, the identity table,
    # the read path in three parts; the core flow in five; every sequence diagram at most five lanes, a one-sentence lead-in before it,
    # and the step numbers running on across the parts of a path.
    def test_news_feed_diagram_blocks(self) -> None:
        doc = self.docs["lessons/sd-ex-news-feed.json"]
        arrow = re.compile(r"^\s*\S+\s*(?:-->>|->>|--\)|-\)|--x|-x)[+-]?\s*\S+\s*:")

        def kinds(sid):
            return ["flow" if b["type"] == "diagram" and b["mermaid"].startswith("flowchart") else "seq" if b["type"] == "diagram" else b["type"]
                    for b in section(doc, sid)["blocks"]]

        def chains(sid):
            """(start, count) of each sequence diagram, in order, from its autonumber line and its arrows."""
            out = []
            for b in section(doc, sid)["blocks"]:
                if b["type"] == "diagram" and b["mermaid"].startswith("sequenceDiagram"):
                    m = re.search(r"^\s*autonumber(?: (\d+))?\s*$", b["mermaid"], re.M)
                    self.assertIsNotNone(m, "every sequence diagram carries autonumber")
                    out.append((int(m.group(1) or 1), sum(1 for l in b["mermaid"].splitlines() if arrow.match(l))))
            return out

        aws = kinds("building-it-on-aws")
        self.assertEqual(aws[:2], ["flow", "flow"])
        self.assertEqual(aws.count("seq"), 6)
        seqs = [i for i, k in enumerate(aws) if k == "seq"]
        self.assertEqual(aws[seqs[2] + 2], "table", "the identity table follows the fan-out diagram and its line")
        self.assertEqual(aws[seqs[5] + 2], "decision", "the decisions follow the last read diagram and its line")
        self.assertEqual(kinds("core-flow").count("seq"), 5)
        self.assertEqual(kinds("core-flow").count("flow"), 0)
        for sid in ("building-it-on-aws", "core-flow"):
            bl = section(doc, sid)["blocks"]
            for i, b in enumerate(bl):
                if b["type"] == "diagram" and b["mermaid"].startswith("sequenceDiagram"):
                    self.assertLessEqual(len(scan.sequence_participants(b["mermaid"])), 5, f"{sid}[{i}]")
                    self.assertEqual(bl[i - 1]["type"], "p", f"{sid}[{i}]: a lead-in paragraph before every sequence diagram")
                    self.assertNotIn(". ", bl[i - 1]["text"], f"{sid}[{i}]: the lead-in is one sentence")
                    self.assertTrue(set(re.findall(r"\bs\d+\b", b.get("legend", ""))) <= set(b.get("cites", [])), f"{sid}[{i}]: legend ids are cites")
        # write a, b, c run 1..13, 14..18, 19..28; read a, b, c run 1..9, 10..14, 15..20; the core flow 1..22 over five parts
        c = chains("building-it-on-aws")
        self.assertEqual([s for s, _ in c], [1, 14, 19, 1, 10, 15])
        self.assertEqual([s + n - 1 for s, n in c], [13, 18, 28, 9, 14, 20])
        c = chains("core-flow")
        self.assertEqual([s for s, _ in c], [1, 5, 11, 16, 20])
        self.assertEqual([s + n - 1 for s, n in c], [4, 10, 15, 19, 22])

    def test_aws_diagram_cites_must_resolve(self) -> None:
        def bad(s): s["blocks"][2]["cites"] = ["s1", "s9"]
        self.assertTrue(any("s9" in p for p in self.problems_after(EXERCISE, self.with_aws(bad))))

    def test_core_flow_sequence_diagram_stands_in_for_the_steps(self) -> None:
        def seq(d): section(d, "core-flow")["blocks"] = [{"type": "diagram", "mermaid": self.SEQUENCE, "legend": "Post, then read."}]
        self.assertEqual(self.problems_after(EXERCISE, seq), [])
        def flow(d): section(d, "core-flow")["blocks"] = [copy.deepcopy(section(d, "high-level-design")["blocks"][0])]
        self.refuses(EXERCISE, flow, "section core-flow: a diagram here is a sequence diagram")
        self.refuses(EXERCISE, flow, "section core-flow: needs a steps block or a sequence diagram")

    def test_sequence_diagram_in_failure_modes(self) -> None:
        def m(d): section(d, "failure-modes")["blocks"].append({"type": "diagram", "mermaid": self.SEQUENCE})
        self.refuses(EXERCISE, m, "section failure-modes: a diagram block belongs in high-level-design only")

    def test_high_level_design_diagram_is_the_flowchart(self) -> None:
        self.refuses(EXERCISE, lambda d: section(d, "high-level-design")["blocks"][0].update(mermaid=self.SEQUENCE), "section high-level-design: the diagram must be a Mermaid flowchart or flow block (the architecture)")

    def test_diagram_kind_unknown(self) -> None:
        self.refuses(EXERCISE, lambda d: section(d, "high-level-design")["blocks"][0].update(mermaid="gantt\n  title x"), "must be a Mermaid flowchart or sequence diagram")

    def test_aws_section_without_a_decision(self) -> None:
        def drop(s): s["blocks"] = [b for b in s["blocks"] if b["type"] != "decision"]
        self.refuses(EXERCISE, self.with_aws(drop), "section building-it-on-aws: needs at least one decision block")

    def test_aws_section_with_two_cost_tables(self) -> None:
        def second(s):
            s["blocks"].insert(4, {"type": "table", "caption": "Posts store priced", "columns": ["option", "unit price", "quantity per month", "monthly cost"],
                                   "rows": [["DynamoDB", "$0.625 per million writes", "60 million", "$37.50"]]})
        self.refuses(EXERCISE, self.with_aws(second), "section building-it-on-aws: at most one cost table (a column header containing monthly, cost or price), has 2")
        def pillars_are_not_cost(s):
            s["blocks"].insert(4, {"type": "table", "caption": "Components", "columns": ["component", "AWS pick", "the alternative"], "rows": [["store", "DynamoDB", "Aurora"]]})
        self.assertEqual(self.problems_after(EXERCISE, self.with_aws(pillars_are_not_cost)), [])

    def test_aws_section_is_the_only_other_place_for_a_diagram(self) -> None:
        def m(d):
            self.with_aws()(d)
            section(d, "at-10x")["blocks"].append(copy.deepcopy(self.AWS["blocks"][0]))
        self.refuses(EXERCISE, m, "section at-10x: a diagram block belongs in high-level-design only (or in building-it-on-aws, or a sequence diagram in core-flow)")

    def test_cite_column_holds_source_ids(self) -> None:
        def m(d):
            tb = first(d, "table"); tb["columns"].append("cites")
            for r in tb["rows"]: r.append("s1, s2")
        self.assertEqual(self.problems_after(LESSON, m), [])
        def bad(d):
            tb = first(d, "table"); tb["columns"].append("source")
            for r in tb["rows"]: r.append("the whitepaper")
        self.refuses(LESSON, bad, "holds source ids of this lesson")

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
            d["sim"] = copy.deepcopy(self.docs["lessons/sd-ex-rate-limiter.json"]["sim"])
            d["sim"]["caption"] = d["sim"]["caption"] + " It always lands at 47% for a reason nobody measured."
        self.refuses(LESSON, m, "not covered by a sim_claims entry")

    def test_sim_passes_on_v2(self) -> None:
        def m(d): d["sim"] = copy.deepcopy(self.docs["lessons/sd-ex-rate-limiter.json"]["sim"])
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
        self.refuses(EXERCISE, lambda d: section(d, "core-flow").update(blocks=[{"type": "list", "items": ["a"]}]), "section core-flow: needs a steps block or a sequence diagram")

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

    def test_decision_header_reads_for_this_design_on_an_exercise(self) -> None:
        block = {"type": "decision", "rows": [{"option": "A", "pick_when": "x", "avoid_when": "y", "example": "For this design: A."}]}
        self.assertIn('<th scope="col">Avoid when</th><th scope="col">For this design</th>', build.render_block(build.Page([], exercise=True), block))
        self.assertIn('<th scope="col">Avoid when</th><th scope="col">Example</th>', build.render_block(build.Page([]), block))
        self.assertIn('<th scope="col">Example</th>', self.lesson)   # a concept lesson keeps Example

    def test_diagram_legend_source_ids_render_as_marks(self) -> None:
        pg = build.Page([{"id": "s1"}, {"id": "s2"}, {"id": "s3"}])
        block = {"type": "diagram", "mermaid": "sequenceDiagram\n  A->>B: hi", "legend": "The retry s1, s3; S3 stays a name.", "cites": ["s1", "s2", "s3"]}
        html_ = build.render_block(pg, block)
        self.assertIn('<pre class="mermaid">sequenceDiagram\n  A-&gt;&gt;B: hi</pre>', html_)
        self.assertIn('<p class="muted diagram-legend">The retry <sup class="cite"><a href="#source-s1" aria-label="Source 1">[1]</a></sup>, '
                      '<sup class="cite"><a href="#source-s3" aria-label="Source 3">[3]</a></sup>; S3 stays a name.'
                      '<sup class="cite"><a href="#source-s2" aria-label="Source 2">[2]</a></sup></p>', html_)
        self.assertEqual(html_.count("[1]"), 1)
        plain = build.render_block(pg, {"type": "diagram", "mermaid": "flowchart LR\n  A --> B", "legend": "No sources."})
        self.assertIn('<p class="muted diagram-legend">No sources.</p>', plain)

    def test_news_feed_sequence_style_opt_in(self) -> None:
        marker = 'data-diagram-style="sequence"'
        for page in (self.site / "learn" / "lessons").glob("*/index.html"):
            html_ = page.read_text(encoding="utf-8")
            if page.parent.name == "sd-ex-news-feed":
                self.assertEqual(html_.count(marker), 11)
                marked = re.findall(r'<div class="mermaid-wrap" data-diagram-style="sequence"><pre class="mermaid">(.*?)</pre>', html_, re.S)
                self.assertEqual(len(marked), 11)
                self.assertTrue(all(s.startswith("sequenceDiagram") for s in marked))
                self.assertNotIn('<div class="mermaid-wrap"><pre class="mermaid">flowchart', html_)
                self.assertEqual(html_.count('<section class="flow"'), 3)
                self.assertIn('/_assets/flow.js', html_)
                self.assertIn('/_assets/flow.css', html_)
            else:
                self.assertNotIn(marker, html_, page.parent.name)
                self.assertNotIn('/_assets/flow.js', html_, page.parent.name)
                self.assertNotIn('/_assets/flow.css', html_, page.parent.name)

    def test_styled_diagram_source_stays_text(self) -> None:
        block = {"type": "diagram", "mermaid": "sequenceDiagram\n  A->>B: call<br/>reply", "legend": "Calls."}
        original = copy.deepcopy(block)
        styled = build.render_block(build.Page([], styled_sequences=True), block)
        plain = build.render_block(build.Page([]), block)
        self.assertEqual(styled.replace(' data-diagram-style="sequence"', ""), plain)
        self.assertIn('A-&gt;&gt;B: call&lt;br/&gt;reply', styled)
        self.assertNotIn("<svg", styled)
        self.assertEqual(block, original)
        flow = {"type": "diagram", "mermaid": "flowchart LR\n  A --> B"}
        self.assertEqual(build.render_block(build.Page([], styled_sequences=True), flow),
                         build.render_block(build.Page([]), flow))

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


class Flows(unittest.TestCase):
    def setUp(self):
        self.block = {
            "type": "flow",
            "nodes": [{"id": "a", "label": "Caller", "kind": "actor"},
                      {"id": "b", "label": "Service", "kind": "service"},
                      {"id": "q", "label": "Events", "kind": "queue"},
                      {"id": "s", "label": "Store", "kind": "store"}],
            "frames": [{"id": "private", "title": "Private services", "nodes": ["b", "s"]}],
            "edges": [{"id": "call", "from": "a", "to": "b", "label": "Call"},
                      {"from": "b", "to": "q", "kind": "async", "label": "Enqueue"},
                      {"from": "q", "to": "s", "kind": "async", "label": "Consume"}],
            "steps": [{"edge": "call", "caption": "Call the service"},
                      {"edge": 1, "caption": "Enqueue an event"}, {"edge": 2, "caption": "Consume the event"}],
            "legend": "Calls s1.", "cites": ["s1"],
        }

    def rejects(self, mutate, needle):
        mutate(self.block)
        problems = scan.block_problems(self.block, "$")
        self.assertTrue(any(needle in p for p in problems), problems)

    def test_valid(self):
        self.assertEqual(scan.block_problems(self.block, "$"), [])

    def test_duplicate_nodes(self):
        self.rejects(lambda b: b["nodes"].append(copy.deepcopy(b["nodes"][0])), "node ids must be unique")

    def test_missing_edge_node(self):
        self.rejects(lambda b: b["edges"][0].update(to="missing"), "existing nodes")

    def test_missing_step_edge(self):
        self.rejects(lambda b: b["steps"][0].update(edge="missing"), "existing edges")

    def test_negative_step_edge(self):
        self.rejects(lambda b: b["steps"][0].update(edge=-1), "existing edges")

    def test_edge_without_step(self):
        self.rejects(lambda b: b["steps"].pop(), "every edge needs a step")

    def test_frame_missing_node(self):
        self.rejects(lambda b: b["frames"][0]["nodes"].append("missing"), "existing nodes")

    def test_overlapping_frames(self):
        self.rejects(lambda b: b["frames"].append({"id": "other", "title": "Other", "nodes": ["b"]}), "not overlap")

    def test_nested_frames(self):
        self.rejects(lambda b: b["frames"].append({"id": "outer", "title": "Outer", "nodes": ["private"]}), "never nested")

    def test_frame_nesting_field(self):
        self.rejects(lambda b: b["frames"][0].update(frames=[]), "no nesting")

    def test_blank_labels(self):
        for field, key in (("nodes", "label"), ("edges", "label"), ("frames", "title"), ("steps", "caption")):
            with self.subTest(field=field):
                b = copy.deepcopy(self.block)
                b[field][0][key] = " "
                self.assertTrue(any("non-empty" in p for p in scan.block_problems(b, "$")))

    def test_multiline_caption(self):
        self.rejects(lambda b: b["steps"][0].update(caption="One\nTwo"), "single lines")

    def test_invalid_kinds(self):
        for field in ("nodes", "edges"):
            with self.subTest(field=field):
                b = copy.deepcopy(self.block)
                b[field][0]["kind"] = "invalid"
                self.assertTrue(any("invalid" in p for p in scan.block_problems(b, "$")))

    def test_node_limit(self):
        self.rejects(lambda b: b["nodes"].extend({"id": f"x{i}", "label": "Extra", "kind": "service"} for i in range(9)), "1 to 12")

    def test_no_coordinates(self):
        self.rejects(lambda b: b["nodes"][0].update(x=1), "no coordinates")

    def test_legend_cites(self):
        self.rejects(lambda b: b.update(legend="Unknown s2."), "legend source s2")

    def test_duplicate_edge_ids(self):
        self.rejects(lambda b: b["edges"][1].update(id="call"), "edge ids must be unique")

    def test_duplicate_frame_ids(self):
        self.rejects(lambda b: b["frames"].append({"id": "private", "title": "Other", "nodes": ["a"]}), "frame ids must be unique")

    def test_blank_short_label(self):
        self.rejects(lambda b: b["edges"][0].update(short=" "), "short labels must be non-empty")

    @staticmethod
    def collinear_overlap(a, z, c, d):
        if a[0] == z[0] == c[0] == d[0]:
            return max(0, min(max(a[1], z[1]), max(c[1], d[1]))-max(min(a[1], z[1]), min(c[1], d[1])))
        if a[1] == z[1] == c[1] == d[1]:
            return max(0, min(max(a[0], z[0]), max(c[0], d[0]))-max(min(a[0], z[0]), min(c[0], d[0])))
        return 0

    def test_render_and_geometry(self):
        news = json.loads((ROOT / "content/lessons/sd-ex-news-feed.json").read_text())
        blocks = [self.block] + [b for b in blocks_of(news) if b["type"] == "flow"]
        self.assertEqual(len(blocks), 4)
        for block in blocks:
            with self.subTest(nodes=[n["id"] for n in block["nodes"]]):
                original = copy.deepcopy(block)
                geometry = build.flow_layout(block)
                self.assertEqual(geometry, build.flow_layout(block), "layout must be deterministic")
                for frame in geometry["frames"]:
                    for member in frame["nodes"]:
                        n = geometry["nodes"][member]
                        self.assertGreaterEqual(n["x"], frame["x"])
                        self.assertGreaterEqual(n["y"], frame["title_box"][3])
                        self.assertLessEqual(n["x"] + n["w"], frame["x"] + frame["w"])
                        self.assertLessEqual(n["y"] + n["h"], frame["y"] + frame["h"])
                    left, top, right, bottom = frame["title_box"]
                    for route in geometry["routes"]:
                        for a, z in zip(route, route[1:]):
                            self.assertTrue(a[0] == z[0] or a[1] == z[1], "orthogonal edge")
                            crossed = (left < a[0] < right and max(min(a[1], z[1]), top) < min(max(a[1], z[1]), bottom)) if a[0] == z[0] else (
                                top < a[1] < bottom and max(min(a[0], z[0]), left) < min(max(a[0], z[0]), right))
                            self.assertFalse(crossed, (frame["id"], a, z))
                    border = [(frame["x"], frame["y"]), (frame["x"]+frame["w"], frame["y"]),
                              (frame["x"]+frame["w"], frame["y"]+frame["h"]), (frame["x"], frame["y"]+frame["h"])]
                    for route in geometry["routes"]:
                        for a, z in zip(route, route[1:]):
                            for c, d in zip(border, border[1:]+border[:1]):
                                self.assertEqual(self.collinear_overlap(a, z, c, d), 0, "edge runs along frame border")
                for i, frame in enumerate(geometry["frames"]):
                    for other in geometry["frames"][i+1:]:
                        gap_x = max(other["x"]-frame["x"]-frame["w"], frame["x"]-other["x"]-other["w"])
                        gap_y = max(other["y"]-frame["y"]-frame["h"], frame["y"]-other["y"]-other["h"])
                        self.assertGreaterEqual(max(gap_x, gap_y), 10, "frames need a visible gap")
                for i, route in enumerate(geometry["routes"]):
                    for other in geometry["routes"][i+1:]:
                        for a, z in zip(route, route[1:]):
                            for c, d in zip(other, other[1:]):
                                self.assertLessEqual(self.collinear_overlap(a, z, c, d), 3, "edges share a trunk")
                for node in geometry["nodes"].values():
                    if node["kind"] == "store":
                        baseline = node["y"]+(node["h"]-len(node["lines"])*18)/2+18
                        self.assertGreaterEqual(baseline-16, node["y"]+18, "label touches cylinder lid")
                self.assertEqual(len(geometry["labels"]), len(block["edges"]))
                for frame in geometry["frames"]:
                    self.assertLessEqual(frame["y"]+frame["h"], geometry["height"], "frame clipped by viewBox")
                for item in geometry["labels"]:
                    left, top, right, bottom = item["box"]
                    for frame in geometry["frames"]:
                        l, t, r, bot = frame["x"], frame["y"], frame["x"]+frame["w"], frame["y"]+frame["h"]
                        forbidden = [(l-4, t-4, r+4, frame["title_box"][3]+4),
                                     (l-4, t-4, l+4, bot+4), (r-4, t-4, r+4, bot+4), (l-4, bot-4, r+4, bot+4)]
                        for x1, y1, x2, y2 in forbidden:
                            self.assertFalse(max(left, x1) < min(right, x2) and max(top, y1) < min(bottom, y2),
                                             "edge label sits on a frame title row or border")
                    for other in geometry["labels"]:
                        if abs(item["edge"]-other["edge"]) == 1 and max(left, other["box"][0]) < min(right, other["box"][2]):
                            self.assertGreaterEqual(max(top-other["box"][3], other["box"][1]-bottom), 10,
                                                    "consecutive call labels crowd vertically")
                    for route in geometry["routes"]:
                        for a, z in zip(route, route[1:]):
                            crossed = (left < a[0] < right and max(min(a[1], z[1]), top) < min(max(a[1], z[1]), bottom)) if a[0] == z[0] else (
                                top < a[1] < bottom and max(min(a[0], z[0]), left) < min(max(a[0], z[0]), right))
                            self.assertFalse(crossed, "edge crosses a short label")
                pg = build.Page([{"id": "s1"}])
                html = build.render_block(pg, block)
                self.assertTrue(pg.flow)
                self.assertIn('<svg', html)
                self.assertIn('<noscript>', html)
                self.assertIn('aria-live="polite"', html)
                self.assertEqual(html.count('<li data-edge='), len(block["steps"]))
                self.assertEqual(html.count('class="flow-edge-label"'), len(block["edges"]))
                for action in ("previous", "next", "play", "reset"):
                    self.assertIn(f'data-action="{action}"', html)
                for frame in block.get("frames", []):
                    self.assertIn(f'data-frame="{frame["id"]}"', html)
                self.assertEqual(block, original)

    def test_news_feed_entry_chains_are_straight(self):
        news = json.loads((ROOT / "content/lessons/sd-ex-news-feed.json").read_text())
        halves = section(news, "building-it-on-aws")["blocks"][:2]
        for block in halves:
            geometry = build.flow_layout(block)
            for route in geometry["routes"][:3]:
                self.assertEqual(len(route), 2, "entry chain must not wrap around a frame")
                self.assertEqual(route[0][0], route[1][0])
        self.assertLessEqual(build.flow_layout(halves[0])["height"], 750)
        neutral = next(b for b in section(news, "high-level-design")["blocks"] if b["type"] == "flow")
        geometry = build.flow_layout(neutral)
        for edge, route in zip(neutral["edges"], geometry["routes"]):
            if edge["from"] == "FS" and edge["to"] in ("TL", "PDB"):
                distance = sum(abs(a[0]-z[0])+abs(a[1]-z[1]) for a, z in zip(route, route[1:]))
                direct = abs(route[0][0]-route[-1][0])+abs(route[0][1]-route[-1][1])
                self.assertLessEqual(distance, direct+40, "cross-frame read takes a long loop")
                self.assertLessEqual(max(p[0] for p in route), geometry["nodes"][edge["to"]]["x"],
                                     "cross-frame read goes around the far side of its store")

    def test_exercise_accepts_flow_architecture(self):
        doc = json.loads((FIXTURES / f"{EXERCISE}.json").read_text())
        section(doc, "high-level-design")["blocks"] = [self.block]
        self.assertEqual(scan.exercise2_checks(doc), [])
        aws = {"id": scan.AWS_SECTION, "title": "AWS", "blocks": [self.block, copy.deepcopy(self.block),
               {"type": "decision", "rows": [{"option": "A", "pick_when": "B", "avoid_when": "C"}]}]}
        doc["exercise"]["reference_answer"].insert(2, aws)
        self.assertEqual(scan.exercise2_checks(doc), [])
        aws["blocks"].insert(2, copy.deepcopy(self.block))
        self.assertTrue(any("later diagram" in p for p in scan.exercise2_checks(doc)))


if __name__ == "__main__":
    if "--keep" in sys.argv:
        at = sys.argv.index("--keep")
        KEEP = Path(sys.argv[at + 1]).resolve()
        del sys.argv[at:at + 2]
    unittest.main()
