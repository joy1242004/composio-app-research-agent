"""FastAPI server that serves the preserved dashboard and its live research API."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from server.research_service import ROOT, CsvValidationError, RunManager, parse_csv

app = FastAPI(title="Composio Live Research Dashboard")
manager = RunManager()
SITE = ROOT / "site"
DATA = ROOT / "data"


class UploadPayload(BaseModel):
    filename: str
    csv_content: str


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    # index.html remains the source dashboard. The old generated data bundle is injected at serve time.
    html = (SITE / "index.html").read_text(encoding="utf-8")
    bundle = (SITE / "data_embed.js").read_text(encoding="utf-8")
    return HTMLResponse(html.replace("__DATA__", bundle, 1))


@app.get("/api/existing")
async def existing_seed() -> JSONResponse:
    import csv
    with (DATA / "apps_seed.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return JSONResponse({"apps": [{"name": row["name"], "website": row["hint_url"]} for row in rows]})


@app.post("/api/runs")
async def start_run(payload: UploadPayload) -> JSONResponse:
    if not payload.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv file.")
    try:
        apps = parse_csv(payload.csv_content)
    except CsvValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
    run = await manager.create_run(apps, source=payload.filename)
    return JSONResponse(run, status_code=201)


@app.get("/api/runs/{run_id}")
async def run_status(run_id: str) -> JSONResponse:
    state = manager.get(run_id)
    if not state:
        raise HTTPException(404, "Research run not found.")
    return JSONResponse({**manager.summary(state), "results": state["results"]})


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    state = manager.get(run_id)
    if not state:
        raise HTTPException(404, "Research run not found.")

    async def stream() -> AsyncIterator[str]:
        next_event = 0
        while True:
            while next_event < len(state["events"]):
                event = state["events"][next_event]
                next_event += 1
                yield f"data: {json.dumps(event)}\n\n"
                if event["type"] == "run_finished":
                    break
            if next_event and state["events"][next_event - 1]["type"] == "run_finished":
                break
            await asyncio.sleep(0.25)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/runs/{run_id}/export/{format}")
async def export_run(run_id: str, format: str):
    state = manager.get(run_id)
    if not state:
        raise HTTPException(404, "Research run not found.")
    if format == "json":
        return JSONResponse(state["results"], headers={"Content-Disposition": f'attachment; filename="{run_id}-results.json"'})
    if format == "csv":
        import csv
        import io
        fields = ["name", "category", "desc", "auth", "selfServe", "surface", "mcp", "verdict", "blocker", "evidence", "evidenceSnippet", "confidence", "fetch_status", "status", "failure_reason"]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(state["results"])
        from fastapi.responses import Response
        return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{run_id}-results.csv"'})
    raise HTTPException(404, "Export format must be csv or json.")
