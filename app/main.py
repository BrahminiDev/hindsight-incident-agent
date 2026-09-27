"""HTTP API + static UI for the incident agent."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import IncidentAgent
from .config import settings
from .llm import GroqLLM
from .memory import IncidentMemory

logging.basicConfig(level=logging.INFO)
ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
DATA = ROOT / "data"

app = FastAPI(title="Paylane Incident Memory Agent")


@lru_cache
def memory() -> IncidentMemory:
    mem = IncidentMemory.connect(settings.hindsight_url, settings.hindsight_api_key, settings.bank_id)
    mem.ensure_bank()
    return mem


@lru_cache
def agent() -> IncidentAgent:
    llm = GroqLLM(settings.groq_api_key or "", settings.groq_model, settings.groq_fallback_model)
    return IncidentAgent(llm, lambda q, s: memory().recall(q, s), settings.groq_model)


def _require_config() -> None:
    missing = settings.missing()
    if missing:
        raise HTTPException(503, f"Missing configuration: {', '.join(missing)}. Copy .env.example to .env.")


class TriageRequest(BaseModel):
    alert: str = Field(min_length=5)
    service: str | None = None
    mode: str = Field("memory", pattern="^(memory|no_memory|compare)$")


class ResolveRequest(BaseModel):
    incident_id: str
    service: str
    alert: str
    root_cause: str = Field(min_length=3)
    fix: str = Field(min_length=3)
    suggestion_verdict: str = Field("helped", pattern="^(helped|partial|wrong)$")
    time_to_mitigate_min: int | None = None
    notes: str | None = None


@app.get("/api/health")
def health():
    return {"ok": not settings.missing(), "missing": settings.missing(), "bank_id": settings.bank_id,
            "model": settings.groq_model, "hindsight_url": settings.hindsight_url}


@app.get("/api/demo-alerts")
def demo_alerts():
    return json.loads((DATA / "demo_alerts.json").read_text(encoding="utf-8"))


@app.post("/api/triage")
def triage(req: TriageRequest):
    _require_config()
    a = agent()
    try:
        if req.mode == "compare":
            with ThreadPoolExecutor(2) as pool:
                without = pool.submit(a.triage, req.alert, req.service, False)
                with_mem = pool.submit(a.triage, req.alert, req.service, True)
                return {"without_memory": without.result().to_json(), "with_memory": with_mem.result().to_json()}
        result = a.triage(req.alert, req.service, req.mode == "memory")
        return {"with_memory" if result.memory_enabled else "without_memory": result.to_json()}
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from e


@app.post("/api/resolve")
def resolve(req: ResolveRequest):
    _require_config()
    memory().retain_resolution(req.model_dump())
    return {"retained": True, "incident_id": req.incident_id}


@app.get("/api/memories")
def memories(q: str, service: str | None = None):
    _require_config()
    return {"memories": [asdict(m) for m in memory().recall(q, service)]}


@app.get("/api/playbook")
def playbook():
    _require_config()
    return {"markdown": memory().playbook()}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
