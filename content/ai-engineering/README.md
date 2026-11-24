# Learn AI engineering end to end: a 60-day track

This track is for a working software engineer who wants to do applied-AI work: put a language model inside a real system and know, with numbers, whether each change helped. At the end you can read model output and turn it into failure classes, write evals, an LLM judge and the check that validates it, trace and cost a pipeline, give a model tools, retrieval and guardrails, route between models and release the result. Each week pairs readings with building one part of a real system, and you measure every change in a paired experiment before you keep it.

> *"Educational software. Not investment advice. No orders are placed; trades are hypothetical and settled from historical bars by written rules. Past results, including these, do not predict future results."*

## What you learn, week by week

| Week | Skill | What you build that week |
|---|---|---|
| [Week 1](week-1.md) | Error analysis and evals | The first evals on `tr analyze`: 20 analyses read and labelled, a failure taxonomy with counts, one eval with a spec and tests, and a prompt variant measured in a paired experiment |
| [Week 2](week-2.md) | LLM judges and CI gates | Starting from a shipped `tr thesis`, `tr reconcile`, screen and CI gate: the P2-P4 process checks as code with tests, the P1 rubric and a draft judge (ADR-003), a review of the thesis prompt on real output, a pre-registered teacher bake-off, and the runbook that starts the live after-close stream |
| [Week 3](week-3.md) | Observability and SLOs | The P1 judge as code and `tr grade --judge`, ADR-004 on what never enters a trace, an SLO review with an injected breach, and a measured-cost page, operating the shipped traces, `tr grade`, `tr report`, `tr slo` and `tr label` |
| [Week 4](week-4.md) | Agents, tools and MCP | `analyze` as a tool-using agent compared with the fixed-context version on the same tickers in one paid run (ADR-005), the first pre-registered rule change with its challenger arm, and an optional MCP server over the journal |
| [Week 5](week-5.md) | Context engineering | Over the shipped playbook and headline context: per-section grounding graders and a pre-registered three-arm ablation that drops headlines and EDGAR facts on the same ticker-days, with a paired interval per variant (ADR-007) |
| [Week 6](week-6.md) | Retrieval and RAG evals | Retrieval over filings and headlines (BM25, dense, hybrid, reranked) with recall@k on 30 hand-labelled queries, and a citation-accuracy eval |
| [Week 7](week-7.md) | Prompt injection and guardrails | Over the shipped guard layer: 30 injected headlines, a rule list with two fetched-text rules, an `injection_resisted` grader with its spec, and a pre-registered five-arm run measured before and after the defences (ADR-010) |
| [Week 8](week-8.md) | Routing, caching and cost | Model routing, prompt caching and the cost table, compared on $ per ticker-day, latency and quality |
| [Week 9](week-9.md) | Release and self-hosting economics | The frozen rules, the scorecards exported as aggregates, the release checklist as code and the README as a reference architecture; the self-check covers the API vs self-host break-even |

## The project

`tradingresearch` (repo `tradingresearch`, command `tr`) is a stock research desk that runs on your own machine. After the US close, code computes every number about a stock (indicators, price levels and the market regime from Alpaca bars, fundamentals from SEC EDGAR), and a language model writes short claims about it. Each claim is tagged fact, inference or opinion, must cite the numbers it rests on, and is checked by code before it is stored. Later weeks turn analyses into theses with an entry, a stop, a target and a holding period; written rules settle each thesis from real bars, and each is graded on the outcome (R after costs) and on the process (did the stated reason play out).

The project is the vehicle, not the point. Prices settle claims within days, so you cannot fool yourself for long: "No edge detected, with its [confidence interval](https://en.wikipedia.org/wiki/Confidence_interval)" (the range of differences the data are consistent with; see *The loop* below) is a valid result, and the likely one. The pace and the readings are in [SCHEDULE.md](SCHEDULE.md); the design decisions behind the project (records, rules, sources and costs) are recorded in the repo's ADRs, `docs/adr/`, as each chapter writes them.

