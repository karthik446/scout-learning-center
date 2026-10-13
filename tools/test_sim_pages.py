#!/usr/bin/env python3
"""The simulator's scan rules and page rendering, on a temp copy of content/ (standard library only, no network, no browser).

    python3 tools/test_sim_pages.py

The digit rule is proved with negative tests: a caption or step number that the committed golden run does not show is refused,
a number with no claim is refused, a claim on a failing assertion is refused, a stale golden file is refused. The positive case
is built into a temp site and its HTML checked (module script, data-pagefind-ignore, the scenario copied, the sheet linked).
The fixture borrows the sd-caching scenario for an existing exercise page; nothing is written to content/ or site/.
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
sys.path.insert(0, str(TOOLS))
import scan  # noqa: E402

LESSON = "sd-ex-rate-limiter"
GOOD = {
    "scenario": "sd-caching",
    "caption": "The database only sees the misses, about 29 requests a second at the defaults.",
    "steps": ["Leave the hit rate at 0.85 and read the database utilisation, about 22%.",
              "Set the hit rate to 0.3 and wait; the database saturates at 100% busy."],
    "sim_claims": [{"text": "about 29 requests a second", "assertion": "db-sees-misses"},
                   {"text": "about 22%", "assertion": "db-sees-misses"},
                   {"text": "saturates at 100% busy", "assertion": "low-hit-overloads-db"}],
}


class SimPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="sim-pages-"))
        cls.content = cls.tmp / "content"
        shutil.copytree(ROOT / "content", cls.content)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def problems(self, sim: dict | None, golden_edit=None) -> list[str]:
        docs, probs = scan.load_all(self.content)
        self.assertEqual(probs, [])
        if sim is not None:
            docs[f"lessons/{LESSON}.json"]["sim"] = copy.deepcopy(sim)
        old = scan.GOLDEN
        if golden_edit:
            g = self.tmp / "golden"
            shutil.rmtree(g, ignore_errors=True)
            shutil.copytree(old, g)
            golden_edit(g)
            scan.GOLDEN = g
        try:
            return scan.validate(docs)
        finally:
            scan.GOLDEN = old

    def test_committed_content_is_clean(self) -> None:
        self.assertEqual(self.problems(None), [])

    def test_good_sim_passes(self) -> None:
        self.assertEqual(self.problems(GOOD), [])

    def test_number_not_in_golden_is_refused(self) -> None:
        bad = copy.deepcopy(GOOD)
        bad["caption"] = "The database only sees the misses, about 61 requests a second at the defaults."
        bad["sim_claims"][0]["text"] = "about 61 requests a second"
        out = self.problems(bad)
        self.assertTrue(any("'61'" in p or "number 61" in p for p in out), out)

    def test_number_without_claim_is_refused(self) -> None:
        bad = copy.deepcopy(GOOD)
        bad["steps"] = bad["steps"] + ["Expect the p99 to reach 740 ms."]
        out = self.problems(bad)
        self.assertTrue(any("'740'" in p and "not covered" in p for p in out), out)

    def test_quantity_word_without_claim_is_refused(self) -> None:
        bad = copy.deepcopy(GOOD)
        bad["steps"] = bad["steps"] + ["Latency doubles."]
        out = self.problems(bad)
        self.assertTrue(any("doubles" in p for p in out), out)

    def test_knob_setting_needs_no_claim(self) -> None:
        ok = copy.deepcopy(GOOD)
        ok["steps"] = ok["steps"] + ["Raise the offered load to 1200."]
        self.assertEqual(self.problems(ok), [])

    def test_claim_on_unknown_assertion_is_refused(self) -> None:
        bad = copy.deepcopy(GOOD)
        bad["sim_claims"][0]["assertion"] = "no-such-assertion"
        self.assertTrue(any("not an assertion" in p for p in self.problems(bad)))

    def test_claim_on_failing_assertion_is_refused(self) -> None:
        def fail(g: Path) -> None:
            f = g / "sd-caching.json"
            d = json.loads(f.read_text())
            for r in d["rows"]:
                if r["assertion"] == "db-sees-misses":
                    r["pass"] = False
            f.write_text(json.dumps(d))
        self.assertTrue(any("FAILS in the golden run" in p for p in self.problems(GOOD, fail)))

    def test_stale_golden_is_refused(self) -> None:
        def stale(g: Path) -> None:
            f = g / "sd-caching.json"
            d = json.loads(f.read_text())
            d["scenario_sha256"] = "0" * 64
            f.write_text(json.dumps(d))
        self.assertTrue(any("stale" in p for p in self.problems(GOOD, stale)))

    def test_missing_golden_and_scenario_are_refused(self) -> None:
        gone = copy.deepcopy(GOOD)
        gone["scenario"] = "no-such-scenario"
        self.assertTrue(any("has no file" in p for p in self.problems(gone)))
        self.assertTrue(any("no golden run" in p for p in self.problems(GOOD, lambda g: (g / "sd-caching.json").unlink())))

    def test_scenario_shape_rules(self) -> None:
        docs, _ = scan.load_all(self.content)
        sc = copy.deepcopy(docs["scenarios/sd-caching.json"])
        sc["nodes"][1]["kind"] = "nonsense"
        del sc["nodes"][0]["config"]["rps"]
        sc["knobs"][1]["default"] = 0.5
        sc["assertions"][0]["metric"] = "util:nope"
        out = scan.scenario_checks("scenarios/sd-caching.json", sc)
        for needle in ("unknown kind", "config.rps", "differs from the node's config", "unknown metric"):
            self.assertTrue(any(needle in p for p in out), (needle, out))

    def test_build_renders_the_block(self) -> None:
        lesson = self.content / "lessons" / f"{LESSON}.json"
        d = json.loads(lesson.read_text())
        d["sim"] = GOOD
        lesson.write_text(json.dumps(d, indent=1))
        site = self.tmp / "site"
        r = subprocess.run([sys.executable, str(TOOLS / "build.py"), "--content", str(self.content), "--out", str(site)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        page = (site / "learn/lessons" / LESSON / "index.html").read_text(encoding="utf-8")
        self.assertIn('<div class="sim" data-scenario="/learn/scenarios/sd-caching.json" data-pagefind-ignore>', page)
        self.assertIn('<script type="module" src="/_assets/sim/sim.js"></script>', page)
        self.assertIn('<link rel="stylesheet" href="/_assets/sim/sim.css">', page)
        self.assertIn("Simulation engine: Breakscale (MIT, the Breakscale contributors), commit d2c876e0", page)
        self.assertIn('id="simulate"', page)
        self.assertTrue((site / "learn/scenarios/sd-caching.json").is_file())
        for f in ("sim.js", "sim.css", "LICENSE.txt", "UPSTREAM.txt"):
            self.assertTrue((site / "_assets/sim" / f).is_file(), f)
        other = (site / "learn/lessons/sd-ex-chat/index.html").read_text(encoding="utf-8")
        self.assertNotIn("sim.js", other)
        self.assertNotIn("sim.css", other)


if __name__ == "__main__":
    unittest.main(verbosity=1)
