# Week 4: give analyze tools, measure it, start the challenger

> *"Educational software. Not investment advice. No orders are placed; trades are hypothetical and settled from historical bars by written rules. Past results, including these, do not predict future results."*

**Code:** start [`week-4-start`](https://github.com/karthik446/tradingresearch/tree/week-4-start) · reference answer [`week-4-end`](https://github.com/karthik446/tradingresearch/tree/week-4-end) · [the chapter diff](https://github.com/karthik446/tradingresearch/compare/week-4-start...week-4-end) (repo: [karthik446/tradingresearch](https://github.com/karthik446/tradingresearch)).

**You start at** `week-4-start`: week-3-end plus shipped code for this week's plumbing. `tr learn` prints the playbook and the rule-change status, `rules.register` stores a pre-registered RuleChange, `tr daily` runs a challenger arm while one is pending, and `tests/fixtures/week4/` holds one real two-turn tool exchange. `tests/test_week4.py` fails by design (23 cases).
**You end at** `week-4-end`: three analyze tools and the tool loop, a `mode = "tools"` experiment arm, the `tool_calls_ok` grader, one paid run of tools against fixed context with ADR-005 deciding from it, a route-provenance fix the recorded exchange exposed, and the first real rule change, pre-registered and stored in the live journal.
**Cash:** the code costs $0, because the loop tests replay the recording. The one paid step is the experiment: the author's run cost $0.877992. **Time:** about 10 hours, the sum of the section guides below.

Concepts this week, each explained in one or two lines with a link where it is first used: tool use and the agent loop (§2, §3), tool design (§2), retries with jitter (§3, shipped in week 3), McNemar's test (§4), champion/challenger (§6), Cohen's κ (§7) and MCP (§8). Week 3 graded trades after the market answered. Week 4 asks whether a model that fetches its own rows writes better claims than one handed them, and starts the one controlled change to the rules that the 60 days are allowed.

This chapter was checked on 2026-11-17 between 02:30 and 02:35 ET. The live pin had moved to `week-4-end` and `rc_1` was registered, but the first covered session (2026-11-17) had not opened. Every number that needs a live session sits in an "Awaiting" block with the command that will fill it.

## Where everything is

Every file this chapter names, the tag where it first appears, and how to look at it. `git diff week-4-start week-4-end --stat` lists what week 4 adds: 18 files, 1,038 insertions, 25 deletions.

| What | Path | Tag | See it |
|---|---|---|---|
| Rule-change store, playbook, the day-60 adoption rule | `src/tradingresearch/journal.py` (`rule_change`), `playbook.py`, `adopt.py`, `commands/learn.py` | week-4-start | `uv run tr learn --status` |
| Challenger rules and the challenger arm | `src/tradingresearch/rules.py` (`CHALLENGER_RULES`, `register`), `daily.py`, `commands/thesis.py` (`--arm challenger`) | week-4-start | `uv run tr daily --help` |
| Judge score store, `tr grade` help | `src/tradingresearch/journal.py` (`add_judge_score`), `commands/grade.py` | week-4-start | `uv run tr grade --help` |
| Tools capability, `mode` arm knob, retries (unchanged) | `src/tradingresearch/openrouter.py`, `experiment.py`, `retry.py`, `tests/fixtures/tools/` | week-3-start | `git show week-3-start:tests/fixtures/tools/get_close.request.json` |
| Week-4 contract: tests and the recorded tool exchange | `tests/test_week4.py`, `tests/fixtures/week4/` (`turn1`/`turn2` `.request.json` and `.reply.json`, `fakea.context.json`, `models.json`) | week-4-start | `uv run pytest tests/test_week4.py -q` |
| The three tools, `run_tool` (§2) | `src/tradingresearch/tools.py`, `tests/test_tools.py` | week-4-end | `git show week-4-end:src/tradingresearch/tools.py` |
| The tool loop (§3) | `src/tradingresearch/analyze.py` (`analyze_with_tools`, `MAX_TOOL_TURNS`, `tools_prompt`) | week-4-end | `git diff week-4-start week-4-end -- src/tradingresearch/analyze.py` |
| The tools arm (§3) | `src/tradingresearch/experiment.py` (`run_tools`, `graded`) | week-4-end | `git diff week-4-start week-4-end -- src/tradingresearch/experiment.py` |
| `tool_calls_ok` grader (§3) | `src/tradingresearch/evals.py` (`ToolCallsOk`) | week-4-end | `git show week-4-end:src/tradingresearch/evals.py` |
| Experiment config (§4) | `experiments/tools-vs-fixed.toml` | week-4-end | `git show week-4-end:experiments/tools-vs-fixed.toml` |
| ADR-005, tools vs fixed (§4) | `docs/adr/ADR-005-tools-vs-fixed-context.md` | week-4-end | `git show week-4-end:docs/adr/ADR-005-tools-vs-fixed-context.md` |
| Measured costs, week 4 (§4) | `docs/measured-costs.md` | week-4-end (modified; new in week-3-end) | `git diff week-4-start week-4-end -- docs/measured-costs.md` |
| Route provenance (§5) | `src/tradingresearch/openrouter.py` (`exchange_key`, `route_for`), `records.py` (`clean_route`), `tests/test_route.py` | week-4-end (commits `235fd20`, `2ed97a9`) | `git show 235fd20 --stat` |
| First rule change (§6) | `experiments/rule-change-1.toml`, `rules.py` (`short-sma50-trend`) | week-4-end | `git show week-4-end:experiments/rule-change-1.toml` |
| Runbook: tools mode, provenance, week-4 acceptance | `docs/runbook.md` | week-4-end (modified; new in week-2-end) | `git diff week-4-start week-4-end -- docs/runbook.md` |
| MCP server, ADR-006 (§8) | none | not in the repo (optional) | — |

The week-4-end files are the reference answers: write yours first, then compare.

---

## 1. Setup and a tour of the shipped code (1 h, $0)

**Goal:** the week-4-start repo runs on your machine, you know which 23 tests are yours, and you have seen `tr learn` and the challenger flags.

Do [SETUP.md](SETUP.md) first if you have not. Week 4 runs on OpenRouter alone, and the code at this tag finds `.env` only through `TR_ENV_FILE`:

```bash
cd tradingresearch && git checkout week-4-start
export TR_ENV_FILE="$PWD/.env"         # once per shell, for every tag before week-6-end
uv sync
uv run pytest -q                       # 498 passed, 23 failed, 1 skipped, 2 deselected: all 23 are tests/test_week4.py
uv run python ci/gate.py               # gate: ok (90 reconcile cases at rules-1, 3 prompts)
```

The 23 failures are the week's assignment, in seven groups. Each names the missing piece:

| Cases | Error at week-4-start | You write |
|---|---|---|
| 6 | `ModuleNotFoundError: No module named 'tradingresearch.tools'` | `tools.py` (§2) |
| 5 | `AttributeError: module 'tradingresearch.analyze' has no attribute 'analyze_with_tools'` | the loop (§3) |
| 2 | `NotImplementedError: mode=tools: week 4 learner work` | the tools arm (§3) |
| 6 | `KeyError: 'tool_calls_ok'` | the grader (§3) |
| 1 | `FileNotFoundError: ... experiments/tools-vs-fixed.toml` | the config (§4) |
| 1 | `docs/adr/ADR-005-tools-vs-fixed-context.md is missing` | ADR-005 (§4) |
| 2 | `experiments/rule-change-1.toml is missing` | the rule change (§6) |

The week-4 commands, from `uv run tr --help` (excerpt). The `grade` line now says the judge pays, which fixes week 3's top-level-help trap:

```text
    grade               shadow baselines and grades for closed theses (a paid
                        P1 judge with --judge)
    learn               playbook per horizon and setup; rule changes and their
                        adoption (no model call)
```

`tr learn` and `tr learn --status` read only the journal. `--decide CHANGE_ID` writes one final decision and is for week 9. `tr daily` gains `--no-challenger`, and `tr thesis --arm challenger` writes one challenger thesis by hand. On the author's live journal, 2026-11-17 02:30 ET, the playbook has nothing to learn from yet:

```text
$ uv run tr learn
playbook: champion theses graded and closed by 2026-11-16, one row per (horizon, setup_type), never pooled; cells with n < 5 are thin (few trades overfit)
  no graded champion theses closed by 2026-11-16 yet: nothing to learn from
```

**Done when**
- `pytest` shows the 23 `test_week4.py` failures and nothing else red, and `ci/gate.py` says `gate: ok`.
- You have run `tr learn`, `tr learn --status` and `tr daily --help` on your journal.

**Traps (real)**
- *The tools capability is not this week's.* `OpenRouter` already sends `tools` and returns `tool_calls`, and `Arm.mode` already takes `fixed` or `tools`: both shipped in `week-3-start` (week 3's table). Week-4-start adds the recorded exchange and the contract, not the transport.
- *Shipped code needs a pin move to run live.* The live LaunchAgent runs `tradingresearch-live`, a detached worktree. Until 2026-11-17 it sat at `a9eafa3` (week-3-start), which has no challenger arm, so a registered change would have had no challenger to answer it. The author moved the pin to `2ed97a9` (week-4-end) before registering `rc_1` (§6); `git worktree list` shows it there.