**Code:** [github.com/karthik446/tradingresearch](https://github.com/karthik446/tradingresearch) (public; MIT licence). Each chapter links its start tag, its reference tag and the chapter diff.

## You start from a working core

You do not type the plumbing. The core is prebuilt and tagged: data, indicators, the journal, the model call, the claim checks, the trace viewer (a trace is the full record of one model call; see *The loop* below) and the experiment runner. Each chapter starts at a tag and ends at the next one. [SETUP.md](SETUP.md) has the clone, the settings file and the free key checks; after it you move between tags with git:

```bash
git checkout week-1-start                                     # week 1 starts here
git switch -c my-week-1 week-1-start                          # your own branch for the chapter, so your commits stay reachable (SETUP.md explains)
git tag -l                                                    # every tag, alphabetically: week-1-end, week-1-start, week-2-end, ...
git show week-1-end:prompts/analyze-2.txt                     # read one file of the reference answer without checking it out
git diff week-1-start week-1-end --stat                        # every file a chapter adds
git diff week-1-start week-1-end -- prompts/                   # what changed in one folder
```

You read the core through the tool, not through a code listing: `tr --help`, `tr <command> --help`, `git log --stat` and the docstrings the help points to. What you write is the part that needs judgement: labels and a **failure taxonomy** (the classes of what goes wrong, each with a definition and counts; Husain & Shankar, [*AI Evals: Everything You Need to Know*](https://hamel.dev/blog/posts/evals-faq/), "Axial Coding"), **eval specs** (what a grader measures, how it scores and how you know the grader is right; Anthropic, [*Define success criteria and build evaluations*](https://platform.claude.com/docs/en/test-and-evaluate/develop-tests)) with acceptance checks, prompts, experiment configs and **decision records** (ADRs: one short file per decision with its context, the decision and its consequences; [adr.github.io](https://adr.github.io/)). When a chapter needs new code, such as a grader, you write the spec and the acceptance checks, then have your own coding agent (Claude Code, Codex or similar) write it against them. The reference version is at the chapter's end tag; each section ends with the `git show` or `git diff` command that prints it. Read it after yours passes.

Each chapter opens with a table, *Where everything is*: every file the chapter names, its path, the tag it first appears at, and the command to see it.

## Labs: optional practice in small steps

Alongside each chapter the public repo's `labs` branch has short exercises that build the chapter's code one checked step at a time: a stub to fill in, a pytest check with a message that teaches, hints that unlock after failed runs, and a solution that unlocks after ten. They cost nothing: no key and no model call, because the exercises regrade recordings of the author's runs. Week 1 has 19 exercises in four labs; the labs for later weeks are added week by week. Start with the `labs` branch and `tr lab`:

```bash
git clone https://github.com/karthik446/tradingresearch.git && cd tradingresearch
git checkout labs
uv sync
.venv/bin/tr lab start w1l1
```

The chapters stand on their own, so the labs are optional. [Week 1](week-1.md) has its lab table; the commands are in the [labs README](https://github.com/karthik446/tradingresearch/blob/labs/labs/README.md).

## The loop

Every chapter runs the same loop, on a different part of the system:

1. **Observe.** Run the system on real inputs and read the **traces**, the full record of each model call from input to checked output (`tr check <analysis_id>`; the evals FAQ, ["What is a trace?"](https://hamel.dev/blog/posts/evals-faq/#q-what-is-a-trace)).
2. **Error analysis.** Read real outputs and find what goes wrong before writing any eval (Husain, [*A Field Guide to Rapidly Improving AI Products*](https://hamel.dev/blog/posts/field-guide/)). Write a note per output (open coding), then group the notes into failure classes with counts (axial coding). Both terms come from grounded theory (Corbin & Strauss, [*Basics of Qualitative Research*](https://www.sagepub.com/shop/buy-a-book/basics-of-qualitative-research-4-235578), on open coding; [Wikipedia, *Axial coding*](https://en.wikipedia.org/wiki/Axial_coding)).
3. **Specify an eval.** Pick the class that matters, write what it measures, how it scores and how you will know the grader is right.
4. **Change one thing.** A prompt, a context field, a model, a tool.
5. **Run the experiment.** Both arms on the same ticker-days, from a config file: `tr exp run experiments/<name>.toml`.
6. **Read the interval.** A paired difference (both arms on the same items, compared item by item) with its [confidence interval](https://en.wikipedia.org/wiki/Confidence_interval) and minimum detectable effect (the smallest difference the run could reliably see), never one run's score (Miller, [*Adding Error Bars to Evals*](https://arxiv.org/abs/2411.00640)).
7. **Decide.** Write an ADR: ship, drop, or measure more, and why.

Experiments are config files, not scripts: a name, a model, a cash cap per arm, the tickers, the sessions, the graders and the arms. The runner refuses before spending if the cap cannot cover the worst case, and refuses to compare arms that did not see the same inputs.

## Setup

[SETUP.md](SETUP.md) covers it once: Python 3.12 and uv, the accounts (Alpaca Basic for bars, US residents only; a SEC EDGAR User-Agent; a model-API key with a spend limit), one clone with one `.env` file that `tr` reads itself, the free checks that prove each key, and which provider serves which week. Weeks 1 to 5 run through OpenRouter; from week 6 on `TR_PROVIDER` picks Anthropic or OpenRouter. Do it before week 1.

## Repo layout at the end of week 1

Later chapters add modules (`screen`, `thesis`, `reconcile`, `grade`, `learn`) and more ADRs. Files marked *you* first appear at `week-1-end` (read one with `git show week-1-end:<path>`); everything else ships at `week-1-start`.

```text
tradingresearch/
├── pyproject.toml          # deps, the `tr` script, pytest markers
├── uv.lock
├── prompts/
│   ├── analyze-1.txt       # the shipped system prompt
│   └── analyze-2.txt       # you: the variant your taxonomy suggests
├── experiments/
│   ├── observe.toml        # 10 tickers x 2 sessions, one arm: the observation run
│   └── prompt-v2.toml      # you: baseline vs variant
├── src/tradingresearch/
│   ├── config.py           # settings; keys as Secret, read from the env file only
│   ├── hashing.py          # digests and ids (gigai-core style)
│   ├── records.py          # the core records (gigai-core CoreModels)
│   ├── journal.py          # SQLite journal: append-only tables enforced by triggers
│   ├── sessions.py         # the NYSE calendar (exchange_calendars XNYS)
│   ├── alpaca.py           # daily bars into the journal
│   ├── edgar.py            # SEC company facts, selected by frame
│   ├── indicators.py       # indicators, levels, regime
│   ├── openrouter.py       # OpenRouter as a gigai-core ModelProvider
│   ├── analyze.py          # context, source table, claim validators, `tr analyze`
│   ├── evals.py            # the grader registry (you add inferences_grounded via your agent)
│   ├── experiment.py       # TOML config -> one gigai-core run per arm -> paired compare
│   └── cli.py              # the `tr` command
├── tests/                  # no network by default
├── evals/                  # you: labels.csv, taxonomy.md, specs/
├── docs/                   # you: scope.md, fine-tuning.md, adr/ADR-001..., adr/ADR-002...
└── data/                   # git-ignored: journal.db, runs/, traces/
```

`data/` holds Alpaca-derived content and model traces. Alpaca's terms forbid redistributing its content, so nothing under `data/` is ever committed or published.

## How the chapters work

- One chapter per week of the schedule (`week-1.md`, `week-2.md`, ...), one section per build step, in order. Each concept is explained where you first use it, with a link to the reading that covers it in depth.
- Each section has: the goal and time, what to do, the commands with real output, **done when** checks, traps that actually happened, the cash it costs, and the command that prints the reference.
- **The outputs are real.** Each was pasted from a run on 2026-11-16 and trimmed, never edited. Your numbers will differ because your sessions differ, and the model's prose differs even on the same day: the Claude routes on OpenRouter take no seed or temperature (a seed fixes the sampling randomness, temperature sets how much of it there is; [OpenRouter, *Parameters*](https://openrouter.ai/docs/api_reference/parameters)).
- In the author's runs `TR_DATA_DIR` pointed to a scratch folder, so some paths start with `/private/tmp/tr-guide/data`, and the repo was checked out at `/private/tmp/tr-guide/tradingresearch`.
- Tests never touch the network: tests marked `live` are excluded by default. Steps that cost money say so, with the amount.

## Cash per week

All amounts are model-API spend; market data (Alpaca Basic) and filings (SEC EDGAR) cost $0. Weeks 1 to 5 run through OpenRouter; from week 6 on the provider is your choice (teachers and the judge stay on OpenRouter), see [SETUP.md](SETUP.md#which-provider-runs-which-week). The track's budget is about **$61 in total** (including +50% for development and reruns) with a **$10 cap per session**. The budget prices items one at a time; the "one-off" column is the sum of those item estimates (the author's arithmetic).

| Week | One-off build items (budget estimates) | One-off sum | Running from this week on |
|---|---|---|---|
| 1 | `tr analyze` on 1 ticker ≈ $0.10; open coding on 20 ticker-days ≈ $0.90 | ≈ $1.00 | — |
| 2 | `tr thesis` ≈ $0.30 | ≈ $0.30 | the after-close live stream from day 10: ≈ $0.75 per session (10 tickers × $0.075) |
| 3 | — | — | `tr grade`: ≈ $0.013 per closed trade |
| 4 | tool-using `analyze` ≈ $1; judge agreement ≈ $1.20 | ≈ $2.20 | challenger arm from day 22: ≈ $0.31 per session |
| 5 | context ablation ≈ $1–2 | ≈ $1–2 | — |
| 6 | retrieval `analyze` on 20 ticker-days ≈ $1; citation-accuracy eval ≈ $0.30 (embeddings and reranker run locally, $0) | ≈ $1.30 | — |
| 7 | injection test set ≈ $1; baseline run ≈ $1; rerun after defences ≈ $1 | ≈ $3 | — |
| 8 | model routing ≈ $1; prompt caching ≈ $0.50 | ≈ $1.50 | the judge moves to the half-price `:batch` variant |
| 9 | no paid build items | $0 | the stream runs to day 60 |

Terms in this table, each explained in its chapter:
- **Tool-using `analyze`**: the model may call functions you expose and read their results before answering ([Anthropic, *Tool use*](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)).
- **Judge agreement**: how often an LLM judge matches your labels, beyond chance ([Wikipedia, *Cohen's kappa*](https://en.wikipedia.org/wiki/Cohen%27s_kappa); Husain, [*Using LLM-as-a-Judge For Evaluation*](https://hamel.dev/blog/posts/llm-judge/)).
- **Challenger arm**: a second configuration run on the same live inputs as the current one, compared like an A/B test ([Wikipedia, *A/B testing*](https://en.wikipedia.org/wiki/A/B_testing)).
- **Context ablation**: remove one block of the prompt's context and measure what it contributed ([Wikipedia, *Ablation*](https://en.wikipedia.org/wiki/Ablation_(artificial_intelligence))).
- **Retrieval `analyze`**: retrieval-augmented generation, fetching relevant passages and putting them in the prompt ([Wikipedia, *RAG*](https://en.wikipedia.org/wiki/Retrieval-augmented_generation)); **embeddings** are vectors that place similar texts close together ([Anthropic, *Embeddings*](https://platform.claude.com/docs/en/build-with-claude/embeddings)); a **reranker** re-scores the retrieved candidates with a slower, more exact model ([Sentence Transformers, *Retrieve & Re-Rank*](https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html)).
- **Citation accuracy**: whether each cited passage supports the sentence that cites it ([Gao et al., *Enabling LLMs to Generate Text with Citations*](https://arxiv.org/abs/2305.14627)).
- **Injection test set, defences**: inputs that try to override the model's instructions, and the measures against them ([OWASP, *Prompt Injection*](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)).
- **Model routing**: sending each request to the model that fits it ([OpenRouter, *Auto Router*](https://openrouter.ai/docs/guides/routing/routers/auto-router)); **prompt caching**: reusing an unchanged prompt prefix at a lower price ([OpenRouter, *Prompt caching*](https://openrouter.ai/docs/guides/best-practices/prompt-caching)); a **batch** variant trades latency for price by processing requests asynchronously ([OpenRouter, *Batch API*](https://openrouter.ai/docs/guides/features/batch-api)).

**Week 1 as measured** (Claude Sonnet 5.5 through OpenRouter, key spend read before and after each run): the observation run of 20 analyses cost **$0.3468** and the two-arm experiment of 40 analyses **$0.6877**, about $0.017 per ticker-day (≈ 2,500 input and ≈ 1,100 output tokens). With one `tr analyze` ($0.0165) and the earlier pilot calls ($0.0656), the week came to **$1.1166**, close to the budget's ≈ $1.00. The key books usage tens of seconds late, so read `tr usage` a minute after a run, not right away.

**Week 3 as measured** (OpenRouter): building `week-3-start` cost **$0.0082** on the key ($61.997785 → $62.005975: one teacher thesis capture $0.003016, one retry/tools check $0.0000109, one P1 judge recording $0.005163); the reference answers cost $0. One judged trade cost $0.005163 on a synthetic trade; live judge spend awaits the first closed trade.

**Week 4 as measured** (OpenRouter): **$0.900880** ($0.022888 recording the tool exchange that `week-4-start`'s tests replay, plus $0.877992 for the one tools-vs-fixed run of 20 ticker-days: fixed $0.339358, tools $0.538634). Tools cost 1.59× as much per item and the paired difference on `all_claims_valid` was 0. The challenger's sessions and the first live judge spend await live data.

**Week 5 as measured** (OpenRouter): **$1.005334** ($0.016048 recording the analyze-3 exchange that `week-5-start`'s tests replay, plus $0.989286 for the one context-ablation run of 3 arms × 20 ticker-days: full $0.343838, no-headlines $0.337578, no-edgar $0.307870). Both drops showed no loss in `claims_valid`, under a rule without a non-inferiority margin, so analyze keeps analyze-1. Running total for weeks 3 to 5: about $1.92.

## Licence

- Guide text: [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).
- Code (the snippets and reference solutions here, and the `tradingresearch` repo): MIT. Its dependency gigai-core is `Apache-2.0 AND MIT`.
- Data is not covered: Alpaca content stays under Alpaca's terms and is never redistributed. SEC EDGAR data is US government public data.
