# Composio App Research — No-API-Key Edition

## Live research dashboard

This repository now includes a live, local dashboard on top of the original
100-app assignment. It preserves the existing dataset and its research
narrative while letting a reviewer upload a separate CSV, start a run, and
watch the same no-key agent fetch apps sequentially. Each finished row is
published immediately over Server-Sent Events (SSE), including failures.

### Architecture

```
Browser CSV upload -> FastAPI (server/main.py) -> RunManager
                                                -> agent/research_agent.py
Browser SSE <---------------------------------- per-app results + progress
                                                -> data/runs/<run-id>/
```

`agent/research_agent.py` remains the sole research implementation. The
backend calls its `derive_record()` function; it does not invent a second
research engine. New runs write only to `data/runs/<timestamp>-<id>/`:
`input.json`, incrementally updated `results.json`, and final verification
report/queue files. The existing `data/apps_*.json`, analytics, and seed CSV
are never overwritten by the live dashboard.

### Install and start

Use Python 3.10+ in a virtual environment if preferred:

```bash
python -m pip install -r requirements.txt
python -m uvicorn server.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Do not open the HTML
file directly: the live interface needs the local backend for uploads, SSE,
exports, and loading the original seed list.

### CSV format

The primary format is:

```csv
name,website
Salesforce,https://salesforce.com
HubSpot,https://hubspot.com
Notion,https://notion.so
```

The dashboard also accepts `app_name,url`, `name,url`, `app,website`, and the
repository's original `name,hint_url` seed format.
It requires HTTP(S) URLs, rejects malformed/incomplete rows, accepts only
`.csv`, and limits a run to 500 apps or 2 MB. Values are rendered as text,
never inserted as executable HTML.

### Using a live run

1. Click **Upload App CSV** (or **Load Existing 100 Apps**) and inspect the preview.
2. Click **Start Research**. Processing is deliberately sequential and uses
   actual HTTP fetch completion, not a timer-based progress simulation.
3. Watch the activity feed, counts, current app, and results table update
   after every app. A failed request is recorded with its fetch status and
   does not stop later apps.
4. Filter the live table and use **Export CSV** or **Export JSON** after the
   run. Exports contain the results from that run only.

### Output and verification methodology

Each record contains category, description, auth/access/API/MCP signals,
buildability verdict, blocker, evidence URL/snippet, confidence, and exact
fetch status. The agent is keyword/evidence extraction, not comprehension:
a successful HTTP response is not a verified fact. Insufficient evidence is
kept as `Unknown`/`Unclear`; failed or low-confidence entries are placed in a
human verification queue. No OpenAI, Anthropic, Composio, Tavily, Serper, or
other paid API key is required.

### Troubleshooting

- `ModuleNotFoundError: fastapi`: run `python -m pip install -r requirements.txt`.
- Dashboard cannot load data: start the server and open `http://127.0.0.1:8000`.
- Many failures: target sites may block automated requests, rate-limit, or be
  unreachable from your network. The failure is retained honestly; retry from
  a network with normal outbound access and perform human verification.
- A run is interrupted: completed rows are already saved in that run's
  `results.json`; start a fresh run to continue research.

## Assignment objective
Research 100 apps (category, auth, self-serve vs gated, API surface, MCP
status, buildability verdict, blocker, evidence URL), find the patterns
across them, do it with an agent/script rather than by hand, and verify
accuracy honestly — including reporting where the agent was wrong.

This version removes the requirement for any paid API key (no Anthropic
API key, no Composio API key, no search API key). The research agent uses
only `requests` + `BeautifulSoup` + Python's standard library.

## Architecture

```
data/apps_seed.csv          100 apps: id, name, category, hint_url
        │
        ▼
agent/research_agent.py     plain HTTP GET → strip HTML → regex keyword
                             banks (oauth2, api_key, mcp, rest, graphql,
                             contact_sales, free_trial, ...) → deterministic
                             confidence score + verdict → AppRecord
        │
        ├──► data/apps_pipeline_output.json   (raw output of this run)
        ├──► data/verification_report.json    (confidence/fetch counts)
        └──► data/verification_queue.json     (every row that needs a human)
        │
        ▼
merge step (see below)      combines the pipeline output with a prior
                             background-knowledge reference set and a
                             2-app human spot-check into one dataset,
                             with every row labeled by its evidence tier
        │
        ▼
data/apps_final.json        what site/index.html actually renders
data/analytics.json         computed distributions (not hand-typed)
data/accuracy_log.json      the 3-tier honesty report
```

