"""Run management and CSV validation for the live research dashboard."""
from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.research_agent import derive_record, verify_pass

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "data" / "runs"
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_APPS = 500
REQUIRED_ALIASES = {
    "name": {"name", "app_name", "app"},
    # hint_url keeps the repository's original 100-app seed CSV directly usable.
    "website": {"website", "url", "hint_url"},
}


class CsvValidationError(ValueError):
    """A user-facing problem with an uploaded CSV."""


def parse_csv(csv_content: str) -> list[dict[str, str]]:
    """Validate and normalize supported CSV headers without trusting its values."""
    if not csv_content or not csv_content.strip():
        raise CsvValidationError("The CSV is empty.")
    if len(csv_content.encode("utf-8")) > MAX_CSV_BYTES:
        raise CsvValidationError("The CSV is larger than the 2 MB limit.")

    try:
        reader = csv.DictReader(io.StringIO(csv_content))
        fieldnames = reader.fieldnames or []
    except csv.Error as exc:
        raise CsvValidationError(f"The CSV could not be read: {exc}") from exc

    normalized = {name.strip().lower(): name for name in fieldnames if name}
    name_column = next((normalized[x] for x in REQUIRED_ALIASES["name"] if x in normalized), None)
    website_column = next((normalized[x] for x in REQUIRED_ALIASES["website"] if x in normalized), None)
    if not name_column or not website_column:
        raise CsvValidationError(
            "Expected name and website columns (also accepts app_name,url; name,url; app,website; or the existing hint_url seed column)."
        )

    apps: list[dict[str, str]] = []
    for row_number, row in enumerate(reader, start=2):
        name = (row.get(name_column) or "").strip()
        website = (row.get(website_column) or "").strip()
        if not name and not website:
            continue
        if not name or not website:
            raise CsvValidationError(f"Row {row_number} needs both an app name and website URL.")
        if not re.match(r"^https?://[^\s/$.?#][^\s]*$", website, flags=re.I):
            raise CsvValidationError(f"Row {row_number} has an invalid http(s) website URL.")
        apps.append({"name": name[:200], "website": website[:2048]})
    if not apps:
        raise CsvValidationError("No valid app rows were found.")
    if len(apps) > MAX_APPS:
        raise CsvValidationError(f"A run can contain at most {MAX_APPS} apps.")
    return apps


class RunManager:
    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.lock = asyncio.Lock()

    async def create_run(self, apps: list[dict[str, str]], source: str) -> dict[str, Any]:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        state: dict[str, Any] = {
            "id": run_id, "source": source, "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "queued", "total": len(apps), "completed": 0, "failed": 0,
            "current_app": None, "apps": apps, "results": [], "events": [],
            "run_dir": run_dir,
        }
        async with self.lock:
            self.runs[run_id] = state
        (run_dir / "input.json").write_text(json.dumps(apps, indent=2), encoding="utf-8")
        await self._publish(state, "run_started", message=f"Queued {len(apps)} apps for sequential research.")
        asyncio.create_task(self._process(state))
        return self.summary(state)

    async def _process(self, state: dict[str, Any]) -> None:
        state["status"] = "running"
        for position, app in enumerate(state["apps"], start=1):
            state["current_app"] = app["name"]
            await self._publish(state, "app_started", app=app, position=position,
                                message=f"Fetching {app['website']}")
            try:
                # The existing agent does the actual network fetch and evidence extraction.
                record = await asyncio.to_thread(derive_record, position, app["name"], "Unknown", app["website"])
                payload = asdict(record)
                payload["status"] = "Completed" if record.fetch_status == "ok" else "Failed"
                payload["failure_reason"] = "" if record.fetch_status == "ok" else record.fetch_status
            except Exception as exc:  # keep one broken URL from halting the run
                payload = {
                    "id": position, "name": app["name"], "category": "Unknown", "desc": "Not independently verified.",
                    "auth": "Unknown", "selfServe": "Unknown", "mcp": "Unknown", "surface": "Unknown",
                    "verdict": "Unclear", "blocker": "Research worker error; human verification required.",
                    "evidence": app["website"], "evidenceSnippet": "", "confidence": "Low", "verified": False,
                    "matched_terms": [], "fetch_status": f"worker_error:{type(exc).__name__}",
                    "status": "Failed", "failure_reason": f"worker_error:{type(exc).__name__}",
                }
            state["results"].append(payload)
            state["completed"] += 1
            if payload["status"] == "Failed":
                state["failed"] += 1
            self._save_results(state)
            await self._publish(state, "app_completed", app=payload, position=position,
                                message=("completed" if payload["status"] == "Completed" else f"failed: {payload['failure_reason']}"))

        state["current_app"] = None
        state["status"] = "completed"
        records = [self._record_proxy(result) for result in state["results"]]
        report, queue = verify_pass(records)
        (state["run_dir"] / "verification_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (state["run_dir"] / "verification_queue.json").write_text(json.dumps(queue, indent=2), encoding="utf-8")
        await self._publish(state, "run_finished", message="Research run finished.")

    @staticmethod
    def _record_proxy(data: dict[str, Any]) -> Any:
        """verify_pass only needs attribute access; retain the agent's reporting logic."""
        return type("Record", (), data)()

    def _save_results(self, state: dict[str, Any]) -> None:
        (state["run_dir"] / "results.json").write_text(json.dumps(state["results"], indent=2), encoding="utf-8")

    async def _publish(self, state: dict[str, Any], event_type: str, **data: Any) -> None:
        event = {"type": event_type, "run": self.summary(state), **data}
        state["events"].append(event)

    @staticmethod
    def summary(state: dict[str, Any]) -> dict[str, Any]:
        return {key: state[key] for key in ("id", "source", "created_at", "status", "total", "completed", "failed", "current_app")}

    def get(self, run_id: str) -> dict[str, Any] | None:
        return self.runs.get(run_id)
