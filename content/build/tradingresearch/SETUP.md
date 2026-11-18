# Setup: one clone, one `.env`

> *"Educational software. Not investment advice. No orders are placed; trades are hypothetical and settled from historical bars by written rules. Past results, including these, do not predict future results."*

Do this once, before [week 1](week-1.md). Every chapter assumes the clone, the `.env` file and the checks below. Nothing on this page spends money.

## What you need

| What | Why | Check |
|---|---|---|
| Python 3.12 | The repo pins `requires-python = ">=3.12"` and `.python-version` says `3.12`; `uv` installs it for you | `uv run python --version` → `Python 3.12.x` |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Project, dependencies and the lock file | `uv --version` (the guide was written with 0.9.17) |
| git | Each chapter starts at a tag and ends at the next | `git --version` |
| sqlite3, the command-line shell | Week 1 §2 lists your analyses straight from the journal. macOS ships it; on Linux or Windows install it, or use the `uv run python` one-liner the chapter gives instead | `sqlite3 --version` |
| A coding agent you already use | Writes new code from your spec in weeks 1 to 9 | Claude Code, Codex or similar |
| An Alpaca account, free Basic plan ([alpaca.markets](https://alpaca.markets/)) | Daily bars. A paper account is enough: `tr` talks only to the market-data host and never places an order | `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` |
| A SEC EDGAR User-Agent with your contact email ([SEC, *Accessing EDGAR data*](https://www.sec.gov/os/accessing-edgar-data)) | SEC asks every client to declare itself and to stay under 10 requests per second. No key is needed | `TR_SEC_USER_AGENT="Your Name you@example.com"` |
| A model-API key: OpenRouter ([openrouter.ai](https://openrouter.ai/)), and from week 6 on Anthropic ([console.anthropic.com](https://console.anthropic.com/)) if you prefer | The model calls. Which weeks need which key is in [Which provider runs which week](#which-provider-runs-which-week) | `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY` |

**Put a spend limit on every model key before the first paid call.** On OpenRouter, set a credit limit on the key in the dashboard; on Anthropic, set a monthly spend limit in the console ([Anthropic, *Rate limits and spend limits*](https://platform.claude.com/docs/en/api/rate-limits)). The experiment runner caps each run, but a key limit also catches bugs. For OpenRouter, `tr usage` (below) is the free check: it reads the key's spend counter. No free call proves an Anthropic key: `tr` exits before any network call when a key is missing, and the first paid command is the test, so set the limit first.

**US residents only, for Alpaca.** [Alpaca's Terms and Conditions](https://files.alpaca.markets/disclosures/library/TermsAndConditions.pdf) say that "The Content and the Service are intended for United States residents only." Readers outside the US need another source of daily bars; the guide does not supply one.

**Timing.** The free Alpaca plan serves historical SIP bars once a request's `end` is at least 15 minutes old, so `tr` works on the latest session whose close is at least 15 minutes old: after 16:15 New York time that is today's session; before 16:15 it is the previous completed session, and the commands run without complaint. To name a session yourself, pass `--session YYYY-MM-DD` where a command takes it. Nothing else depends on the clock.

## Clone, settings file, first checkout

**The code:** [github.com/karthik446/tradingresearch](https://github.com/karthik446/tradingresearch) (public; MIT licence). Tags `week-1-start` … `week-9-end` mark where each chapter starts and ends.

```bash
git clone https://github.com/karthik446/tradingresearch.git tradingresearch
cd tradingresearch
cp .env.example .env            # the template lives on the default branch; .env is git-ignored at every tag
chmod 600 .env                  # then fill it in an editor (next section)
git checkout week-1-start       # week 1 starts here; .env is untracked, so it stays through every checkout
git switch -c my-week-1 week-1-start   # your own branch on that tag (next paragraph)
uv sync
uv run pytest -q                # no keys, no network: 44 passed, 1 skipped at week-1-start
```

`git tag -l` lists every tag, in alphabetical order (`week-1-end`, `week-1-start`, `week-2-end`, ... `week-9-start`). Each chapter says which tag it starts from.

**Work on a branch, not on the tag.** `git checkout <tag>` leaves you on a detached HEAD: commits made there belong to no branch and drop out of sight at the next checkout. So each chapter starts with `git switch -c my-week-N week-N-start`, which puts your work on a branch of your own; your commits, and the tag you put on them at the end of a chapter (`git tag my-week-1-end`), stay reachable. The reference tags (`week-1-end` and so on) already exist in the clone, so name yours differently.

## Fill `.env`

`.env` holds the keys and the settings; it is read by `tr` itself, in Python (`config.py`), and never put into your shell's environment. Do not `source` it, `cat` it or paste it into a chat with your coding agent; keys that reach a shell or a transcript leak into logs. Inside the code each key is a `Secret` that prints as `Secret('***')`.

| Variable | Value | Needed |
|---|---|---|
| `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` | Your Alpaca market-data keys | Every week |
| `TR_SEC_USER_AGENT` | `Your Name you@example.com` | Every week |
| `OPENROUTER_API_KEY` | Your OpenRouter key | Weeks 1 to 5 (the only provider the code knows at those tags); from week 6 on for the teacher arms and the judge, and for everything if `TR_PROVIDER=openrouter` |
| `ANTHROPIC_API_KEY` | Your Anthropic key | From week 6 on, if `TR_PROVIDER=anthropic` |
| `TR_PROVIDER` | `openrouter` or `anthropic` | Read from week 6 on (tag `week-6-end` and later); ignored by earlier tags |
| `TR_FEED` | `sip` (default; `iex` is the fallback feed) | Optional |
| `TR_DATA_DIR` | Where the journal, runs and traces go; default `data/` inside the repo | Optional |

Settings that are not secret (`TR_SEC_USER_AGENT`, `TR_FEED`, `TR_DATA_DIR`, `TR_PROVIDER`) may also be exported in the shell; the shell value wins over the file.

**Tags before `week-6-end` look for the settings file elsewhere.** The code at `week-1-start` through `week-6-start` defaults to a file under your home folder and reads `.env` in the repo only when `TR_ENV_FILE` points at it. So, for weeks 1 to 5 (and the start of week 6), run this once per shell, from the repo root:

```bash
export TR_ENV_FILE="$PWD/.env"
```

If you forget it, every `tr` command stops at once with the repo's own message, here for the OpenRouter key: `OPENROUTER_API_KEY is not set: add it to ~/.config/tradingresearch/verify.env (see the README, Prerequisites)`. The path is the file it read, under your home folder, not your `.env`; set `TR_ENV_FILE` and run again. Ignore the "see the README, Prerequisites" part: the repo README at these tags has no such section and still describes the home-folder file; this page replaces it. From `week-6-end` on, `tr` finds the repo's `.env` by itself and `TR_ENV_FILE` is no longer needed (it still works).

## Check the keys without spending

```bash
export TR_ENV_FILE="$PWD/.env"   # weeks 1 to 5; see above
uv run tr usage                  # free: prints `openrouter key usage $<total spend so far>`
uv run tr snapshot AAPL --prompt # free: the analyze prompt, with its SOURCES table: Alpaca bars, indicators and SEC facts, one `src_` id per row
```

`tr usage` reads the OpenRouter key's spend counter and is the check for that key; log its value before and after every paid run (the counter books usage tens of seconds late, so read it a minute after a run). Under `TR_PROVIDER=anthropic` it says that Anthropic has no spend endpoint; use the console's usage page instead. `tr snapshot` exercises the Alpaca keys and the SEC User-Agent and costs nothing; without `--prompt` it prints the snapshot as JSON, which has the indicators but neither the `src_` ids nor the SEC facts, so use `--prompt` to see that the User-Agent worked (look for the `revenue_` and `eps_diluted_` rows). A missing key is reported by name, never by value.

## Which provider runs which week

The provider adapter (`TR_PROVIDER`, `ANTHROPIC_API_KEY`) arrives inside week 6, between `week-6-start` and `week-6-end` ([ADR-014](https://github.com/karthik446/tradingresearch/blob/week-6-end/docs/adr/ADR-014-provider-interface.md), [docs/providers.md](https://github.com/karthik446/tradingresearch/blob/week-6-end/docs/providers.md)). Before that tag the code has one provider, OpenRouter, and the Claude models are reached through it. OpenRouter stays a full first-class provider afterwards: both settings run every chapter from week 6 on.

| Weeks | Tags | Model calls go through | Keys that must be set |
|---|---|---|---|
| 1 to 5 | `week-1-start` to `week-6-start` | OpenRouter only (`TR_PROVIDER` is ignored) | `OPENROUTER_API_KEY` |
| 6 to 8 | `week-6-end` to `week-8-end` | `TR_PROVIDER`: `anthropic` or `openrouter`, your choice, for `analyze`, `thesis` and the experiments. The teacher arms (`--arm teacher`, `tr daily --teachers`, `tr bakeoff`, `tr dataset`) and the judge (`tr grade --judge`, `tr label`, week 8's batch judge) always go through OpenRouter, because those models are not served by the Anthropic API | `OPENROUTER_API_KEY`; plus `ANTHROPIC_API_KEY` if `TR_PROVIDER=anthropic` |
| 9 | `week-9-start` to `week-9-end` | No paid commands; the live stream keeps running with the week-8 settings | as in week 8 |

Measured numbers in the chapters say which provider produced them: weeks 1 to 5 were measured on OpenRouter (Claude Sonnet 5.5, key spend read before and after each run); the week 6 §8 rerun, the week 7 injection runs and the week 8 routing run were measured on Anthropic's API with `TR_PROVIDER=anthropic`; the judge and teacher numbers in every week are OpenRouter prices. Your totals differ by the provider's price list and by the day's sessions.

## Cash, in short

All amounts are model-API spend; market data (Alpaca Basic) and filings (SEC EDGAR) cost $0. The guide's budget is about **$61 in total** over nine weeks (including +50% for development and reruns) with a **$10 cap per session**. Week by week, as budgeted and as the author measured it, is in the README's [Cash per week](README.md#cash-per-week). Three rules keep you inside it:

- Every experiment config carries a cash cap per arm; the runner refuses before spending if the cap cannot cover the worst case.
- `tr usage` before and after every paid run; the week chapters show the readings.
- Any command that spends says so in its chapter, with the amount; `--dry-run`, `tr screen`, `tr reconcile`, `tr grade` without `--judge`, `tr report` and `tr usage` are free.

Next: [week 1](week-1.md).
