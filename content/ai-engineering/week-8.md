# Week 8: routing, caching and cost

**What you learn:** how to cut the cost of a pipeline without fooling yourself: a route knob that puts a cheaper model on one step with a fallback, prompt caching with its write premium, a cost table with cost per item and p50/p95 latency, a batch mode for the judge, and a pre-registered run whose pass you learn to read as a pass and not a proof.

> *"Educational software. Not investment advice. No orders are placed; trades are hypothetical and settled from historical bars by written rules. Past results, including these, do not predict future results."*

**Code:** start [`week-8-start`](https://github.com/karthik446/tradingresearch/tree/week-8-start) · reference answer [`week-8-end`](https://github.com/karthik446/tradingresearch/tree/week-8-end) · [the chapter diff](https://github.com/karthik446/tradingresearch/compare/week-8-start...week-8-end) (repo: [karthik446/tradingresearch](https://github.com/karthik446/tradingresearch)).

**You start at** `week-8-start`: week-7-end, plus the plumbing for this week. That means a `route` arm knob that puts a different model on the analyze or thesis step, a Haiku 5.5 price row, a fallback model for retryable failures, a `cache` arm knob for Anthropic prompt caching, a cost table (`tr usage --by step|model`) with cost per item and p50/p95 latency, a batch mode for the P1 judge (`tr grade --judge --batch` and `--collect`, tested on fake HTTP only), and a plan pre-flight in `tr exp run` that refuses a cap before the first call. `tests/test_week8.py` fails by design (6 of its 21 cases).
**You end at** `week-8-end`: `experiments/routing.toml` with three pipeline arms, and ADR-011 with its pre-registration committed before the paid run, then the result of one run: **the registered rule passes, but the evidence is too noisy to call it a proof**, so the live loop stays on Sonnet 5.5 (§9). The reference answers are at the tag `week-8-end` (`cc2ead9`).
**Cash:** the code costs $0. The tests use fake providers and fake HTTP, and the cap probe stops before any call. The one paid step is the three-arm run on Anthropic's API: $5.6118 (§9). **Time:** about 12 hours, the sum of the section guides below.

Week 7 ended with a cost table: an injected item cost about $0.043 against about $0.038 clean, and every item made two Sonnet 5.5 calls. Week 8 asks the plain serving question: can the cheaper of those two calls go to a cheaper model without losing quality, and what does a prompt cache save? You answer it the way week 7 taught: write the rule first, commit it, then pay for one run and read the result under the rule you wrote. Each new concept gets one or two lines and a link where it is first used.

This chapter was checked on 2026-11-17 (America/Phoenix) at `week-8-end` (`cc2ead9`). Both week-8 tags are annotated tags in the author's checkout; this check made no network call, so it did not ask origin whether they are pushed. The live worktree is still pinned at `830d0ef` (§10). The paid experiment is done, and its result is in §9.

## Where everything is

- **The shipped plumbing.** `git diff week-7-end week-8-start --stat`: 24 files, 2,557 insertions, 109 deletions, in ten commits. Two of them close week 7 (`f248d12` the runbook line that called the week-7 run "not yet run", `78a12fd` COST-4: a billed empty OpenRouter reply keeps its cost). The other eight are this week: `e4273d7` G15a, `0ce0c09` G15b, `cab15b3` G15c, `3a61de3` G15d, `dd0bddd` COST3a, `9c9a32c` G15e, then two fix rounds after an independent review, `7c91535` W8Fix-B and `5d72c01` W8Fix-A.
- **The reference.** `git diff week-8-start week-8-end --stat`: 5 files, 222 insertions, in two commits (`3792699` the pre-registration and the config, `cc2ead9` the result).

| What | Path | Tag | See it |
|---|---|---|---|
| The `route` knob, `Route`, `experiment.models`, the arm header line (§2) | `src/tradingresearch/experiment.py`, `commands/exp.py` | week-8-start (commit `e4273d7`) | `git show week-8-start:src/tradingresearch/experiment.py` |
| The fallback wrapper (§2) | `src/tradingresearch/providers/__init__.py` (`Fallback`, `with_fallback`), `tests/test_fallback.py` | week-8-start (commit `e4273d7`) | `git show week-8-start:tests/test_fallback.py` |
| The Haiku 5.5 price row and the cache-write rates (§2, §3) | `src/tradingresearch/providers/anthropic.py` (`PRICES`, `CACHE_WRITE`, `cached`) | week-8-start (commits `e4273d7`, `0ce0c09`) | `git show week-8-start:src/tradingresearch/providers/anthropic.py` |
| The cache knob's golden request bodies (§3) | `tests/test_provider_anthropic.py` | week-8-start (commit `0ce0c09`) | `git show week-8-start:tests/test_provider_anthropic.py` |
| The cost table: `tr usage --by step\|model` (§4) | `src/tradingresearch/usage.py`, `trace.py`, `commands/usage.py`, `tests/test_usage.py` | week-8-start (commit `cab15b3`) | `git show week-8-start:src/tradingresearch/usage.py` |
| The batch judge (§5) | `src/tradingresearch/commands/grade.py`, `providers/openrouter.py` (`submit_batch`, `get_batch`), `evals.py` (`judge_item`, `judge_run`), `tests/test_batch.py` | week-8-start (commits `3a61de3`, `7c91535`) | `git show week-8-start:tests/test_batch.py` |
| Background on both providers and the batch | `docs/providers.md` | week-8-start | `git show week-8-start:docs/providers.md` |
| The plan pre-flight and the thesis-refusal exit (§6) | `src/tradingresearch/experiment.py` (`stage`, `plan`, `Worst`, `OverCap`, `ThesisRefused`), `tests/test_preflight.py` | week-8-start (commits `dd0bddd`, `5d72c01`) | `git show week-8-start:tests/test_preflight.py` |
| Week-8 contract | `tests/test_week8.py` | week-8-start (commit `9c9a32c`) | `uv run pytest tests/test_week8.py -q` |
| Runbook: Providers, the plan pre-flight, Week 8, the week-8 contract | `docs/runbook.md` | week-8-start | `git show week-8-start:docs/runbook.md` |
| The experiment config (§7) | `experiments/routing.toml` | week-8-end (commit `3792699`) | `git show week-8-end:experiments/routing.toml` |
| ADR-011: pre-registration, then the result (§8, §9) | `docs/adr/ADR-011-model-routing.md` | week-8-end (commits `3792699` pre-registration, `cc2ead9` result) | `git show week-8-end:docs/adr/ADR-011-model-routing.md` |
| The measured cost of the run (§9) | `docs/measured-costs.md` ("Week 8: routing and caching") | week-8-end (commit `cc2ead9`) | `git show week-8-end:docs/measured-costs.md` |

The `week-8-end` files are the reference answers: write yours first, then compare. This week the reference holds a number you should not see early: the result. If you read ADR-011's Result before you write your own pre-registration, your margin and your item count are no longer chosen blind.

The split follows the usual rule: shipped = plumbing, learner-written = the lesson. You read the knobs, the cost table, the batch judge and the pre-flight (§2 to §6). You write the experiment and the rule that judges it, commit both, then run it and read it (§7 to §9).

---

## 1. Setup and a tour of the shipped code (1 h, $0)

**Goal:** the week-8-start repo runs on your machine, you know which 6 tests are yours, and you have a plan for days 50 to 56.

Do [SETUP.md](SETUP.md) first if you have not. `tr` reads the repo's `.env` by itself at this tag, and `TR_PROVIDER` chooses Anthropic or OpenRouter for the analyze, thesis and experiment calls; the batch judge (§5) is OpenRouter whatever the provider:

```bash
cd tradingresearch && git checkout week-8-start
uv sync
uv run pytest tests/test_week8.py -q   # 6 failed, 15 passed
uv run pytest -q                       # 1293 passed, 7 failed, 3 skipped, 2 deselected
uv run python ci/gate.py               # gate: ok (90 reconcile cases at rules-1, 5 prompts)
```

The author ran these on a `git archive` copy of `week-8-start`, with the repo's existing virtualenv and the copy's `src` first on `PYTHONPATH` (week 7, §1, explains why the path matters), and got exactly those lines. Of the 7 failures in the full suite, 6 are `tests/test_week8.py`. The 7th is week 6's `test_every_gold_quote_resolves_in_the_local_index`: a fresh copy has no retrieval index, so it fails by design (week 6, §1). The gate still hashes 5 prompts, because week 8 adds no prompt.

Every one of the 6 failures says `learner part missing: <what> (contract in tests/test_week8.py)`. Each is one test:

| Test | Missing at week-8-start | You write |
|---|---|---|
| `test_the_routing_experiment_has_baseline_routed_and_cached_arms` | `experiments/routing.toml`: a baseline, a routed and a cached pipeline arm, at least 10 tickers, the same prompts, `all_claims_valid` among the graders | the config (§7) |
| `test_every_routing_model_has_an_anthropic_price` | the same file; then every model it may ask (`experiment.models`) must have a row in `anthropic.prices` | the config (§7) |
| `test_adr_011_records_the_options_the_decision_and_the_readings` | `docs/adr/ADR-011-<slug>.md`: Status, at least two options, Decision, Consequences, Readings with a link, and the name `routing.toml` | ADR-011 (§8) |
| `test_adr_011_preregisters_the_rule` | a `**Pre-registration...**` paragraph before `**Decision.**` naming `all_claims_valid`, `NoWorseThan`, the margin, the item count and the cap | ADR-011 (§8) |
| `test_adr_011_has_the_routing_comparison_table` | one column per arm; rows `all_claims_valid`, `$ per ticker-day`, `p50`, `p95`, `thesis changed`; cells `awaiting experiment` or plain numbers, with run ids beside the table | ADR-011 (§8, §9) |
| `test_adr_011_has_the_judge_sync_vs_batch_table` | `sync` and `batch` columns; rows `cost per call`, `turnaround`, `cost per day at 10x shortlist`; cells `awaiting run` or numbers | ADR-011 (§8) |

The 15 tests that pass from the start run the same checks on a small example config and ADR inside the test file. They need no learner file, so no check passes on nothing.

**What the tests check, and what they leave to you.** The tests check shapes: the arms exist and differ in the one way each should, every model has a price, the ADR has its parts, and each table cell is a number or the awaiting text. They cannot check what makes the week worth doing:
- whether your pre-registration was committed before the paid run (the test file's docstring says so: "Code cannot see commit order");
- whether your margin and item count were chosen before you saw a number, and whether your power estimate is honest;
- whether your Result follows your rule, including the part of the rule that says when a pass is not a proof;
- whether a cached arm actually cached anything (a cell can hold a number while the cache wrote 0 tokens).

**The week, day by day.** The schedule gives week 8 seven 2-hour build sessions. This is how the sections map onto days 50 to 56:

| Day | Sections | Leaves you with |
|---|---|---|
| 50 | §1, §2, §3 | the repo running; the route knob, the fallback and the cache knob read, with their limits |
| 51 | §4, §5 | the cost table read on your own data-dev runs; the batch judge read, and why it stays unmeasured |
| 52 | §6, §7 | the pre-flight understood, including when it refuses a cap your run would fit; `experiments/routing.toml` written; tests 1 and 2 green |
| 53 | §8 | ADR-011's pre-registration written, the cap probe run, both files committed; all 21 tests green |
| 54 | §9, first half | the one paid run, its output saved to a file |
| 55 | §9, second half | the routing table filled, the rule applied by hand, ψ counted, the Result written |
| 56 | §10 | what stays on OpenRouter and what moved to Anthropic, written down; `week-8-end` tagged |

**Done when**
- You can name the six tests and the file each needs.
- You can say which parts of the week no test can check.

**Traps (real)**
- *The gold-quote test is not yours this week.* It needs `uv run tr retrieval build` (week 6, §2). It is the 7th failure on a fresh copy.
- *The suite count is not the week-7 count plus six.* Week 8 ships four new test files (`test_batch.py`, `test_fallback.py`, `test_preflight.py`, `test_week8.py`) and extends four others (`test_experiment.py`, `test_openrouter.py`, `test_provider_anthropic.py`, `test_usage.py`). Compare against the line above, not against week 7's.

**Cash:** $0. **Reference:** `git diff week-7-end week-8-start --stat`; `docs/runbook.md`, "Week 8 contract".

---

## 2. The route knob, the Haiku price and the fallback (1 h, $0, shipped)

**Goal:** know how an arm puts a different model on one step, what a fallback does and does not do, and what it costs if it fires.

**Model routing** sends each request to a model that fits it, often a cheap model where it is good enough and a strong one where it is not. A **cascade** is the ordered form: try the cheap model first, escalate when it fails a check ([Ong et al. 2024, *RouteLLM*](https://arxiv.org/abs/2406.18665); [Chen et al. 2023, *FrugalGPT*](https://arxiv.org/abs/2305.05176)). Week 8 tests the simplest static route: one step always on Haiku 5.5, the other always on Sonnet 5.5. No per-request decision is made.

An arm in an experiment config may now say:

```toml
route = { analyze = "anthropic/claude-haiku-5.5", fallback = "anthropic/claude-sonnet-5.5" }
```

`experiment.Route` holds three keys, `analyze`, `thesis` and `fallback` (`ROUTE_KEYS`). A step you leave out runs on the arm's `model`. `experiment.load` refuses a route on an analyze arm, an unknown key, or a value that is not a model id. `experiment.models(config)` lists every model the config may ask: each arm's `model`, its route's step models and its fallback. Before any call, `tr exp run` checks that every one of them has a price, and prints one line per arm:

```text
    arm routed: analyze anthropic/claude-haiku-5.5  thesis anthropic/claude-sonnet-5.5  fallback anthropic/claude-sonnet-5.5
```

That line is from the author's run (§9, `data-dev/scratch/w8refb-run.txt`). Read it first in any routed run's output: it is the only place the run tells you which model it meant to use on which step.

**The Haiku 5.5 price row.** `providers/anthropic.py` prices `claude-haiku-5-5` per million tokens at $0.10 input, $0.50 output, $0.125 for a 5-minute cache write, $0.20 for a 1-hour cache write and $0.01 for a cache read. The comment says the rates were read from Anthropic's pricing page on 2026-11-17 and hold for prompts up to 100k tokens; above that every category costs 5x and the table does not model it ([Anthropic, *Pricing*](https://platform.claude.com/docs/en/about-claude/pricing)). Sonnet 5.5 in the same table: $2.00 input, $10.00 output. So Haiku is 20x cheaper per token in both directions. At week-8-start no billed Haiku call had been checked against the row (runbook, "Untested against the real endpoints").

**The fallback.** A **fallback model** is a second model you ask when the first one cannot answer, so a provider outage does not stop the run. This one is a client-side fallback the repo builds, for transport errors. `providers.with_fallback(provider, model)` wraps the adapter. It asks the fallback model once, and only after the adapter has spent its own retries on a retryable error: a 429, a 5xx, a connection error or a timeout (`retry.retryable`). The first error is kept as the new one's `__context__`. It never falls back after a refusal, a 401, a billing, credit or spend-limit error, a 400, or a `BudgetExceeded`. A refusal is the model's answer, and a budget stop is yours; this repo routes around neither. Anthropic's own fallback ([Anthropic, *Refusals and fallback*](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback)) does the reverse: it retries only a safety-classifier refusal and returns a rate limit, overload or server error as-is. This repo treats a refusal as the answer it records (week 7).

Three limits of the fallback, all stated in the G15a report and the runbook:
- **The budget reserves at the first model's price.** A routed arm reserves each analyze call at Haiku's rate. If Sonnet answers instead, that call costs up to 20x its reservation (the price ratio above), so a run with many fallbacks can overshoot its cap.
- **`retry_count` counts only the fallback's tries.** The first model's retries are not in the span.
- **A fallback is visible only as `resolved_model`.** The span records the model asked and the model that answered. No `tr usage` view compares the two (§8 shows what that cost the author).

**Done when**
- You can say which of these errors falls back: a 503 after retries, a refusal, a 401, a budget stop.
- You can say why a routed arm with a dearer fallback can spend past its reservation.

**Traps (real)**
- *A test on a fake provider is not a test of the endpoint.* `tests/test_fallback.py` drives a fake provider. At week-8-start the fallback had never run against Anthropic's API, and in the paid run it did not fire once (§9). It is still untested against a real outage.
- *The price row is a claim until a bill confirms it.* Costs on the Anthropic provider are derived from the table (`cost_status = "derived"`), not reported by the API. A wrong row gives a wrong cost with no error.

**Cash:** $0. **Reference:** `git show week-8-start:src/tradingresearch/providers/__init__.py`; `docs/runbook.md`, "Arm knobs: `route` and `cache`".

---

## 3. The cache knob and the cache-write premium (1 h, $0, shipped)

**Goal:** know what the cache knob sends, what a cache write costs, and why the pre-flight treats a cached arm as dearer.

**Prompt caching** lets the provider keep the processed form of a fixed prompt prefix for a few minutes, so a later request with the same prefix reads it at a fraction of the input price. The first request pays a **cache-write premium** above the normal input price: on Anthropic a 5-minute write costs 1.25x input and a 1-hour write 2x ([Anthropic, *Prompt caching*](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)). The repo's price table: Sonnet 5.5 input $2.00, 5-minute write $2.50, 1-hour write $4.00, read $0.10 per million tokens, so a Sonnet read costs 1/20 of input (the pricing page's footnote: 0.05x for Sonnet and Opus 5.5; Haiku's row: 1/10). A prefix under the model's minimum length is not cached at all.

An arm may now say `cache = "5m"` or `cache = "1h"`. On `TR_PROVIDER=anthropic`, `body()` sends the system turns as text blocks with one `cache_control {"type": "ephemeral", "ttl": ...}` breakpoint on the last block. The user turn (the ticker-day's facts and headlines) is never cached, because it changes on every item. With the knob off, the request body is byte-identical to week 7's; golden-body tests in `tests/test_provider_anthropic.py` pin both shapes.

On OpenRouter the knob is refused before any call: `cache '5m' runs on TR_PROVIDER=anthropic only; OpenRouter sends no cache_control`. `cache` is not part of `input_hash`, because it does not change what the model sees.

**What the cache costs before it saves.** `anthropic.CACHE_WRITE = {"5m": 1.25, "1h": 2.0}`. A cached arm's budget reserves and plans its input at the write rate, since any call might be the one that writes. So its pre-flight floor and upper bound are higher than the same arm without a cache, and a cap refuses it sooner (§6). The recorded spend (`spent=`) and each call's `cost_usd` in the trace are exact, writes and reads included. The first draft of the CHANGES entry said the recorded spend was also at the write rate; an independent review found that wrong, and commit `5d72c01` (W8Fix-A) corrected it.

**Will it cache?** Anthropic caches nothing under its minimum prompt length. The runbook's check: if every call of the cached arm shows 0 cache-write tokens in `tr usage --by step`, the prompt was too short to cache. Before the run, ADR-011 estimated the analyze system prompt at about 510 tokens (2,038 characters at 4 characters a token) against a 512-token minimum, and registered "too short to cache" as a possible measured outcome. The week's design note had a second estimate, a regression intercept of 1,386 to 1,847 tokens for the cacheable prefix, and said only the paid run or a `count_tokens` call would settle it. §9 has the answer.

**Done when**
- You can say which part of the request is cached and which never is.
- You can say why a cached arm is refused by a cap sooner than the same arm without the knob, while its recorded spend is lower.

**Traps (real)**
- *A cache cell that holds a number can still mean nothing was cached.* The contract tests cannot see cache tokens. Read the cache-write column on the cached arm's own runs (§4) before you call a saving a cache saving.
- *A wrong claim in the changelog is still a wrong claim.* "Reserves at the write rate" and "records at the write rate" differ by one word. A reader who believed the second would have read the cached arm's spend as too high.

**Cash:** $0. **Reference:** `git show week-8-start:src/tradingresearch/providers/anthropic.py`; `docs/providers.md`.

---

## 4. The cost table: cost per item and p50/p95 (0.75 h, $0, shipped)

**Goal:** read a cost per item and a latency percentile from your own runs, and know when the table mixes arms.

**Cost per item** is what one unit of work costs end to end, here one ticker-day through analyze and thesis. It is the number that scales with the shortlist, so it is the one to compare between designs ([Anthropic, *Pricing*](https://platform.claude.com/docs/en/about-claude/pricing) gives the per-token rates it is built from). **p50 and p95** are the 50th and 95th percentiles of a latency: the time half of the items finish under, and the time all but the slowest 5% finish under ([Wikipedia, *Percentile*](https://en.wikipedia.org/wiki/Percentile)). The mean hides a slow tail; p95 shows it.

`tr usage --by step` and `--by model` print, per row: calls, items (distinct item ids), tokens in (cache included), cache write, cache read (`-` when no call reported them), tokens out, cost, `$/item`, and p50/p95 over items of each item's summed latency in the row, by nearest rank (`usage.nearest_rank`). A step is `analyze`, `thesis`, `judge` or `other`; no call is dropped. Their total uses each run's micro-dollar cost, so it equals the `--by run` total. `--by model` keys on the **requested** model, not the one that answered.

The G15c report shows the view on the author's data-dev at the time: the analyze row held 360 calls over 52 items, $5.763970, $0.110846 per item, p50 40,316 ms. A p50 of 40 seconds for one analyze call looks broken until you see the call count: 360 calls over 52 items is about 7 calls per item, from many runs and arms of the same ticker-days added together.

That is the defect an independent review filed: an item is one ticker-day across every arm and run in the table, so `$/item` and p50/p95 merge them. The fix is in the docs, not the code: for one arm's figures, pass its run id.

```bash
uv run tr usage --by step --run RUN_ID   # the run= id for an arm's analyses, theses= for its theses
```

`tr exp run` prints both ids per arm. `--by arm` gives cost and mean latency per arm, with no per-item columns.

As a worked example, the author recomputed the six runs of the week-8 experiment from their run files with `usage.total` over `trace.calls`, the same code the `--run` view uses, with no network call:

| Run | Step | Calls | Tokens in | Cache write | Cache read | Tokens out | Cost | $/item | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| `sonnet` run_1eba503380b7444c | analyze | 60 | 181,139 | 0 | 0 | 66,809 | $1.030368 | $0.017173 | 7,819 | 9,515 |
| `sonnet` run_b7a046db477e4359 | thesis | 60 | 252,802 | 0 | 0 | 77,266 | $1.278264 | $0.021304 | 10,678 | 13,041 |
| `routed` run_98681aba3fe24a79 | analyze | 60 | 181,139 | 0 | 0 | 135,389 | $0.085808 | $0.001430 | 9,714 | 11,872 |
| `routed` run_80c8bf85db874007 | thesis | 60 | 251,672 | 0 | 0 | 76,252 | $1.265864 | $0.021098 | 10,956 | 14,168 |
| `cached` run_0311bd3c03344a3a | analyze | 60 | 181,139 | 1,216 | 71,744 | 67,243 | $0.899002 | $0.014983 | 7,676 | 11,778 |
| `cached` run_073c4b1e547f4930 | thesis | 60 | 252,296 | 2,112 | 124,608 | 78,360 | $1.052493 | $0.017542 | 10,530 | 13,319 |

Every analyze p50/p95 matches ADR-011's table. Each row is 60 calls over 60 items, which is what one arm's run should look like.

You can check a derived cost by hand. Haiku's analyze run: 181,139 input tokens at $0.10 per million is $0.018114, and 135,389 output tokens at $0.50 is $0.067695, which adds to the $0.085808 above (the two parts are rounded; unrounded they are $0.0181139 and $0.0676945, which sum to $0.0858084). Sonnet's: 181,139 at $2.00 is $0.362278, and 66,809 at $10.00 is $0.668090, which adds to $1.030368. Both match to the micro-dollar, so the table and the trace agree. Neither has been checked against Anthropic's Console bill.

**Done when**
- You can say why a p50 over a whole data dir can be several times one call's latency.
- You have run `tr usage --by step --run` on one of your own runs and matched one cost by hand.

**Traps (real)**
- *A per-item figure over the whole table is a mix.* The G15c demo row is the real case: 360 calls, 52 items, a 40-second p50. Always pass `--run` for one arm.
- *`--by model` is not "who answered".* It keys on the requested model. A routed arm whose fallback fired would still show every call under Haiku.
- *`tr usage` reads the OpenRouter key's lifetime spend after the table.* That is a network read. There is no such line for Anthropic: compare the trace total with the Console.

**Cash:** $0. **Reference:** `git show week-8-start:src/tradingresearch/usage.py`; `docs/runbook.md`, "The cost table: `tr usage --by step|model`".

---

## 5. The batch judge, and why it stays unmeasured (1 h, $0, shipped)

**Goal:** know what a batch API trades, how the batch judge is built, and why its row in ADR-011 still reads `awaiting run`.

A **batch API** takes many requests at once and returns the answers later, often within a day, at a lower price; it suits work nobody waits for ([OpenRouter, *Batch API*](https://openrouter.ai/docs/guides/features/batch-api)). The P1 judge is that kind of work: it grades closed theses after the fact. On OpenRouter `openai/gpt-6-sol:batch` costs $1 input and $5 output per million tokens against $2 and $10 sync (from OpenRouter's public model list, read before the run), so a batch halves the judge's price. The build-guide README's cost plan says the same for week 8: "the judge moves to the half-price `:batch` variant".

The judge is not Claude on purpose. ADR-003 says the judge must be a different vendor from the writer, so a model does not grade its own family's work. That is why the batch goes to OpenRouter and needs `OPENROUTER_API_KEY`, whatever `TR_PROVIDER` the rest of the week uses.

How it is built (commits `3a61de3` G15d, then `7c91535` W8Fix-B):
- `evals.p1_judge` is split into `judge_item` (build one judge request) and `judge_run` (store the answers). A sync call and a batch both go through `judge_run`, so a batch verdict lands in the same run file, spans, score and verdict as a sync one.
- `uv run tr grade --judge --batch` checks the key first and **exits 2** with an empty `OPENROUTER_API_KEY`, before the grade step and before Alpaca. It reads the `:batch` price, reserves each waiting thesis under `--judge-max-usd`, submits one POST `/batches` (never retried, so a timeout cannot submit twice), and writes `<data_dir>/batches/<id>.json`. Each entry's `custom_id` is the thesis id, checked against `[a-zA-Z0-9_-]{1,64}`.
- `uv run tr grade --judge --collect BATCH_ID` polls once. Still running: it prints `still <status>` and exits 0. Failed, expired or cancelled: exit 1, nothing stored. Completed: `providers.BatchReplay` replays each answer with identity `openrouter:batch`, latency 0 and the cost derived at the `:batch` price. If that derived cost differs from the batch's own `usage.cost` by more than $0.001, it prints both and exits 1, verdicts kept. Entries with no `custom_id` are skipped.

**What is not measured.** The batch judge has fake-HTTP tests only (`tests/test_batch.py`). Its turnaround, per-entry usage and real `usage.cost` are unknown, and so is whether OpenRouter lists the `:batch` id in `/models` at the time you run it. ADR-011 excludes the batch run: it needs a funded OpenRouter key and at least 10 graded trades, and at the pre-registration the journal held 1 graded trade and 0 verdicts. So the judge table at `week-8-end` reads `awaiting run` in every cell. Nothing in this chapter tells you what a batch costs or how long it takes.

**Done when**
- You can say why the judge runs on OpenRouter while the experiment runs on Anthropic.
- You can say which exit codes `--collect` returns and what each means.

**Traps (real)**
- *A 50% price cut is a price, not a measurement.* The `:batch` price comes from a price list. The `usage.cost` check exists because the derived cost and the billed cost can disagree, and nobody has seen them side by side yet.
- *A batch submit must not retry.* A retried POST after a timeout can create a second batch that bills twice. The submit is sent once on purpose.

**Cash:** $0. **Reference:** `git show week-8-start:src/tradingresearch/commands/grade.py`; `docs/runbook.md`, "The batch judge"; ADR-003.

---

## 6. The plan pre-flight, and the refusal review found (1 h, $0, shipped)

**Goal:** know what the pre-flight checks, why it can refuse a cap your run would fit, and which exit code means what.

Week 7 paid for a stopped run. The week-7 config at a $1.50 cap sent 50 calls and then stopped, `$1.001580 does not fit the remaining $0.931740` (COST3a, describing the week-7 run; week 7, §8). The pre-flight (COST3a) exists so that a cap too small for the plan stops the run before the first call.

Before any call, `tr exp run` prices each arm's whole plan the way its budgets reserve it (`experiment.stage`, `plan`, `run_staged`):
- **The floor** (`Worst.floor`): every analysis request at its reservation, plus the smallest thesis reservation per item (a thesis built from an analysis with no claims and no cited headline).
- **The upper bound** (`Worst.bound`): every thesis at its longest possible prompt (the item's prompt, plus 4,000 tokens of reply at 4 characters a token, plus a 1,000-character frame).

If any arm's floor is over `max_usd_per_arm`, the run prints the arm, the floor, the cap and the smallest whole-cent cap that clears the check, and **exits 2** with no call made. If only the upper bound is over, it prints a `WARNING arm ...` line and goes on. When the plan fits, the header prints `plan worst case $X per arm (arm A, floor $F), cap $C`.

**The refusal the review found.** The first version called the floor a lower bound on the spend and said so in its message. An independent review showed it is not. The floor counts every analysis at its full reservation. The real run gives its thesis stage the cap minus what the analyses **actually** spent, and real analysis replies are much shorter than their reservations. W7RefB's first arm spent $0.644 on its 30 analyses and then reserved $1.011862 for its theses, so a $1.70 cap would have fitted it. On the fixture version of that shape the floor is $2.249640, so the check named $2.25 and refused every cap from $1.70 up to $2.24.

The fix chosen was to describe it honestly, not to change the check (commit `5d72c01`). The message now reads: "conservative pre-flight $X (analysis reservations + smallest thesis reservations) is over max_usd_per_arm $C; the smallest whole-cent cap that clears this check is $Y. Real spend is lower and the cap is a ceiling: the thesis stage gets the cap minus what the analyses actually spend, so this check can refuse a cap the run would fit (no call made)". The header says `floor`, not "at least". `tests/test_preflight.py::test_the_pre_flight_refuses_a_cap_the_w7refb_run_would_have_fitted` keeps the $1.70 case, so the over-refusal is pinned as known behaviour, not hidden.

**The thesis refusal exit.** A `WARNING` run can still fail late: the analyses spend, then the thesis stage's reservations no longer fit the rest of the cap. Core plans every thesis request before the first thesis call, so the stage is refused whole. An independent review asked for a clean exit for this case. Now `experiment.ThesisRefused` (a `BudgetExceeded`) is caught, `tr exp run` prints one stderr line naming the arm, what its analyses spent and the analysis run id, and **exits 1**.

So `tr exp run` has three outcomes you must tell apart:

| Exit | Meaning | Money spent |
|---|---|---|
| 2 | the pre-flight refused the cap | none |
| 1 | a thesis stage was refused after its analyses ran | the analyses of that arm |
| 0 | every arm ran | the run's spend |

There is no dry run. The pre-flight stops a run that cannot fit, and a run that fits spends.

**Done when**
- You can say why the floor is not a lower bound on the spend, using the W7RefB numbers.
- You can name the exit codes above and say which one costs money.

**Traps (real)**
- *A check named "floor" can still be too high.* The reader caught the word, not a crash. A message that says "at least" when it means "conservatively" sends the learner to raise a cap they did not need to raise.
- *A cap is a ceiling, not a forecast.* §8 shows the cost of reading it the other way: the design note planned the week-8 cap from its forecast and would have been refused.

**Cash:** $0. **Reference:** `git show week-8-start:tests/test_preflight.py`; `docs/runbook.md`, "Experiment cap: the plan pre-flight".

---

## 7. Write `experiments/routing.toml`: three arms, each isolating one thing (1 h, $0)

**Goal:** a config whose arms differ in exactly one way each, and tests 1 and 2 green.

The contract (the docstring of `tests/test_week8.py`, and the runbook's "Week 8 contract") asks for:
- every arm a pipeline arm (`kind = "pipeline"`: analyze, then a thesis in memory, nothing journaled), over at least 10 tickers;
- the first arm is the baseline, and the only arm with no `route` and no `cache`;
- a routed arm: `route.analyze` is not the baseline model, and its thesis runs on the baseline model;
- a cached arm: identical to the baseline except its name and `cache`;
- the same `prompt` and `thesis_prompt` on every arm, and `all_claims_valid` among the graders.

Think about what each pair of arms isolates before you write it:
- **baseline vs routed** changes the analyze model only. The thesis model, the prompts, the items and the graders are the same, so a difference is the analyze model's effect plus noise.
- **baseline vs cached** changes nothing the model sees. A cache changes the price, not the content. So this pair is a **second sample of the baseline**: any difference it shows is noise. That makes it the noise floor for the first pair. This is week 7's clean-rerun lesson, bought here for free with an arm you wanted anyway.

The reference (`git show week-8-end:experiments/routing.toml`) uses model `anthropic/claude-sonnet-5.5`, prompt `analyze-3`, `max_usd_per_arm = 5.50`, the ten tickers of `injection.toml` (AAPL MSFT NVDA AMZN JPM XOM UNH HD KO CAT), six sessions (2026-11-10, 11, 12, 13, 16 and 17), the graders `parsed`, `claims_valid`, `all_claims_valid` and `inferences_grounded`, and three arms:

```toml
[[arms]]
name = "sonnet"
kind = "pipeline"
prompt = "analyze-3"

[[arms]]
name = "routed"
kind = "pipeline"
prompt = "analyze-3"
route = { analyze = "anthropic/claude-haiku-5.5", fallback = "anthropic/claude-sonnet-5.5" }

[[arms]]
name = "cached"
kind = "pipeline"
prompt = "analyze-3"
cache = "5m"
```

Those are the file's arm tables as committed; the top-level keys and a six-line header comment come before them. No arm sets `thesis_prompt`, so all three use the same default and the contract's "same prompts" holds. With the file in place, `uv run pytest tests/test_week8.py -q` turns tests 1 and 2 green. Test 2 checks that `anthropic.prices` knows every model `experiment.models` lists, so a typo in the fallback id fails here, not mid-run.

**Why 5.50.** You cannot pick the cap yet. §8 is where it comes from.

**Done when**
- Tests 1 and 2 pass.
- You can say, for each pair of arms, what one thing differs and what the pair measures.

**Traps (real)**
- *A routed arm that also changes the thesis model measures two things.* Leave `route.thesis` out, or set it to the baseline model. The contract checks this.
- *A cached arm with a different prompt is not a noise floor.* The contract requires identical arms apart from the name and `cache`, for this reason.
- *Fewer sessions than the planning note asked for, silently.* The design note planned "the latest 6 sessions with bars". The reference picks the six latest sessions with stored headlines and says in the ADR that they are the same six. If yours differ, say which rule you used.

**Cash:** $0. **Reference:** `git show week-8-end:experiments/routing.toml`.

---

## 8. Write ADR-011's pre-registration, and commit it before you pay (2 h, $0)

**Goal:** a pre-registration that fixes the metric, the rule, the margin, the item count, the cap and what a pass means, committed before the paid run; all 21 tests green.

**A non-inferiority test** asks whether a new option is "not worse by more than a margin", not whether it is better. You pick the **margin** first: the largest loss you would accept. The new option passes if the lower end of the confidence interval of (new minus old) stays above minus the margin ([Wikipedia, *Equivalence test*](https://en.wikipedia.org/wiki/Equivalence_test), which covers the one-sided non-inferiority case). This is the right shape for routing: you do not expect Haiku to beat Sonnet, you want to know whether it loses enough to matter. The interval matters as much as the point estimate ([Miller 2024, *Adding error bars to evals*](https://arxiv.org/abs/2411.00640)).

The reference rule, from ADR-011's pre-registration: `routed` counts as not worse than `sonnet` if `NoWorseThan("all_claims_valid", margin=0.15, bound="ci_lower")` would pass, that is, the lower 95% bound of routed minus sonnet is at least -0.15. The interval is the seeded paired cluster bootstrap, clustered by ticker (10 clusters). `tr exp run` prints the difference and its CI in `compare sonnet -> routed` but applies no gate and sets no exit code from it, so you compare the bound with -0.15 by hand. If it is below, the result reads "cannot show non-inferior", not "worse".

**Power, and discordant pairs.** With a yes/no metric scored on the same items under two arms, only the items where the arms **disagree** carry information. These are the **discordant pairs**; McNemar's test is built on them ([Wikipedia, *McNemar's test*](https://en.wikipedia.org/wiki/McNemar%27s_test)). **Power** is the chance the test detects a difference that is really there ([Wikipedia, *Power (statistics)*](https://en.wikipedia.org/wiki/Power_(statistics))). For a paired non-inferiority test the items you need grow with the discordant share ψ: the design note gives n = 6.19 ψ / margin², for a true difference of 0, one-sided α 0.05 and power 0.80. Earlier same-model resamples gave discordant shares of 1/10, 1/10, 2/10, 2/20 and 5/20, so it planned ψ at about 0.10 to 0.25. Then 60 items cover ψ up to 0.218 (60 × 0.15² / 6.19), and the formula treats the 60 items as independent, which the 10-ticker bootstrap does not, so the real coverage is lower still. The ADR registers the consequence too: "A different model will disagree with Sonnet more than a resample does. If ψ(routed, sonnet) ... is above 0.22, a failed rule reads as 'cannot show', and a pass with a wide interval is not a proof." That sentence decides how §9 reads.

**The cap: a worked refusal you get for free.** The design note's cost table expected about $5.4 for the whole run (sonnet about $2.28, routed about $1.30, cached about $1.81 to $1.86), and planned a cap of $3.00 per arm. The author probed the config with the cap set to 0.01. The pre-flight refuses before any call, so the probe costs nothing and prints every arm's floor: $4.508856 (sonnet), $2.085773 (routed), $4.586072 (cached) (ADR-011; commit message of `3792699`). A $3.00 cap would have stopped the run with exit 2. The ADR fixes 5.50 and says why, with the upper bound placed about 12% above the floor `[INFERENCE: the week-7 ratio, $2.518230 over $2.249640]`, about $5.05 for sonnet and $5.13 for cached. Week 7 raised its cap after a stopped run (ADR-010 Amendment 1); this ADR fixes the cap before the run for that reason. Do the same probe on your config: it is the cheapest number you will get this week.

**The fallback count: a command that did not exist.** The pre-registration lists the secondary readings, and one is how many routed analyze calls the fallback answered. The author's first draft named `tr usage --by call --run <routed analysis run>`, "served-model column", and noted that the column name was not checked. It does not exist: `--by call` prints one row per call with tokens, cost and latency, keyed on run and item, and no served model; `--by model` keys on the requested model. Before the commit, the text was corrected to the line now in the ADR: "No `tr usage` view shows it ... so it is counted from the arm's analysis run in `traces/`, where each call records the model that answered in `resolved_model`". A pre-registration that names a reading nobody can take is a rule nobody can apply. Check every command you name against `--help` or the code before you commit.

**The rest of the reference pre-registration**, in the order ADR-011 gives it: one run of `TR_PROVIDER=anthropic TR_DATA_DIR=$PWD/data-dev uv run tr exp run experiments/routing.toml`; the three arms; 10 tickers x 6 sessions = 60 items per arm; the four graders; the primary metric and the rule; that a pass is a recommendation only and the live loop is not routed in week 8; power; the secondary readings (drift, $ per ticker-day, p50/p95 on the analysis run, cache tokens on both cached runs, the fallback count); the exclusions (P1 vs Sonnet, because the journal has 1 graded trade and 0 verdicts; the batch judge run); cost and cap; and the cache-minimum risk from §3. The Options list names six choices, including the two not tested (both steps on Haiku; Anthropic Message Batches for experiment arms) and why. Add both tables with every cell `awaiting experiment` (routing) or `awaiting run` (judge). Then tests 3 to 6 pass: 21 passed (the reference's acceptance run at commit `3792699`: `21 passed in 0.61s`).

**Commit order is your discipline.** The runbook says it plainly: "The pre-registration only counts if it is committed before the run. No test can check that: code cannot see commit order." The reference shows the order you can audit afterwards. Commit `3792699` ("W8RefA: ADR-011 pre-registration and experiments/routing.toml, committed before the paid run") is dated 2026-11-17 22:31:00 -0700, which is 05:31:00 UTC on 2026-11-18. The first run file of the experiment, `run_1eba503380b7444c`, records `created_at` 2026-11-18T05:31:21Z, 21 seconds later, and the last, `run_073c4b1e547f4930`, 06:18:44Z. The result commit `cc2ead9` follows at 23:31:27 -0700. Anyone can rebuild that timeline from `git log` and the run headers; nobody can rebuild it if the ADR is committed after.

**Done when**
- `uv run pytest tests/test_week8.py -q` gives 21 passed.
- Your pre-registration says what a pass means when ψ is higher than planned, before you know ψ.
- Every command your ADR names exists and prints what you say it prints.
- `git log` shows your ADR and config committed before your first paid run file's `created_at`.

**Traps (real)**
- *A planned cap from a cost forecast.* The design note's $3.00 would have been refused. The probe at 0.01 is free; run it before you write the cap.
- *A reading named but never checked.* The `--by call` "served-model column" survived one draft. It was caught by the author reading the code, not by a test.
- *The power formula's α and the rule's α are not the same.* The formula uses one-sided α 0.05; the rule reads the lower end of a two-sided 95% interval, which is one-sided α 0.025. At α 0.025 and power 0.80 the factor is (1.96 + 0.84)² ≈ 7.85, and 60 items cover ψ up to about 0.17, not 0.218 `[INFERENCE: the author's arithmetic, not in ADR-011 or the design note]`. Either way, the observed ψ in §9 is above both.

**Cash:** $0 (the cap probe makes no call). **Reference:** `git show week-8-end:docs/adr/ADR-011-model-routing.md` (stop at **Decision.**, the rest is §9); `git show 3792699 --stat`.

---

## 9. The run, the rule, and why a pass is not a proof (3 h; the run cost $5.6118)

**Goal:** one paid run, the routing table filled from its output, the rule applied by hand, ψ counted, and a Result that follows your rule.

The command, from ADR-011 and the runbook. It needs `ANTHROPIC_API_KEY` in the repo-root `.env`, and the news store filled for each of the 10 tickers on each of the 6 sessions in the config (`tr news TICKER --session DATE`). `data-dev/` is gitignored, so a fresh clone has no `data-dev/scratch/`; the first line makes it, so `tee` can save the output of a paid run:

```bash
mkdir -p data-dev/scratch
TR_PROVIDER=anthropic TR_DATA_DIR=$PWD/data-dev uv run tr exp run experiments/routing.toml 2>&1 | tee data-dev/scratch/w8-run.txt
```

The author's output is `data-dev/scratch/w8refb-run.txt` (27 lines, `exit=0`). Its header and the three arm lines:

```text
experiment routing: 60 ticker-days x 3 arm(s), graders parsed, claims_valid, all_claims_valid, inferences_grounded, cap $5.50/arm, provider anthropic
plan worst case $5.270661 per arm (arm cached, floor $4.586072), cap $5.50
arm sonnet     prompt=analyze-3 run=run_1eba503380b7444c theses=run_b7a046db477e4359 spent=$2.3086 failed=0 analyses=0
    all_claims_valid=0.767 (n=60)  claims_valid=0.962 (n=60)  inferences_grounded=0.983 (n=60)  parsed=1.000 (n=60)
arm routed     prompt=analyze-3 run=run_98681aba3fe24a79 theses=run_80c8bf85db874007 spent=$1.3517 failed=0 analyses=0
    all_claims_valid=0.800 (n=60)  claims_valid=0.973 (n=60)  inferences_grounded=0.983 (n=60)  parsed=1.000 (n=60)
arm cached     prompt=analyze-3 run=run_0311bd3c03344a3a theses=run_073c4b1e547f4930 spent=$1.9515 failed=0 analyses=0
    all_claims_valid=0.700 (n=60)  claims_valid=0.960 (n=60)  inferences_grounded=1.000 (n=60)  parsed=1.000 (n=60)
```

(The three `audit drop=... flag=... reject=...` lines are trimmed; `routed` had `reject=1`, the others 0.) The plan worst case, $5.270661, is under the $5.50 cap, so there was no `WARNING` line. The run spent $2.3086 + $1.3517 + $1.9515 = $5.6118.

**The rule.** The decisive line:

```text
compare sonnet -> routed: 60 items, 10 clusters
    all_claims_valid   0.767 -> 0.800  diff +0.033  CI [-0.100, +0.167] (95%)  mcnemar p=0.824  mde=0.205  n=60
```

The lower bound is -0.100. The margin line is -0.15. -0.100 is above -0.15, so **the registered rule passes**, applied by hand. Write that sentence first, in those words, before anything else in the Result.

**Why the pass is not a proof.** Three readings, all from the same run, say the evidence is weak:
- **ψ is above plan.** Counted from the paired item scores, 20 of the 60 items disagreed: 9 valid only on `sonnet`, 11 only on `routed`. ψ = 20/60 = 0.333, against the 0.22 the 60 items were sized for (ADR-011, Result). The pre-registration said what that means: a pass with a wide interval is not a proof.
- **The interval is wide.** [-0.100, +0.167] cannot rule out a loss of 0.10 in the share of all-valid analyses. The printed `mde=0.205` is the smallest true difference this run would detect 80% of the time (two-sided α 0.05).
- **The noise floor is as large as the effect.** The `cached` pair differs only by a cache, so the model sees the same thing:

```text
compare sonnet -> cached: 60 items, 10 clusters
    all_claims_valid   0.767 -> 0.700  diff -0.067  CI [-0.167, +0.050] (95%)  mcnemar p=0.454  mde=0.183  n=60
```

  Its ψ is 0.267 (10 and 6), and its lower bound, -0.167, is **below** -0.15. Read under the same rule, a same-model pair would "fail" non-inferiority against itself. So a pass or fail for `routed` at this n says little about Haiku. The design note's ψ of 0.10 to 0.25 came from resamples of 10 and 20 items; on these 60 items the same-model ψ is 0.267, so the plan was too low.

The secondary graders move little: `claims_valid` 0.962 -> 0.973 (CI [-0.011, +0.032]), `inferences_grounded` 0.983 -> 0.983 (CI [-0.050, +0.050]), `parsed` 1.000 in all three arms. Drift does not separate the model either: the thesis changed on 0.617 of items under `routed` (CI [0.483, 0.750]) and on 0.650 under `cached` (CI [0.483, 0.800]). A thesis changes between two runs of the same model about as often as it changes under a different analyze model. Week 7 found the same noise in its clean rerun.

**Cost.** From `docs/measured-costs.md` ("Week 8: routing and caching") and the run files (§4's table):

| Arm | Analysis cost | Thesis cost | Spend | Per ticker-day |
|---|---|---|---|---|
| sonnet | $1.0304 | $1.2783 | $2.3086 | $0.0385 |
| routed | $0.0858 | $1.2659 | $1.3517 | $0.0225 |
| cached | $0.8990 | $1.0525 | $1.9515 | $0.0325 |

Haiku cut the analyze step by 92% ($0.0858 against $1.0304), with the same 181,139 input tokens and about twice the output (135,389 against 66,809). The thesis step did not move. Per ticker-day `routed` costs 41% less than `sonnet`. Note where the rest of the money is: after routing, the thesis is about 94% of the routed arm's spend ($1.2659 of $1.3517). The next saving, if any, is on the thesis step, and ADR-011's Options explain why week 8 did not touch it: it is the step that makes the money-relevant decision.

**Latency.** Haiku is slower per item on the analyze step: p50 9,714 ms against 7,819 ms, p95 11,872 ms against 9,515 ms. The ADR's reading is that it writes about twice as many tokens. A cheaper model per token is not a faster model per item when it writes more.

**Cache.** It worked. The cached analyze run wrote 1,216 tokens once and read 71,744 (59 calls of 1,216); the thesis run wrote 2,112 and read 124,608. `cached` cost 12.7% less on the analysis ($0.8990 against $1.0304) and 17.7% less on the thesis ($1.0525 against $1.2783). The arithmetic from the price table, as a check `[INFERENCE: the author's arithmetic from PRICES, not a separate measurement]`: 71,744 read tokens save ($2.00 - $0.10) per million, $0.1363; the one write costs an extra $0.50 per million on 1,216 tokens, $0.0006; and the cached arm wrote 434 more output tokens (67,243 against 66,809), $0.0043. Net about $0.1314, against the measured $1.030368 - $0.899002 = $0.131366.

The 510-token estimate was wrong in the safe direction: the cached analyze block is 1,216 tokens, so the "too short to cache" outcome the ADR registered did not occur. Characters over four is a rough guess for a prompt with JSON and tickers in it, and the design note's regression estimate (1,386 to 1,847 tokens) had already said the cacheable prefix was larger than the system prompt alone `[INFERENCE: what fills the gap between 510 and 1,216 tokens was not measured]`.

**Fallback.** 0 of 60 routed analyze calls fell back: every span's `resolved_model` is `claude-haiku-5-5` (ADR-011; the author's recount of the routed analysis run's spans gave the same). The fallback path did not run, so the run tells you nothing about it.

**The Result and the recommendation.** ADR-011's recommendation: route the analyze step to Haiku 5.5 only after a second run settles the quality question, because the interval cannot rule out a loss of 0.10 and ψ is above the registered 0.22. The saving is measured (41% per ticker-day); the quality evidence is not conclusive. `tr daily` stays on Sonnet 5.5 on both steps; nothing was adopted. The Status line still reads `proposed`: the result is in, and the decision it supports is "run again", not "adopt".

Fill the routing table from these lines and from `tr usage --by step --run`, with the six run ids in a line beside the table, never in a cell. The judge table stays `awaiting run`.

**Done when**
- Your Result states the rule's outcome first, by hand, against your margin.
- It states ψ and the noise-floor pair, and calls the pass what your pre-registration said it would be.
- The routing table is filled, with run ids beside it, and the cache and fallback readings are given with the command or file they came from.
- Your recommendation does not adopt anything the evidence does not support.

**Traps (real)**
- *A pass read as a proof.* The rule passed. The same-model pair would have failed the same rule. Both facts go in the Result.
- *A cost saving read as a quality result.* 41% cheaper is measured. "Just as good" is not.
- *An unrun path read as tested.* 0 fallbacks means the fallback is still untested against a real failure.
- *A cost read as a bill.* All costs here are derived from the price table. The Console's billed amount was not read (`docs/measured-costs.md`).

**Cash:** $5.6118 (the run; recomputed from the run files as $5.611799). **Reference:** `git show week-8-end:docs/adr/ADR-011-model-routing.md` (Result); `git show week-8-end:docs/measured-costs.md`.

---

## 10. What stays on OpenRouter, what ran on Anthropic, and where week 9 starts (0.25 h, $0)

**Goal:** know which provider serves which part of the system after week 8, and why the live loop did not move.

| Part | Provider | Why |
|---|---|---|
| The routing experiment's arms | Anthropic (`TR_PROVIDER=anthropic`) | the `route` and `cache` knobs need the Messages API; the run used Anthropic credit only |
| The judge, sync and batch | OpenRouter | ADR-003: the judge is a different vendor; the batch needs a funded `OPENROUTER_API_KEY` |
| The teachers and the bake-off | OpenRouter (pinned DeepInfra routes) | the runbook's "Providers" table |
| The live pin (`tr daily` in the live worktree) | OpenRouter | ADR-011: "the live pin and the bake-off run on OpenRouter"; `tr daily` runs fixed `DEFAULT_MODEL`s for analyze and thesis, and week 8 changes none of them |

The paid run is on Anthropic because the author had prepaid Anthropic credit to use before it expired; with `TR_PROVIDER=openrouter` the same config runs on OpenRouter. The two providers are never mixed inside one experiment: every row's `provider_route` starts with the provider, so a comparison across providers cannot happen by accident.

The live worktree did not move: `git worktree list` shows `tradingresearch-live` at `830d0ef` (detached), the pin from week 6. ADR-011 adopts nothing in `tr daily`, so nothing here waits on a live session.

Carried forward, as ADR-011 states them:
- **A second run for the routing question**, sized for the ψ this run measured (0.333 cross-model, 0.267 same-model), with the noise-floor arm kept. ADR-011 recommends it; it is not registered yet.
- **The batch judge is unmeasured.** It waits on a funded OpenRouter key and at least 10 graded trades. The judge table reads `awaiting run`.
- **The fallback is untested against a real failure.** It never fired.
- **Limits of this design**, from ADR-011's Consequences: one model family, so nothing follows about other cheap models; 60 items from 6 sessions of one market week, so a week-wide effect is not separated from the model effect; the Haiku price has not been checked against a billed call.

**Done when**
- You can say why the experiment ran on Anthropic and the judge did not.
- You can list what ADR-011 leaves open, and which item a week-9 experiment would need first.

**Traps (real)**
- *A recommendation that quietly becomes a config change.* "Route analyze to Haiku after a second run" is not "route analyze to Haiku". `tr daily` is unchanged, and the live pin proves it.

**Cash:** $0. **Reference:** ADR-011, "Consequences"; `docs/runbook.md`, "Providers"; [week-9.md](week-9.md).

---

## Week 8 cash, as measured by the author

| Step | Spent | Source |
|---|---|---|
| Building `week-8-start`: knobs, cost table, batch judge, pre-flight, the contract tests, two fix rounds | $0 | no model call (workers G15a to G15e, COST3a, W8Fix-A and -B; every provider in the tests is a fake, the batch tests use fake HTTP) |
| Week-8 reference: `routing.toml`, ADR-011 pre-registration, the cap probe at 0.01 | $0 | the probe is refused by the pre-flight before any call (ADR-011; commit `3792699`) |
| The run of `experiments/routing.toml` | $5.6118 | by arm, from `w8refb-run.txt`: `sonnet` $2.3086, `routed` $1.3517, `cached` $1.9515; $5.611799 recomputed by the author from the six run files with `usage.total` |
| Week 8 | $5.6118 | all on Anthropic credit |

Per ticker-day: `sonnet` $0.0385, `routed` $0.0225, `cached` $0.0325. Costs are derived from the tokens by the adapter's Anthropic price table, not read from a provider bill. The pre-run estimate was about $5.4 for the three arms; the run cost $5.61. The build-guide README budgets week 8 at about $1.50 (model routing about $1, prompt caching about $0.50). The run cost more than that because every arm ran both steps on 60 items, and two of the three arms ran Sonnet on both.

## Week 8 is done when

- `uv run pytest -q` passes apart from the index test that needs a local build, and `ci/gate.py` says `gate: ok (90 reconcile cases at rules-1, 5 prompts)`. `uv run pytest tests/test_week8.py -q` gives 21 passed.
- `experiments/routing.toml` has a baseline, a routed arm that changes only the analyze model, and a cached arm that changes only the cache.
- ADR-011's pre-registration names the metric, the rule, the margin, the item count, the cap and what a pass means when ψ is above plan, and `git log` shows it committed before your first paid run file.
- Every command your ADR names exists and prints what you say it prints.
- ADR-011's routing table holds the numbers of one complete run with its run ids beside it, and its Result follows the rule: the rule's outcome, ψ, the noise-floor pair, cost, latency, cache and fallback readings.
- The judge table reads `awaiting run`, and the ADR says why.
- Nothing in `tr daily` changed.
- `git tag week-8-end` on your commit.

Every result in this chapter comes from a run that happened: ADR-011's Result, `data-dev/scratch/w8refb-run.txt` and `docs/measured-costs.md` "Week 8: routing and caching" at `week-8-end`, and the author's own free checks named where they appear (the `git archive` test run in §1, the per-run recompute in §4 and §9, the commit and run timestamps in §8).
