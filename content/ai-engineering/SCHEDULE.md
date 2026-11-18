# Schedule: 60 days, nine weeks

> *"Educational software. Not investment advice. No orders are placed; trades are hypothetical and settled from historical bars by written rules. Past results, including these, do not predict future results."*

The track is paced as a 60-day plan: eight weeks of seven days and a ninth of four. Each week has one build chapter (`week-N.md`) and a reading list. This page is the pace and the readings; the chapters are the work.

**How a day goes**

- **1-hour session (one per day):** 40 minutes of Python coding practice of your own, then a 20-minute reading slot. The readings listed under *In the 20-minute slots* fill that slot; a week's slots add up to 140 minutes (80 in week 9).
- **2-hour session (one per day):** the chapter's build steps plus the longer readings and course videos listed under *In the 2-hour sessions*; 840 minutes a week (480 in week 9). Each week's total below counts the readings and the chapter's build estimates together; tick items off in any session that has room, in the order listed.
- **The live stream starts by day 10:** from week 2 the after-close run writes theses every trading day, so the steps through `thesis` must be built by then. It runs at or after 16:15 New York time, when Alpaca's free plan serves the day's bars (see [SETUP.md](SETUP.md)).
- **Expected result:** "no edge detected, with its confidence interval" is a valid result, and the likely one. With the S&P 100 and a shortlist of 10, the plan expects about 104 day, 60 short and 24 swing trades to close by day 60, so only edges of about 0.28–0.39 R on day trades are detectable.
- **The process judge** runs in descriptive mode: its agreement (Cohen's kappa) with your blind labels is reported from 30 labels and grows as trades close; it is never claimed as validated (gigai-core's gate needs 126 labels).
- An ADR is a one-page decision record in `docs/adr/`. Every ADR answers "does this need an LLM, classical ML, or plain code?".
- Cash: about $61 of model-API spend over the nine weeks, $10 cap per session; data costs $0. Details in [SETUP.md](SETUP.md#cash-in-short) and the README's [Cash per week](README.md#cash-per-week).

**Data docs, used every week:** [Alpaca Market Data API](https://docs.alpaca.markets/us/docs/about-market-data-api) (Basic plan: historical SIP bars, `feed=iex` fallback, news headlines; US residents only); SEC EDGAR APIs, `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` and `https://data.sec.gov/submissions/CIK##########.json` (a User-Agent is required, 10 requests per second; [SEC, *Accessing EDGAR data*](https://www.sec.gov/os/accessing-edgar-data)).

Reading and video minutes come from the source pages; build minutes are the plan's estimates. Book chapters are from O'Reilly; each title links to its page.

---

## Week 1 (days 1–7): learn error analysis, eval basics and when fine-tuning pays off; build the first evals on `tr analyze`

### Readings

**In the 20-minute slots (7 this week)**
- Moroney, [*Fine-Tuning AI*](https://learning.oreilly.com/library/view/-/0642572310455/) ch 1, 2 (70 min)
- Gayle, [*The Forward Deployed Engineer*](https://learning.oreilly.com/library/view/-/0642572416485/) ch 2 (29 min)
- Moroney, *Fine-Tuning AI* ch 7, 8 and 10, headings only (~40 min)

Total: 139 / 140 min

**In the 2-hour sessions**
- OpenAI, [*What forward deployed engineering means at OpenAI*](https://openai.com/index/forward-deployed-engineering-means/) (~15 min)
- Moroney, *Fine-Tuning AI* ch 4, 5, 6 (110 min)
- Shankar & Husain, [*Evals for AI Engineers*](https://learning.oreilly.com/library/view/-/9798341660717/) ch 1–2, 3 (81 min)
- Moroney, *Fine-Tuning AI* ch 9, 14 (95 min)

Readings 301 min + build ~510 min = 811 / 840 min

### Build

[week-1.md](week-1.md): a tour of the core, 20 analyses read and labelled (open coding), a claim-failure taxonomy with counts (axial coding), a new eval with a spec and tests, a prompt variant measured in a paired experiment, ADR-001 and ADR-002, a scope one-pager and a fine-tuning note.

**Works by end of week:** `tr analyze AAPL` writes an `Analysis` whose claims all validate, from Alpaca bars, EDGAR facts and code-computed indicators. 20 analyses carry notes and are grouped in `evals/taxonomy.md` into 5–8 classes with counts; ADR-001 says which classes code checks.

### Self-check (answer out loud, no notes)
1. Error analysis (open and axial coding) and why it precedes metrics.
2. When fine-tuning beats prompting/RAG and when not.
3. Data for fine-tuning: curation, synthetic data, eval before/after.
4. One-page scope (SOW as spec) for a customer who cannot specify: outcome, metric, eval set, out of scope.
5. LoRA/PEFT and GPU memory arithmetic: what fits on one GPU, and why.

---

## Week 2 (days 8–14): learn LLM judges, judge validation and CI gating; build thesis, reconcile and the screen, and start the live stream by day 10

### Readings

**In the 20-minute slots (7 this week)**
- Hamel Husain, [*Your AI Product Needs Evals*](https://hamel.dev/blog/posts/evals/) (~20 min)
- Hamel Husain, [*Using LLM-as-a-Judge for Evaluation*](https://hamel.dev/blog/posts/llm-judge/) (~20 min)

Total: 40 / 140 min; the remaining slots go to Python reading of your own

**In the 2-hour sessions**
- Moroney, *Fine-Tuning AI* ch 15 (29 min)
- Shankar & Husain, *Evals for AI Engineers* ch 4, 5 (70 min)
- Shankar et al., [*Who Validates the Validators?*](https://arxiv.org/abs/2404.12272) (~40 min)
- Anthropic, [*Best practices for Claude Code*](https://www.anthropic.com/engineering/claude-code-best-practices) (~20 min)
- Shankar & Husain, *Evals for AI Engineers* ch 9 (21 min)
- Huyen, [*AI Engineering*](https://learning.oreilly.com/library/view/-/9781098166298/) ch 3 (82 min)

Readings 262 min + build ~515 min = 777 / 840 min

### Build

[week-2.md](week-2.md): `tr thesis` with its validators, the one-open rule, the stop floor and `NoTrade`; `tr open`; the code-only `tr screen` over your S&P 100 list; `tr reconcile` (state machine, fill, gap and same-bar rules, cost model, idempotence); the CI gate with fixture tests and a fake LLM client; versioned prompts in `prompts/`; the scheduled after-close run from day 10; the process rubric and the judge prompt; a demo script and a runbook.

**Works by end of week:** the after-close run has written live theses every session since day 10, and the first ones are settled from real bars by `tr reconcile`. Reconcile fixture tests pass in CI on every pull request, and the prompts carry a version id. The process rubric and the judge prompt are drafted.

### Self-check
1. Build an LLM judge and validate it against human labels (precision, recall, kappa); when to trust it.
2. True success rate from judged samples, with confidence interval and judge-error correction.
3. Prompt versioning and gating of prompt changes.
4. Eval thresholds as CI gates: what blocks a merge and why.
5. How do you keep coding-agent changes safe: which tests gate them, and what do you still review by hand?

---

## Week 3 (days 15–21): learn observability and SLOs; build traces, grading, the per-horizon report, SLO checks and the first labels

### Readings

**In the 20-minute slots (7 this week)**
- No AI reading this week: the slot goes to Python concurrency reading (asyncio and threading), about 127 min

Total: 127 / 140 min

**In the 2-hour sessions**
- Watch/do: DeepLearning.AI (Arize), [*Evaluating and Improving Agentic Applications*](https://www.deeplearning.ai/courses/evaluating-and-improving-agentic-applications/), module 1 lab "Trace an Agent with Phoenix", as a warm-up for the traces step (30 min)
- Huyen, *AI Engineering* ch 4 (99 min)
- Carter, [*Observability for LLMs*](https://learning.oreilly.com/library/view/-/9781098159757/) (45 min)
- Albada, [*Building Applications with AI Agents*](https://learning.oreilly.com/library/view/-/9781098176495/) ch 10 (37 min)
- Shankar & Husain, *Evals for AI Engineers* ch 11–12 (42 min)
- Watch: DeepLearning.AI, *Evaluating and Improving Agentic Applications*, module 3 videos (33 min; the 40-min lab is Optional)
- Watch: Stanford [CME295](https://cme295.stanford.edu/) lecture 6, AI agents (101 min)

Readings and videos 387 min + build ~440 min = 827 / 840 min

### Build

[week-3.md](week-3.md): traces with a model span per call and a tool span per fetch on every step of the after-close run, cost per run from measured usage; `tr grade` (outcome grade, shadow baseline, P2–P4 code checks, the P1 judge); `tr report` with per-horizon scorecards, Wilson and bootstrap intervals and the detectable-effect line; SLOs and `slo_check.py`; ADR-002 on what never goes into a trace; `tr label` and the first ~15 blind labels; a demo script and write-up.

**Works by end of week:** every step of the after-close run writes a trace with model and tool spans and its cost. `tr report` shows n, Wilson and bootstrap intervals, real vs shadow and the detectable-effect line per horizon. `slo_check.py` fires on a breach, as shown once with an injected delay. About 15 closed trades carry blind labels.

### Self-check
1. Why HTTP 200 is not correct; which LLM-specific signals to monitor.
2. An SLO for an LLM feature (latency + judged quality) and its alerting.
3. Top failure class in 1,000 traces within an hour.
4. OTel GenAI spans on a pipeline: p50/p95 latency, tokens and $ per task from spans.
5. Silent quality degradation without labels: drift signals and judge sampling.

---

## Week 4 (days 22–28): learn agent and tool design and production prompts; build the tool-using analyze, retries, an MCP server, judge agreement and the first pre-registered rule change

### Readings

**In the 20-minute slots (7 this week)**
- AWS Builders' Library, [*Timeouts, retries, and backoff with jitter*](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/) (~20 min)
- AWS Architecture Blog, [*Exponential Backoff and Jitter*](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/) (~10 min)

Total: 30 / 140 min; the remaining slots go to Python reading of your own

**In the 2-hour sessions**
- Watch: DeepLearning.AI, [*MCP: Build Rich-Context AI Apps with Anthropic*](https://www.deeplearning.ai/courses/mcp-build-rich-context-ai-apps-with-anthropic/), before the MCP server step (118 min)
- Huyen, *AI Engineering* ch 5 (69 min)
- Anthropic, [*Building effective AI agents*](https://www.anthropic.com/engineering/building-effective-agents) (~20 min), [*Writing effective tools for AI agents*](https://www.anthropic.com/engineering/writing-tools-for-agents) (~25 min), [*How we built our multi-agent research system*](https://www.anthropic.com/engineering/multi-agent-research-system) (~20 min)
- Albada, *Building Applications with AI Agents* ch 2 (43 min)
- Shankar & Husain, *Evals for AI Engineers* ch 8 (26 min)
- Huyen, *AI Engineering* ch 6, part 1 of 2 (49 min)

Readings and videos 370 min + build ~415 min = 785 / 840 min

### Build

[week-4.md](week-4.md): `analyze` as a tool-using agent next to the fixed-context version, compared on the same tickers, with trajectory checks in CI and ADR-003; retries with exponential backoff and jitter on retryable errors only, tested against a fake server; a read-only MCP server over the journal with a client contract test and ADR-004; judge agreement on 30 blind labels (Cohen's kappa, at most 3 rubric rounds); the first `tr learn` and one pre-registered `RuleChange`, with the challenger arm writing theses daily from day 22.

**Works by end of week:** both `analyze` variants run on the same tickers and are compared on P2 and P1. Retry tests pass for Alpaca's and the SEC's limits. Kappa on 30 labels is stored as a `JudgeValidationRecord` and reported as descriptive. The first `RuleChange` is pre-registered, and the challenger arm writes theses daily from day 22. The journal is readable through the MCP server, and the Python client contract test passes in CI (if built).

### Self-check
1. Workflow vs agent, and when a fixed workflow beats an agent loop.
2. A read-only MCP server over tradingresearch's journal, tested from a client.
3. Tool bloat: progressive discovery, fewer and better tools.
4. A production system prompt (structure, constraints, examples) on request.
5. Exponential backoff + jitter, retry budgets, how retries amplify outages.

---

## Week 5 (days 29–35): learn context engineering and multi-team MCP; build the playbook into the thesis prompt and a context ablation

### Readings

**In the 20-minute slots (7 this week)**
- Watch: talk, [*Your Sub-Agents Are a Distributed System. Treat Them Like One.*](https://www.youtube.com/watch?v=DxP5aW4VknQ) (23 min)
- Anthropic, [*Effective context engineering for AI agents*](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) (~20 min)
- Watch: talk, [*How Uber Runs 60,000 AI Agent Tasks Per Week With MCP*](https://www.youtube.com/watch?v=yVqMxBahjfA) (15 min)

Total: 58 / 140 min

**In the 2-hour sessions**
- Huyen, *AI Engineering* ch 6, part 2 of 2 (49 min)
- Watch: Stanford [CS329A](https://cs329a.stanford.edu/), Learning from Feedback with Tools/Code (71 min)
- Albada, *Building Applications with AI Agents* ch 4, 5, 9 (114 min)
- Mendelevitch & Bao, [*Hands-On RAG for Production*](https://learning.oreilly.com/library/view/-/9798341621701/) ch 2 (72 min)
- Pai, [*Designing LLM Applications*](https://learning.oreilly.com/library/view/-/9781098150495/) ch 12 (63 min)

Readings and videos 369 min + build ~285 min = 654 / 840 min

### Build

[week-5.md](week-5.md): the code-computed playbook rendered into the `thesis` prompt as Fact claims, with the rule that a setup whose upper confidence bound is below 0 R needs an explicit reason; a context ablation of headlines and EDGAR facts on the same ticker-days, measured on P2, P1 and tokens with a paired bootstrap interval per variant; ADR-005 on an MCP gateway and registry for many teams; a demo script and write-up.

**Works by end of week:** the `thesis` prompt carries the playbook rendered from code. The ablation table shows P2, P1 and tokens with and without headlines and facts. ADR-005 is written.

### Self-check
1. Which of two agent versions ships, with a significance argument.
2. MCP gateway/registry for many teams: auth, governance, discovery.
3. Context limits and rot; compaction, scratchpads, sub-agent isolation.
4. An MCP client with schema validation, tested in CI.
5. RAG vs long context vs fine-tuning vs no LLM.

---

## Week 6 (days 36–42): learn retrieval and RAG evals; build retrieval over filings and headlines and a citation-accuracy eval

### Readings

**In the 20-minute slots (7 this week)**
- Gayle, *The Forward Deployed Engineer* ch 1 (34 min)
- Ramp, [*Forward Deployed Engineering*](https://builders.ramp.com/post/forward-deployed-engineering) (~15 min)
- Pragmatic Engineer, [*Forward Deployed Engineers*](https://newsletter.pragmaticengineer.com/p/forward-deployed-engineers) (~20 min)
- [OWASP Top 10 for LLM Applications](https://genai.owasp.org/llm-top-10/), part 1 of 3 (~20 min)

Total: 89 / 140 min

**In the 2-hour sessions**
- Huyen, *AI Engineering* ch 8, skim (~30 min)
- Mendelevitch & Bao, *Hands-On RAG for Production* ch 3 (77 min)
- Shankar & Husain, *Evals for AI Engineers* ch 7 (25 min)
- Albada, *Building Applications with AI Agents* ch 6 (37 min)
- Mendelevitch & Bao, *Hands-On RAG for Production* ch 6 (64 min)

Readings 233 min + build ~570 min = 803 / 840 min

### Build

[week-6.md](week-6.md): a scoping one-pager for retrieval ("what changed at this company?"); cached 8-K/10-Q text and headlines chunked and embedded with a local model; 30 hand-labelled queries with gold passages and recall@k for dense, BM25 + reciprocal-rank-fusion and a local cross-encoder reranker; `analyze` on retrieval, compared with fixed context on 20 ticker-days; a citation-accuracy eval (numeric facts within a 0.5% relative tolerance, plus a judge for claims that cite filing text); ADR-006 on permissions-aware retrieval and freshness; a scoping one-pager and threat model for the guardrails work.

**Works by end of week:** retrieval over filings and headlines reports recall@k for dense, BM25 + RRF and reranked search on 30 hand-labelled queries. The citation-accuracy eval scores `analyze`'s facts against their sources, on fixed context and on retrieval. ADR-006 and the threat model are written.

### Self-check
1. BM25 vs dense vs hybrid; when lexical wins.
2. Hybrid + reranker, delta on the same metric.
3. Answer evals: groundedness, citation correctness, freshness. (Freshness: answer from ADR-006.)
4. Permissions-aware retrieval and reindexing/freshness.
5. Push back: agent vs workflow vs no software; when to kill a POC.

---

## Week 7 (days 43–49): learn prompt injection, guardrails and structured output; build the injection set, a strict thesis schema and the guardrails

### Readings

**In the 20-minute slots (7 this week)**
- OWASP Top 10 for LLM Applications, parts 2–3 of 3 (~40 min)
- Simon Willison, [*The lethal trifecta for AI agents*](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) (~10 min)
- Google SRE book, [*Handling Overload*](https://sre.google/sre-book/handling-overload/) and [*Addressing Cascading Failures*](https://sre.google/sre-book/addressing-cascading-failures/) (~60 min)

Total: 110 / 140 min; the remaining slots go to Python reading of your own

**In the 2-hour sessions**
- Huyen, *AI Engineering* ch 10 (74 min)
- Souza & Regenstein, [*LLMs: The Hard Parts*](https://learning.oreilly.com/library/view/-/9798341622517/) ch 5, 6 (75 min)
- Chip Huyen, [*Building A Generative AI Platform*](https://huyenchip.com/2024/07/25/genai-platform.html) (~45 min)
- Albada, *Building Applications with AI Agents* ch 12 (55 min)
- Huyen, *AI Engineering* ch 9 (81 min)

Readings 330 min + build ~475 min = 805 / 840 min

### Build

[week-7.md](week-7.md): an injection test set of 30 indirect injections planted in cached headlines and filing excerpts, each tied to a recorded `analyze` input; a baseline run (share of theses changed); strict schema output for `Thesis` with its failure rate measured; guardrails that reject rule-breaking theses before they are stored, each rejection in `audit.jsonl`; an injection detector on fetched text and redaction in traces; the rerun after the defences with the false-rejection rate on clean theses; ADR-007 on where each guardrail sits and when a human reviews.

**Works by end of week:** headlines and filings are treated as untrusted input. The injection set changes 0 theses after the defences, with before and after in the results table. `Thesis` output is schema-strict with a measured schema-failure rate, and guardrails reject rule-breaking theses before they are stored, each rejection in `audit.jsonl`.

### Self-check
1. Direct vs indirect prompt injection; the lethal trifecta.
2. Injection suite: ASR before/after and false-refusal rate.
3. Least privilege for tool-using agents: scopes, sandbox, human approval, audit log.
4. Backpressure and load shedding for an LLM API.
5. A model is confident but wrong in a high-risk flow: investigate and mitigate.

---

## Week 8 (days 50–56): learn serving, routing, caching and GPUs on Kubernetes; build model routing, prompt caching and the cost table

### Readings

**In the 20-minute slots (7 this week)**
- Nuland, Goin & Costa, [*AI Inference at Scale*](https://learning.oreilly.com/library/view/-/0642572392468/) ch 1 (31 min)
- Kubernetes docs, [*Schedule GPUs*](https://kubernetes.io/docs/tasks/manage-gpus/scheduling-gpus/) (~12 min); [NVIDIA GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/index.html) overview (~13 min); KEDA docs, [Prometheus scaler](https://keda.sh/docs/latest/scalers/prometheus/) (~15 min)
- [vLLM production-stack](https://docs.vllm.ai/projects/production-stack/en/latest/) overview (~12 min); the [llm-d](https://llm-d.ai/) site (~13 min); vLLM docs, [*Troubleshooting*](https://docs.vllm.ai/en/latest/usage/troubleshooting.html) (~15 min)

Total: 111 / 140 min

**In the 2-hour sessions**
- Wang & Hu, [*Hands-On LLM Serving and Optimization*](https://learning.oreilly.com/library/view/-/9798341621480/) ch 2, 3 (124 min)
- Huß & Zonca, [*Generative AI on Kubernetes*](https://learning.oreilly.com/library/view/-/9781098171919/) ch 5 (39 min)
- Wang & Hu, *Hands-On LLM Serving and Optimization* ch 4, part 1 of 2 (43 min)
- Huß & Zonca, *Generative AI on Kubernetes* ch 3, part 1 of 2 (34 min)

Readings 240 min + build ~330 min = 570 / 840 min

### Build

[week-8.md](week-8.md): a scoping one-pager for the cost work and a baseline table from a fresh week of runs ($ per ticker-day, p50/p95 run time, P1 and P2); model routing (a budget model for `analyze`, a mid model for `thesis`, fallback on provider errors) on the baseline's ticker-days; prompt caching of the static context with cached tokens, latency and $ measured; the after-close judge on the half-price batch variant with a before/after table; the routing comparison table and ADR-008 on which model runs each step. The GPU and Kubernetes readings stay reading-only; the kind lab is in the Optional section.

**Works by end of week:** the routing comparison table shows $ per ticker-day, latency and P1/P2 for the default models, the routed set and the cached prompts. The judge runs through the batch variant, and ADR-008 records which model runs each step.

### Self-check
1. Route each call to the cheapest model that clears the bar, with fallback.
2. Prompt caching mechanics and when it pays.
3. What continuous batching and PagedAttention fix.
4. On kind: model server with requests/limits and probes on a fake GPU node; HPA vs KEDA on a queue metric.
5. Benchmark a served model: throughput vs p95 latency over concurrency.

---

## Week 9 (days 57–60): learn distributed inference and self-hosting economics; freeze the rules, publish the scorecards and release the repo

### Readings

**In the 20-minute slots (4 this week)**
- vLLM docs, [*Production Metrics*](https://docs.vllm.ai/en/latest/usage/metrics.html) (~15 min)
- OpenAI, [*Scaling Kubernetes to 7,500 nodes*](https://openai.com/index/scaling-kubernetes-to-7500-nodes/) (~20 min)
- Review: the self-check questions you missed in weeks 1–8, answered out loud again (30 min)

Total: 65 / 80 min

**In the 2-hour sessions**
- Nuland, Goin & Costa, *AI Inference at Scale* ch 4 (28 min)
- Huß & Zonca, *Generative AI on Kubernetes* ch 3, part 2 of 2 (34 min)
- Wang & Hu, *Hands-On LLM Serving and Optimization* ch 4, part 2 of 2 (42 min)
- Huß & Zonca, *Generative AI on Kubernetes* ch 4 (61 min)

Readings 165 min + build ~310 min = 475 / 480 min

### Build

[week-9.md](week-9.md): freeze the rules (tag the commit) and publish the final per-horizon scorecards with confidence intervals, real vs shadow and the detectable-effect line, open trades reported as "open, not graded"; the adoption decision for the one challenger (paired cluster bootstrap on per-session r_net plus the P1 guard); the API vs self-host break-even and ADR-009; the write-up and README as a reference architecture; the release: MIT licence for the code, CC BY-NC 4.0 for the guide text, the not-investment-advice note at the top of the README and in every `report`, a `.gitignore` audit (journal, cache, traces and keys stay private), the aggregate scorecard export, and green tests from a fresh clone.

**Works by end of week:** the rules are frozen and the public repo is tagged. Final per-horizon scorecards (n, win rate, mean r_net with confidence intervals, real vs shadow, detectable-effect line) are published as aggregates. The write-up states the result, including "no edge detected" with its confidence interval if that is the outcome, and the challenger's adoption decision. The README holds the reference architecture, the results table and ADR-001 to ADR-009.

Fine-tuning is outside these 60 days; the Moroney chapters in this schedule stay readings only.

### Self-check
1. TP vs PP vs DP vs EP, and why TP across nodes hurts.
2. Unit economics at 10× traffic; batch vs real-time; API vs self-host break-even.
3. Debug a vLLM pod: OOMKilled vs CUDA OOM vs KV pressure (preemptions); triage order.
4. A reference architecture another team can adopt.
5. An org-wide eval standard: what every team needs before shipping.

---

## Optional (moved out so every week fits its budget)

- TypeScript, off the weekly budget (tradingresearch is Python; its MCP server is built in week 4):
  - Read: [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html) (~100 min)
  - Build: a strict-mode TypeScript client on the [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk). It connects to the week-4 journal MCP server, lists the tools and validates their input schemas (~75 min)
  - Build: the TypeScript client calls one tool end to end and validates the result; add it to CI (~75 min)
- Kubernetes lab K1 (tradingresearch needs no cluster or GPU; the readings stay in weeks 8–9; $0 cash):
  - Build: Kubernetes on kind: a container image for the after-close run, run as a `CronJob` at 16:15 ET, and the read-only MCP server as a Deployment with requests/limits and probes, exposing an in-flight-requests gauge on `/metrics` (`prometheus_client`). `make up` creates the kind cluster, builds and loads the images and applies the manifests; `make down` deletes it (~120 min)
  - Build: install Prometheus and KEDA in kind. Add a fake GPU node with [kwok](https://github.com/kubernetes-sigs/kwok) and a taint, plus a placeholder pod that tolerates the taint and requests `nvidia.com/gpu`. Compare HPA on CPU with KEDA on the in-flight gauge (~120 min)
- Build: [AgentDojo](https://github.com/ethz-spylab/agentdojo)'s prompt-injection attacks (≈ 249 cases on its banking and slack suites) against your `analyze` agent loop through a custom pipeline, as a generic comparison for week 7's injection set (~120 min, cash ≈ $3–5)
- Watch: DeepLearning.AI, [*Agentic AI*](https://www.deeplearning.ai/courses/agentic-ai/), module 4 (73 min). It repeats material from the evals book; no question relies on it alone.
- Read: Souza & Regenstein, *LLMs: The Hard Parts* ch 7 (70 min). The questions on a confidently wrong model in a high-risk flow and on PII leakage are still answered by ch 6, Huyen ch 10 and the guardrails work.
- Build: one GraphRAG session on cross-references between the week-6 filings, tested on 10 multi-hop questions written first, with an optional 50-question [HotpotQA](https://huggingface.co/datasets/hotpotqa/hotpot_qa) cross-check (~75 min). The question on when GraphRAG is worth it is still answered by Albada ch 6.
- Watch: Stanford CS329A, Agentic Evaluations and Long Horizon Tasks (75 min). No question relies on it alone.
- Watch/do: the 40-min lab of the Arize module 3.
