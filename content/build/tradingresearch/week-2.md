# Week 2: grade the process, not the P&L, and start the live stream

> *"Educational software. Not investment advice. No orders are placed; trades are hypothetical and settled from historical bars by written rules. Past results, including these, do not predict future results."*

**Code:** start [`week-2-start`](https://github.com/karthik446/tradingresearch/tree/week-2-start) · reference answer [`week-2-end`](https://github.com/karthik446/tradingresearch/tree/week-2-end) · [the chapter diff](https://github.com/karthik446/tradingresearch/compare/week-2-start...week-2-end) (repo: [karthik446/tradingresearch](https://github.com/karthik446/tradingresearch)).

**You start at** `week-2-start`: the daily loop runs end to end. `tr screen` picks a shortlist, `tr analyze` writes checked claims, `tr thesis` turns them into 0-3 theses or a no-trade, `tr reconcile` settles them from raw bars and `tr daily` runs all four. Teacher models can write the same analyses, a free CI gate guards the reconcile rules and the prompts, and `tests/test_week2.py` fails by design.
**You end at** `week-2-end`: three code checks of a thesis's process (P2-P4) with graders and tests, a rubric and a draft judge for the one check that needs reading (P1), ADR-003 on the judge, a review of the thesis prompt on real output, a pre-registered teacher bake-off and a runbook for the live stream.
**Cash:** the code work costs $0. The paid step is one `tr daily` on a completed session, which cost $0.1893 in the author's run, plus an optional teacher call ($0.004119). **Time:** about 7.5 hours, the sum of the section guides below.

Concepts this week, each explained in one or two lines with a link where it is first used: process versus outcome grading (§2), LLM-as-judge and judge validation (§3), a CI gate for prompts (§4), pre-registration and teacher/student models (§5). Week 1 graded what the model *wrote*. Week 2 grades what it *proposed*, before the market answers, because the P&L of a handful of trades says almost nothing about whether the reasoning was sound.

## Where everything is

Every file this chapter names, the tag where it first appears, and how to look at it. `git diff week-2-start week-2-end --stat` lists what week 2 adds: 11 files, 656 insertions, 4 deletions.

| What | Path | Tag | See it |
|---|---|---|---|
| Command table (one module per command) | `src/tradingresearch/commands/` | week-2-start | `uv run tr --help` |
| Daily screen (no model call) | `src/tradingresearch/screen.py` | week-2-start | `uv run tr screen --help` |
| Thesis prompt and validators (`check_thesis`) | `prompts/thesis-1.txt`, `src/tradingresearch/thesis.py` | week-2-start | `git show week-2-start:prompts/thesis-1.txt` |
| Reconcile engine, command, costs | `src/tradingresearch/reconcile.py`, `reconcile_run.py`, `costs.py` | week-2-start | `uv run tr reconcile --help` |
| Daily run (`daily_run` table, budget cap) | `src/tradingresearch/daily.py`, `commands/daily.py` | week-2-start | `uv run tr daily --dry-run` |
| Teacher adapter (DeepInfra pins) | `src/tradingresearch/teacher.py` | week-2-start | `uv run tr analyze --help` |
| Bake-off draw and report | `src/tradingresearch/bakeoff.py` | week-2-start | `uv run tr bakeoff --help` |
| Headline store (not yet in any prompt) | `src/tradingresearch/news.py`, `docs/news-history-depth.md` | week-2-start | `uv run tr news --help` |
| Trace and usage | `src/tradingresearch/trace.py`, `usage.py` | week-2-start | `uv run tr usage --by day` |
| CI gate | `ci/gate.py`, `ci/prompt-hashes.json`, `tests/gate/` | week-2-start | `uv run python ci/gate.py` |
| Week-2 contract: specs, fixtures, tests | `evals/specs/p1_judge.md` … `p4_levels_coherent.md`, `tests/fixtures/week2/`, `tests/test_week2.py` | week-2-start | `uv run pytest tests/test_week2.py -q` |
| P2-P4 checks (§2) | `src/tradingresearch/checks.py`, `tests/test_checks.py` | week-2-end | `git show week-2-end:src/tradingresearch/checks.py` |
| Graders P2-P4 and the P1 draft (§2, §3) | `src/tradingresearch/evals.py` | week-2-end | `git diff week-2-start week-2-end -- src/tradingresearch/evals.py` |
| P4 amendment (§2) | `evals/specs/p4_levels_coherent.md` | week-2-end | `git diff week-2-start week-2-end -- evals/specs/` |
| P1 rubric and judge prompt (§3) | `evals/rubrics/p1_thesis_quality.md`, `p1_judge_prompt.txt` | week-2-end | `git show week-2-end:evals/rubrics/p1_thesis_quality.md` |
| ADR-003 (§3) | `docs/adr/ADR-003-judge-choice-and-validation.md` | week-2-end | `git show week-2-end:docs/adr/ADR-003-judge-choice-and-validation.md` |
| Thesis prompt review (§4) | `docs/thesis-prompt-review.md` | week-2-end | `git show week-2-end:docs/thesis-prompt-review.md` |
| Bake-off pre-registration (§5) | `experiments/bakeoff-prereg.toml` | week-2-end | `git show week-2-end:experiments/bakeoff-prereg.toml` |
| Runbook and LaunchAgent template (§6) | `docs/runbook.md`, `ops/daily.launchd.plist.example` | week-2-end (runbook new; plist modified, first in week-2-start) | `git show week-2-end:docs/runbook.md` |

The week-2-end files are the reference answers: write yours first, then compare.

---

## 1. Setup and a tour of the daily loop (1 h, ≈ $0.19)

**Goal:** the week-2-start repo runs on your machine, you have seen one real `tr daily` and you know which tests are yours to make pass.

Do [SETUP.md](SETUP.md) first if you have not: the clone, the `.env` file and the free key checks. Week 2 runs on OpenRouter alone, and the code at this tag finds `.env` only through `TR_ENV_FILE`:

```bash
cd tradingresearch && git checkout week-2-start
export TR_ENV_FILE="$PWD/.env"         # once per shell, for every tag before week-6-end
uv sync
uv run pytest -q                       # 278 passed, 49 failed, 1 skipped: all 49 failures are tests/test_week2.py
uv run python ci/gate.py               # gate: ok (90 reconcile cases at rules-1, 3 prompts)
```

The settings file is the same `.env` as in week 1 ([SETUP.md](SETUP.md)), and `tr` reads it itself. The 49 failures are the week's assignment. 44 are `ModuleNotFoundError: tradingresearch.checks` (the module you write in §2), 4 are `KeyError` for grader ids not yet registered and 1 is `FileNotFoundError` for the P1 rubric (§3).

The tool lists its own commands:

```text
$ uv run tr --help
  {sessions,bars,facts,snapshot,news,screen,analyze,thesis,open,reconcile,daily,check,exp,usage,bakeoff}
    news                stored Alpaca headlines for one ticker (untrusted input)
    screen              code-only daily shortlist of the universe (no model call)
    thesis              write 0-3 checked theses or no-trades from a stored Analysis (paid call)
    open                theses whose last event is PROPOSED or OPEN
    reconcile           settle PROPOSED and OPEN theses from raw bars (no model call)
    daily               the evening run for one session: screen, analyze, thesis, reconcile (paid)
    bakeoff             the teacher bake-off: date-seeded draw and report (no model call)
```

(Excerpt: the week-1 commands are left out.) Look before you pay: `uv run tr daily --dry-run` prints what it would analyze and an estimate; it stores the free screen but writes no `daily_run` row and makes no model call. Then run one session for real, `uv run tr daily --session <a completed session>`. The author's run on 2026-11-16 stored these `daily_run` rows (read from the journal; ids and timestamps cut):

```text
step      ticker status  reason                               cost_usd
screen           ok      10 rows, shortlist 5                 0.0
analyze   HD     ok      7 claims, 5 rejected                 0.017924
analyze   JPM    ok      7 claims, 4 rejected                 0.01692
analyze   KO     ok      10 claims, 2 rejected                0.017176
analyze   AMZN   ok      8 claims, 3 rejected                 0.016208
analyze   XOM    ok      11 claims, 1 rejected                0.017034
thesis    AAPL   skipped already done (an_17f4a186735341a7)   0.0
thesis    HD     ok      accepted 1, no_trade 2, rejected 0   0.021766
thesis    JPM    ok      accepted 2, no_trade 1, rejected 0   0.0232
thesis    KO     ok      accepted 0, no_trade 3, rejected 0   0.014856
thesis    AMZN   ok      accepted 0, no_trade 3, rejected 0   0.020052
thesis    XOM    ok      accepted 2, no_trade 1, rejected 0   0.024198
reconcile        ok      reconcile 2026-11-16: 6 subjects, 0 changed, 0 events, 0 teacher outcomes (appended)  0.0
```

One thesis-step call covers three horizons (day, short, swing), so each ticker gets three decisions: a thesis or a no-trade. AAPL's analysis and thesis predate this run (week 1's analysis, then the author's separate `tr thesis` call at $0.0195), which is why AAPL's thesis step is skipped. `uv run tr open` now lists the six theses that every check in this chapter runs on (the `created` column cut):

```text
thesis_id           ticker horizon direction state    entry          stop   target
th_d7359e73ebb947a4 AAPL   swing   long      PROPOSED limit@343.41   338.7  360.83
th_0460596ced92436e HD     swing   long      PROPOSED limit@335.71   332.56 349.18
th_c0dbaf9326954bd6 JPM    short   long      PROPOSED limit@336.67   334.8  340.01
th_813ac52eb68c4df3 JPM    swing   long      PROPOSED limit@335.11   332.8  344.4
th_6786e3f15a95453e XOM    short   long      PROPOSED limit@163.38   160.11 168.75
th_066251b3465b4405 XOM    swing   long      PROPOSED limit@163.38   160.11 169.64
6 open
```

Last, the **teacher arm**. A *teacher* is a model whose outputs may later train a smaller *student* model ([Hinton et al., distillation](https://arxiv.org/abs/1503.02531)). Here three open-weights models are each pinned to one DeepInfra endpoint, whose terms let you keep the output. `uv run tr analyze KO --session 2026-11-16 --arm teacher --teacher deepseek/deepseek-v4-pro` writes the same kind of analysis as the main model, and the author's call cost $0.004119 (`run_7d0a596b94a44095`).

**Done when**
- `pytest` shows the 49 `test_week2.py` failures and nothing else red, and `ci/gate.py` says `gate: ok`.
- You have one session's `daily_run` rows and at least one PROPOSED thesis in `tr open`.

**Traps (real)**
- *The estimate is not the cost.* The dry run for 2026-11-16 said "estimated $0.25 (≈$0.02 per analyze, $0.03 per thesis)"; the run cost $0.1893 ($0.085262 analyze + $0.104072 thesis). The budget cap uses the estimates, so it stops early rather than late.
- *Reruns are free, by design.* The author's second run of the same session wrote 13 rows at $0.0 and ended `daily 2026-11-16: already done, no model call`. Finished work is read from the journal, not redone.
- *Teacher claims fail differently.* An earlier DeepSeek teacher analyze of AAPL kept 4 claims and rejected 7, all `number_in_text`: the model writes numbers into the prose, which the validators forbid. That is why the bake-off (§5) has a claim-validation bar.

**Cash:** $0.1893 for the author's `tr daily` (5 analyze + 5 thesis calls) and $0.004119 for one teacher call. **Reference:** `uv run tr daily --help`.

---

## 2. Process versus outcome: P2-P4 as code (2 h, $0)

**Goal:** `src/tradingresearch/checks.py` with three pure functions, three `@grader` classes in `evals.py`, and `tests/test_week2.py` green for P2-P4.

**Process versus outcome grading** means scoring each step of the reasoning, not only the final result. A model trained or judged on outcomes alone can be right for the wrong reasons ([Lightman et al., *Let's Verify Step by Step*](https://arxiv.org/abs/2305.20050)). For a trade the outcome is the P&L in R, and it is mostly noise over a few trades. So each thesis gets four process checks, written before it settles:

| Check | Question | Graded by |
|---|---|---|
| P1 | Did the mechanism in `reason` happen? | a judge (met / not met / unknown), §3 |
| P2 | Is the evidence real: facts traceable to the source table? | code, bool |
| P3 | Can the invalidation be reached before the stop? | code, bool |
| P4 | Are stop and target placed against the levels? | code, bool |

Once trades close, the two grades are read together. In week 3 `tr report` prints this grid per horizon:

| | Process met | Process not met |
|---|---|---|
| r_net > 0 | Earned | Lucky |
| r_net ≤ 0 | Unlucky (a good idea that lost) | Deserved loss |

Read the P2 spec first; it is the longest and the other two follow its shape:

```markdown
# evals/specs/p2_evidence_valid.md (excerpt)
`p2_evidence_valid(thesis: Thesis, claims: tuple[Claim, ...], values: dict[str, float | None], tolerance: float = 0.005) -> bool`

**Rule** (True only if all hold, for every id in `thesis.evidence`):
1. The id is the `claim_id` of a claim in `claims`.
2. That claim is tagged `fact` or `inference`. An `opinion` (a hypothesis such as "buyers should return at the
   level") is not evidence, even beside a fact. (`thesis.check_thesis` only refuses evidence that is *all*
   opinion; P2 is stricter.)
3. A fact cites at least one source id that is in `values`; a cited id missing from `values` fails.
4. A fact with a `value` matches at least one cited source holding a number, within `tolerance`. A fact without a
   `value` (a text-only fact) needs no number. A numeric fact whose cited sources hold only `None` fails.

**Worked example:** `values = {"src_close": 100.0}`; claim `cl_f4` is a fact citing `src_close` with value 100.4.
|100.4 − 100.0| = 0.4 ≤ 0.005 × 100.4 = 0.502, so a thesis with `evidence = ("cl_f4",)` passes. A fact with value
100.6 gives 0.6 > 0.503 and fails. With `tolerance=0.001`, `cl_f4` fails too (0.4 > 0.1004).
```

The grader scores a whole thesis-run sample: 1 if every thesis in it passes and 0 if any fails. Being binary lets experiments compare it with McNemar's test ([Wikipedia](https://en.wikipedia.org/wiki/McNemar%27s_test)).

**P3** (`evals/specs/p3_invalidation_testable.md`) is one line of logic. A long needs stop ≤ invalidation < entry and a short needs entry < invalidation ≤ stop; a `market_open` entry uses the snapshot's close. Spec example: stop 96 and invalidation 101 fail with a reference close of 100 and pass with 102.

**P4** (`evals/specs/p4_levels_coherent.md`): for a long, the stop sits strictly below the nearest level under the entry, and the target sits at or below the next level above it plus 0.5·ATR14. A short mirrors this, and a level exactly at the entry is ignored. With the spec's levels 90/95/105/110/115, ATR 4 and entry 101, the rule gives a long stop below 95 and a target at most 107.

Write the three functions, then the graders, then run the contract:

```bash
uv run pytest tests/test_week2.py -q                        # 51 passed at week-2-end
uv run pytest tests/test_checks.py tests/test_week2.py -q   # 63 passed
uv run pytest -q                                            # 339 passed, 1 skipped
```

Then run the checks on the six real theses from §1. The reference did this with a read-only scratch script. Here is its table at week-2-end, with P4 computed twice: on the raw stored floats and at cents, as the amended spec does:

| Thesis | Entry | Stop | Target | Inval | P2 | P3 | P4 raw | P4 cents |
|---|---|---|---|---|---|---|---|---|
| AAPL swing | 343.41 | 338.7 | 360.83 | 338.7 | 1 | 1 | 1 | **0** |
| HD swing | 335.71 | 332.56 | 349.18 | 332.56 | 1 | 1 | **0** | **0** |
| JPM short | 336.67 | 334.8 | 340.01 | 335.11 | 1 | 1 | 1 | 1 |
| JPM swing | 335.11 | 332.8 | 344.4 | 333.0 | 1 | 1 | **0** | 1 |
| XOM short | 163.38 | 160.11 | 168.75 | 160.11 | 1 | 1 | 1 | **0** |
| XOM swing | 163.38 | 160.11 | 169.64 | 160.11 | 1 | 1 | 1 | **0** |
| **Total** | | | | | 6/6 | 6/6 | 4/6 | 2/6 |

**Read the table.** P2 and P3 are clean. P4 flips on four of six theses depending on rounding. AAPL's hvn level is stored as 343.40978, and the entry is 343.41, so at raw precision the level sits *below* the entry and becomes the stop's floor. At cents it equals the entry and is ignored, so the floor is the pivot low 338.70, and the stop sits exactly on it. XOM is the same story: hvn 163.37702 rounds to the entry, and low_20 160.1101 rounds to the stop, 160.11. JPM swing goes the other way. Its hvn 335.11379 is 0.0038 above the entry, so raw P4 caps the target at 338.77 and fails it. HD fails both ways: its nearest level below is hvn 319.08 and the stop 332.56 is not below it. In three of the six, the model put the stop *exactly* on a level's cent price. That is a pattern to count, not yet a finding (§4).

**Done when**
- `tests/test_week2.py` passes for P2-P4, and the registry holds `p2_evidence_valid`, `p3_invalidation_testable` and `p4_levels_coherent`.
- You can explain each 0 in the table from the stored levels.

**Traps (real)**
- *Floats against cents.* The model quotes prices in cents and the levels are stored unrounded, so the first P4 marked JPM swing a fail over 0.0038 and passed three stops sitting on a level. The amendment compares at cents (`checks.cents`, 2 decimals) and is part of the spec at week-2-end. Write the rule into the spec, not only into the code.
- *EDGAR facts in the grader.* The thesis-stage source table holds only snapshot rows, so in the grader a fact that cites only an EDGAR source fails rule 3. The spec says so; when you call the function directly, pass the full table.
- *Opinion beside a fact.* `check_thesis` accepts evidence that is partly opinion and P2 does not. Two layers that disagree are fine if each spec says which one it is.

**Cash:** $0; every check runs on stored theses. **Reference:** `git diff week-2-start week-2-end -- src/tradingresearch/checks.py src/tradingresearch/evals.py tests/test_checks.py`.

---

## 3. P1: a rubric, a draft judge and ADR-003 (1.5 h, $0)

**Goal:** a P1 rubric, a judge prompt that wraps it, a registered draft grader that refuses to run, and ADR-003, which says which model judges and how it earns trust.

P1 asks whether the mechanism in `reason` actually happened ("breakout holds above 104.0 with rel_volume ≥ 1.5"). Code cannot read that, so P1 is an **LLM-as-judge**: a second model grades the first model's output against a written rubric ([Zheng et al.](https://arxiv.org/abs/2306.05685)). A judge is itself a model with errors, so its verdicts count only after **judge validation**: you label a sample by hand, blind to the judge, and measure agreement ([Shankar et al., *Who Validates the Validators?*](https://arxiv.org/abs/2404.12272); [Husain, *Using LLM-as-a-Judge For Evaluation*](https://hamel.dev/blog/posts/llm-judge/)). Agreement is measured with **Cohen's kappa**, which corrects raw agreement for the share expected by chance ([Wikipedia](https://en.wikipedia.org/wiki/Cohen%27s_kappa)).

The rubric (`evals/rubrics/p1_thesis_quality.md`) has seven headings: Question, Inputs, Met, Not met, Unknown, Hindsight, Verdict format. The judge sees the thesis text, the claims it cites and a post-trade summary written by code. It never sees raw bars and computes no numbers. The verdict is JSON, `{"verdict": "pass" | "fail", "explanation": ...}`, and *unknown* is a fail whose explanation starts `unknown:`. The spec's worked example: a breakout over 104.0 with rel_volume 1.8 that closes at 102.9 and then 101.5 did not hold, so the verdict is fail. The judge prompt opens:

```text
You are grading one trading thesis after its trade closed. You decide one thing: did the mechanism the thesis
gives as its reason actually happen? You are not grading whether the trade made money, whether the idea was
clever, or whether you would have taken it.
```

The grader is registered so experiments can name it, but it cannot produce a number yet:

```python
class P1Judge:            # src/tradingresearch/evals.py at week-2-end
    id = "p1_judge"
    version = "1"
    kind = "model"
    validated = False

    def grade(self, sample, expected) -> Score:
        raise CannotGrade("p1_judge is a draft: no model call until it runs on closed trades in week 3")
```

ADR-003 (status: model accepted, thresholds proposed, 2026-11-17) records the choice:
- **Judge:** `openai/gpt-6-sol` at $2 / $10 per 1M tokens in/out ($1 / $5 on `:batch`), budget fallback `openai/gpt-6-luna` at $0.10 / $0.50. Prices were read from the OpenRouter models API at 2026-11-17T04:42:35Z.
- **Different family from the writer.** The theses are written by `anthropic/claude-sonnet-5.5`. A judge tends to prefer its own outputs ([Panickssery et al., self-preference](https://arxiv.org/abs/2404.13076)).
- **Bar:** κ ≥ 0.6 (gigai-core `MIN_KAPPA`) on 30 blind human labels, about 15 in week 3 and 30 by week 4. Up to 3 rubric rounds are allowed; if it still fails, P1 is reported from human labels only. After that, a re-check every 2 weeks on 10 new labels.
- **Cost:** an *estimate* of ≈ $0.013 per closed trade (4,000 tokens in, 500 out). Nothing has been measured; no call has been made.

> **Awaiting sessions 1-N: judge validation (N = the session on which the 30th labelled trade closes)**
> Filled in when the data exists; nothing here is an estimate of the result.
> - Needs: closed trades and your blind labels.
> - Command: `uv run tr label` (week 3; flags not defined yet).
> - Earliest: when 30 trades are closed and labelled; date unknown. The first trade can close on 2026-11-17, session 1: a limit entry that fills and then touches its stop closes that same session (reconcile rule 3), settled by that evening's reconcile.
> - Then: κ on 30 labels against ≥ 0.6, recorded in an ADR that flips `validated`.

**Done when**
- The rubric has the seven headings, and `tests/test_week2.py` finds the file and the `p1_judge` registry entry.
- ADR-003 names the judge, its price and source, the κ bar, the label count and what happens if it fails.

**Traps (real)**
- *The library gate cannot pass at this size.* gigai-core's agreement check requires `MIN_UNITS = 126`, so on 30 labels it fails by construction. ADR-003 reports κ as "descriptive, not validated" and says why.
- *Thirty labels give a wide interval.* With 30 labels the 95% half-width of κ is about ±0.29 (a large-sample estimate): a point estimate of 0.6 is consistent with anything from about 0.31 to 0.89. The bar separates a working judge from a broken one; it does not rank judges.
- *A draft that quietly runs.* If the draft grader called a model, a config naming it would produce a P1 rate nobody validated. `CannotGrade` makes that impossible until week 3.

**Cash:** $0. **Reference:** `git show week-2-end:docs/adr/ADR-003-judge-choice-and-validation.md`.

---

## 4. Review thesis-1 on real output, and the CI gate (1 h, $0)

**Goal:** `docs/thesis-prompt-review.md`, a list of what the thesis prompt gets wrong on real data, and an understanding of why you cannot fix any of it by editing the prompt in place.

The author read all 18 decisions from §1 (6 tickers × 3 horizons): 6 theses and 12 no-trades, with 0 rejections. The 6 thesis runs cost $0.123590 together and scored 1.0 on the code checks that existed then. With P2-P4 in hand, the review found eight problems:

1. 3 stops sit on a level and HD's sits inside one: 4 of 6 fail P4 at cents (§2).
2. The prompt tells the model that code rejects bad level placement, but `check_thesis` does not check it.
3. Rounding: the prompt shows 6 significant digits and the levels are stored unrounded, so 4 of 6 P4 verdicts flip on raw floats.
4. Prompt rule 6 and P4's target allowance disagree (XOM swing, target 169.64).
5. Limit entries sit far below the close: AAPL 1.16 ATR (2.66%), HD 1.37 ATR (3.40%).
6. The evidence does not cover the levels that set entry and stop (HD).
7. One reason names two mechanisms (XOM swing, earnings), a likely P1 `unknown`.
8. One setup is recorded twice (XOM short and swing).

To watch, not yet problems: every thesis is long in a bull-high regime, swing always holds 10 sessions and short 3, and JPM short clears its floor by 0.04.

**What you may not do is edit `prompts/thesis-1.txt`.** A **CI gate for prompts** is a check that blocks a prompt change unless an eval justifies it, so a "small wording fix" cannot slip in untested ([Husain, *Your AI Product Needs Evals*](https://hamel.dev/blog/posts/evals/)). Here `ci/gate.py` does two things, free and offline. It re-settles 90 synthetic reconcile cases against goldens, and it checks every file in `prompts/` against the sha256 in `ci/prompt-hashes.json`:

```text
$ uv run python ci/gate.py
gate: ok (90 reconcile cases at rules-1, 3 prompts)
```

A change to thesis-1 means a new file, `prompts/thesis-2.txt`, named in an experiment arm under `experiments/`, then `uv run python ci/gate.py --record-prompts`. As in week 1 (ADR-002), thesis-2 ships only after a paired run against thesis-1.

**Done when**
- Your review lists each problem with the thesis ids that show it, and separates findings from things to watch.
- `ci/gate.py` still says `gate: ok`: you changed no recorded prompt.

**Traps (real)**
- *A prompt that promises a check.* Finding 2 is the dangerous one. The model is told code will catch bad placement, nothing does, and the stops land on levels. Every "code rejects X" line in a prompt needs a test that X is rejected.
- *Scored 1.0, still wrong.* All six theses passed the code checks of week-2-start. A clean score means the checks you have pass, not that the output is good.
- *A rounding bug looks like a model bug.* Finding 3 is a data-presentation problem, not a model problem. Fix how numbers are shown and compared before you blame the prompt.

**Cash:** $0; the review reads stored runs. **Reference:** `git show week-2-end:docs/thesis-prompt-review.md`.

---

## 5. Pre-register the teacher bake-off (1 h, $0 now)

**Goal:** `experiments/bakeoff-prereg.toml`, committed before bake-off session 1, which says how one of three teachers will be picked.

**Pre-registration** means writing the metric, the sample and the decision rule down *before* you see data, so the result cannot pick its own test ([Center for Open Science](https://www.cos.io/initiatives/prereg)). Week 1 did it inside ADR-002; here it is a file with a timestamp that must come before session 1. The three teachers, each on its pinned endpoint (prices per 1M tokens in/out):

| Teacher | Endpoint | Price |
|---|---|---|
| `deepseek/deepseek-v4-pro` | deepinfra/fp8/flex | $1.04 / $2.08 |
| `qwen/qwen3.5-397b-a17b` | deepinfra/fp8/flex | $0.36 / $2.40 |
| `openai/gpt-oss-120b` | deepinfra/bf16 (no flex) | $0.037 / $0.17 |

Each session, a seeded draw picks 4 shortlist names; the seed is the sha256 of the date, not the screen rank. All three teachers write analyses and theses for the same 4 names. Over 10 sessions that is 40 paired items per teacher in 10 clusters (gigai-core's `MIN_CLUSTERS`). The fields, as committed:

```toml
# experiments/bakeoff-prereg.toml (fields; the comments above them hold the teachers, sessions and pick rule)
primary_metric = "p2_p4_pass"
guard_metric = "parse_ok"
margin = 0.10
n_planned = 40
pass_rule = "eligible (parse_ok >= 38/40, fact claims valid >= 90%); leader on p2_p4_pass wins unless a cheaper eligible teacher is within margin, then the cheapest such; ties: higher claim-validation share, then lower price"
hypothesis = "On the same 40 drawn items, at least one pinned open-weights teacher is eligible, and the cheapest eligible teacher's p2_p4_pass is within 0.10 of the leader's."
registered_at = 2026-11-17T04:55:00Z
```

In words: a teacher is eligible if at least 38 of 40 items parse and at least 90% of its fact claims pass the validators. The leader on P2-P4 wins unless a cheaper eligible teacher is within 0.10 (4 of 40). With n = 40 the paired standard error is about 0.12-0.17, so this is a decision procedure, not a significance test, and the file says so. Session 1 is the first NYSE session on or after 2026-11-17 with a stored teacher analysis. The two teacher analyses from 2026-11-16 (AAPL, KO) were a pre-live test and are excluded.

The draw is free and reproducible:

```text
$ uv run tr bakeoff draw --session 2026-11-16
bake-off draw 2026-11-16: AMZN HD KO XOM  (4 of a shortlist of 5, seeded by sha256 of 2026-11-16)
```

**At week-2-end `tr daily` has no teacher step.** The prereg's comment says the draws run by hand: `tr bakeoff draw --session D`, then `tr analyze` and `tr thesis` with `--arm teacher --teacher MODEL` for each name and teacher. The commit after week-2-end adds an opt-in `tr daily --teachers`, capped by `--teacher-max-usd` (default 0.40), together with the bake-off start date 2026-11-17 (see `git log week-2-end..week-3-start`).

> **Awaiting sessions 1-10: teacher bake-off**
> Filled in when the data exists; nothing here is an estimate of the result.
> - Needs: teacher analyses and theses stored for each session's 4 drawn names; the teacher draws are run by `tr daily --teachers` (from the commit after week-2-end).
> - Earliest: session 1 = 2026-11-17. With 2026-11-26 closed (Thanksgiving) and 2026-11-27 a half day, session 10 = 2026-12-01 (`uv run tr sessions --session 2026-12-02 --count 12`).
> - Command: `uv run tr bakeoff report` (it takes no options). You pick; the report makes no automatic pick.

**Done when**
- The prereg loads (`bakeoff.prereg(...)`, the load check is in the file's header) and its `registered_at` is before session 1.
- The file names the teachers and endpoints, the sessions, the eligibility bars and the pick rule.

**Traps (real)**
- *The report counts the wrong session.* At week-2-end, `uv run tr bakeoff report` prints `bake-off sessions 2026-11-16..2026-11-16 (1 of 10), 4 drawn items`. The planner counts any session with a stored teacher analysis, so the pre-live test would become session 1. The prereg's header records this as a known gap, and the start date arrives in the commit after the tag.
- *The primary metric is not wired yet.* The same report prints `p2_p4_pass  n/a: P2-P4 graders not written yet (week 2)` for every teacher. §2 wrote the graders, but the report does not call them yet. Check that every metric a prereg names can actually be computed before session 1.
- *A stale pointer.* The report's last line still names `experiments/bakeoff-prereg.example.toml`, the template, not the committed file.
- *Price is not cost.* The only measured teacher figure is one DeepSeek analyze call at $0.004119. The bake-off's ≈ $2.70 (with margin) is a budget estimate, paid from the lane budget.

**Cash:** $0 this week. **Reference:** `git show week-2-end:experiments/bakeoff-prereg.toml`.

---

## 6. The runbook and the live stream (0.5 h, $0)

**Goal:** `docs/runbook.md`, saying how `tr daily` runs every evening without you, how to check it and what to do when it fails.

The LaunchAgent `com.tradingresearch.daily` runs `uv run tr daily --teachers` Monday to Friday at 14:30 and 19:00, and Tuesday to Saturday at 05:00, in the Mac's zone, America/Denver: 16:30, 21:00 and 07:00 in New York. The 19:00 run is a catch-up, and 05:00 is a second one, before the 09:30 ET entry window: it retries what an upstream model failure (a 429 or 503) left undone, and costs nothing when everything is stored (15 runs a week). `--teachers` (the bake-off step) arrives at week-3-start; with week-2 code, leave it out of the plist and of the dry-run below. It logs to `<repo>/data/logs/daily.log`. `tr` reads its settings file itself, so no key goes in the plist; with the week-2 code the agent's environment needs `TR_ENV_FILE` as well, because launchd does not see your shell's exports ([SETUP.md](SETUP.md)). `ops/daily.launchd.plist.example` is the template, written for a Mac on New York time. Day 1 of the live stream is 2026-11-17.

**Pin the code that writes evidence; dev never writes the live journal.** The journal is append-only (the triggers below) and the bake-off is pre-registered, so the code that writes it must not change under the stream: an unfinished edit on the branch you work on would write the 14:30 rows. So the agent does not run from your working checkout. Its `WorkingDirectory` is a git worktree, `<repo>-live` next to your clone, detached at a commit whose tests and `ci/gate.py` pass, and its environment sets `TR_DATA_DIR=<repo>/data`, the live journal. Nothing but the agent writes rows to it. Everything you run yourself (tests, experiments, packet runs) writes to `TR_DATA_DIR=<repo>/data-dev` (add `data-dev/` to `.gitignore`; master has it); report, usage, slo and `--dry-run` may read the live data. A git worktree is a second checkout of the same repository ([git worktree docs](https://git-scm.com/docs/git-worktree)); a detached HEAD is a checkout that follows no branch, so nothing moves it. The pin moves only to a commit you have verified. The last trap below explains why opening the journal can still add empty tables:

```text
git -C <repo>-live checkout --detach <sha> && (cd <repo>-live && uv sync -q)
(cd <repo>-live && TR_DATA_DIR=<repo>/data uv run tr daily --teachers --dry-run)
```

Never move it between 14:15 and 14:45, between 18:45 and 19:15 or between 04:45 and 05:15 (Tuesday to Saturday) America/Denver, the run windows. The master runbook's "Pinned code, live data" section has the same steps; it is written after week-2-end.

```text
$ uv run tr daily --help
usage: tr daily [-h] [--session SESSION] [--top TOP] [--max-usd MAX_USD] [--dry-run] [--no-model]
  --session SESSION  a completed session (default: the latest, after 16:15 ET)
  --top TOP          analyze the screen's top N (default 10, SPIKE §4.2)
  --max-usd MAX_USD  stop before the next model call that would take the run past this (default
                     1.00)
  --dry-run          free steps only (reconcile writes nothing): print what would be analyzed and
                     its cost
  --no-model         run the free steps for real; skip analyze and thesis
```

A rerun shows the log format; these lines are from `data/logs/daily.log` (one ticker shown of each step):

```text
analyze   XOM    skipped already done (an_caae3c0914d34ee0)
thesis    XOM    skipped already done (an_caae3c0914d34ee0)
  XOM swing PROPOSED unchanged  (th_066251b3465b4405, champion)
    note: waiting: the entry window opens on 2026-11-17
reconcile -      ok      reconcile 2026-11-16: 6 subjects, 0 changed, 0 events, 0 teacher outcomes (appended)
daily 2026-11-16: already done, no model call
```

The rules the runbook writes down:
- **Budget:** each paid step is estimated first ($0.02 analyze, $0.03 thesis). A step that would pass `--max-usd` gets a `stopped` row.
- **Late:** once the next entry window opens (09:30 ET the next session), analyze and thesis are skipped. A thesis written after its window opens would be hindsight.
- **Missed:** a session with no `daily_run` row in the last 10 trading days gets a `missed` row and is never backfilled.
- **Append-only:** `events`, `thesis` and `daily_run` refuse updates and deletes (triggers), so nothing is corrected in place.
- **Checks:** `tail -20 data/logs/daily.log`, `launchctl list | grep tradingresearch`, `uv run tr usage --by day`.

**Done when**
- `launchctl list | grep tradingresearch` shows the agent, and the runbook says what each failure row means and what to do about it.
- The first live `daily_run` rows, for 2026-11-17, are written by the agent, not by hand.

**Traps (real)**
- *launchd reads the Mac's clock.* Hour and Minute are local time in your zone. If the Mac changes zone, the times must be converted again. The template (New York) and the installed agent (Denver) differ for that reason.
- *Hand runs on a live session.* The agent owns live sessions; use `--dry-run` to look. A rerun would cost nothing, but a run made after 09:30 ET the next day is skipped as late, and a missed session stays missed. For anything that writes (a test run of `analyze`, `thesis`, `reconcile`, an experiment), set `TR_DATA_DIR=<repo>/data-dev`: a write to `data/` is evidence you cannot take back.
- *A newer checkout opens an older journal.* Opening the live `data/journal.db` with newer code runs its `CREATE TABLE IF NOT EXISTS` script, so a dev command adds empty tables (week 4's `rule_change` is one). That is safe for the pinned code, which ignores tables it does not know. A change that adds, alters or drops a column is not: land it together with a pin move.
- *Holidays are not failures.* The default session is the last completed one, so on a market holiday the run finds it already done.

**Cash:** $0 for the runbook. Each live session then costs about what §1 measured. **Reference:** `git show week-2-end:docs/runbook.md`.

---

## 7. What week 3 does with this (0.5 h, $0)

**Goal:** know what the week-2 pieces feed, so nothing is built twice.

Week 3 (`week-3-start` → `week-3-end`) adds `tr grade` (the outcome `r_net`, a shadow baseline, the P2-P4 checks and the P1 judge), `tr report` (per-horizon scorecards, never pooled, with the Earned/Lucky grid of §2), `tr label` (blind P1 labels for the judge) and `slo_check.py`. The plan also lists `trace.py` and `usage.py` for week 3, but they are already in `week-2-start` (`tr usage`). A **service-level objective** is a measured target that says when a running service counts as healthy ([Google SRE book](https://sre.google/sre-book/service-level-objectives/)). The four for the desk: a report by 17:30 ET, zero missed sessions, fresh data, and an alert that fires on an injected delay. About 15 blind P1 labels feed the first κ, and ADR-004 sets the trace policy: what never goes in a trace.

> **Awaiting sessions 1-N: P1-P4 scorecards over settled theses (N = the latest settled session)**
> Filled in when the data exists; nothing here is an estimate of the result.
> - Needs: theses settled by `tr reconcile` from session 1 on.
> - Command: `uv run tr report` (week 3; flags not defined yet).
> - Earliest: the first settle, 2026-11-17 (session 1), if a thesis closes that session.
> - P2-P4 can be scored on any stored thesis today (§2); the scorecard waits for settled outcomes, and P1 waits for the validated judge (§3).

**Done when**
- You can say which week-2 file each week-3 command reads: the graders, the rubric, the prereg and the `daily_run` table.

**Traps (real)**
- *Reporting before the data.* Every number above that waits on sessions sits in an "Awaiting" block with the command that will fill it. None is filled with a guess.

**Cash:** $0. **Reference:** [week-3.md](week-3.md).

---

## Week 2 cash, as measured by the author

| Step | Spent | Source |
|---|---|---|
| Building `week-2-start` (all paid calls, key $61.778267 → $61.997785) | $0.2195 | the OpenRouter key |
| of which: `tr daily` on 2026-11-16, 5 analyze + 5 thesis | $0.1893 | `daily_run` rows, §1 |
| of which: one teacher analyze (KO, DeepSeek) | $0.004119 | `run_7d0a596b94a44095` |
| Week-2 reference answers (P2-P4, P1 draft, ADR-003, review, prereg, runbook) | $0 | no model call |
| Teacher bake-off, sessions 1-10 | awaiting | lane budget, not the learner's |

## Week 2 is done when

- `uv run pytest -q` is green (339 passed, 1 skipped at the reference) and `ci/gate.py` says `gate: ok`.
- P2-P4 run on your real theses and you can explain every 0.
- The P1 rubric, the draft judge and ADR-003 exist, and the judge cannot run until it is validated.
- The thesis-1 review lists findings and watch items, and no recorded prompt changed.
- The bake-off prereg is committed with `registered_at` before session 1.
- The runbook is written, the LaunchAgent is installed, and the three Awaiting blocks name the command that fills each one.
- `git tag week-2-end` on your commit.

Nothing in this chapter reports a result that has not happened. The live stream supplies the data from 2026-11-17, and week 3 reads it.