**Cash:** $0. **Reference:** `uv run tr learn --help`.

---

## 2. Tool design: three tools over the context (2 h, $0)

**Goal:** `src/tradingresearch/tools.py` with the tools and `run_tool`, making the 6 tools cases pass.

**Tool use** means the model answers with a structured request (a tool name and JSON arguments) instead of text. Your code runs it and sends the result back as a `tool` turn, and the model goes on ([Anthropic, *Tool use*](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview)). **Tool design** is interface design for a reader that cannot ask questions: few tools, names that say what comes back, descriptions that name the rows, and errors the model can act on ([Anthropic, *Writing effective tools for agents*](https://www.anthropic.com/engineering/writing-tools-for-agents)).

The contract, from `tests/test_week4.py`:

```python
tools.TOOLS: tuple[ToolSpec, ...]                       # gigai-core ToolSpec, unique valid names, closed schemas
tools.run_tool(ctx: Context, name: str, arguments: str) -> str   # JSON text; a bad call is {"error": ...}, never raised
```

The tools serve the same `Context` rows the fixed SOURCES table shows, offline and deterministic, so the experiment in §4 changes only *how* the rows arrive. The reference has three (`git show week-4-end:src/tradingresearch/tools.py`):

| Tool | Arguments (closed schema) | Rows |
|---|---|---|
| `get_indicators` | `names?`: non-empty string list | price, moving averages, RSI, ATR, volume, range, distances in ATR, `regime_spy` |
| `get_levels` | none | high-volume nodes, pivot highs and lows, their ATR distances, the congestion zone |
| `get_fundamentals` | `metrics?`: an enum of the four EDGAR metrics | revenue, net income, diluted EPS per quarter, annual revenue |

Each row comes back as `{source_id, name, unit, value}`, with the value rounded as the fixed table shows it, so a claim cites the same `source_id` in both modes. Every mistake is a result the model reads. Real output, from `run_tool` on the test fixture's 38-row FAKEA context (2026-11-17 02:33 ET):

```text
run_tool(ctx, 'get_indicators', '{"names": ["close", "rsi_14"]}')
   {"rows": [{"source_id": "src_98651de31e6271aa", "name": "close", "unit": "USD", "value": 101.4}, {"source_id": "src_e80e4812c8cf9f6d", "name": "rsi_14", "unit": "index", "value": 61.3}]}
run_tool(ctx, 'get_quote', '{}')
   {"error": "unknown tool 'get_quote'; the tools are get_indicators, get_levels, get_fundamentals"}
run_tool(ctx, 'get_indicators', '{"names": ["rsi"]}')
   {"error": "get_indicators: no row named rsi; names: close, sma_20, sma_50, sma_200, ema_9, ema_21, rsi_14, ...   [cut here; the real line lists every name]
run_tool(ctx, 'get_fundamentals', 'not json')
   {"error": "get_fundamentals: arguments are not valid JSON (Expecting value); send a JSON object"}
```

The recorded exchange the tests replay was captured on 2026-11-17 (01:48 ET, the generation id's timestamp) for FAKEA with prompt analyze-1 on `anthropic/claude-sonnet-5.5`. It used one capture tool, `get_sources(groups)`, not the three above. Turn 1 sent the tools with `tool_choice: "auto"`; the model asked for every group at once. A summary, not command output: the values come from `turn1.reply.json` and `turn2.reply.json`, and the claim verdicts from the capture's report:

```text
turn 1  provider Azure   finish tool_calls  1593 in /   76 out  $0.003946  gen-1794898101-V821yVnFt7udLbpHjPRq
        get_sources {"groups": ["price_and_indicators","levels_and_congestion","regime","fundamentals"]}
turn 2  provider Google  finish stop        2911 in / 1312 out  $0.018942  gen-1794898105-87Cc3rq2ON2Dro6qcwgI
        11 claims: 6 kept, 5 rejected (number_in_text ×2, bad_derivation, empty_placeholder, not_a_claim)
```

Two calls, $0.022888. Two providers served one exchange, which is §5's bug.

**Done when**
- The 6 tools cases pass: unique valid names, every argument described, every schema closed (`additionalProperties: false`), an unknown tool names every tool, malformed JSON, a non-object and an unknown argument each come back as an error for every tool.

**Traps (real)**
- *`tool_choice: "required"` is refused.* The capture first tried forcing a tool call and got HTTP 400 `tool_choice: type "tool" and "any" are not supported for this model`, at $0. The route only takes `auto`, so the model may answer with no tool call at all (§3).
- *The fixture never calls a shipped tool.* `get_sources` is unknown to the three reference tools. The replay checks the loop's wiring (turns, `tool_call_id`s, spans), not your tools' rows; `tests/test_tools.py` covers those.
- *A raised exception is a crash the model never sees.* Return `{"error": ...}`; the loop also catches a crash inside a tool and records it on the span (`tool_exception`), so one bad tool cannot end an arm.

**Cash:** $0; the capture was a build cost of week-4-start. **Reference:** `git show week-4-end:tests/test_tools.py`.

---

## 3. The loop, its cap and the budget (2 h, $0)

**Goal:** `analyze.analyze_with_tools`, the `mode = "tools"` branch of `experiment.run_arms`, and `evals.GRADERS["tool_calls_ok"]`, making 13 more cases pass.

An **agent loop** lets the model decide the next step: call, run its tool requests, call again, until a reply asks for nothing. A **workflow** fixes the steps in code. Anthropic's advice is to prefer the workflow until the loop earns its cost ([*Building effective agents*](https://www.anthropic.com/engineering/building-effective-agents)); §4 measures exactly that. The contract:

```python
analyze.analyze_with_tools(ctx, provider, *, model, prompt_version, max_turns) -> Sample
    # one ModelSpan per call, one ToolSpan per tool call, the trial span; hitting the cap is outcome="failed", not an exception
evals.GRADERS["tool_calls_ok"]   # code grader with max_calls; reasons tool_error, repeated_call, too_many_calls
```

Build it in this order (the reference is `git diff week-4-start week-4-end -- src/tradingresearch/`):
1. `tools_prompt(ctx)`: the user turn names only the ticker and session and says the SOURCES table is not included, so every number cited came through a tool.
2. The loop: call with `tools=TOOLS`; for each `tool_call` append the assistant turn, run the tool, append a `tool` turn with its `tool_call_id`; stop at the first reply with no tool calls and parse it. `MAX_TOOL_TURNS = 5` model calls per item: up to 4 rounds of tools, then the answer. If the fifth reply still asks for tools, the sample fails with `CallError(code="max_tool_turns")` and no sixth call is made. A `ProviderError` fails the sample the way gigai-core `run` does; `BudgetExceeded` propagates.
3. `run_tools`: gigai-core `run` asks once per item, so the tools arm runs its own loop and builds the same `Run`: one trace file, a `RunRecord`, code graders on each succeeded sample. The budget is planned on every item's first request before any call; every later call is reserved through gigai-core `budgeted`. A model grader on a tools arm is refused before the first call.
4. `ToolCallsOk`: 0 with the first fault (`tool_error`, `repeated_call` with arguments compared after `sort_keys`, `too_many_calls`), else 1. `max_calls = 2 × len(TOOLS) = 6`: every tool once plus one follow-up each.

The retries under all of this shipped in week 3, not here. The plan puts "retries with exponential backoff and jitter" in week 4; the repo shipped them in `week-3-start` (`retry.py`, Alpaca, EDGAR and OpenRouter alike). Full **jitter** is a random wait before each retry, so clients that failed together do not retry together ([AWS Builders' Library](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/)). A retried call stays one `ModelCall`, so a loop turn that retried is still one turn against `MAX_TOOL_TURNS`.

Before the paid run, the reference's plan check on the config: the worst case of one first call is $0.040692, so 20 items plan at $0.81, under the $1.00 cap per arm.

**Done when**
- The 5 loop cases, 2 tools-arm cases and 6 grader cases in `tests/test_week4.py` pass, among them a model that never stops getting exactly `max_turns` calls and a failed sample.
- `uv run pytest tests/test_week4.py tests/test_tools.py tests/test_route.py -q` at the reference: 67 passed.

**Traps (real)** (from a review of the reference code)
- *A failed item is never graded.* `run_tools` grades only `outcome == "succeeded"` samples (`experiment.py:169`), so a loop that hit the cap vanishes from every metric, the `parsed` guard included. The guard cannot see the failure it exists to catch; ADR-005 lists it under Gaps.
- *A budget refusal mid-arm drops the whole arm.* The plan covers only each item's first call. The review reproduced it at a $0.042 cap: `BudgetExceeded $0.040740 does not fit the remaining $0.038054 of max_usd=0.042`. `tr exp run` ends, the arm has no results, and its trace has no trial span for the item it stopped in.
- *The plan undercounts.* The estimate ignores the tool schemas: about 350 estimated input tokens for a first call the real capture billed at 1,593.
- *`tool_calls_ok` is 1.0 with no tool calls*, by design, so `compare` keeps the grader when the fixed arm has none. On the fixed arm it is constant 1.0 and its McNemar row means nothing. `""` and `"{}"` are the same request but not detected as a repeat.
- *Same hash, different input.* A tools analysis and a fixed analysis of one ticker-day share an `input_hash`, though one model saw a table and the other asked.

**Cash:** $0. **Reference:** `git show week-4-end:src/tradingresearch/analyze.py`.

---

## 4. The experiment: tools vs fixed, ADR-005 (2 h, $0.88 at the author's run)

**Goal:** `experiments/tools-vs-fixed.toml`, one paid run, and `docs/adr/ADR-005-tools-vs-fixed-context.md` deciding from its pre-registered metrics.

The config differs between arms only in `mode` (the reference, condensed; its header comment is the pre-registration: primary metric `all_claims_valid`, guard `parsed` must not drop):

```toml
name = "tools-vs-fixed"
model = "anthropic/claude-sonnet-5.5"
max_usd_per_arm = 1.00
tickers = ["AAPL", "MSFT", "NVDA", "AMZN", "JPM", "XOM", "UNH", "HD", "KO", "CAT"]
sessions = ["2026-11-12", "2026-11-13"]
graders = ["parsed", "claims_valid", "all_claims_valid", "inferences_grounded", "tool_calls_ok"]
# then two [[arms]] tables, both prompt = "analyze-1": name = "fixed" with mode = "fixed", name = "tools" with mode = "tools"
```

`tr exp run` has no dry run, so check the config is what you mean before paying (the runbook gives a one-line `experiment.load` print). Items are paired by ticker-day and clustered by ticker: 20 items, 10 clusters. A binary metric on paired items is compared with **McNemar's test**, which looks only at the pairs where the two arms disagree ([Wikipedia](https://en.wikipedia.org/wiki/McNemar%27s_test)); the interval is week 3's cluster bootstrap. The author's run, 2026-11-17, rc 0, 394 s:

```text
$ TR_DATA_DIR=$PWD/data-dev uv run tr exp run experiments/tools-vs-fixed.toml
experiment tools-vs-fixed: 20 ticker-days x 2 arm(s), graders parsed, claims_valid, all_claims_valid, inferences_grounded, tool_calls_ok, cap $1.00/arm
arm fixed      prompt=analyze-1 run=run_a24247c2a8b54462 spent=$0.3394 failed=0 analyses=20
    all_claims_valid=0.100 (n=20)  claims_valid=0.798 (n=20)  inferences_grounded=0.200 (n=20)  parsed=1.000 (n=20)  tool_calls_ok=1.000 (n=20)
arm tools      prompt=analyze-1 run=run_e80dcfcca6294408 spent=$0.5386 failed=0 analyses=20
    all_claims_valid=0.100 (n=20)  claims_valid=0.798 (n=20)  inferences_grounded=0.250 (n=20)  parsed=1.000 (n=20)  tool_calls_ok=1.000 (n=20)
compare fixed -> tools: 20 items, 10 clusters
    parsed             1.000 -> 1.000  diff +0.000  CI [+0.000, +0.000] (95%)  mcnemar p=1  mde=-
    claims_valid       0.798 -> 0.798  diff -0.000  CI [-0.083, +0.086] (95%)  wilcoxon p=0.739  mde=0.124
    all_claims_valid   0.100 -> 0.100  diff +0.000  CI [-0.200, +0.200] (95%)  mcnemar p=1  mde=-
    inferences_grounded 0.200 -> 0.250  diff +0.050  CI [-0.200, +0.250] (95%)  mcnemar p=1  mde=-
    tool_calls_ok      1.000 -> 1.000  diff +0.000  CI [+0.000, +0.000] (95%)  mcnemar p=1  mde=-
```

Cost, tokens and latency come from `tr usage` and the traces (ADR-005, means per ticker-day, n = 20 per arm):

| | fixed | tools |
|---|---|---|
| tokens in / out, mean | 2,537.7 / 1,189.25 | 7,054.1 / 1,282.35 |
| cost, mean (arm total) | $0.016968 ($0.339358) | $0.026932 ($0.538634) |
| latency, mean | 8,344.5 ms | 10,929.15 ms |
| model calls / tool calls, mean | 1 / 0 | 2.05 / 3.05 |

What the tools arm did, from its trace: in 19 of 20 items the model made one round calling all three tools with `{}` (every row), then answered. AAPL:2026-11-12 made a second round, `get_indicators {"names": ["close"]}`. No tool erred, none repeated, no item made zero tool calls, none used more than 3 of its 5 model calls. Input is 2.78 times the fixed arm's because every call re-sends the conversation. The key moved $62.028863 → $62.906855 across the run, $0.877992, equal to the trace total.

ADR-005's decision: no difference at n = 20. The primary metric moved +0.000 (interval −0.200 to +0.200, McNemar p = 1) and the guard held, so tools mode is not adopted. `tr analyze` and `tr daily` keep the fixed context, and `mode = "tools"` stays an experiment arm. Cost and latency were not pre-registered; they point the same way (1.59 times the cost, 1.31 times the latency).

What it cannot say: "no difference" means none was seen, not that none exists. Twenty items in ten clusters see only a large effect, and `compare` prints no MDE for McNemar metrics. The model fetched every row in 19 of 20 items, so the run tested the same rows in a second turn, not selective retrieval. [INFERENCE, ADR-005] With a 2,538-token context, asking saves nothing; a larger context is where the modes could differ.

The finding to carry forward is not about tools. `all_claims_valid` is 0.10 in *both* arms while `claims_valid` is 0.80: on average about four claims in five pass, but only 2 of 20 analyses pass whole. That is the lead for week 5's error analysis, not a result about tool use.

**Done when**
- `uv run pytest tests/test_week4.py -k "experiment or adr_005" -q` passes (2 cases): two arms that differ only in `mode`, and an ADR whose table cells are numbers with a run id or say "awaiting", stating the pre-registration, the result with its interval, the decision and its gaps.

**Traps (real)**
- *Run once.* The whole cost of the week is this run; a rerun to "check" pays again. Write the ADR from the run files and `tr usage`.
- *Latency is per call in `tr usage --by arm`.* It prints 5,331 ms for tools; the per-item figure is 5,331.29 × 41 ÷ 20 = 10,929.15 ms. Quote the one you mean.
- *The pre-registration is a comment.* `RunRecord.prereg` is `None` for both arms; nothing but the commit date shows the TOML predates the run.
- *Hypothetical savings are arithmetic.* ADR-005's $0.09964 per `tr daily` (10 × the mean difference) is labelled [INFERENCE], not measured.

**Cash:** the author's run, $0.877992 ($0.339358 fixed, $0.538634 tools). **Reference:** `git show week-4-end:docs/adr/ADR-005-tools-vs-fixed-context.md`.

---

## 5. The route bug the recorded exchange found (0.5 h, $0)

**Goal:** know why `provider_route` reads `openrouter:mixed(...)` for most tool loops, and why a trainable record refuses it.

**Done when**
- `uv run pytest tests/test_route.py -q` passes at the reference, and you can say which route a two-provider loop records.

**Traps (real)**
- *Keyed by the last turn, shared across arms.* The route used to be keyed by the last turn's content, so in a tool loop every turn after the first was keyed by tool text and dropped, and one `routed()` dict was shared between arms. Commit `235fd20` keys every call by the exchange's first user turn, gives each arm its own log, and records `openrouter:mixed(Azure+Google)` (sorted) or `openrouter:unknown`; `records.clean_route` refuses a mixed, unknown or empty route on a trainable record, so a tools teacher arm needs a provider pin. The route is per exchange, not per turn inside the trace; a per-turn route would need a gigai-core span field that does not exist.
- *One loop, several providers.* The recorded exchange went Azure then Google (§2); that exposed the bug, and `235fd20` landed before the paid run. The run then measured it: 12 of the 20 tools items were mixed (4 Anthropic+Azure, 4 Anthropic+Google, 4 Azure+Google); the fixed arm, one call per item, had none.
- *Two holes the review found.* Commit `2ed97a9` closed them: a `"provider": null` reply produced `openrouter:None`, which passed (now `unknown`), and the check was case-sensitive (`openrouter:Unknown` passed).

**Cash:** $0. **Reference:** `git show 235fd20 -- src/tradingresearch/openrouter.py`.

---

## 6. Champion/challenger: the first rule change (1.5 h, $0 now)

**Goal:** `experiments/rule-change-1.toml` and one `rules.CHALLENGER_RULES` entry, pre-registered and stored before any session it covers, making the last 2 cases pass.

**Champion/challenger** runs the current rules (champion) and one changed rule (challenger) side by side on the same inputs, and adopts the change only if it wins by a rule fixed in advance, as in an A/B test ([Wikipedia, *A/B testing*](https://en.wikipedia.org/wiki/A/B_testing)). Here the challenger answers each analysis the champion decided on, right after it, in the same `tr daily` run. One change may be pending at a time.

The reference change (`git show week-4-end:experiments/rule-change-1.toml`, condensed):

```toml
change_id = "rc_1"
description = "drop short-horizon theses against the 50-session trend (long below sma_50, short above)"
diff_ref = "short-sma50-trend"
decided = "pending"
[prereg]
primary_metric = "session_r_net_delta:short"
pass_rule = "delta_ci_lower > 0"
guard_metric = "p1_met_rate"
margin = 0.10
n_planned = 20
registered_at = 2026-11-17T07:08:00Z
```

`short-sma50-trend` is a `Filter` (`rules.short_with_sma50_trend`): the challenger writes its own thesis, then drops a short-horizon long when `dist_sma_50_atr < 0` and a short when it is above 0; a missing value (fewer than 50 bars) is dropped too. Other horizons pass untouched. The store refuses a `diff_ref` that is not a `CHALLENGER_RULES` key (the two `example-` entries are examples, not proposals), a Prereg that is not the §8.2 one, a second pending change, and a `registered_at` at or after the first challenger thesis. Commit the file first, then store it once with `rules.register(conn, RuleChange.model_validate(tomllib.loads(text)))`.

The author did both on 2026-11-17: the pin moved to `week-4-end` (§1), then `rc_1` was registered in the live journal before the 2026-11-17 session opened. The first covered session is 2026-11-17. Read back on the live journal, 2026-11-17 02:30 ET:

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

A pair is one session on the change's horizon: summed r_net per arm, 0 with no trade. Pairs stop at the first session with a short thesis not yet graded, expired or cancelled, so a pair counts only once both arms' theses are closed. The dates come from `uv run tr sessions --session 2026-12-23 --count 27` and the short horizon (entry window the next session, hold 2-5 sessions after the fill).

> **Awaiting sessions 1-20: the challenger's pairs and the week-9 decision**
> Filled in when the data exists; nothing here is an estimate of the result.
> - Shows: paired sessions so far, the challenger-minus-champion session r_net with its interval, the P1 met-rate guard, then `adopted`, `rejected` or `insufficient` for `rc_1`; and the challenger's own spend per evening, from the `challenger rc_1 (short-sma50-trend) <session>` line of each `tr daily` run.
> - Command: `uv run tr learn --status` (each evening); `uv run tr usage --by day`; at 20 pairs, `uv run tr learn --decide rc_1` from the pinned code.
> - Earliest: the first challenger theses after the 2026-11-17 close; the bootstrap prints from 10 pairs (the 10th session is 2026-12-01; its pair counts once its theses close). Session 20 is 2026-12-15; its short theses enter 2026-12-16 and a full 5-session hold ends 2026-12-23, so the decision is due between 2026-12-16 and 2026-12-23 if no session is left out, and by day 60 (2027-01-15) at the latest.

**Done when**
- The 2 rule-change cases pass: the TOML is the §8.2 Prereg, names a real `CHALLENGER_RULES` entry, and registers in a scratch journal.
- `tr learn --status` on your journal shows the change pending, with its first covered session.

**Traps (real)**
- *Register only after the pin moves.* The pinned code writes the challenger's theses; code without the arm never answers, and once the next entry window opens those sessions are left out for good (`left out N, the challenger never answered: <dates>`).
- *Twenty pairs see only a large effect.* At n = 20 the detectable delta is 0.63 R at an assumed σ of 1.0 R. A "rejected" or "insufficient" is the likely honest outcome, and the write-up must say so with its interval.
- *Prereg fields never change.* Triggers refuse an update; a second idea waits for the first decision.
- *The challenger costs a thesis call per champion decision.* The plan's figure is "≈ $0.31 per session", an estimate; the Awaiting block above measures it.

**Cash:** $0 to register; the challenger's calls run inside each live `tr daily` and its `--max-usd`. **Reference:** `git show week-4-end:src/tradingresearch/rules.py`.

---

## 7. κ and the judge on live trades (0.5 h, $0 now)

**Goal:** know when the planned "κ on 30 labels" can start, and what the first live judge call will cost.

**Cohen's κ** is agreement between two raters beyond chance: 1 is perfect, 0 is chance ([Wikipedia](https://en.wikipedia.org/wiki/Cohen%27s_kappa)); here the raters are you and the P1 judge. The plan wants κ on 30 blind labels this week, stored as a `JudgeValidationRecord`. No trade has closed, so there is nothing to label or judge. On the author's live journal, 2026-11-17 02:30 ET:

```text
$ uv run tr label list
nothing to label: no graded champion or challenger thesis without a label (0 labelled)
$ uv run tr grade --judge --dry-run
grade 2026-11-16 (dry run): would grade 0, would create 0 shadow(s), 6 waiting; nothing written
judge: nothing to judge (no graded champion or challenger thesis without a verdict)
```

The six waiting theses are week 2's pre-live ones, all `PROPOSED: not filled yet`. When trades close is week 3 §7's table: the pre-live six can close from 2026-11-17, the first live theses enter from 2026-11-18, and the day, short and swing holds are 0, 2-5 and 5-20 sessions after the fill.

> **Awaiting sessions 1-N: κ on closed trades (N = the session with at least 2 label–verdict pairs; 30 labels planned)**
> Filled in when the data exists; nothing here is an estimate of the result.
> - Shows: your blind labels against the judge's verdicts, κ with its interval and n, reported as descriptive.
> - Command: `uv run tr label list`, `uv run tr label show <id>`, `uv run tr label add <id> met|not_met|unknown`, then `uv run tr label agree`; dates from `uv run tr sessions --session 2026-12-03 --count 13`.
> - Earliest: one label from the first graded thesis, 2026-11-17 at the earliest; κ needs two judged and labelled theses, and the planned 30 need 30 graded trades.

> **Awaiting sessions 1-N: the first live `tr grade --judge` spend (N = the first evening a graded thesis is judged)**
> Filled in when the data exists; nothing here is an estimate of the result.
> - Shows: the cost per judged trade on a real summary, against the one synthetic $0.005163 of week 3.
> - Command: `uv run tr grade --judge`, then `uv run tr usage --by call`.
> - Earliest: the evening the first champion thesis is graded, 2026-11-17 at the earliest.

**Done when**
- You can say which thesis `tr label list` will offer first, and that every κ is printed with its n.

**Traps (real)**
- *Who writes the live rows (ruling of 2026-11-17, now in the runbook, rule 2).* The LaunchAgent writes the daily rows. Two further live writes are sanctioned and logged, run from the pinned worktree with `TR_DATA_DIR=<repo>/data`: registering a rule change, once, and `tr grade --judge`, with its spend. **`tr label add` is human only**: your labels are the ground truth κ measures the judge against, and a label written by a model or a worker would make κ model against model, which means nothing. `tr learn --decide` runs only after your go, because the decision is an ADR at `n_planned`. Everything else a worker does goes to `data-dev`. In the pinned worktree `tr label list` works today and prints "nothing to label" until the first thesis is graded; `tr label show` prints the thesis, its claims and the post-trade summary and never a judge verdict or an earlier label (tested in `tests/test_label.py`).
- *The reference labels in this repo are not κ labels.* `evals/labels.csv` (week 1) is a reference answer to the open-coding exercise, written by the author's worker as an answer key; no label of the P1 kind exists anywhere yet (live journal 0 labels, 0 judge verdicts, read on 2026-11-17). Do not validate the judge against it.
- *Thirty labels still decide little.* ADR-003 puts κ's 95% half-width near ±0.29 at 30 labels, and gigai-core's gate needs 126; the judge stays "descriptive, not validated".

**Cash:** $0 now; each judged trade costs about what week 3 §4 measured. **Reference:** `uv run tr label --help`.

---

## 8. Optional: an MCP server over the journal and ADR-006 (stretch, $0)

**Goal:** if you have time, a read-only MCP server over the journal and ADR-006 on MCP vs in-process tools. Nothing here is in the repo, and nothing here was built or tested by the author.

**MCP** (Model Context Protocol) is an open protocol for serving tools and data to any model client over one interface, instead of wiring tools into each app ([modelcontextprotocol.io](https://modelcontextprotocol.io/)). The plan sketches the step: a read-only server over open trades, scorecards and the playbook, and a Python client contract test in CI that lists the tools, validates their input schemas with `jsonschema` and calls one end to end. The plan marks it optional.

**Done when** (if you build it)
- The contract test runs in `ci/gate.py` with no network and no key, and the server cannot write the journal.

**Traps (real)**
- *The ADR numbers moved.* The plan numbered the tools ADR "ADR-003" and the MCP one "ADR-004"; in the repo ADR-003 is the judge and ADR-004 the trace policy, so tools is ADR-005 and MCP would be ADR-006.
- *A server is another writer.* Open the journal read-only (`mode=ro`); a dev process opening it with newer code adds empty tables (runbook, "Pinned code, live data").

**Cash:** $0. **Reference:** none; there is no reference answer.

---

## 9. ADR-005 in review, and what week 5 does with it (0.5 h, $0)

**Goal:** know what ADR-005 settles, what it leaves open, and which week-4 pieces week 5 builds on.

ADR-005 settles one thing: on this context, this prompt and this model, tools mode is not worth 1.59 times the cost. It leaves open whether tools help on a larger context, and how a run with failed items is read (its Gaps). Week 5 is context engineering: what goes into the prompt, including the headlines the measured prompt still lacks (week 3 §6), tested by dropping one source at a time against the full context and feeding ADR-007 and ADR-008 (about $1-2, an estimate). Its error analysis starts from §4's gap between `claims_valid` 0.80 and `all_claims_valid` 0.10. The challenger collects pairs every evening meanwhile, untouched until week 9.

**Done when**
- You can say what week 5 needs from this week: the fixed context kept, the tools arm available for a larger context, the 2-of-20 whole-analysis pass rate to explain, and `rc_1` left alone.

**Traps (real)**
- *Reporting before the data.* Three numbers in this chapter wait on sessions. Each sits in an Awaiting block with its command and earliest date, and none is filled with a guess.

**Cash:** $0. **Reference:** [week-5.md](week-5.md).

---

## Week 4 cash, as measured by the author

| Step | Spent | Source |
|---|---|---|
| Building `week-4-start` (all paid calls, key $62.005975 → $62.028863) | $0.022888 | the OpenRouter key |
| of which: the recorded tool exchange, turn 1 + turn 2 (a first try with `tool_choice: "required"` got HTTP 400 at $0) | $0.003946 + $0.018942 | `gen-1794898101-...`, `gen-1794898105-...` |
| Week-4 reference code, route fix, rule change, ADR-005, registering `rc_1` in the live journal | $0 | no model call |
| The tools-vs-fixed run (key $62.028863 → $62.906855) | $0.877992 | `run_a24247c2a8b54462` $0.339358, `run_e80dcfcca6294408` $0.538634 |
| Week 4 total (key $62.005975 → $62.906855) | $0.900880 | the key: $62.005975 at 01:33 ET (week 3 §6), $62.906855 by `tr usage` at 02:30 ET, both 2026-11-17 |
| Challenger and champion arms, live sessions from 2026-11-17 | awaiting | §6 |
| First live `tr grade --judge` | awaiting | §7 |

## Week 4 is done when

- `uv run pytest -q` is green (566 passed, 1 skipped, 2 deselected at the reference) and `ci/gate.py` says `gate: ok`.
- The tools return every mistake as `{"error": ...}`, and the loop stops at a final reply or at `MAX_TOOL_TURNS` with a failed sample.
- One paid run compared tools with fixed context on the same items, and ADR-005 decides from the pre-registered metric with its interval and gaps.
- `rc_1` (or your change) is committed, pre-registered and stored before the first session it covers, from pinned code that has the challenger arm.
- The three Awaiting blocks name the command and the earliest date that will fill them.
- `git tag week-4-end` on your commit.

Nothing in this chapter reports a result that has not happened. The first challenger session closes on 2026-11-17, and its numbers go into the Awaiting blocks above as they arrive.
