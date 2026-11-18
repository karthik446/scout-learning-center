# Week 1: read what the model writes, then measure one change

> *"Educational software. Not investment advice. No orders are placed; trades are hypothetical and settled from historical bars by written rules. Past results, including these, do not predict future results."*

**You start at** `week-1-start`: a working `tr` that fetches bars and filings, computes a snapshot, asks a model for claims, checks them, shows them beside their sources, and runs experiments from config files.
**You end at** `week-1-end`: 20 labelled analyses, a failure taxonomy with counts, a new eval with a spec and tests, a prompt variant, one experiment with a paired interval, and two ADRs, a scope page and a fine-tuning note.
**Cash:** about $1.00 of model-API spend, through OpenRouter (the author's week: $1.12, including $0.07 of earlier pilot calls). **Time:** about 8 hours, most of it reading outputs.

Concepts this week, each explained in one or two lines with a link where it is first used: traces (§2), open and axial coding (§3, §4), code checks versus judges (§5), paired comparison with a clustered interval (§6), scope and the build-versus-tune question (§7). The main reading is Shankar & Husain, [*Evals for AI Engineers*](https://www.oreilly.com/library/view/evals-for-ai/9798341660717/), on error analysis and on evaluators. **Error analysis** means reading many real outputs, writing down what goes wrong and counting it before writing any eval, so the evals measure the failures you actually have; the free companion is Husain & Shankar, [*AI Evals: Everything You Need to Know*](https://hamel.dev/blog/posts/evals-faq/) (the "evals FAQ" below).

## Where everything is

Every file this chapter names, the tag it first appears at, and how to look at it without leaving your branch. `git show <tag>:<path>` prints a file as it is at a tag; `git diff week-1-start week-1-end --stat` lists everything week 1 adds.

| What | Path | Tag | See it |
|---|---|---|---|
| CLI (all `tr` commands) | `src/tradingresearch/cli.py` | week-1-start | `uv run tr --help`, `uv run tr <command> --help` |
| Keys and settings (`Secret`) | `src/tradingresearch/config.py` | week-1-start | `git show week-1-start:src/tradingresearch/config.py` |
| Indicators (`high_20`, `sma_*`) | `src/tradingresearch/indicators.py` | week-1-start | `git show week-1-start:src/tradingresearch/indicators.py` |
| Context, source table, claim checks (`validate_claims`, `item_for`) | `src/tradingresearch/analyze.py` | week-1-start | `git show week-1-start:src/tradingresearch/analyze.py` |
| Grader registry (`parsed`, `claims_valid`, `all_claims_valid`) | `src/tradingresearch/evals.py` | week-1-start | `git show week-1-start:src/tradingresearch/evals.py` |
| Experiment runner | `src/tradingresearch/experiment.py` | week-1-start | `git show week-1-start:src/tradingresearch/experiment.py` |
| Baseline prompt | `prompts/analyze-1.txt` | week-1-start | `git show week-1-start:prompts/analyze-1.txt` |
| Observation config | `experiments/observe.toml` | week-1-start | `git show week-1-start:experiments/observe.toml` |
| Labels (§3) | `evals/labels.csv` | week-1-end | `git show week-1-end:evals/labels.csv` |
| Taxonomy (§4) | `evals/taxonomy.md` | week-1-end | `git show week-1-end:evals/taxonomy.md` |
| Grader spec (§5) | `evals/specs/inferences_grounded.md` | week-1-end | `git show week-1-end:evals/specs/inferences_grounded.md` |
| New grader and tests (§5) | `src/tradingresearch/evals.py`, `tests/test_evals.py` | week-1-end | `git diff week-1-start week-1-end -- src/ tests/` |
| ADR-001 (§5) | `docs/adr/ADR-001-claim-checks.md` | week-1-end | `git show week-1-end:docs/adr/ADR-001-claim-checks.md` |
| Variant prompt (§6) | `prompts/analyze-2.txt` | week-1-end | `git diff week-1-end:prompts/analyze-1.txt week-1-end:prompts/analyze-2.txt` |
| Experiment config (§6) | `experiments/prompt-v2.toml` | week-1-end | `git show week-1-end:experiments/prompt-v2.toml` |
| ADR-002 (§6) | `docs/adr/ADR-002-prompt-analyze-2.md` | week-1-end | `git show week-1-end:docs/adr/ADR-002-prompt-analyze-2.md` |
| Scope, fine-tuning note (§7) | `docs/scope.md`, `docs/fine-tuning.md` | week-1-end | `git show week-1-end:docs/scope.md` |

The week-1-end files are the reference answers: write yours first, then compare.

---

## 1. Setup and a tour of the core (1 h, ≈ $0.02)

**Goal:** the repo runs on your machine with your keys, and you know what each command does without opening the source.

Do [SETUP.md](SETUP.md) first: the clone, the `.env` file and the free key checks. Week 1 runs at `week-1-start`, where `tr` knows one model provider, OpenRouter, so `OPENROUTER_API_KEY` must be in your `.env`, and the code at this tag only finds that file through `TR_ENV_FILE`:

```bash
cd tradingresearch && git checkout week-1-start
git switch -c my-week-1 week-1-start   # your own branch, so the commits you make this week stay reachable (SETUP.md)
export TR_ENV_FILE="$PWD/.env"         # once per shell, for every tag before week-6-end
uv sync
uv run pytest -q                       # 44 passed, 1 skipped: no network, no keys needed
uv run tr usage                        # free: the key's spend so far
uv run tr analyze AAPL                 # paid: one call, ≈ $0.016
```

The outputs below were captured with the repo checked out at `/private/tmp/tr-guide/tradingresearch`, so paths start there.

```text
analysis an_17f4a186735341a7  AAPL 2026-11-16  prompt=analyze-1  model=anthropic/claude-sonnet-5.5  route=openrouter:Google
context_tokens=1894  input_hash=sha256:342567c15d79…  spent=$0.0165
run=/private/tmp/tr-guide/data/runs/run_e72cabf720f94350.jsonl
  [fact     ] AAPL closed the session at 352.78.  <- src_3737a7c770eb2194
  [fact     ] The sma_200 sits at 301.719, well below the close.  <- src_b035a2c24290baec
  [fact     ] The close is 6.34635 ATR above sma_200, a large extension from the long-term average.  <- src_9ea38056ede57021
  [fact     ] The sma_20 is 346.642, below the close.  <- src_d952374e921009a6
  [fact     ] The sma_50 is 339.692, also below the close.  <- src_8d375151f7825551
  [inference] The close is above sma_20, sma_50 and sma_200, with the shorter averages sitting above the longer ones, which is consistent with an established uptrend.  <- cl_b085c75c4af84c32,cl_b82a63e0c1b44bf6,cl_5c2d6f62aa7f439a,cl_42b8b830dbcb46e5
  [fact     ] The rsi_14 reads 56.9998, a mid-range reading.  <- src_858e0bf6cad204cc
  [fact     ] The level_hvn_2 support area is at 343.41, below the close.  <- src_1cad32e483f64af9
  [fact     ] The regime_spy is bull-high, describing the broad market backdrop.  <- src_d7e151e78a501360
  [opinion  ] The setup looks constructive but somewhat extended relative to the long-term average, so a pullback toward nearby support would not be surprising.  <- cl_70b435e5322b46b8,cl_f8c267ead3c04d34,cl_9357533ae3784540
valid 10, rejected 2
  REJECTED c8: bad_placeholder: {dist}
  REJECTED c9: number_in_text: The dist_high_20_atr is {value}, so the close is below the 20-day high by about one ATR.
```

Now tour the core through the tool:

```text
$ uv run tr --help
usage: tr [-h] {sessions,bars,facts,snapshot,analyze,check,exp,usage} ...

tradingresearch: educational, not investment advice

positional arguments:
  {sessions,bars,facts,snapshot,analyze,check,exp,usage}
    sessions            NYSE sessions ending at a date
    bars                fetch and store daily bars
    facts               framed EDGAR facts for one concept
    snapshot            indicators, levels and regime for one ticker-day
    analyze             write a checked Analysis for one ticker-day (paid
                        call)
    check               every claim of an analysis beside the source values it
                        cites
    exp                 experiments as config
    usage               the OpenRouter key's total spend so far (log it before
                        and after paid runs)
```

Run `uv run tr snapshot AAPL --prompt` (free) and compare its SOURCES table with the claims above: every number the model wrote is a row there, with the `src_` id the claim cites, its name, its rounded value and its unit (without `--prompt` the command prints the snapshot as JSON, which has neither the ids nor the SEC rows). Then read three things, in this order:
- The layout in the guide's README, [Repo layout at the end of week 1](README.md#repo-layout-at-the-end-of-week-1): which module does what. (`git log --stat week-1-start` lists the files; it does not say what each one is for.)
- `git show week-1-start:prompts/analyze-1.txt`: the system prompt the model just followed.
- `check_one` in `src/tradingresearch/analyze.py`, the function that rejects a claim. Its rejection reasons are the strings it returns: `grep -n 'return "' src/tradingresearch/analyze.py` lists them (the lines after `def check_one`; the earlier ones are unit names), including the two above, `number_in_text` and `bad_placeholder`.

**Done when**
- `pytest` is green and `tr usage` prints a dollar amount.
- You can say, without opening code, which command fetches data, which one costs money and which one shows a trace (next section).
- You can find, in the SOURCES table of `tr snapshot --prompt`, the row behind each `src_…` id in your analysis. (If your analysis ran on an earlier session, pass the same `--session`.)

**Traps (real)**
- *A key in the shell.* `tr` reads `.env` in Python and wraps each key in `Secret` (`src/tradingresearch/config.py`), whose `repr` prints `Secret('***')`. Sourcing the file or pasting it into your coding agent puts the keys in shell history and transcripts. If `tr` says a key is missing, the message names the file it read; if that is not your `.env`, `TR_ENV_FILE` is not set in this shell. Fix the file or the export, not the key.
- *Read the rejections, not just the count.* c9 calls high_20 "the 20-day high", which the checks reject as a number in text; you will count this class in §4. c8 invented a placeholder, `{dist}`. The kept claims are not clean either: "a large extension" is a verdict the source does not state. (This run was made at `week-1-start` after the close on 2026-11-16, so it analyzed that day's session; the rest of the chapter uses 2026-11-12 and 2026-11-13.)

**Cash:** one call, $0.0165 in the author's run (the key moved from $61.761779 to $61.778267).

---

## 2. Observe 20 runs (1 h, ≈ $0.35)

**Goal:** a fixed set of 20 outputs to study: 10 tickers × 2 sessions, one prompt.

A **trace** is the full record of one model call: the input, the raw output, the parse, the checks (the evals FAQ, ["What is a trace?"](https://hamel.dev/blog/posts/evals-faq/#q-what-is-a-trace), defines it as everything from the request to the final response). You will not find failures by reading scores; you find them by reading traces. `tr check` (in `src/tradingresearch/cli.py`) is the trace viewer: every claim, accepted or rejected, beside the source value it cites.

The observation run is a config file you already have, `experiments/observe.toml` at week-1-start. `src/tradingresearch/experiment.py` turns it into one gigai-core run per arm:

```toml
# experiments/observe.toml
name = "observe"
model = "anthropic/claude-sonnet-5.5"
max_usd_per_arm = 1.00
tickers = ["AAPL", "MSFT", "NVDA", "AMZN", "JPM", "XOM", "UNH", "HD", "KO", "CAT"]
sessions = ["2026-11-12", "2026-11-13"]
graders = ["parsed", "claims_valid", "all_claims_valid"]

[[arms]]
name = "baseline"
prompt = "analyze-1"
```

```text
$ uv run tr usage
openrouter key usage $60.727235
$ uv run tr exp run experiments/observe.toml
experiment observe: 20 ticker-days x 1 arm(s), graders parsed, claims_valid, all_claims_valid, cap $1.00/arm
arm baseline   prompt=analyze-1 run=run_c40caab0968e44a3 spent=$0.3468 failed=0 analyses=20
    all_claims_valid=0.200 (n=20)  claims_valid=0.748 (n=20)  parsed=1.000 (n=20)
$ uv run tr usage
openrouter key usage $61.034119
```

Three graders ship with the core, registered by id in `src/tradingresearch/evals.py` (`GRADERS`) so a config can name them: `parsed` (the reply is valid JSON in the schema), `claims_valid` (share of claims that pass the checks) and `all_claims_valid` (1 only if every claim passes). A **grader** (an eval, or evaluator) scores one output against a written rule; these three are **code-checkable**: deterministic assertions over the parsed reply, free to run and exact about what they test (Husain, [*Your AI Product Needs Evals*](https://hamel.dev/blog/posts/evals/), on unit tests as the first level of evals). Only 4 of 20 analyses are fully valid. That is a number, not a diagnosis; now read the traces, one per analysis:

```text
$ uv run tr check an_33c484d450dc4322
an_33c484d450dc4322  AMZN 2026-11-13  prompt=analyze-1  run=run_c40caab0968e44a3  trace=trace_2e6a3df805204d7c
c1 [fact] ok
    text: AMZN closed the 2026-11-13 session at {value}.  value=266.66 USD
    src:  src_2d17a27b6eb4b8c3 close = 266.66 USD
c2 [fact] ok
    text: The sma_200 stood at {value}, below the close.  value=244.595 USD
    src:  src_c4705784d68df0f2 sma_200 = 244.595 USD
c3 [fact] ok
    text: The close was {value} ATR above sma_200, the farthest of the three moving averages.  value=2.42957 ATR
    src:  src_2596ae2f66f881c4 dist_sma_200_atr = 2.42957 ATR
c4 [inference] ok
    text: Price is above sma_20, sma_50 and sma_200, so the trend is up on all three horizons.
    from: c1, c2, c3 (The close of 266.66 exceeds sma_200, and the dist_sma_200_atr reading is positive, as are the sma_20 and sma_50 distances, which means price is above all three averages.)
...
kept 11, rejected 0
```

The journal lists your 20 ids: `sqlite3 data/journal.db "select analysis_id, ticker, session from analysis order by created_at desc limit 20"`. Without the `sqlite3` shell, the same query through Python: `uv run python -c "import sqlite3; [print(*row) for row in sqlite3.connect('data/journal.db').execute('select analysis_id, ticker, session from analysis order by created_at desc limit 20')]"`.

**Done when**
- The run shows `failed=0 analyses=20` and you logged `tr usage` before and after.
- You have read `tr check` for all 20, top to bottom.

**Traps (real)**
- *The cap refuses before spending.* The author's first try used `max_usd_per_arm = 0.60` and stopped at once: `gigai_core.budget.BudgetExceeded: $0.837568 does not fit the remaining $0.600000 of max_usd=0.6`. gigai-core plans the worst case (every call using its full output limit of 4,000 tokens), not the typical one. Actual spend was less than half of that plan. Set the cap from the plan, and set a credit limit on the key as the outer fence.
- *The key lags the run.* Right after the run the key had moved by only $0.3069, against the run's own $0.3468. Read again a minute later and the gap closes: by the next run the key stood at $61.074033, which is exactly $0.3468 above the starting value. OpenRouter books usage with a delay of tens of seconds. Log `tr usage` before a run, and log it after only once a minute has passed.
- *An analysis with zero rejections is not clean.* AMZN 2026-11-13 above passed every check, yet c4 names two averages nothing cites and c3 claims a comparison ("the farthest of the three") no source states.

**Cash:** $0.3468 for the author (the run's figure; the key agreed once its usage settled).

---

## 3. Open coding: one note per analysis (1.5 h, $0)

**Goal:** `evals/labels.csv` (new file; the reference is at week-1-end), one row per analysis, each note naming the first thing that goes wrong.

**Open coding** means writing what you see in your own words before deciding on categories. Read each trace and write the first failure and anything else odd. Do not count yet and do not invent class names up front; the classes come from the notes in §4. Write what a reader of the analysis would object to, not only what the checks rejected. The term comes from grounded theory in qualitative research (Corbin & Strauss, [*Basics of Qualitative Research*](https://www.sagepub.com/shop/buy-a-book/basics-of-qualitative-research-4-235578)); the evals FAQ (["Open Coding"](https://hamel.dev/blog/posts/evals-faq/#open-coding)) and Husain's [*A Field Guide to Rapidly Improving AI Products*](https://hamel.dev/blog/posts/field-guide/) apply it to model outputs, and the FAQ advises noting the first upstream failure because later errors often follow from it.

```csv
analysis_id,item,first_failure,note,classes
an_33c484d450dc4322,AMZN:2026-11-13,c4,"all claims pass the code checks, yet c4 says price is above sma_20 and sma_50 and cites only close and sma_200",inference_wider;judgement_in_fact
an_eb08e5bb6458451e,HD:2026-11-13,c4,"c4 names sma_20 uncited; c8 ""buyers finished the day in control"" is a judgement tagged fact; c11 opinion says ""20-day high""",inference_wider;judgement_in_fact;window_name
an_7871ad7042e44b48,UNH:2026-11-13,c2,"window names in c2, c6, c7; c10 says the close is closer to low_20 but 407.46 is above the 407.27 midpoint of 388 and 426.55; c9 names sma_50, ema_9, ema_21 uncited",window_name;other;inference_wider;judgement_in_fact;cascade
an_e353bba18c9f4fbd,KO:2026-11-13,-,"clean: every inference cites what it names, facts restate their source without a verdict",
```

Fill the `classes` column only after §4; on the first pass it stays empty. (The `cascade` tag on the UNH row is not a class; §4 says what it marks.)

**Done when**
- 20 rows, each with a concrete note that quotes a claim id.
- At least one note describes a failure the code checks did not reject.

**Traps (real)**
- *Rejection reasons are not notes.* `bad_derivation` (14 claims in the author's run) only means a parent claim was rejected; note the parent's failure instead.
- *Check before you label.* KO 2026-11-13 c5 says the close (99.25) is above high_20 (98.38). That looks wrong until you read how `high_20` is computed in `src/tradingresearch/indicators.py` (`grep -n high_20 src/tradingresearch/indicators.py`): over the prior 20 sessions, excluding today. The claim is right.

**Cash:** $0. **Reference:** `git show week-1-end:evals/labels.csv` (all 20 rows).

---

## 4. Axial coding: a taxonomy with counts (1 h, $0)

**Goal:** `evals/taxonomy.md`: 5 to 8 failure classes, each with a definition, a claim count, an analysis count, what catches it today and one real example.

**Axial coding** groups the open-coded notes into classes and counts them; the classes, each with a definition and counts, are the **failure taxonomy** (the evals FAQ, ["Axial Coding"](https://hamel.dev/blog/posts/evals-faq/#axial-coding)). In grounded theory the term means relating categories to each other ([Wikipedia, *Axial coding*](https://en.wikipedia.org/wiki/Axial_coding)); in evals work it is this grouping. The counts decide what you work on: the largest class that you can measure cheaply comes first. Count claims and analyses separately; a class with many claims in few analyses is a different problem from one that touches everything.

The author's table, from `evals/taxonomy.md` at week-1-end (229 claims, 20 analyses):

| # | Class | Claims | Analyses | Caught today by | Example |
|---|---|---|---|---|---|
| 1 | window_name: an indicator named by its window ("200-day", "20-day", "14-day RSI") | 31 | 15 | code (`number_in_text`) | JPM 11-12 c2 "The 200-day average, sma_200, stood at {value}" |
| 2 | inference_wider: an inference names indicators its parents never cite | 15 | 15 | nothing directly; 9 are rejected only because a parent failed | AMZN 11-13 c4 "above sma_20, sma_50 and sma_200" from close and sma_200 |
| 3 | judgement_in_fact: a fact carries a verdict the source does not state | 33 | 19 | nothing (judge later, ADR-001) | HD 11-13 c8 "buyers finished the day in control" |
| 4 | opinion_cites: an opinion lists derived_from | 5 | 5 | code (`not_a_claim`, record rules) | CAT 11-13 c12 |
| 5 | label_in_value: a text label put in {value} with value null | 4 | 4 | code (`empty_placeholder`) | KO 11-12 c9 "labeled {value} on this date, which is bull-high" |
| 6 | number_outside_value: a number written in prose or in steps | 5 | 3 | code for prose (3); nothing for steps (2) | XOM 11-13 c10 steps quote revenue no parent cites |
| 7 | other: unknown source id, a wrong comparison, a backwards sign | 3 | 3 | code for the unknown source (1) | UNH 11-13 c10 "closer to the low side" (it is above the midpoint) |

Not a class: `bad_derivation` (14 claims) is a consequence of classes 1, 6 and 7. Not a class either: the `cascade` tag that 12 rows of `labels.csv` carry after their classes. It marks an analysis in which some inference or opinion derives from a rejected claim, so one failure took later claims down with it (that is what `bad_derivation` rejects; in NVDA 11-12 the dependent claims were already rejected for window names). The taxonomy does not define it and no count in the table includes it. The file also records the run's rates and what the counts imply; read it with `git show week-1-end:evals/taxonomy.md`. Then go back and fill the `classes` column of `labels.csv`.

**Done when**
- 5 to 8 classes, counts that add up from `labels.csv`, and for each class one real claim quoted.
- You can name the largest class code already catches, and the largest it misses.

**Traps (real)**
- *A class per rejection reason.* Grouping by the validator's reasons hides classes 2 and 3 entirely, because the validators never fire on them.
- *Judgement counts are soft.* Class 3 depends on where you draw the line ("well above" is a comparison; "a large extension" is a verdict). Write the line down in the class definition so a judge (next section) can be trained on it in week 4.

**Cash:** $0.

---

## 5. First evals: base evals, ADR-001, and your new one (2 h, $0)

**Goal:** decide which classes get code checks and which wait for a judge (`docs/adr/ADR-001-claim-checks.md`), then specify one new code eval and have your coding agent build it.

**Code checks versus judges.** A code check is free, deterministic and exact for questions about strings and ids. An **LLM judge** (LLM-as-a-judge: a second model call that grades the output against a rubric) can read wording, but it costs a call per output and is itself a classifier that is wrong some of the time; its score means nothing until its agreement with your labels is measured (the evals FAQ, ["How do I know if I can trust my automated eval?"](https://hamel.dev/blog/posts/evals-faq/#q-how-do-i-know-if-i-can-trust-my-automated-eval); Zheng et al., [*Judging LLM-as-a-Judge*](https://arxiv.org/abs/2306.05685), on judge biases; Husain, [*Using LLM-as-a-Judge For Evaluation*](https://hamel.dev/blog/posts/llm-judge/), on building one). So: code for everything mechanical, a judge only for what needs reading, and only once you have labels to validate it; Anthropic's [*Define success criteria and build evaluations*](https://platform.claude.com/docs/en/test-and-evaluate/develop-tests) ranks grading methods the same way. Write that decision as ADR-001. An **ADR** (architecture decision record) is a short file per decision, kept in the repo, giving the context, the decision and its consequences, so a later reader knows why (Nygard, [*Documenting Architecture Decisions*](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions); [adr.github.io](https://adr.github.io/)). Reference: `git show week-1-end:docs/adr/ADR-001-claim-checks.md`.

The base evals are the three in `src/tradingresearch/evals.py` at week-1-start. Your new one targets class 2, the largest mechanical failure nothing measures. Write the spec first. An **eval spec** fixes, before any code, the failure it measures, the unit and score, the exact rule and the acceptance checks that show the grader is right; it plays the role of the success criteria in Anthropic's guide above. The author's, `evals/specs/inferences_grounded.md` at week-1-end, in full:

```markdown
# Eval spec: inferences_grounded

**Failure it measures:** taxonomy class 2. An inference names an indicator (sma_20, ema_9, ...) that none of its
parents cite, so the conclusion rests on a number the reader cannot trace. In the observe run 15 of 20 analyses
have one, and 6 of those pass every existing check.

**Unit and score:** one analysis. Score 1 if every inference is grounded, 0 if any is not (binary, so experiments
compare it with McNemar). The explanation lists the claims and names, e.g. `c4: sma_20, sma_50`.

**Rule:** for each claim tagged `inference`:
1. allowed = the table names of every source cited by its `derived_from` claims, followed recursively through
   parent inferences. A cited `dist_<name>_atr` also allows `<name>`.
2. used = every table name containing an underscore that appears as a whole token in `text` or `steps`.
   Names without an underscore (close, open) are skipped because they are also English words.
3. The inference is grounded if used ⊆ allowed.

**Inputs:** the parsed reply and `expected["names"]` (source id → table name), added to each dataset item by
`item_for`. Output that did not parse raises CannotGrade (it is already counted by `parsed`).

**Acceptance (all must hold before the grader is registered):**
- On `run_c40caab0968e44a3` it flags exactly the 15 analyses labelled `inference_wider` in `labels.csv`, no more.
- AMZN 2026-11-13 c4 gives `c4: sma_20, sma_50`; MSFT 2026-11-13 c6 (cites all four averages it names) passes.
- `sma_20` does not match inside `sma_200` or `dist_sma_20_atr`.
- Tests in `tests/test_evals.py` use claims copied from that run, not invented ones.

**Out of scope:** whether the inference is true (a judge question), and numbers in steps (class 6, 2 claims; too
few to pay for a grader this week).
```

Give the spec, `src/tradingresearch/evals.py` and `src/tradingresearch/analyze.py` to your coding agent and ask for the grader, its registration in `GRADERS` and tests in `tests/test_evals.py`. Then check the acceptance criteria yourself against the real run, not only the tests. No `tr` command regrades a stored run at this tag, so do it from Python, at $0: the run file from §2 holds every prompt and reply, and the names the grader needs are in each prompt's SOURCES table (`source_table` in `cli.py` reads them back; the items stored in §2 have no `expected["names"]` yet, see the trap below). Put your run id in and run it from the repo root:

```bash
uv run python - <<'EOF'
from pathlib import Path
from gigai_core import open_run
from tradingresearch.cli import source_table
from tradingresearch.evals import InferencesGrounded
run = open_run(Path("data/runs/run_c40caab0968e44a3.jsonl"))   # your observe run, from the §2 `arm baseline` line
grader = InferencesGrounded()
flagged = 0
for sample in sorted(run.samples, key=lambda s: run.items[s.item_id].id):
    item = run.items[sample.item_id]
    names = {sid: name for sid, (name, _, _) in source_table(item.prompt).items()}
    score = grader.grade(sample, {"names": names})
    flagged += score.value == 0
    print(f"{item.id:<16} {int(score.value)}  {score.explanation or ''}".rstrip())
print(f"flagged {flagged} of {len(run.samples)}")
EOF
```

On the author's run it prints:

```text
AAPL:2026-11-12  0  c8: sma_20, sma_50
AAPL:2026-11-13  0  c4: sma_20, sma_50
AMZN:2026-11-12  0  c4: sma_20, sma_50
AMZN:2026-11-13  0  c4: sma_20, sma_50
CAT:2026-11-12   0  c4: sma_20, sma_50
CAT:2026-11-13   1
HD:2026-11-12    0  c4: sma_20
...
UNH:2026-11-13   0  c9: ema_21, ema_9, sma_50
XOM:2026-11-12   1
XOM:2026-11-13   0  c5: sma_50
flagged 15 of 20
```

The 15 flagged analyses are exactly the 15 labelled `inference_wider` by hand: the grader agrees with the labels on all 20. That agreement, not a passing test, is what makes the number usable.

**Done when**
- ADR-001 is written.
- The spec is written before the code, and its acceptance criteria hold on the real run.
- `uv run pytest -q` is green (the author: 48 passed, 1 skipped) and `inferences_grounded` is in `GRADERS`.

**Traps (real)**
- *Words that are also names.* `close` is a table name and an English word. The rule only matches names containing an underscore, so "the close" never counts as a citation problem.
- *Derived names.* A parent citing `dist_sma_200_atr` lets the child talk about `sma_200`. Without that, the grader flags correct inferences.
- *Changing the item changes the dataset.* Adding `expected["names"]` in `item_for` (`git diff week-1-start week-1-end -- src/tradingresearch/analyze.py`, 3 lines) changes every item's digest, so runs made before and after cannot be compared (§6). Make dataset changes before the experiment, not between its arms.

**Cash:** $0; the script above grades the stored run without a model call. **Reference:** class `InferencesGrounded` and its tests, `git diff week-1-start week-1-end -- src/tradingresearch/evals.py tests/test_evals.py`.

---

## 6. First experiment: baseline vs one variant (1.5 h, ≈ $0.70)

**Goal:** a variant prompt `prompts/analyze-2.txt`, an experiment config `experiments/prompt-v2.toml`, a paired interval, and a decision in `docs/adr/ADR-002-prompt-analyze-2.md`.

**Change one thing.** The taxonomy says the two largest mechanical classes are window names (31 claims) and ungrounded inferences (15 analyses). Copy `prompts/analyze-1.txt` to `prompts/analyze-2.txt` and change only the rules aimed at classes 1, 2, 4 and 5. It is one change, a prompt version, even though it carries several rules. A **prompt version** is a prompt kept as its own file in git, so an experiment arm names exact text and a result can be traced to it (the evals FAQ, ["How should I version and manage prompts?"](https://hamel.dev/blog/posts/evals-faq/#q-how-should-i-version-and-manage-prompts)). The author's change, in full (`git diff week-1-end:prompts/analyze-1.txt week-1-end:prompts/analyze-2.txt`):

```diff
@@ -6,9 +6,11 @@ Rules for every claim:
   If the claim has a number, put it in "value" and "unit" exactly as in the cited source.
 - tag "inference": a conclusion drawn from earlier claims. derived_from lists their ids; steps says how in one
   sentence; source_ids is empty. value is null unless the number appears in a cited source.
-- tag "opinion": a judgement. value is null and the text contains no digits.
+  An inference may name only indicators that its derived_from claims cite. To use sma_20, first state it as a fact.
+- tag "opinion": a judgement. value is null, the text contains no digits, and derived_from and source_ids are empty.
 - Write numbers ONLY in "value". In "text", refer to it as {value}. Name indicators by their table name
-  (sma_200, high_20, rsi_14). Dates as YYYY-MM-DD are allowed.
+  (sma_200, high_20, rsi_14); never by their window ("200-day", "20-day", "14-day"). Dates as YYYY-MM-DD are allowed.
+- {value} is the only placeholder, and only when value is set. A label such as the regime goes in the text.
 - Use only the source_ids in the table. Do not invent sources, news or events.
 Write 6 to 12 claims. Ids are c1, c2, ... in order; an inference may only derive from earlier ids.
 This is educational research, not investment advice. Do not recommend buying or selling.
```

Each added line answers one taxonomy row: the inference line class 2, the opinion line class 4, the window line class 1, the placeholder line class 5. A config arm names a prompt version by file stem (`prompt = "analyze-2"` loads `prompts/analyze-2.txt`), and the runner checks every arm's file before spending.

**Why a paired comparison.** Both arms answer the same 20 ticker-days, so compare them item by item, not mean against mean: the variation between stocks cancels out and the interval narrows (Miller, [*Adding Error Bars to Evals*](https://arxiv.org/abs/2411.00640), on paired differences, clustered errors and power). Days of the same stock are not independent, so the interval is clustered by ticker (`cluster_id` in `item_for`). gigai-core's `compare` needs at least 10 clusters, which is why the shortlist has 10 tickers. For a binary metric it uses McNemar's test, for a share it uses Wilcoxon, and it reports the minimum detectable effect (MDE): the smallest difference this many items could reliably see.

In one line each:
- **Confidence interval**: the range of differences the data are consistent with at the stated level ([Wikipedia](https://en.wikipedia.org/wiki/Confidence_interval)).
- **Cluster bootstrap**, how `compare` gets the interval: resample whole tickers with replacement many times, recompute the mean difference each time, and read the interval off that spread ([Wikipedia, *Bootstrapping*](https://en.wikipedia.org/wiki/Bootstrapping_(statistics)), "Cluster data").
- **McNemar's test** uses only the items where the arms disagree ([Wikipedia](https://en.wikipedia.org/wiki/McNemar%27s_test)); the **Wilcoxon signed-rank test** ranks the per-item differences ([Wikipedia](https://en.wikipedia.org/wiki/Wilcoxon_signed-rank_test)).
- **Power** is the chance that a test detects a real effect of a given size; the **MDE** is the effect size at which power reaches the usual target, at the usual significance level ([Wikipedia, *Power*](https://en.wikipedia.org/wiki/Power_(statistics)); Miller, "Power analysis").

Write the decision rule down before running. That is **pre-registration**: the primary metric (the one that decides) and any guard metric (one that must not get worse) are fixed before you see results, because the same data cannot both suggest a rule and confirm it ([COS, *Preregistration*](https://www.cos.io/initiatives/prereg)). The author's config, `experiments/prompt-v2.toml` at week-1-end:

```toml
# Week 1, step 6: does analyze-2 (four rules from the taxonomy) beat analyze-1 on the same 20 ticker-days?
# Pre-registered before the run (ADR-002): primary metric all_claims_valid; guard metric parsed must not drop.
name = "prompt-v2"
model = "anthropic/claude-sonnet-5.5"
max_usd_per_arm = 1.00
tickers = ["AAPL", "MSFT", "NVDA", "AMZN", "JPM", "XOM", "UNH", "HD", "KO", "CAT"]
sessions = ["2026-11-12", "2026-11-13"]
graders = ["parsed", "claims_valid", "all_claims_valid", "inferences_grounded"]

[[arms]]
name = "baseline"
prompt = "analyze-1"

[[arms]]
name = "variant"
prompt = "analyze-2"
```

(The file in the repo says "three rules" in that first comment; the diff above adds four, one per class listed under it, so the guide says four.)

```text
$ uv run tr usage
openrouter key usage $61.074033
$ uv run tr exp run experiments/prompt-v2.toml
experiment prompt-v2: 20 ticker-days x 2 arm(s), graders parsed, claims_valid, all_claims_valid, inferences_grounded, cap $1.00/arm
arm baseline   prompt=analyze-1 run=run_c5fb0100989a4e0d spent=$0.3594 failed=0 analyses=20
    all_claims_valid=0.150 (n=20)  claims_valid=0.814 (n=20)  inferences_grounded=0.300 (n=20)  parsed=1.000 (n=20)
arm variant    prompt=analyze-2 run=run_537a07e6ec264989 spent=$0.3283 failed=0 analyses=20
    all_claims_valid=0.850 (n=20)  claims_valid=0.977 (n=20)  inferences_grounded=0.950 (n=20)  parsed=1.000 (n=20)
compare baseline -> variant: 20 items, 10 clusters
    parsed             1.000 -> 1.000  diff +0.000  CI [+0.000, +0.000] (95%)  mcnemar p=1  mde=-
    claims_valid       0.814 -> 0.977  diff +0.162  CI [+0.085, +0.243] (95%)  wilcoxon p=0.00104  mde=0.111
    all_claims_valid   0.150 -> 0.850  diff +0.700  CI [+0.450, +0.950] (95%)  mcnemar p=0.000122  mde=0.494
    inferences_grounded 0.300 -> 0.950  diff +0.650  CI [+0.350, +0.900] (95%)  mcnemar p=0.000977  mde=0.511
$ uv run tr usage
openrouter key usage $61.729215
```

5 min 52 s wall time for 40 calls.

**Read the interval.** The primary metric rose by 0.70, and even the low end of its interval (+0.45) is far above zero; `parsed` held at 1.0. By the rule written before the run, analyze-2 ships. Note the MDE of 0.494 for `all_claims_valid`: with 20 items, a real improvement of 0.2 would have been invisible. A small effect needs a bigger run, not a second look at this one. Then read the variant's traces with `tr check`: its three remaining failures are two `unknown_source` and one `number_in_text`, and one analysis still has an ungrounded inference (`c4: sma_200`). Write ADR-002: the pre-registered rule, the table, the decision, what to watch (reference: `git show week-1-end:docs/adr/ADR-002-prompt-analyze-2.md`).

**Done when**
- The config names the primary metric before the run.
- Both arms show `failed=0`, and the compare line reports 10 clusters.
- ADR-002 states the decision with the interval, not only the means.

**Traps (real)**
- *The baseline moved.* analyze-1 scored `all_claims_valid` 0.200 in the observe run and 0.150 here, on the same items. Same prompt, same data, no seed: the model's output varies run to run. That is why both arms run fresh in one experiment instead of reusing the observe run as the baseline.
- *Ablations that change the input cannot be paired.* An **ablation** removes one component to measure what it contributes ([Wikipedia](https://en.wikipedia.org/wiki/Ablation_(artificial_intelligence))). Dropping a block of rows from the prompt (say, the EDGAR facts) changes every item, so the two arms have different datasets and `compare` refuses with `different_dataset`. A system-prompt variant keeps the dataset identical; a context ablation needs its own design (week 5).
- *Clustering by the wrong key.* Clustering by session would give 2 clusters, and `compare` refuses with `too_few_clusters` (the minimum is 10).
- *The key lags here too.* Right after the run the key showed $0.6552; once usage settled it showed $0.6877, the runs' combined figure.

**Cash:** $0.6877 for the author ($0.3594 + $0.3283; the key agreed once its usage settled).

---

## 7. Scope one-pager and the fine-tuning question (1 h, $0)

**Goal:** `docs/scope.md` (one page) and `docs/fine-tuning.md` (half a page).

**Scope** says who the user is, what job the system does, what is out of scope and what quality and cost bars a change must meet, with this week's measured numbers. A forward-deployed engineer writes this before building and revisits it when the numbers change; see OpenAI, [*What forward deployed engineering means*](https://openai.com/index/forward-deployed-engineering-means/) ("Start with the outcome"; scoping against key evals), and the AI Engineer [topic page on forward-deployed engineering](https://ai.engineer/topics/forward-deployed-engineering). Out of scope here, by design: orders, paper trading, signals, price targets, backtests as evidence, news.

**When does fine-tuning pay off?** **Fine-tuning** continues training a pre-trained model's weights on your own examples ([Wikipedia](https://en.wikipedia.org/wiki/Fine-tuning_(deep_learning))); the **build-versus-tune** question is whether the next gain comes from the system around the model (prompt, context, checks) or from changing the model. OpenAI's [*Model optimization*](https://developers.openai.com/api/docs/guides/model-optimization) guide orders the work the same way: evals first, then prompting, and fine-tuning only for some tasks. Answer from your taxonomy, not in general. In the author's run every mechanical class is either rejected by code or fixed by a prompt rule, so tuning is not the next step. Write the conditions that would change that: a class that survives several prompt iterations at a rate the interval shows is real, hundreds of labelled passing examples (the journal and `all_claims_valid` already select them), volume high enough that per-call cost matters (at $0.017 per analysis it does not yet), and an eval suite stable enough to judge the tuned model on the same paired items. Name the number you will watch: cost per fully valid analysis.

**Done when**
- The scope page fits on one screen and quotes this week's measured quality and cost.
- The fine-tuning note gives conditions you could check, not opinions.
- `git tag my-week-1-end` on your commit, with `pytest` green (`week-1-end` is the reference tag and already exists in the clone).

**Traps (real)**
- *Quoting the plan instead of the run.* The guide's budget prices `tr analyze` at ≈ $0.10 per ticker-day; the measured cost is $0.017. The scope page quotes measured numbers only, and says which run they come from.

**Cash:** $0. **Reference:** `git show week-1-end:docs/scope.md`, `git show week-1-end:docs/fine-tuning.md`.

---

## Week 1 cash, as measured by the author (OpenRouter key readings)

| Step | Key before | Key after | Spent |
|---|---|---|---|
| first pilot (v1, four single calls) | $60.661639 | $60.727235 | $0.0656 |
| §2 observe, 20 calls | $60.727235 | $61.074033 | $0.3468 |
| §6 experiment, 40 calls | $61.074033 | $61.761779 | $0.6877 |
| §1 one `tr analyze` at `week-1-start` | $61.761779 | $61.778267 | $0.0165 |
| **Week 1 total** | | | **$1.1166** |

Each "after" figure was read once usage had settled; a reading taken right after a run comes out low (see §2).