## No-API mode — what it actually does
`agent/research_agent.py` fetches each seed URL with a normal HTTP GET
(User-Agent set, 10s timeout), extracts visible text with BeautifulSoup
(regex-based fallback if bs4 isn't installed), and scans that text against
keyword banks for auth methods, API surface, MCP mentions, and
gating/self-serve language. Confidence and verdict come from a fixed,
auditable decision tree over the matched keyword banks — read
`derive_record()` in the script, there's no hidden model call.

If a fetch fails (network error, non-2xx status) or the page has no
matching keywords, the app is marked `confidence="Low"` and
`verdict="Unclear"` with an honest blocker string. **Nothing is guessed.**

## Installation
```bash
pip install requests beautifulsoup4
```
No `ANTHROPIC_API_KEY`, no `COMPOSIO_API_KEY`, no search API key needed
anywhere in this repo.

## How to run

Test on 3 apps first (as the assignment asks):
```bash
python agent/research_agent.py \
  --input data/apps_seed.csv \
  --out data/apps_test.json \
  --limit 3
```

Run the full 100:
```bash
python agent/research_agent.py \
  --input data/apps_seed.csv \
  --out data/apps_pipeline_output.json
```

Flags:
```
--input   CSV with columns: id,name,category,hint_url   (required)
--out     where to write the AppRecord JSON list         (required)
--limit   only process the first N rows, for testing
--delay   seconds between requests, default 0.5 (politeness)
```
`--help` documents the same.

Each run also writes `verification_report.json` and
`verification_queue.json` next to `--out`.

## What actually happened when this was run
This repo was built inside a sandboxed agent container whose outbound
network is restricted to a small domain allowlist (`github.com`,
`pypi.org`, package registries). Real docs domains — `salesforce.com`,
`developers.notion.com`, `stripe.com`, etc. — are outside that allowlist,
so the container's egress proxy returned `403` for 97 of the 100 seed
URLs before the request ever reached the target site.

The 3 seed URLs that happened to point at `github.com` (GitHub itself,
Sherlock, Mermaid CLI) fetched successfully and the keyword extractor
found real evidence — for example GitHub's own homepage text matched the
`mcp` keyword bank (GitHub currently promotes an "MCP Registry" on its
homepage). That's proof the fetch → parse → extract → score pipeline
works end-to-end; it just couldn't prove full 100-app coverage from
*this specific sandbox*. Run the identical script from a normal laptop
or CI runner with unrestricted internet and all 100 domains are reachable
the same way GitHub was here.

See `data/verification_report.json` for the exact counts
(`fetch_ok: 3, fetch_failed: 97`) and `data/accuracy_log.json` for the
full three-tier breakdown described below.

## The merge step (how `apps_final.json` was built)
Because live fetch coverage in this environment was limited to 3 apps, the
final dataset combines three evidence tiers so nothing is misrepresented:

1. **Pipeline-fetched (3 apps)** — real HTTP 200 + keyword match, this run.
2. **Human spot-checked (2 apps: Attio, Otter AI)** — manually
   cross-referenced against live docs before this no-API pipeline
   existed. Both checks found the background-knowledge guess was wrong
   or incomplete (see `data/accuracy_log.json` → `tier_2_human_spot_check`
   for the specifics).
3. **Background knowledge (95 apps)** — compiled from general knowledge
   of these products' public docs, *not* verified by a fetch in this run.
   Every one of these rows is labeled `"source": "background-knowledge"`
   and `"verified": false` in `data/apps_final.json`, and all 95 are
   listed in `data/verification_queue.json` as the literal human/agent
   to-do list this project produces.

To rebuild `apps_final.json` after a fresh pipeline run, re-run the merge
logic documented inline where it was produced (tags each record by
`fetch_status`, falls back to the reference set, marks everything else
`background-knowledge`) — it's a ~30-line script, not a separate module,
so it's easy to adapt to your own seed set.

## Verification / accuracy — the honest numbers
- **3/100** apps have a real, live, automatically-fetched evidence
  snippet from this run.
- **2/100** apps were manually checked against live docs by a human; both
  corrections are documented with sources in `data/accuracy_log.json`.
- **95/100** apps are background knowledge, explicitly marked
  "Not independently verified" everywhere in the UI and data — no
  accuracy percentage is claimed for this tier.
- **No single "accuracy %" is reported across all 100.** That would
  average together three different evidence qualities into one
  meaningless number. The three tiers are reported separately, on
  purpose, in `site/index.html` → "Verification" section.

## Output files
| File | What it is |
|---|---|
| `data/apps_seed.csv` | Input: 100 apps + category + hint URL |
| `data/apps_pipeline_output.json` | Raw output of the no-API agent, this run |
| `data/apps_reference.json` | Prior background-knowledge dataset (pre-dates the no-API pipeline) |
| `data/apps_final.json` | Merged, source-labeled dataset the HTML renders |
| `data/analytics.json` | Computed distributions used in the "patterns" section |
| `data/accuracy_log.json` | The 3-tier honesty report |
| `data/verification_report.json` | Fetch/confidence counts from the last agent run |
| `data/verification_queue.json` | Every app still needing human verification |
| `site/index.html` | Case study source (references `data_embed.js`) |
| `site/index_final.html` | Same page with data inlined — the deployable single file |

## Deploying the HTML
`site/index_final.html` is fully self-contained (data inlined, no build
step, no external requests). Open it directly in a browser, or host it
anywhere that serves static files (GitHub Pages, Netlify, S3, etc).

## What was automated vs what still needs a human
**Automated:** fetching, HTML stripping, keyword extraction, confidence
scoring, verdict assignment, the verification queue, and all analytics/
pattern numbers on the page.

**Still needs a human (or a pipeline re-run with real network access):**
the 95 background-knowledge rows listed in `verification_queue.json` —
that file is the actual next step, not a formality.
