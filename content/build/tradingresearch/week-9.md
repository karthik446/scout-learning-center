# Week 9: freeze the rules, publish the aggregates, release the repo

> *"Educational software. Not investment advice. No orders are placed; trades are hypothetical and settled from historical bars by written rules. Past results, including these, do not predict future results."*

**You start at** `week-9-start`: the same commit as `week-8-end` (`cc2ead9`). Nothing new is shipped for this week, and there is no `tests/test_week9.py` that fails by design: the week's contract is the tests the reference adds beside its code (§1).
**You end at** `week-9-end`: `tr report --export PATH`, which writes the graded scorecards as one JSON file of aggregates; `ci/release_check.py`, the release checklist as code, with a `--fresh-clone` mode that clones, installs and tests the repo the way a reader will; `LICENSE` (MIT); a README with a reference architecture, a reader setup, the licences and a disclaimer; and the runbook's "Release" section. The reference answers are at the tag `week-9-end` (`9c0f16a`). The adoption decision for the one rule change (§3), the frozen tag and the write-up (§6) are yours: the reference does not take the decision or cut a `v1.0` tag, and this chapter says so where it matters.
**Cash:** $0. No command in this chapter makes a model call, and the tests use a temp git repo, fake data and a stubbed runner. The live stream keeps running with the week-8 settings until day 60 (2027-01-15), at the per-session cost in the [README](README.md#cash-per-week). **Time:** about 5.5 hours, the sum of the section guides below.

Week 8 ended with a pass that was not a proof, and nothing in `tr daily` changed. Week 9 asks nothing new of the model. It asks you to stop: freeze the rules the stream has been running under, publish what the stream produced as numbers a stranger can check without seeing a ticker or a thesis, decide the one pre-registered rule change by the rule you wrote in week 4, and make the repo something a reader can clone, install and test with no key. Each step is a free command or a document, and each is checked by code where code can check it.

This chapter was checked on 2026-11-17 (America/Phoenix) at `week-9-end` (`9c0f16a`), in a scratch worktree with an empty data directory and a settings file that holds no key. Every output quoted below came from that worktree, and §1 says which numbers came from it. The reference's three commits are dated 2026-11-17, 23:41 to 23:49 -0700: the author released the code on day 1 of the live stream, so the scorecards it exported were empty, and that case is in the tests.

## Where everything is

- **The reference.** `git diff --stat week-9-start week-9-end`: 12 files, 776 insertions, 6 deletions, in three commits (`6e8df6b` the export, the release check and `LICENSE`; `fd7dabe` the README sections; `9c0f16a` the fresh-clone check leaves out the one retrieval-index test). `git show week-9-end:CHANGES.md` has the two week-9 entries at the top.

| What | Path | Tag | See it |
|---|---|---|---|
| `tr report --export PATH`, `--force` (§2) | `src/tradingresearch/report.py` (`EXPORT_SCHEMA`, `card_export`, `export`, `export_text`), `commands/report.py` | week-9-end (commit `6e8df6b`) | `uv run tr report --help` |
| The export tests and the help fixture (§1, §2) | `tests/test_report.py` (the three `test_export…` and `test_the_export_…` cases), `tests/fixtures/help/report.txt` | week-9-end (commit `6e8df6b`) | `uv run pytest tests/test_report.py -q` |
| The adoption rule and the decision command (§3) | `src/tradingresearch/adopt.py` (`RULE`, `DAY_60`, `decide`), `commands/learn.py` (`decide_lines`), `experiments/rule-change-1.toml` | week-4-start (rule), week-4-end (the change) | `uv run tr learn --status` |
| README: reference architecture, reader setup, licences, disclaimer (§4) | `README.md` | week-9-end (commit `fd7dabe`) | `git show week-9-end:README.md` |
| The release checklist as code (§5) | `ci/release_check.py`, `tests/test_release.py`, `ci/README.md` ("Release check") | week-9-end (commits `6e8df6b`, `9c0f16a`) | `uv run python ci/release_check.py` |
| `LICENSE`, `.gitignore` (§5) | `LICENSE` (MIT), `.gitignore` (adds `.idea/`) | week-9-end (commit `6e8df6b`) | `git diff week-9-start week-9-end -- .gitignore` |
| Runbook: "Release" (new), "Playbook and rule changes" (§3, §5) | `docs/runbook.md` | week-9-end (modified) | `git diff week-9-start week-9-end -- docs/runbook.md` |

---

## 1. Setup, and what the week's contract is (0.5 h, $0)

**Goal:** the week-9-start repo runs on your machine, you have the reference's tests as your contract, and you know which of them fail before you write a line.

Do [SETUP.md](SETUP.md) first if you have not. `tr` reads the repo's `.env` by itself at this tag, and `TR_PROVIDER` chooses the provider; nothing this week calls one:

```bash
cd tradingresearch && git checkout week-9-start
uv sync
uv run pytest -q                 # 1297 passed, 1 failed, 5 skipped, 2 deselected
uv run python ci/gate.py         # gate: ok (90 reconcile cases at rules-1, 5 prompts)
```

The author ran these in a scratch worktree at `week-9-start` with `TR_DATA_DIR` pointing at an empty directory, and got those lines. The one failure is week 6's `test_every_gold_quote_resolves_in_the_local_index`: a fresh copy has no retrieval index, and the test says so (week 6, §1). It matters again in §5, because a fresh clone has no index either.

There is no fail-by-design contract file this week. The reference wrote its tests with its code, in two files that already exist or are new at `week-9-end`. Take them as your contract:

```bash
git show week-9-end:tests/test_report.py > tests/test_report.py
git show week-9-end:tests/test_release.py > tests/test_release.py
uv run pytest tests/test_report.py -q    # 3 failed, 12 passed
uv run pytest tests/test_release.py -q   # ModuleNotFoundError: No module named 'release_check'
```

At `week-9-start` the three new report tests fail (`module 'tradingresearch.report' has no attribute 'export'`, then `SystemExit: 2` twice, because `tr report` rejects `--export`), and `tests/test_release.py` does not collect, because it imports `ci/release_check.py` and that file does not exist yet. At `week-9-end` the two files give `34 passed`. Each test names what it wants:

| Test | What you write |
|---|---|
| `test_the_export_holds_the_printed_card_numbers_and_skips_ungraded_cards` | `report.export` (§2): the same numbers the printed card shows, one entry per card with a graded trade |
| `test_export_writes_aggregates_only_refuses_an_overwrite_and_reruns_byte_identical` | `tr report --export PATH` and `--force` (§2) |
| `test_export_with_no_graded_data_writes_empty_arms_and_says_so` | the empty case: `"arms": []` and one line that says so (§2) |
| `test_a_complete_repo_passes_each_check_with_one_line_per_check` | `ci/release_check.py` (§5): seven checks, one `ok` line each, exit 0 |
| `test_each_check_fails_on_its_broken_repo_and_only_it` | each check's `FAIL` line and detail, on a temp repo missing one thing |
| `test_a_secret_shaped_line_fails_by_file_line_and_pattern_never_the_value` | the secret scan names file, line and pattern, never the string |
| `test_named_prefixes_and_placeholders_are_not_secret_shaped` | `sk-ant-` in a doc and `APCA_API_KEY_ID=not-a-real-id` in a test are not secrets |
| `test_fresh_clone_runs_clone_sync_gate_and_tests_in_a_removed_temp_dir` | `--fresh-clone` (§5), with the runner stubbed |
| `test_a_failing_fresh_clone_step_stops_the_rest_and_fails` | the first failing step ends the clone check |

**Done when**
- `uv run pytest -q` at `week-9-start` gives the counts above, and you can say why the one failure is expected.
- The two test files are in your tree, and you can name the three export tests and the six release tests.

**Traps (real)**
- *Copying the help fixture too.* `tests/fixtures/help/report.txt` is the `tr report --help` text at `week-9-end`, with `--export` and `--force` in it. If you copy it before you add the flags, the help test fails for a reason that is not yours. Add the flags first (§2), then diff your help against it.
- *Running the suite in the repo's data directory.* The tests set `TR_DATA_DIR` themselves, but the commands you try by hand read the `.env` and the default `data/` unless you point them elsewhere. Every by-hand command in this chapter was run with `TR_DATA_DIR` set to an empty scratch directory, which is why every scorecard below has zero trades.

**Cash:** $0. **Reference:** `git diff --stat week-9-start week-9-end`; `git show week-9-end:CHANGES.md`.

---

## 2. The scorecard export: aggregates a stranger can read (1 h, $0)

**Goal:** `tr report --export PATH` writes the graded scorecards as one JSON file that holds counts, rates and intervals, and nothing that identifies a ticker, a thesis or a line of model text.

The printed report (week 3) is one scorecard per arm and horizon, never pooled: counts by state, fill rate, abstention, win rate with its Wilson interval, mean r_net with its session-cluster bootstrap, real minus shadow, median MFE and MAE, the detectable-effect line and the P1 result with its 2x2. The export is those numbers as JSON, and nothing else. `report.card_export` builds one entry per card: `arm`, `horizon`, `n` (graded trades), `theses`, `states` (closed, expired, cancelled, open, proposed), `fill_rate` and `abstention` as `{"k", "n", "p"}`, then `win_rate` (with `ci95`), `mean_r_net` and `real_minus_shadow` (value, cluster count and `ci95`, null under 10 entry sessions, the same `insufficient` the card prints), `median_mfe_r`, `median_mae_r`, `mde` (null under two trades) and `p1` (null with no judged trade). `report.export` wraps the entries that have a graded trade:

```json
{"schema": 1, "stream_from": "2026-11-17", "arms": []}
```

`stream_from` is the first live session; `--include-pre-live` sets it to null and counts the dev runs too, as the printed report does. `export_text` writes it with sorted keys, a 2-space indent and a trailing newline, so a rerun on the same data is byte-identical: a reader who checks out your tag and reruns the export can diff the file you published.

The command side is `commands/report.py`: two flags, and one refusal.

```text
$ uv run tr report --help
usage: tr report [-h] [--horizon {day,short,swing}]
                 [--arm {champion,challenger}] [--include-pre-live]
                 [--export PATH] [--force]
...
  --export PATH         also write the graded scorecards' aggregates as JSON
                        (no ticker, id or text)
  --force               with --export: overwrite an existing PATH
```

An existing PATH is refused before anything is read: `refused: <PATH> exists; --force overwrites it` on stderr, **exit 2**. The printed report is unchanged; the export is added after it, with one line that says what was written. On the author's empty scratch journal:

```text
$ uv run tr report --export scorecards.json
report: live stream from 2026-11-17; champion and challenger theses only (teacher theses never enter a scorecard); one scorecard per horizon, never pooled
pre-live, excluded (before 2026-11-17): 0 theses; 0 tr daily runs (--include-pre-live shows them)
champion day: 0 theses: 0 closed (0 graded), 0 expired, 0 cancelled, 0 open, 0 proposed
  fill rate n/a (0 of 0) (filled / (filled + expired)); abstention n/a (0 of 0) (no-trades / main-analysis decisions for day, both arms)
  no closed trades yet
...
exported to scorecards.json: no graded trades yet, "arms": []
$ uv run tr report --export scorecards.json
refused: scorecards.json exists; --force overwrites it
```

With graded trades the last line reads `exported N graded scorecards (aggregates only) to PATH`. The test `test_the_export_holds_the_printed_card_numbers_and_skips_ungraded_cards` builds eleven trades by hand and checks that the export's numbers are the card's numbers, and that a card with no graded trade is left out rather than exported as zeros.

**Why aggregates only.** The journal holds tickers, entry prices and model text, and the theses are hypothetical trades on named stocks. The schedule's rule for the public form is counts and intervals, never a row a reader could turn into "the model said buy X on date D". `card_export`'s docstring states it as the invariant: "never a thesis id, ticker or text". The export test checks the written file for the seeded ticker's name and finds none. Keep that test when you change the schema.

**Done when**
- `uv run pytest tests/test_report.py -q` gives 15 passed, and your `tr report --help` matches `tests/fixtures/help/report.txt`.
- `uv run tr report --export scorecards.json` twice: the second run is refused with exit 2, and `--force` lets it through.
- A rerun with `--force` on the same journal writes a byte-identical file (`cmp`).
- `grep` for any ticker in your universe over the file finds nothing.

**Traps (real)**
- *Pooling horizons to get a bigger n.* The export has one entry per (arm, horizon) because the report does. A pooled number would mix a 1-session hold with a 5-session hold, and the week-3 rule against it stands.
- *Exporting zeros for an empty card.* An entry with `n: 0` and `win_rate.p: null` reads like a result. The reference leaves the card out and says so in the terminal line instead.
- *Reading the file as a result.* `ci95` is null under 10 entry sessions. A mean with a null interval is a number without a claim, and the write-up (§6) must say so in words.

**Cash:** $0. **Reference:** `docs/runbook.md`, "Release" ("Export"); `git show week-9-end:src/tradingresearch/report.py` from the `-- export:` comment on.

---

## 3. The adoption decision: apply the week-4 rule, once (1 h, $0)

**Goal:** you can state the rule for `rc_1` from memory, run `tr learn --status` and read every line of it, and you know what `tr learn --decide rc_1` writes, when, and that it writes once.

Week 4 registered one rule change, `rc_1`, before its first covered session: drop short-horizon theses that trade against the 50-session trend. Its pre-registration is in `experiments/rule-change-1.toml` (primary metric `session_r_net_delta:short`, pass rule `delta_ci_lower > 0`, guard metric `p1_met_rate`, margin 0.10, `n_planned` 20, `registered_at` 2026-11-17T07:08:00Z), and the store refused anything else. The challenger arm has run beside the champion since. Week 9 is where the rule is applied, and the rule is in code, not in your head:

```text
$ uv run tr learn --status
rule changes (SPIKE §8.2-8.3): 1 registered
rule: adopt iff, over the first 20 paired sessions, the 95% CI lower bound of mean(challenger - champion) session r_net is > 0 and that of the P1 met-rate difference is >= -0.10; otherwise rejected; insufficient if 20 pairs are not reached by day 60 (2027-01-15)
rc_1 [pending] short: drop short-horizon theses against the 50-session trend (long below sma_50, short above) (diff short-sma50-trend; registered 2026-11-17 07:08 UTC, active from 2026-11-17)
  paired sessions so far: 0 of 20
  delta session r_net (challenger - champion) insufficient (0 sessions < 10)
  P1 met-rate guard (challenger - champion) insufficient (0 sessions < 10)
  the rule today: pending (0 of 20 paired sessions so far)
  detectable delta at n = 20: 2.80159/sqrt(n) * sigma = 0.63 R at sigma 1.00, 0.89 R at sigma 1.41 (sigma assumed, SPIKE §8.3)
```

That is the week-4 read-back on the live journal, on the morning of 2026-11-17, which is also the day `week-9-end` was tagged. The pair count in your journal on day 57 will be whatever the stream delivered. A pair is one session on the short horizon, summed r_net per arm, 0 with no trade, counted only once both arms' theses on it are graded, expired or cancelled; the first 20 decide (`adopt.decide`, which takes the first `n_planned` sessions by date and ignores the rest).

`tr learn --decide rc_1` runs `adopt.decide_pairs` on the journal's pairs and does one of four things (`commands/learn.py`, `decide_lines`):

| Outcome | When | Written? |
|---|---|---|
| `pending` | fewer than 20 pairs and day 60 (2027-01-15) not yet closed | no: `rc_1: pending, N of 20 paired sessions so far; nothing written` |
| `insufficient` | fewer than 20 pairs and day 60 has closed | yes, final |
| `rejected` | 20 pairs, and the r_net delta's lower bound is not > 0, or the P1 guard's lower bound is below -0.10, or the guard is not computable (under 10 sessions with a P1 rate on both arms) | yes, final |
| `adopted` | 20 pairs, delta lower bound > 0 and guard lower bound >= -0.10 | yes, final |

The reason is printed with the status, and a second `--decide` on a decided change exits with `rc_1 is already <status>: a decision is final`; SQLite triggers back that up. "Day 60 has closed" is `adopt.day60_reached`, true once the last completed session is on or after 2027-01-15, so on day 57 to 59 a short count prints `pending` and writes nothing. Run `--decide` on day 60, from the pinned live worktree, and once.

**What the result means for the code.** `adopted` is a statement about the journal, not a change to `tr daily`: the champion's rules are in `rules.py`, and moving a challenger rule into the champion is a code change you make after the decision, in the next pre-registered cycle, with its own ADR. `rejected` and `insufficient` leave the code as it is. Either way, the frozen tag (§6) carries the decision row in the journal's history and the ADR you write for it. The reference repo holds no such ADR: at `week-9-end`, `docs/adr/` ends at ADR-011 and ADR-014, and the decision is left to the reader because the author's own pair count was zero on the day the code was released.

**Done when**
- You can recite the rule without the terminal, including the guard and the day-60 clause.
- `uv run tr learn --status` on your journal shows the pair count, the two intervals and `the rule today`, and you can say which of the four outcomes the count implies today.
- You know the date you will run `--decide rc_1`, and that it is after the last session of day 60 has been graded.

**Traps (real)**
- *Deciding early.* `--decide` before day 60 with fewer than 20 pairs prints `pending` and writes nothing, which is the safe failure; the unsafe one is counting the pairs yourself from the report and writing an ADR that says `adopted` before the command has.
- *Reading `insufficient` as `rejected`.* It means the stream did not deliver 20 graded short-horizon pairs in 60 days. The write-up states the count and the interval it has, and makes no claim about the rule change either way.
- *A guard that cannot be computed.* The P1 guard pairs only sessions with a P1 rate on both arms. With `tr grade --judge` run on few trades, the guard has few sessions, and under 10 the change cannot be adopted whatever the r_net delta says. If you want the judge's verdicts in the decision, they had to be run through the stream, not on day 59.

**Cash:** $0. **Reference:** `docs/runbook.md`, "Playbook and rule changes (`tr learn`)"; `git show week-4-end:experiments/rule-change-1.toml`; `src/tradingresearch/adopt.py`.

---

## 4. The README as a reference architecture, and the licences (1 h, $0)

**Goal:** a reader who opens the repo at your tag sees what the system is, how to set it up, what it costs, where it runs, that it places no orders, and under which licence each part is published, without opening another file.

At `week-9-start` the README has a short description and a Prerequisites section (68 lines). The reference's second commit (`fd7dabe`) adds four sections, in this order, and §5's checks read them by heading:

- **`## Reference architecture`.** One text diagram of a session's evening as `tr daily` runs it: data in (Alpaca bars and news, EDGAR, the NYSE calendar) into the journal and the indicators, then `tr screen`, `tr analyze`, `tr thesis` / `tr open`, `tr reconcile`, `tr grade`, `tr report` and `tr learn`, each box with its module under `src/tradingresearch/`; below it the cross-cutting parts (traces and run files, evals and graders, experiments as config, guards, retrieval, routing and caching, the cost trail), each with its module and its ADR. Then one bullet per box in prose. This is the whole system in one page, and it names ADR-001, -003, -004, -009, -010, -011 and -014 where each decision lives.
- **`## Reader setup`.** `### Accounts and keys` (Alpaca market data, a paper account is enough; SEC EDGAR, keyless, `TR_SEC_USER_AGENT`; a model provider, `ANTHROPIC_API_KEY` with `TR_PROVIDER=anthropic` or `OPENROUTER_API_KEY` with `TR_PROVIDER=openrouter`; and `OPENROUTER_API_KEY` whatever the provider for the teachers and the P1 judge, because the judge is `openai/gpt-6-sol` and the Anthropic adapter refuses it). `### The settings file` (one `.env` at the repo root, read by `tr` itself, never sourced; a table of the variables and what each is needed for). `### What it costs` (a free read is $0: `tr screen`, `tr reconcile`, `tr grade` without `--judge`, `tr report`, `tr usage` and every `--dry-run`; the paid steps as measured in `docs/measured-costs.md` on `anthropic/claude-sonnet-5.5`: analyze $0.017052 and thesis $0.020814 per ticker, means of 5; the week-8 routing run $5.6118 in all). `### US-only` (US-listed equities, the NYSE calendar, SEC filers; whether Alpaca opens a data account where you live is Alpaca's decision). `### No orders`.
- **`## Licences`.** Code: MIT (`LICENSE`). The build guide's text, published apart from the repo: CC BY-NC 4.0. A dataset release from `tr dataset publish`: CDLA-Permissive-2.0, in the release's own `LICENSE`, and Alpaca prices and headlines are never in the public form.
- **`## Disclaimer`.** "Educational software, not financial advice." No orders; every trade is hypothetical and settled from historical bars; the numbers in the README and the ADRs are measurements of this pipeline on a few tickers and a few sessions, not performance claims.

Read the reference's version (`git show week-9-end:README.md`) once, then write yours from your own repo. Two things the checks in §5 pin: the headings `Reference architecture` and `Reader setup` must exist, with `ANTHROPIC_API_KEY`, `APCA_API_KEY_ID` and `US-only` inside the reader-setup section (a later section does not count: `test_each_check_fails_on_its_broken_repo_and_only_it` moves `APCA_API_KEY_ID` into a following section and expects a FAIL); the strings `MIT`, `CC BY-NC 4.0` and `CDLA-Permissive-2.0` must appear somewhere in the README, and one paragraph must contain `not financial advice`.

**The schedule asked for more than the reference did.** [SCHEDULE.md](SCHEDULE.md) says the README holds the results table and ADR-001 to ADR-009, and that the not-investment-advice note goes in every `report`. At `week-9-end` the README links the ADRs from the architecture bullets and has no results table, and `tr report`'s printed output is unchanged (CHANGES.md says so). The results table is §6's write-up, in whichever file you publish it; whether `tr report` prints the note is your call, and a change there must keep `tests/fixtures/help/report.txt` and the report tests green. The schedule also names an API versus self-host break-even note; the repo at `week-9-end` has none, and nothing in this chapter measures it, so if you write one it rests on the week's readings and your own `tr usage` figures, and says so.

**Done when**
- The four sections exist with those headings, and `uv run python ci/release_check.py` (§5) prints `ok` for `readme_licences`, `disclaimer` and `readme_setup`.
- Every module and ADR your architecture names exists at your tag (`ls src/tradingresearch docs/adr`).
- The cost figures in "What it costs" are the ones in your `docs/measured-costs.md`, with the model and the provider beside each.

**Traps (real)**
- *A diagram that names a command that does not exist.* Week 8, §8, had a pre-registration naming a `tr usage` view nobody could run. The same rule applies here: every `tr` command in the diagram is in `uv run tr --help`.
- *Quoting another repo's costs.* "What it costs" is read as a promise. The reference quotes its own measured runs with their provider; your numbers come from your `docs/measured-costs.md` and your run files, or the section says "not measured".
- *A licence line with no file behind it.* `## Licences` says MIT; §5's `license` check reads `LICENSE` and wants it to start with `MIT License`.

**Cash:** $0. **Reference:** `git show week-9-end:README.md`; `git show week-9-end:CHANGES.md` (the "README release sections" entry).

---

## 5. The release checklist as code (1.5 h, $0)

**Goal:** one command says whether the repo is fit to publish, one line per check, exit 1 on any failure; and a second mode proves that a stranger's clone installs, passes the gate and passes the tests with no key.

`ci/release_check.py` runs seven checks against the repo root and prints `ok <check>: <detail>` or `FAIL <check>: <detail>` for each; `main` returns 1 if any failed. None of them reads a key, opens the network or calls a model. The seven, in order, with the `ok` line each printed at `week-9-end`:

```text
$ uv run python ci/release_check.py
ok license: LICENSE is the MIT licence
ok readme_licences: README.md names MIT (code), CC BY-NC 4.0 (guide text), CDLA-Permissive-2.0 (dataset)
ok disclaimer: README.md carries a `not financial advice` paragraph
ok gitignore: .gitignore covers data/x.db, data-dev/x, .env, .idea/x, data/traces/x
ok tracked_data: no tracked .env, data/ or data-dev/ file
ok secrets: no secret-shaped string in 320 tracked text files
ok readme_setup: README.md has Reference architecture and Reader setup (ANTHROPIC_API_KEY, APCA_API_KEY_ID, US-only)
```

- **`license`**: `LICENSE` exists and starts with `MIT License`. The reference added the file in `6e8df6b`; the copyright line is yours.
- **`readme_licences`**: three regexes over the README, `\bMIT\b`, `CC BY-NC 4\.0`, `CDLA-Permissive-2\.0`; the FAIL line names the missing ones.
- **`disclaimer`**: a README paragraph (paragraphs split on blank lines) containing `not financial advice`, case-insensitive.
- **`gitignore`**: `git check-ignore` on five paths that the program or the editor writes: `data/x.db`, `data-dev/x`, `.env`, `.idea/x`, `data/traces/x`. The reference's `.gitignore` gained `.idea/` for this; `data/` and `.env` have been in it since `week-1-start`, and `data-dev/` since week 2.
- **`tracked_data`**: `git ls-files` holds no `.env` and nothing under `data/` or `data-dev/`. Ignoring a path does not untrack it; this is the check that catches a journal committed before the ignore line.
- **`secrets`**: four secret-shaped patterns over every tracked text file (`sk-ant-` and `sk-or-v1-` followed by a key-length body, `APCA…=` followed by 8 or more key characters, `AKIA` plus 16). A hit is named by file, line and pattern name, never by the string, so the FAIL line itself leaks nothing. The prefixes alone are not hits: the docs name them, `redact.py` matches them, and the tests use `APCA_API_KEY_ID=not-a-real-id` as a placeholder; `test_named_prefixes_and_placeholders_are_not_secret_shaped` pins that.
- **`readme_setup`**: the two headings and the three names inside the second, as §4 said. Headings are read outside code fences only: the test's README puts `reader setup` in a fenced comment to prove that a fence is body, not a heading.

`tests/test_release.py` builds a temp git repo with a passing README, `LICENSE` and `.gitignore`, then breaks one thing at a time and expects exactly one `FAIL` line with its exact detail (the parametrised `test_each_check_fails_on_its_broken_repo_and_only_it`). That is the shape to copy for a checklist of your own: a passing fixture, then one broken fixture per rule.

**`--fresh-clone`.** The offline checks say the repo looks publishable; this mode checks that it works for someone who is not you. `check_fresh_clone` clones HEAD (committed work only; your working tree does not travel) into a temp dir, checks out that commit detached, runs `uv sync --frozen` (the one step that needs network), then `uv run --frozen python ci/gate.py` and `uv run --frozen pytest -q -x` there, with `TR_DATA_DIR` inside the temp dir and `TR_PROVIDER`, `TR_ENV_FILE` and `VIRTUAL_ENV` removed from the environment, so the clone runs as a reader would: no provider chosen, no key, no inherited virtualenv. The first failing step ends the check with the command's last output line, and the temp dir is removed either way. It deselects one test, `tests/test_week6.py::test_every_gold_quote_resolves_in_the_local_index`, because that test wants the retrieval index a reader builds with `tr retrieval build` (network), and a clone does not have it; that deselect is the reference's third commit (`9c0f16a`), a few minutes after the second. On the author's machine at `week-9-end`:

```text
$ uv run python ci/release_check.py --fresh-clone
ok license: LICENSE is the MIT licence
...
ok readme_setup: README.md has Reference architecture and Reader setup (ANTHROPIC_API_KEY, APCA_API_KEY_ID, US-only)
fresh-clone: needs network for `uv sync --frozen`; no key and no model call
ok fresh_clone: HEAD 9c0f16a806cc in a clean clone: uv sync --frozen, ci/gate.py and pytest -q -x pass (the retrieval-index test is deselected)
```

That run took about 26 seconds with a warm `uv` cache, and exit 0. The runbook's "Release" block is the whole release in three lines: the export, the offline checks, the fresh clone.

**Done when**
- `uv run pytest tests/test_release.py -q` passes (the parametrised cases included), and `uv run python ci/release_check.py` prints seven `ok` lines and exits 0 on your repo.
- You have broken one thing on purpose (rename `## Reader setup`, or drop `.idea/` from `.gitignore`), seen the one FAIL line and exit 1, and put it back.
- `uv run python ci/release_check.py --fresh-clone` ends in `ok fresh_clone: HEAD <your sha> …` on the commit you mean to tag.

**Traps (real)**
- *The fresh clone passes on your tree and fails on HEAD.* The clone takes committed work only. An uncommitted fix to a test makes your `pytest` green and the clone's red; commit, then run the clone check again.
- *A tracked file that the ignore line now hides.* `git status` is quiet, `gitignore` says `ok`, and `tracked_data` says `FAIL tracked_data: tracked private files: data-dev/x`. `git rm --cached` it, and then decide whether the history needs rewriting before the repo is public; this check does not look at history.
- *A secret in the history, not the tree.* `secrets` scans tracked files at HEAD. A key committed in week 2 and removed in week 3 is still in `git log -p`. If that happened, rotate the key; a rewritten history is a second step, not a substitute.
- *The index test.* Without the deselect, `pytest -q -x` in the clone stops at `test_every_gold_quote_resolves_in_the_local_index` and the check fails on a test that passes on your machine. If you add a second test that needs a built artefact, add it to the deselect list and say why in the module docstring, as the reference does.

**Cash:** $0. **Reference:** `docs/runbook.md`, "Release"; `ci/README.md`, "Release check"; `git show week-9-end:ci/release_check.py`.

---

## 6. Freeze, tag, write up (0.5 h, $0)

**Goal:** the rules the stream ran under are frozen at one tag; the scorecards are public as aggregates; the write-up states what was measured, with its intervals, and what was decided.

**Freeze.** The rules are `rules.py`, the reconcile rules behind `ci/gate.py`'s goldens, the prompts hashed in `ci/prompt-hashes.json`, and the live worktree's pin. Nothing in them changes this week; the freeze is a tag on the commit the fresh-clone check passed on, after the export and the README are in. Name it as you like (`v1.0` is the schedule's name); the reference repo stops at `week-9-end` and leaves that tag to you. `git tag -a` it with a message that names the date, the last live session the export covers and the `scorecards.json` sha, and push the tag with the repo. From then on, the live worktree's pin may move only to a commit that changes nothing a rule depends on, and the day-60 `--decide` (§3) is a journal write, not a code change.

**Publish.** `uv run tr report --export scorecards.json` from the pinned worktree, on the live journal, after the last session you mean to cover is graded; commit the file beside the README or in `docs/`, and name the session range in the commit. A reader checks out the tag and reruns the export against nothing (they have no journal), so the file's provenance is the tag, the commit and the `stream_from` key, and your write-up's table is the file's numbers, copied, not recomputed.

**Write up.** One page, in the README or a `docs/` file linked from it, with:
- the per-horizon table from the export: n, win rate and its interval, mean r_net and its interval, real minus shadow, the detectable-effect line; open trades as "open, not graded" from `states`;
- the result in a sentence that the intervals support. If every interval straddles zero, the sentence is "no edge detected at n = N; the 95% interval on mean r_net is [a, b]", and the detectable-effect line says what size of edge the stream could have seen;
- the `rc_1` decision as `tr learn --decide` printed it, with the pair count and the two lower bounds, or `pending` with the day it will be run if you are writing before day 60;
- the experiments' decisions, one line each, as the ADRs recorded them: ADR-005 (tools), ADR-007 (context sections), ADR-009 (retrieval), ADR-010 (guards), ADR-011 (routing), with the cost of each run from `docs/measured-costs.md` and the provider it ran on;
- what the design leaves open, from the ADRs' Consequences, so a reader does not take silence for a pass.

The reference repo does not contain this write-up, and this chapter does not invent one: the author's journal held no graded live trade on the day the release code was tagged, and every number above is the reader's to measure.

**Done when**
- One annotated tag on the commit `--fresh-clone` passed on, and the live worktree's pin is that commit or an earlier verified one.
- `scorecards.json` is committed at that tag, and `cmp` against a fresh `--export --force` on the same journal says they are identical.
- The write-up's every number is in the export or an ADR, and every sentence about the edge names an interval.

**Traps (real)**
- *Tagging, then fixing.* A fix after the tag is a new tag or an honest note, never a moved tag: the pre-registrations (weeks 4 to 8) are only evidence while the tags they point at stand still.
- *A write-up that improves on the export.* Dropping an arm, pooling horizons, or quoting the mean without its null interval are all ways of saying more than the data does. The file is public; make the page say the same thing.
- *"No edge detected" read as "no edge".* The detectable-effect line is the size of an edge the stream could have seen at this n. Below that, the stream saw nothing, and that is the claim: nothing, at this size, in these 60 days.

**Cash:** $0. **Reference:** [SCHEDULE.md](SCHEDULE.md), week 9 ("Works by end of week"); `docs/runbook.md`, "Release"; the ADRs named above at your tag.

---

## Week 9 cash

| Step | Spent | Source |
|---|---|---|
| The export, the release check, `LICENSE`, the README sections, the runbook | $0 | no model call; the tests use a temp git repo, hand-built trades and a stubbed runner |
| The author's checks for this chapter: `pytest`, `ci/gate.py`, `tr report --export`, `tr learn --status`, `release_check.py` with and without `--fresh-clone` | $0 | no key in the settings file; an empty `TR_DATA_DIR` |
| The live stream to day 60 | per session, as in the [README](README.md#cash-per-week) | the week-8 settings, OpenRouter for the live pin and the teachers |
| Week 9 | $0 | — |

Running total for weeks 3 to 9 of one-off build spend: about $13.59 (weeks 3 to 7 about $7.98, as week 7 reports it; week 8 $5.6118 on Anthropic; week 9 $0). The live stream's per-session cost is on top of that and runs to 2027-01-15.

## Week 9 is done when

- `uv run pytest -q` passes apart from the index test that needs a local build, `ci/gate.py` says `gate: ok (90 reconcile cases at rules-1, 5 prompts)`, and `uv run pytest tests/test_report.py tests/test_release.py -q` gives 34 passed.
- `uv run tr report --export scorecards.json` writes aggregates only, refuses an overwrite with exit 2, and reruns byte-identical.
- `uv run python ci/release_check.py` prints seven `ok` lines and exits 0, and `--fresh-clone` ends in `ok fresh_clone` on the commit you tag.
- The README has `## Reference architecture`, `## Reader setup`, `## Licences` and `## Disclaimer`, and every command and module it names exists.
- `uv run tr learn --status` shows `rc_1` and its pair count, and your calendar holds the day-60 `--decide`.
- One annotated tag on that commit, `scorecards.json` committed at it, and a write-up whose every claim names an interval.

Every output in this chapter came from a command the author ran at `week-9-start` or `week-9-end` in a scratch worktree with an empty data directory and no key, except the `tr learn --status` block in §3, which is week 4's read-back on the live journal of 2026-11-17. No scorecard number, no decision and no write-up is reported here, because none existed at the tag.
