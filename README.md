# Composio App Research Agent

An agent-driven research workflow for analyzing API accessibility, authentication, MCP support, and integration readiness across 100 applications.

Built for the **Composio AI Product Ops Intern take-home assignment**.

## Live Demo

**Live Dashboard:**
https://composio-app-research-agent-oz3q.onrender.com/

**GitHub Repository:**
https://github.com/joy1242004/composio-app-research-agent

---

## What This Project Does

The system researches applications and collects evidence about:

* Category and description
* Authentication methods
* Self-serve vs gated access
* REST / GraphQL API availability
* MCP support
* Free trial / free tier signals
* Contact-sales / partner requirements
* Main integration blocker
* Buildability verdict
* Evidence URL and snippet
* Confidence level

It supports both the original **100-app dataset** and live research of a new CSV.

---

## Latest Live Run

The live dashboard was tested with the complete 100-app list.

| Metric                      | Result |
| --------------------------- | -----: |
| Applications                |    100 |
| Successfully fetched        |     94 |
| Failed fetches              |      6 |
| High confidence             |     16 |
| Medium confidence           |     43 |
| Low confidence              |     41 |
| Human verification required |     84 |

### Verdict Distribution

| Verdict           | Count |
| ----------------- | ----: |
| Unclear           |    30 |
| Needs partnership |    31 |
| Partial           |    20 |
| Buildable         |    19 |

These numbers come directly from the latest live run's generated verification report.

---

## How It Works

```text
App name + URL
      ↓
Fetch website
      ↓
Parse HTML
      ↓
Extract research signals
      ↓
Check auth / API / MCP / access signals
      ↓
Generate structured result
      ↓
Assign confidence + verdict
      ↓
Route uncertain results to verification queue
```

The current research agent uses HTTP requests, BeautifulSoup, and deterministic keyword/pattern matching. Each application is processed independently, so a failed request does not stop the remaining apps.

---

## Live Research Workspace

The deployed dashboard allows a reviewer to upload a CSV and research applications sequentially.

Example:

```csv
name,website
Salesforce,https://salesforce.com
HubSpot,https://hubspot.com
Notion,https://notion.so
```

The workspace supports:

* CSV upload and preview
* Sequential live research
* Live progress updates
* Activity feed
* Result filtering
* CSV export
* JSON export
* Loading the existing 100-app dataset

Supported input: up to **500 applications / 2 MB CSV**.

---

## Verification

The project uses a human-in-the-loop verification approach.

### Automated Evidence

Each result records:

* Source URL
* Evidence snippet
* Matched research signals
* Confidence
* Verdict
* Fetch status

### Human Spot Checks

Two applications were manually cross-checked against their live documentation:

* **Attio**
* **Otter AI**

These checks demonstrated that homepage-level automated extraction can miss important API, authentication, or MCP information.

### Failed Fetches

Failed requests are retained as failures instead of being silently removed or guessed.

---

## Important Limitations

The current agent is an evidence-gathering and triage system rather than a full semantic research agent.

### Homepage-first research

The agent starts with the supplied seed URL. Important information may exist only in developer portals, API documentation, pricing pages, or authentication documentation.

### Keyword-based extraction

The current implementation uses deterministic keyword and pattern matching.

```text
Keyword detected ≠ confirmed capability
Successful fetch ≠ verified fact
```

When evidence is insufficient, fields can remain `Unknown` and the verdict can remain `Unclear`.

### MCP verification

MCP-related signals are detected from fetched pages, but the current pipeline does not perform a complete live cross-check against an MCP registry.

### Human verification

Only a subset of the dataset has been manually spot-checked. Remaining uncertain records are tracked in the verification queue.

---

## Architecture

```text
                    Browser Dashboard
                           │
                           ▼
                    FastAPI Backend
                    server/main.py
                           │
                           ▼
                   Research Service
                server/research_service.py
                           │
                           ▼
                    Research Agent
                 agent/research_agent.py
                           │
                           ▼
                  External App Websites
```

Live runs are stored separately under:

```text
data/runs/<run-id>/
```

They do not overwrite the original assignment dataset.

---

## Tech Stack

**Frontend**

* HTML
* CSS
* JavaScript

**Backend**

* Python
* FastAPI
* Uvicorn

**Research**

* Requests
* BeautifulSoup
* Python standard library

**Data**

* CSV
* JSON

No paid API key is required for the current research workflow.

---

## Project Structure

```text
composio-app-research-agent/
│
├── agent/
│   └── research_agent.py
│
├── data/
│   ├── apps_seed.csv
│   ├── apps_final.json
│   ├── apps_pipeline_output.json
│   ├── apps_reference.json
│   ├── analytics.json
│   ├── accuracy_log.json
│   ├── verification_queue.json
│   └── verification_report.json
│
├── server/
│   ├── main.py
│   └── research_service.py
│
├── site/
│   ├── index.html
│   ├── index_final.html
│   └── data_embed.js
│
├── reconcile.py
├── fix_human.py
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Run Locally

### 1. Clone the repository

```bash
git clone https://github.com/joy1242004/composio-app-research-agent.git
cd composio-app-research-agent
```

### 2. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 3. Start the dashboard

```bash
python -m uvicorn server.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

---

## Run the Research Agent Directly

### Test with 3 apps

```bash
python agent/research_agent.py --input data/apps_seed.csv --out data/apps_test.json --limit 3
```

### Run the full 100-app pipeline

```bash
python agent/research_agent.py --input data/apps_seed.csv --out data/apps_pipeline_output.json
```

### Reconcile results

```bash
python reconcile.py
```

---

## Design Principles

* **Evidence over assumptions**
* **Transparent failures**
* **Human-in-the-loop verification**
* **Reproducible research**
* **Separate live runs from baseline data**

The goal is not to force every application into a confident answer. The system identifies what can be determined automatically and clearly surfaces where additional human verification is required.

---

## Submission

**Live Dashboard:**
https://composio-app-research-agent-oz3q.onrender.com/

**Source Repository:**
https://github.com/joy1242004/composio-app-research-agent

**Author:** Mayank Tiwari
