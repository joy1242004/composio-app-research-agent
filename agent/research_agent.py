#!/usr/bin/env python3
"""
Composio App-Research Agent — NO-API-KEY MODE
================================================
Researches a list of apps by actually fetching their public docs/marketing
pages over HTTP and scanning the rendered text for evidence of auth
methods, API surface, MCP support, and access gating. No LLM API key,
no Composio API key, no paid search API required — just `requests` (or
stdlib urllib as a fallback) and `beautifulsoup4` if installed.

This is a keyword/evidence-extraction agent, not a language model. It is
deliberately conservative: if a page can't be fetched, or doesn't contain
enough signal, the record is marked confidence="Low" / verdict="Unclear"
rather than guessed. That's the whole point of the assignment's accuracy
requirement — an honest "I don't know" beats a fabricated answer.

USAGE
-----
    python research_agent.py --input data/apps_seed.csv --out data/apps.json
    python research_agent.py --input data/apps_seed.csv --out data/apps_test.json --limit 3
    python research_agent.py --help

OUTPUT
------
    <out>                                — the AppRecord list (see schema below)
    <out-dir>/verification_report.json   — pass counts, confidence breakdown,
                                            URL fetch success/failure
    <out-dir>/verification_queue.json    — apps flagged for a human to check

SCHEMA (AppRecord)
-------------------
    id, name, category, desc, auth, selfServe, mcp, surface,
    verdict, blocker, evidence, evidenceSnippet, confidence, verified

NETWORK NOTE
------------
This script needs normal outbound internet access to the target docs
domains (salesforce.com, developers.notion.com, etc). Some sandboxed
environments (including the one this was authored in) only allow a
small domain allowlist (github.com, pypi.org, npm registries, ...) —
in that case every non-allowlisted fetch will fail with a network
error, and the script will correctly mark those apps "Unclear" with
blocker="Public documentation could not be fetched automatically."
Run it from a normal machine/CI box for full coverage. See README.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass, asdict, field
from typing import Optional

try:
    import requests
    HAVE_REQUESTS = True
except ImportError:
    import urllib.request
    HAVE_REQUESTS = False

try:
    from bs4 import BeautifulSoup
    HAVE_BS4 = True
except ImportError:
    HAVE_BS4 = False

USER_AGENT = "Mozilla/5.0 (compatible; ComposioResearchAgent/1.0; +https://composio.dev)"
TIMEOUT_SECS = 10

KEYWORD_BANKS = {
    "oauth2":     [r"oauth\s*2", r"oauth2", r"authorization code flow", r"oauth flow"],
    "api_key":    [r"api key", r"api[- ]token", r"access token", r"secret key", r"x-api-key"],
    "basic_auth": [r"basic auth", r"http basic"],
    "bot_token":  [r"bot token"],
    "mcp":        [r"\bmcp\b", r"model context protocol", r"mcp server"],
    "rest":       [r"rest api", r"restful"],
    "graphql":    [r"graphql"],
    "free_trial": [r"free trial", r"start free", r"try for free", r"free tier", r"free plan"],
    "contact_sales": [r"contact sales", r"talk to sales", r"request a demo", r"book a demo", r"request access"],
    "partner_gated": [r"partner program", r"become a partner", r"approved partners"],
    "enterprise_only": [r"enterprise plan", r"enterprise only", r"custom pricing"],
    "developer_docs": [r"developer docs", r"api docs", r"api reference", r"developer portal", r"for developers"],
}


@dataclass
class AppRecord:
    id: int
    name: str
    category: str
    desc: str
    auth: str
    selfServe: str
    mcp: str
    surface: str
    verdict: str
    blocker: str
    evidence: str
    evidenceSnippet: str
    confidence: str
    verified: bool = False
    matched_terms: list = field(default_factory=list)
    fetch_status: str = "not_attempted"


def fetch_page(url: str) -> tuple[Optional[str], str]:
    headers = {"User-Agent": USER_AGENT}
    try:
        if HAVE_REQUESTS:
            resp = requests.get(url, headers=headers, timeout=TIMEOUT_SECS, allow_redirects=True)
            if resp.status_code >= 400:
                return None, f"http_error_{resp.status_code}"
            return resp.text, "ok"
        else:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECS) as r:
                return r.read().decode("utf-8", errors="ignore"), "ok"
    except Exception as e:
        return None, f"network_error:{type(e).__name__}"


def extract_text(html: str) -> str:
    if HAVE_BS4:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return soup.get_text(" ", strip=True)
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def find_evidence(text: str) -> dict:
    lowered = text.lower()
    hits = {}
    for bank, patterns in KEYWORD_BANKS.items():
        found = []
        for pat in patterns:
            m = re.search(pat, lowered)
            if m:
                start = max(0, m.start() - 40)
                end = min(len(lowered), m.end() + 40)
                found.append(text[start:end].strip())
        if found:
            hits[bank] = found
    return hits


def derive_record(app_id: int, name: str, category: str, hint_url: str) -> AppRecord:
    text, status = fetch_page(hint_url)

    if text is None:
        return AppRecord(
            id=app_id, name=name, category=category,
            desc="Not independently verified.",
            auth="Unknown", selfServe="Unknown", mcp="Unknown", surface="Unknown",
            verdict="Unclear",
            blocker="Public documentation could not be fetched automatically.",
            evidence=hint_url, evidenceSnippet="", confidence="Low",
            verified=False, matched_terms=[], fetch_status=status,
        )

    page_text = extract_text(text)
    hits = find_evidence(page_text)
    matched = sorted(hits.keys())

    auth_bits = []
    if "oauth2" in hits: auth_bits.append("OAuth2")
    if "api_key" in hits: auth_bits.append("API key")
    if "basic_auth" in hits: auth_bits.append("Basic auth")
    if "bot_token" in hits: auth_bits.append("Bot token")
    auth = " / ".join(auth_bits) if auth_bits else "Unknown (no auth keywords found on fetched page)"

    if "contact_sales" in hits or "partner_gated" in hits or "enterprise_only" in hits:
        selfServe = "Signals of gating found (contact-sales / partner / enterprise-only language)"
    elif "free_trial" in hits:
        selfServe = "Signals of self-serve found (free trial / free tier language)"
    else:
        selfServe = "Unknown (no explicit access-model language found on fetched page)"

    surface_bits = []
    if "rest" in hits: surface_bits.append("REST")
    if "graphql" in hits: surface_bits.append("GraphQL")
    if "developer_docs" in hits: surface_bits.append("has a developer docs/API reference page")
    surface = ", ".join(surface_bits) if surface_bits else "Unknown (no API-surface keywords found)"

    mcp = "Mentions MCP on this page" if "mcp" in hits else "No MCP mention found on this page"

    signal_count = len(matched)
    if signal_count >= 4:
        confidence = "High"
    elif signal_count >= 2:
        confidence = "Medium"
    else:
        confidence = "Low"

    if signal_count == 0:
        verdict = "Unclear"
        blocker = "Fetched page had no matching auth/API/access keywords — likely a marketing homepage, not docs."
    elif "contact_sales" in hits or "partner_gated" in hits:
        verdict = "Needs partnership"
        blocker = "Page language suggests a sales/partner gate before API access."
    elif auth_bits and ("rest" in hits or "graphql" in hits or "developer_docs" in hits):
        verdict = "Buildable" if confidence != "Low" else "Partial"
        blocker = "—" if verdict == "Buildable" else "Only weak signal found on the fetched page; recommend a deeper doc-site crawl."
    elif auth_bits or surface_bits:
        verdict = "Partial"
        blocker = "Some signal found, but not enough to confidently call it buildable from this one page."
    else:
        verdict = "Unclear"
        blocker = "Insufficient evidence on the fetched page."

    snippet = ""
    for bank in ("mcp", "oauth2", "api_key", "developer_docs"):
        if bank in hits:
            snippet = hits[bank][0]
            break
    if not snippet and hits:
        snippet = next(iter(hits.values()))[0]

    return AppRecord(
        id=app_id, name=name, category=category,
        desc=f"Evidence pulled from {hint_url}",
        auth=auth, selfServe=selfServe, mcp=mcp, surface=surface,
        verdict=verdict, blocker=blocker,
        evidence=hint_url, evidenceSnippet=snippet, confidence=confidence,
        verified=False, matched_terms=matched, fetch_status=status,
    )


def verify_pass(records: list) -> tuple:
    report = {
        "total_apps": len(records),
        "confidence_high": sum(1 for r in records if r.confidence == "High"),
        "confidence_medium": sum(1 for r in records if r.confidence == "Medium"),
        "confidence_low": sum(1 for r in records if r.confidence == "Low"),
        "fetch_ok": sum(1 for r in records if r.fetch_status == "ok"),
        "fetch_failed": sum(1 for r in records if r.fetch_status != "ok"),
        "verdict_breakdown": {},
        "requires_human_verification": 0,
    }
    for r in records:
        report["verdict_breakdown"][r.verdict] = report["verdict_breakdown"].get(r.verdict, 0) + 1

    queue = []
    for r in records:
        needs_human = (
            r.confidence in ("Low", "Medium")
            or r.verdict == "Unclear"
            or r.fetch_status != "ok"
        )
        if needs_human:
            queue.append({
                "id": r.id, "name": r.name,
                "reason": "fetch failed" if r.fetch_status != "ok" else f"confidence={r.confidence}",
                "evidence": r.evidence,
            })
    report["requires_human_verification"] = len(queue)
    return report, queue


def load_seed(path: str, limit) -> list:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if limit:
        rows = rows[:limit]
    return rows


def main():
    parser = argparse.ArgumentParser(
        description="No-API-key research agent: fetches each app's public docs "
                     "page over HTTP and extracts auth/API/access evidence via "
                     "keyword analysis. Requires no LLM or Composio API key."
    )
    parser.add_argument("--input", required=True, help="CSV with columns: id,name,category,hint_url")
    parser.add_argument("--out", required=True, help="Where to write the AppRecord JSON list")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N rows (for testing)")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds to sleep between requests (politeness)")
    args = parser.parse_args()

    rows = load_seed(args.input, args.limit)
    print(f"[research_agent] {len(rows)} apps to research "
          f"(requests={'yes' if HAVE_REQUESTS else 'stdlib-fallback'}, "
          f"bs4={'yes' if HAVE_BS4 else 'regex-fallback'})", file=sys.stderr)

    records = []
    for i, row in enumerate(rows, start=1):
        name, category, url = row["name"], row["category"], row["hint_url"]
        print(f"[{i}/{len(rows)}] fetching {name} -> {url}", file=sys.stderr)
        rec = derive_record(int(row["id"]), name, category, url)
        print(f"    fetch_status={rec.fetch_status} confidence={rec.confidence} verdict={rec.verdict}", file=sys.stderr)
        records.append(rec)
        time.sleep(args.delay)

    report, queue = verify_pass(records)

    out_dir = os.path.dirname(os.path.abspath(args.out)) or "."
    os.makedirs(out_dir, exist_ok=True)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in records], f, indent=2)

    report_path = os.path.join(out_dir, "verification_report.json")
    queue_path = os.path.join(out_dir, "verification_queue.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)

    print(f"[research_agent] wrote {args.out}", file=sys.stderr)
    print(f"[research_agent] wrote {report_path}", file=sys.stderr)
    print(f"[research_agent] wrote {queue_path}", file=sys.stderr)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
