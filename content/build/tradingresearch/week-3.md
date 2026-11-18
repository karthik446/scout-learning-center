# Week 3: grade the trades, watch the loop, count the cost

> *"Educational software. Not investment advice. No orders are placed; trades are hypothetical and settled from historical bars by written rules. Past results, including these, do not predict future results."*

**Code:** start [`week-3-start`](https://github.com/karthik446/tradingresearch/tree/week-3-start) · reference answer [`week-3-end`](https://github.com/karthik446/tradingresearch/tree/week-3-end) · [the chapter diff](https://github.com/karthik446/tradingresearch/compare/week-3-start...week-3-end) (repo: [karthik446/tradingresearch](https://github.com/karthik446/tradingresearch)).

**You start at** `week-3-start`: week-2-end plus shipped code for this week's plumbing. `tr grade` writes a shadow baseline and an outcome grade with P2-P4 for every closed trade, `tr report` prints per-horizon scorecards, `tr slo` checks the evening run, `tr label` stores blind P1 labels, and one retry policy covers every HTTP source. `tests/test_week3.py` fails by design (19 cases).
**You end at** `week-3-end`: the P1 judge as code and `tr grade --judge`, ADR-004 on what never enters a trace, an SLO review and a measured-cost page, each checked against the live journal on the morning of its first live session.
**Cash:** the work costs $0, because the judge tests replay one recorded reply. The one optional paid step is `tr grade --judge` once a trade has closed: the author's single recorded judge call cost $0.005163. **Time:** about 9 hours, the sum of the section guides below.

Concepts this week, each explained in one or two lines with a link where it is first used: traces and redaction (§2), retries with jitter (§2), shadow baselines (§3), SLIs and SLOs (§5), the Wilson interval, the cluster bootstrap and the minimum detectable effect (§5), and Cohen's κ (§7). Week 2 graded a thesis before the market answered. Week 3 grades it after, keeps the evening loop honest, and replaces every cost estimate with a measured one.

The live stream starts on 2026-11-17. This chapter was checked on 2026-11-17 between 01:19 and 01:37 ET, before that session opened, so no live session has closed. Every number that needs one sits in an "Awaiting" block with the command that will fill it.

## Where everything is

Every file this chapter names, the tag where it first appears, and how to look at it. `git diff week-3-start week-3-end --stat` lists what week 3 adds: 19 files, 775 insertions, 80 deletions.

| What | Path | Tag | See it |
|---|---|---|---|
| Outcome grade, shadow baselines, P2-P4 on closed trades, post-trade summary | `src/tradingresearch/grade.py`, `commands/grade.py` | week-3-start | `uv run tr grade --dry-run` |
| Grade step in the evening run | `src/tradingresearch/daily.py` | week-3-start | `uv run tr daily --help` |
| Per-horizon scorecards | `src/tradingresearch/report.py`, `commands/report.py` | week-3-start | `uv run tr report` |
| SLO checks | `src/tradingresearch/slo_check.py`, `commands/slo.py` | week-3-start | `uv run tr slo` |
| Blind labels, judge-verdict store, κ | `src/tradingresearch/label.py`, `commands/label.py` | week-3-start | `uv run tr label list` |
| One retry policy (Alpaca, EDGAR, OpenRouter) | `src/tradingresearch/retry.py`, `openrouter.py` | week-3-start | `git show week-3-start:src/tradingresearch/retry.py` |
| Tools capability, `mode` arm knob | `src/tradingresearch/openrouter.py`, `experiment.py`, `tests/fixtures/tools/` | week-3-start | `git show week-3-start:tests/fixtures/tools/get_close.request.json` |
| Traces and usage (unchanged) | `src/tradingresearch/trace.py`, `usage.py` | week-2-start | `uv run tr usage --by day` |
| P1 rubric, judge prompt, judge spec | `evals/rubrics/p1_thesis_quality.md`, `p1_judge_prompt.txt`, `evals/specs/p1_judge.md` | week-2-start (judge spec), week-2-end (rubric, prompt) | `git show week-2-end:evals/rubrics/p1_judge_prompt.txt` |
| Week-3 contract: tests and the recorded judge exchange | `tests/test_week3.py`, `tests/fixtures/week3/` (`judge_request.json`, `judge_reply.json`, `models.json`) | week-3-start | `uv run pytest tests/test_week3.py -q` |
| Live stream starts at one date | `src/tradingresearch/sessions.py` (`FIRST_SESSION`), `report.py`, `slo_check.py` | week-3-end (commit `081481a`) | `git show 081481a --stat` |
| P1 judge (§4) | `src/tradingresearch/evals.py` (`p1_verdict`, `p1_judge`) | week-3-end | `git diff week-3-start week-3-end -- src/tradingresearch/evals.py` |
| `tr grade --judge` (§4) | `src/tradingresearch/grade.py`, `commands/grade.py` | week-3-end | `uv run tr grade --help` |
| ADR-004, trace policy (§2) | `docs/adr/ADR-004-trace-policy.md` | week-3-end | `git show week-3-end:docs/adr/ADR-004-trace-policy.md` |
| SLO review (§5) | `docs/slo-review.md` | week-3-end | `git show week-3-end:docs/slo-review.md` |
| Measured costs (§6) | `docs/measured-costs.md` | week-3-end | `git show week-3-end:docs/measured-costs.md` |
| Runbook: judge, live-stream start | `docs/runbook.md` | week-3-end (modified; new in week-2-end) | `git diff week-3-start week-3-end -- docs/runbook.md` |

The week-3-end files are the reference answers: write yours first, then compare.

---

## 1. Setup and a tour of the shipped code (1 h, $0)

**Goal:** the week-3-start repo runs on your machine, you know which 19 tests are yours, and you have seen `tr grade`, `tr report`, `tr slo` and `tr label` on your own journal.

Do [SETUP.md](SETUP.md) first if you have not. Week 3 runs on OpenRouter alone, and the code at this tag finds `.env` only through `TR_ENV_FILE`:

```bash
cd tradingresearch && git checkout week-3-start
export TR_ENV_FILE="$PWD/.env"         # once per shell, for every tag before week-6-end
uv sync
uv run pytest -q                       # 426 passed, 19 failed, 1 skipped, 2 deselected: all 19 are tests/test_week3.py
uv run python ci/gate.py               # gate: ok (90 reconcile cases at rules-1, 3 prompts)
```

The 19 failures are the week's assignment. Thirteen are the judge (§4): `AttributeError: module 'tradingresearch.evals' has no attribute 'p1_verdict'` (or `'p1_judge'`), and for the CLI case `AssertionError: tr grade has no --judge flag yet`. Six are the documents: `docs/adr/ADR-004-trace-policy.md is missing: it is a week-3 file you write`, and the same for `docs/slo-review.md` (one case) and `docs/measured-costs.md` (four, one per step: analyze, thesis, judge, daily).

One fix to shipped code landed after the tag: commit `081481a` makes `tr slo` and `tr report` start at the first live session, 2026-11-17, with one `sessions.FIRST_SESSION` constant. It is not learner work. Take it with `git cherry-pick 081481a`; it applies cleanly on week-3-start (`git merge-tree` reports no conflict). It adds the 3 tests that take week-3-end to 448 passed.

The week-3 commands, from `uv run tr --help` (excerpt):

```text
    grade               shadow baselines and grades for closed theses (no
                        model call)
    daily               the evening run for one session: screen, analyze,
                        thesis, reconcile, grade (paid)
    report              per-horizon scorecards: win rate, r_net, shadow,
                        power, P1 (no model call)
    slo                 check finish by 17:30 ET, zero missed sessions, fresh
                        data; exit 1 on a breach
    label               blind P1 labels of graded theses and judge agreement
                        (no model call)
```

All four are free. `tr report` and `tr slo` read only the journal; `tr grade` and `tr label show` also fetch Alpaca bars (free). The only writes are the ones `tr grade` and `tr label add` exist to make. Look first: `tr grade --dry-run` on the author's live journal, 2026-11-17 01:33 ET, before the first live session opened. The six theses are week 2's, written after the 2026-11-16 close; their entry windows open on the 17th.

```text
$ uv run tr grade --dry-run
AAPL   swing th_d7359e73ebb947a4 PROPOSED  waiting: PROPOSED: not filled yet
HD     swing th_0460596ced92436e PROPOSED  waiting: PROPOSED: not filled yet
JPM    short th_c0dbaf9326954bd6 PROPOSED  waiting: PROPOSED: not filled yet
JPM    swing th_813ac52eb68c4df3 PROPOSED  waiting: PROPOSED: not filled yet
XOM    short th_6786e3f15a95453e PROPOSED  waiting: PROPOSED: not filled yet
XOM    swing th_066251b3465b4405 PROPOSED  waiting: PROPOSED: not filled yet
grade 2026-11-16 (dry run): would grade 0, would create 0 shadow(s), 6 waiting; nothing written
```

**Done when**
- `pytest` shows the 19 `test_week3.py` failures and nothing else red, and `ci/gate.py` says `gate: ok`.
- You have run `tr grade --dry-run`, `tr report`, `tr slo` and `tr label list` on your journal.

**Traps (real)**
- *The pinned live code is week-3-start.* The author's LaunchAgent runs `tr daily --teachers` from the `tradingresearch-live` worktree, detached at `a9eafa3` (week-3-start). It grades every evening, but it has no `--judge` and no `081481a`. To use either on live data, move the pin as week 2 §6 says, outside the two run windows.
- *Dev runs are not live runs.* The six theses and both `tr daily` runs of 2026-11-16 predate the stream. With `081481a`, `tr report` and `tr slo` name them and leave them out (§5).

**Cash:** $0. **Reference:** `uv run tr grade --help`.

---

## 2. Traces, redaction and retries: ADR-004 (1 h, $0)

**Goal:** `docs/adr/ADR-004-trace-policy.md`, saying what may never enter a trace and which of those rules the code enforces. Read the retry policy that shipped with week-3-start.

A **trace** is one record per model call, a *span*, holding the model, tokens, latency, cost and outcome ([OpenTelemetry GenAI conventions](https://github.com/open-telemetry/semantic-conventions-genai)). **Redaction** keeps secrets and personal data out of what you store; a trace that holds a key leaks it to anyone who reads the file ([OWASP LLM Top 10](https://genai.owasp.org/llm-top-10/), LLM02 *Sensitive Information Disclosure*). gigai-core's `run()` writes the traces: each model step passes `trace_dir=data_dir / "traces"`, so every run leaves `data/traces/<run_id>.jsonl` and `data/runs/<run_id>.jsonl`. Read one real span before writing anything. A span holds the call settings, a `ProviderIdentity`, `request_sha256`, the last turn sent and the reply in full, usage, cost, latency, and a `CallError` on failure. The full conversation (`request_turns`) is stored only with `store_inputs=True`, and no tradingresearch call sets it.

The ADR has four decisions (excerpt of week-3-end):

```markdown
- **API keys never enter a trace, a run file, a log line or a committed file.** Keys are read from
  [the settings file] in Python into `config.Secret`, whose `repr` and `str` print a mask ...
- **No account data exists to trace.** The repo calls Alpaca's market-data host only ...
- **Fetched content stays in the git-ignored `data/`.** ...
- **Redaction rule: structural, not pattern-based.** Nothing scans or rewrites text before it is written.
```

The retries are shipped code, not your work, but ADR-004's error gap comes from them. `retry.Policy()` makes at most 4 tries within 300 s. Before retry *n* it sleeps `uniform(0, min(30, 1 × 2**n))` seconds: exponential backoff with **full jitter**, a random wait so clients that failed together do not retry together ([AWS Builders' Library](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/)). A `Retry-After` header, in seconds or as an HTTP date, replaces the jitter and is capped at 30 s. 429, 5xx and httpx connection or timeout errors are retried. A 401 and every other 4xx are never retried. The retry runs inside `OpenRouter.invoke`, so a retried call is still one `ModelCall`, with `retry_count` and `last_error_class`.

**Done when**
- `uv run pytest tests/test_week3.py -k adr_004 -q` passes.
- Each decision names the code that enforces it, or says under Gaps that nothing does.

**Traps (real)**
- *The error body is the hole.* `CallError.message` is `str(exc)`. For an `OpenRouterError` that is the HTTP status plus the first 300 characters of the response body (`openrouter.py`, `_post`), so a provider that echoed a key would write it into the span. ADR-004 lists this as a gap; there is no scrub.
- *A copy bypasses `.gitignore`.* `tests/fixtures/usage/` holds two real committed runs (`run_10fc0a886ddb42a2`, `run_c40caab0968e44a3`) whose last turns carry indicators computed from Alpaca bars, plus EDGAR facts. A grep there for key prefixes finds nothing, but no test runs that grep.
- *Not every paid call is in the trace total.* The week-3-start live check of the tools capability (`openai/gpt-4.1-nano`, 81 in / 7 out, $0.0000109) went through `invoke` directly, not through `run()`. It shows on the key, not in `tr usage`'s trace total.
- *No retention rule.* On 2026-11-17, `data/traces/` and `data/runs/` held 21 files each, and both keep growing.

**Cash:** $0. **Reference:** `git show week-3-end:docs/adr/ADR-004-trace-policy.md`.

---

## 3. `tr grade`: the outcome, the shadow and P2-P4 (1 h, $0)

**Goal:** read the shipped grade path until you can say what one Grade row means. Your judge in §4 runs on its output.

A **shadow baseline** is a naive trade placed at the same moment as the real one, so a result can be read against "what a dumb rule did" ([Hyndman & Athanasopoulos, *Simple forecasting methods*](https://otexts.com/fpp3/simple-methods.html)). When a thesis fills, `grade.shadow_for` opens a shadow at the same entry (the OPEN event). Its direction is d = sign(close − sma_20), its stop is E − d·|E − S|, its target is 2R, and it keeps the thesis's `hold_sessions` (`grade.py:150-167`). The frozen `reconcile.settle` settles shadows as `market_open` subjects. Once the thesis and its shadow are both CLOSED, `build_grade` writes three things in one transaction: a Grade, a `ScoreRecord` (`outcome_r_net` v1) and a `GRADED` event. It also runs the week-2 P2-P4 checks. In `tr daily`, the grade step is a `reconcile` row whose reason starts with `grade: `.

`post_trade_summary` writes the closed trade as plain lines for a reader, and §4's judge sees exactly those lines. This one is from the recorded judge request (synthetic ticker FAKEA):

```text
exit: target at 106 on 2026-11-18, filled at 101 on 2026-11-17; r_net +1.65, MFE +1.67R, MAE +0.00R, 1 session(s) held after the fill day
closes: 2026-11-17 101.3, 2026-11-18 106.2
vs congestion_high 100.5: closed at or above it on 2 of 2 sessions
vs invalidation 98: closed at or above it on 2 of 2 sessions
```

**Done when**
- You can name the three rows a grade writes, and why the shadow keeps the thesis's hold.
- `tr grade --dry-run` on your journal shows what is waiting and why (§1).

**Traps (real)**
- *Champion outcomes are not stored.* No table holds a champion's OutcomeGrade, so every grade replays the recorded events through `settle`. The replay is deterministic, but a change to `settle` would change old grades.
- *The fill minute counts whole.* For a shadow, the entire fill minute counts toward MFE, MAE and the stop check, with its open replaced by the entry price, including the part before the fill.
- *No dividend flag.* Bars are raw (`reconcile_run.py:20`) and the corporate-action check asks only for splits and spin-offs (`reconcile_run.py:50`). A cash dividend's ex-date drops the raw price by the dividend mid-trade with no flag, which can trip a long's stop or shave its r_net; a short gains it.
- *One summary, two readers.* `post_trade_summary` is what `tr label show` (week-3-start, §7) prints and what `p1_judge` (§4) sends, so a change to it changes both what you label and what the judge reads; label and judge always see the same lines.

**Cash:** $0. **Reference:** `git show week-3-start:src/tradingresearch/grade.py`.

---

## 4. The P1 judge and `tr grade --judge` (2 h, $0)

**Goal:** `evals.p1_verdict`, `evals.p1_judge`, a judge step in `grade.py`, and `tr grade --judge` with `--judge-max-usd`, making 13 of the 19 `test_week3.py` cases pass.

Week 2 wrote the P1 rubric, the judge prompt and ADR-003; here the judge runs. The contract, from `tests/test_week3.py`:

```python
evals.p1_verdict(reply: str) -> tuple[str, str]            # (verdict, reason)
evals.p1_judge(conn, bars, thesis_id, provider, *, prices, data_dir, max_usd) -> Score
```

The tests replay one real exchange, recorded on 2026-11-17 for a synthetic FAKEA trade (`tests/fixtures/week3/`): one user message, with the body's other fields `{"model":"openai/gpt-6-sol","max_tokens":4000}`. The message is the judge prompt with the rubric filled in, then the cited claims and the post-trade summary as INPUT and the thesis as OUTPUT:

```text
[BEGIN OUTPUT]
prediction: Reaches 106 within 2 sessions.
reason: The break above the 7-session congestion top and 20-day high at 100.5 holds: every close after the fill stays above 100.5.
invalidation_text: A close back below 98.
[END OUTPUT]
```

The reply's last line (two sentences of reasoning come first), and its cost from the run file:

```text
{"verdict":"pass","explanation":"Both reported closes stayed above the 100.5 congestion top and 20-day high, so the named break held."}

$ TR_DATA_DIR=data/scratch/g9c uv run tr usage --by call
call                                 calls  tokens in  tokens out       cost  mean latency
run_54953ec7ce484649 FAKEA:p1_judge      1       1558         127  $0.005163       4350 ms
```

Build it in this order (the reference is `git diff week-3-start week-3-end -- src/tradingresearch/`):
1. `p1_verdict`: take the last JSON object in the reply (gigai-core `last_json_object`). `unknown` becomes `("fail", "unknown: ...")`, as ADR-003 says. A reply with no pass/fail/unknown verdict raises `CannotGrade`.
2. `p1_judge`: refuse teacher theses and theses with no Grade *before* any call (`label.labelable`). Build the INPUT from `label.cited` and `label.summary`, and render the prompt with gigai-core `llm_judge(...).render`. Make one call through `run()` with `CallBudget(max_usd)` and `trace_dir`, then save the run under `data_dir/runs`. Store the `ScoreRecord` and the verdict (`journal.add_judge_verdict`) in one transaction. The test asserts one request, the ADR-003 model, a bounded `max_tokens`, the rubric's sections, the summary lines and no raw bar values. The reference's body also matches the recording byte for byte (`same body: True`).
3. `grade.judge`: one dollar cap for the whole run (`JUDGE_MAX_USD = 0.25`). When the cap is spent, the rest are left as `cap is spent; next run`, and an error on one thesis does not stop the others.
4. `--judge` stays off by default. `tr grade --help` says what it costs:

```text
  --judge               also run the P1 judge (openai/gpt-6-sol, one paid call
                        per graded thesis without a verdict; off by default)
  --judge-max-usd JUDGE_MAX_USD
                        dollar cap for the whole judge run (default: 0.25)
```

On the author's live journal (2026-11-17 01:33 ET) the judge has nothing to do yet; the dry run ends with:

```text
$ uv run tr grade --judge --dry-run
grade 2026-11-16 (dry run): would grade 0, would create 0 shadow(s), 6 waiting; nothing written
judge: nothing to judge (no graded champion or challenger thesis without a verdict)
```

**Done when**
- The 13 judge cases in `tests/test_week3.py` pass, and `tr grade` without `--judge` makes no call.
- The judge's `validated` is still False: only an ADR that records κ on your labels turns it on (§7).

**Traps (real)**
- *The top-level help still says free.* `tr --help` lists `grade` as "(no model call)" at week-3-end, while `--judge` pays. The subcommand help is right; the summary line was not updated.
- *Cache writes cost more than input.* The recorded prompt cost $0.0038935, not 1,558 × $2/1e6 = $0.003116: 1,555 of its tokens were billed as cache writes at $2.50 per million (`judge_reply.json`, `usage.prompt_tokens_details`; [OpenRouter, *Prompt caching*](https://openrouter.ai/docs/guides/best-practices/prompt-caching)). The 127 output tokens include 49 reasoning tokens.
- *A failed reply is still paid.* A call with no verdict is `CannotGrade` after the call. Its cost is in the run file, nothing is stored, and the thesis is tried again next run.
- *The evening run never judges.* `tr daily` has no judge step, so every judge call is a deliberate `tr grade --judge`. `P1Judge.grade` refuses experiment samples ("p1_judge is a draft judge of closed trades (`tr grade --judge`), not of experiment samples").

**Cash:** $0; the tests replay the recording. The recording itself was a build cost of week-3-start ($0.005163). **Reference:** `git show week-3-end:src/tradingresearch/evals.py`.

---

## 5. SLOs and the report (1.5 h, $0)

**Goal:** `docs/slo-review.md`: the four SLOs, their targets, what is measured today, and the injected breach.

An **SLI** is a number you measure, and an **SLO** is the target you hold it to ([Google SRE book](https://sre.google/sre-book/service-level-objectives/)). The desk has four:

| SLO | Target | Checked by |
|---|---|---|
| `finished` | the first `tr daily` run that reached reconcile ends by 17:30 ET | `tr slo` |
| `missed` | 0 missed sessions in the last 10 (`--window`), counted from 2026-11-17 | `tr slo` |
| `fresh` | a screen result, and the session's daily bars for every screened ticker | `tr slo` |
| injected-delay alert | `--inject-delay-minutes M` turns a met finish into `BREACH ... (+M min injected)`, exit 1 | `tr slo` itself |

On the author's live journal, 2026-11-17 01:33 ET, there is no live session to check yet. Naming the pre-launch dev run shows every path:

```text
$ uv run tr slo
slo: no live session yet: the live stream starts 2026-11-17; the latest tr daily run (2026-11-16) predates it and is not checked
$ uv run tr slo --session 2026-11-16 --inject-delay-minutes 60
pre-live: 2026-11-16 predates the live stream (from 2026-11-17); a dev run, checked because --session named it
BREACH finished dy_4c43ee70dec141a7 finished 2026-11-17 00:21 ET (+60 min injected)  (target: by 17:30 ET on 2026-11-16)
ok     missed   0 of the last 1 sessions since 2026-11-16  (target: 0 in the last 10 sessions)
ok     fresh    10 of 10 screened tickers have 2026-11-16 bars  (target: a screen result for 2026-11-16 and sip daily bars for every screened ticker)
slo 2026-11-16: 2/3 met
```

The first exits 0, the second exits 1. Without the injection the breach line reads `finished 2026-11-16 23:21 ET`. That breach is real but not a live one. `tr daily` was committed at 23:19:48 ET on 2026-11-16 (`febe6b9`), and the run started by hand 7 s later as the end-to-end check of the new loop. Its first `daily_run` row is at 04:19:55Z and its last at 04:21:39Z, a run of 1 min 44 s. Call it the pre-launch dev run.

`tr report` prints one scorecard per arm and horizon, never pooled. A win rate comes with a **Wilson interval**, a confidence interval for a proportion that stays sensible at small n ([Wikipedia](https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval)). Mean r_net and real-minus-shadow use a **cluster bootstrap** over the entry session: it resamples whole sessions, because trades entered on the same day move together ([Miller, *Adding error bars to evals*](https://arxiv.org/abs/2411.00640)). It runs with 2,000 resamples and seed 0, and below 10 sessions it prints `insufficient (n sessions < 10)`. The **minimum detectable effect** is the smallest true difference a sample this size would detect at 80% power ([Wikipedia, *Power*](https://en.wikipedia.org/wiki/Power_(statistics))). In the tests, r_net 1, −1, 2, 0 gives 1.81 R. The Earned/Lucky grid of week 2 appears only once P1 results exist. On 2026-11-17 01:33 ET every live card was empty (excerpt: the swing card; the day and short cards read the same):

```text
$ uv run tr report
report: live stream from 2026-11-17; champion and challenger theses only (teacher theses never enter a scorecard); one scorecard per horizon, never pooled
pre-live, excluded (before 2026-11-17): 6 theses: th_d7359e73ebb947a4, ...; 2 tr daily runs (--include-pre-live shows them)
champion swing: 0 theses: 0 closed (0 graded), 0 expired, 0 cancelled, 0 open, 0 proposed
  no closed trades yet
cost per tr daily run: no run recorded
```

> **Awaiting session 1 (2026-11-17): the first live `tr slo`**
> Filled in when the data exists; nothing here is an estimate of the result.
> - Shows: `finished`, `missed` and `fresh` for 2026-11-17, and whether the 16:30 ET run met 17:30 ET.
> - Command: `uv run tr slo`, then `uv run tr slo --inject-delay-minutes 60` for the alert on a met finish.
> - Earliest: 2026-11-17 after 17:30 ET.

> **Awaiting sessions 1-10: the first full `missed` window**
> Filled in when the data exists; nothing here is an estimate of the result.
> - Shows: missed sessions in the last 10, the SLO's full window.
> - Command: `uv run tr slo`; the window's dates come from `uv run tr sessions --session 2026-12-01 --count 10`.
> - Earliest: 2026-12-01 after 17:30 ET (2026-11-26 is a holiday; 2026-11-27 closes at 18:00Z).

> **Awaiting sessions 2-N: scorecards per horizon (N = the session on which the first live thesis and its shadow are both CLOSED)**
> Filled in when the data exists; nothing here is an estimate of the result.
> - Shows: closed and graded counts, the Wilson win rate, mean r_net, real minus shadow, the MDE, per horizon.
> - Command: `uv run tr report` (`--horizon`, `--arm` to pick one card).
> - Earliest: the first live theses are written after the 2026-11-17 close and enter from 2026-11-18, so a card's first row is 2026-11-18 at the earliest (§7 has the dates). The bootstrap needs 10 entry sessions: 2026-12-02 at the earliest.

**Done when**
- `uv run pytest tests/test_week3.py -k slo_review -q` passes, and the review labels the dev run as not live.

**Traps (real)**
- *A breach on the dev run is not a live miss.* Report it, name the commit that explains it, and keep it out of the live numbers.
- *Nothing runs the check.* The LaunchAgent runs `tr daily`, not `tr slo`, so the "alert" is an exit code and a `BREACH` line nobody sees unless they run it.
- *`finished` times the first run that reached reconcile.* A 16:30 ET run that fails before reconcile and is rescued by the 21:00 catch-up breaches. `fresh` checks that bars exist, not that they are right.

**Cash:** $0. **Reference:** `git show week-3-end:docs/slo-review.md`.

---

## 6. Measured costs (1 h, $0)

**Goal:** `docs/measured-costs.md`, with one row per model step: the pre-run token estimate, the measured tokens and cost, and the run ids.

Every number comes from OpenRouter's `usage` on each call, stored in the run file and summed by `tr usage`. Analyze and thesis run on `anthropic/claude-sonnet-5.5`, the judge on `openai/gpt-6-sol`. The analyze, thesis and daily rows are the 2026-11-16 dev run; the judge row is one synthetic FAKEA call recorded 2026-11-17 (reference, condensed):

| Step | Pre-run estimate | Measured | Measured ÷ estimate |
|---|---|---|---|
| analyze, per ticker | 12,000 in / 2,000 out, $0.044 | mean of 5: 2,558.2 in / 1,193.6 out, $0.017052 | 0.388 |
| thesis, per ticker | 8,000 in / 1,500 out, $0.031 | mean of 5: 4,025.2 in / 1,276.4 out, $0.020814 | 0.671 |
| judge, per closed trade | 4,000 in / 500 out, $0.013 | 1 call, synthetic FAKEA: 1,558 in / 127 out, $0.005163 | 0.397 |
| daily, one run (shortlist 5) | $0.375 | dev run `dy_4c43ee70dec141a7`: $0.189334 ($0.085262 analyze + $0.104072 thesis) | 0.505 |
| learn, per week | 20,000 in / 3,000 out, $0.070 | not measured: no learn run exists | — |

At the decided shortlist of 10, the same per-name cost gives $0.378668 a day. That is arithmetic on one dev run, an **estimate**, not a measurement. The author's `tr usage`, 2026-11-17 01:33 ET, ends:

```text
total                                                 78     206988       94054  $1.333396
openrouter key usage $62.005975
```

> **Awaiting session 1 (2026-11-17): measured cost per live day**
> Filled in when the data exists; nothing here is an estimate of the result.
> - Shows: what one scheduled `tr daily --teachers` run costs, against the dev run's $0.189334.
> - Command: `uv run tr report` (last line, `cost per tr daily run`) and `uv run tr usage --by day`.
> - Earliest: 2026-11-17 after the 16:30 ET run.

> **Awaiting sessions 1-N: the first live judge spend (N = the first evening a graded thesis is judged)**
> Filled in when the data exists; nothing here is an estimate of the result.
> - Shows: the cost per judged trade on real summaries, against the one synthetic $0.005163.
> - Command: `uv run tr grade --judge` (from code that has it; §1), then `uv run tr usage --by call`.
> - Earliest: the evening the first champion thesis is graded, 2026-11-17 at the earliest.

**Done when**
- The four `measured_costs` cases pass, and every row names its run ids or says why it has none.

**Traps (real)**
- *The estimate counted inputs the prompt does not have.* The 12,000-token analyze estimate included 3,000 tokens of headlines and an 8-K list. The measured prompt has indicators, levels and EDGAR facts, and no headline rows.
- *A free rerun halves the mean.* `tr report --include-pre-live` prints `2 runs, total $0.189334, mean $0.094667`, because the second 2026-11-16 run did nothing and cost $0. Quote the run you mean.
- *Hand runs are not the loop.* AAPL's analysis and thesis were made by hand before the dev run, so they are left out of the means.

**Cash:** $0. **Reference:** `git show week-3-end:docs/measured-costs.md`.

---

## 7. Blind labels and Cohen's κ (1 h, $0 now)

**Goal:** know the labelling loop well enough to start it the evening the first trade is graded, and know when κ means something.

**Cohen's κ** measures how far two raters agree beyond the agreement chance alone would give: 1 is perfect, 0 is chance ([Wikipedia](https://en.wikipedia.org/wiki/Cohen%27s_kappa)). Here the raters are you and the judge, and κ on your labels is what ADR-003 needs before the judge's `validated` turns True. `tr label list` shows graded champion and challenger theses that have no label yet. `tr label show <id>` prints the thesis, its cited claims and the post-trade summary, and never the verdict or an earlier label. `tr label add <id> met|not_met|unknown` stores a blind label (`--relabel` chains a new one to the old). `tr label agree` pairs labels with verdicts through gigai-core `agreement`. The shipped test `test_kappa_on_a_hand_computed_two_by_two` checks a hand-worked case: 10 pairs, 7 agree, human met 6/10, judge pass 5/10, so p_e = 0.5 (p_e, the agreement chance alone gives: 0.6·0.5 + 0.4·0.5) and κ = (0.7 − 0.5)/(1 − 0.5) = 0.40. The output also prints ADR-003's PROPOSED threshold (κ ≥ 0.6 on 30 labels), gigai-core's own gate (n ≥ 126) and `validated = False`. On the author's live journal, 2026-11-17 01:33 and 01:37 ET:

```text
$ uv run tr label list
nothing to label: no graded champion or challenger thesis without a label (0 labelled)
$ uv run tr label agree
agree: awaiting labels (n = 0 pairs; kappa needs at least 2)
  labels: 0 met/not met, 0 unknown (left out); of the 0: 0 paired, 0 judge unknown: (left out), 0 not judged; 0 judged without a label
```

When the first trade is graded depends on the entry window and the hold (`thesis.windows`, `records.HOLD_RANGE`; hold counts sessions after the fill session), with dates from `uv run tr sessions --session 2026-12-03 --count 13`. A grade needs the shadow closed too, and the shadow keeps the same hold.

| Theses | Entry window | Hold | Earliest close | Time exit if filled on the window's first day |
|---|---|---|---|---|
| The 6 from 2026-11-16 (2 short, 4 swing, all limit entries; pre-live) | short 2026-11-17; swing 2026-11-17 to -18 | short 3, swing 10 | 2026-11-17 (a limit fill that hits its stop the same session) | short 2026-11-20; swing 2026-12-02 (2026-12-03 if filled on the 18th) |
| The first live theses (written after the 2026-11-17 close) | from 2026-11-18 | day 0, short 2-5, swing 5-20 | 2026-11-18 | set by each thesis's hold |

> **Awaiting sessions 1-N: the first κ (N = the session with at least 2 label–verdict pairs)**
> Filled in when the data exists; nothing here is an estimate of the result.
> - Shows: your blind labels against the judge's verdicts, κ with its interval, n pairs.
> - Command: `uv run tr label list`, `uv run tr label show <id>`, `uv run tr label add <id> met|not_met|unknown`, then `uv run tr label agree`.
> - Earliest: the first graded thesis (table above) for a label, and two judged and labelled theses for any κ. The plan sets about 15 labels for week 3 and ADR-003 30 by week 4; both are descriptive.

**Done when**
- You can say which theses `tr label list` will offer first, and from which date.
- You label before you look at the judge's verdict, every time.

**Traps (real)**
- *The CLI word is `not_met`, the stored word is "not met".* `tr label agree` and the rubric use the stored form.
- *`unknown` is left out of κ*, on both sides: an `unknown` label and a judge `unknown:` verdict are counted and reported, but never paired.
- *Thirty labels still decide little.* ADR-003 estimates κ's 95% half-width at about ±0.29 on 30 labels, so a κ of 0.6 means 0.31-0.89. gigai-core's own gate needs 126 labels, so the judge stays "descriptive, not validated" and every κ is printed with its n.

**Cash:** $0 for labels. Each judged trade costs about what §4 measured. **Reference:** `git show week-3-start:src/tradingresearch/label.py`.

---

## 8. What week 4 does with this (0.5 h, $0)

**Goal:** know which week-3 pieces week 4 builds on.

Week 4 makes `analyze` use tools: `Arm.mode` already takes `fixed` or `tools`, and `tools` raises `NotImplementedError("mode=tools: week 4 learner work")`. The week-4 experiment runs tool-using analyze against fixed context and feeds ADR-005. κ is reported on 30 labels, still descriptive. The challenger arm starts at day 22, and `tr learn` ships at week-4-start, where `tr learn --status` is described. The live pin must move to code that has `--judge` before any live trade can be judged (§1).

**Done when**
- You can say what week 4 needs from this week: graded trades and judge verdicts for κ, labels from you, and the measured cost per step to price the tools arm.

**Traps (real)**
- *Reporting before the data.* Six numbers in this chapter wait on sessions. Each sits in an Awaiting block with its command and earliest date, and none is filled with a guess.

**Cash:** $0. **Reference:** [week-4.md](week-4.md).

---

## Week 3 cash, as measured by the author

| Step | Spent | Source |
|---|---|---|
| Building `week-3-start` (all paid calls, key $61.997785 → $62.005975) | $0.008190 | the OpenRouter key |
| of which: one teacher thesis capture (DeepSeek V4 Pro, the `tr daily --teachers` packet) | $0.003016 | `run_4e42bd3f4aa64f1d` |
| of which: the retry and tools live check (`openai/gpt-4.1-nano`) | $0.0000109 | the key only (§2) |
| of which: the P1 judge recording (synthetic FAKEA) | $0.005163 | `run_54953ec7ce484649` |
| Week-3 reference answers (judge, `--judge`, ADR-004, SLO review, measured costs) | $0 | no model call |
| First live `tr grade --judge` | awaiting | §6 |
| Live sessions from 2026-11-17 | awaiting | §6 |

## Week 3 is done when

- `uv run pytest -q` is green (448 passed, 1 skipped, 2 deselected at the reference, with `081481a`) and `ci/gate.py` says `gate: ok`.
- `tr grade --judge` judges a graded thesis once, inside its cap, and `tr grade` alone makes no call.
- ADR-004 lists what never enters a trace and, under Gaps, what the code does not enforce.
- The SLO review shows the four SLOs and the injected breach, and keeps the dev run out of the live numbers.
- The measured-cost page has a row per step with its run ids, and labels every estimate.
- The six Awaiting blocks name the command and the earliest date that will fill them.
- `git tag week-3-end` on your commit.

Nothing in this chapter reports a result that has not happened. The first live session closes on 2026-11-17, and its numbers go into the Awaiting blocks above as they arrive.
