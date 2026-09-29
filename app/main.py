"""HTTP API + static UI for the incident agent."""

from __future__ import annotations

import base64
import json
import logging
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import IncidentAgent
from .config import settings
from .llm import GroqLLM
from .memory import IncidentMemory, MemoryUnavailable

logging.basicConfig(level=logging.INFO)
ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
DATA = ROOT / "data"

app = FastAPI(title="Paylane Incident Memory Agent")

OPEN_PATHS = {"/healthz"}  # hosting platform liveness probe; touches no paid service


@app.middleware("http")
async def require_password(request: Request, call_next):
    """Optional site-wide password, so a public deployment can't be used to drain API quota."""
    password = settings.app_password
    if not password or request.url.path in OPEN_PATHS:
        return await call_next(request)
    header = request.headers.get("authorization", "")
    if header.lower().startswith("basic "):
        try:
            _, _, given = base64.b64decode(header[6:]).decode("utf-8").partition(":")
        except (ValueError, UnicodeDecodeError):
            given = ""
        if secrets.compare_digest(given.encode(), password.encode()):
            return await call_next(request)
    return Response("Password required", status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="Paylane On-call", charset="UTF-8"'})


@app.get("/healthz")
def healthz():
    return {"ok": True}


_local = threading.local()
_bank_lock = threading.Lock()
_bank_ready = False
_compare_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="compare")


def memory() -> IncidentMemory:
    """One Hindsight client per thread.

    The sync client runs an aiohttp session on the calling thread's event loop, so a
    client created on one request thread fails on another ("Timeout context manager
    should be used inside a task"). The bank itself only needs creating once.
    """
    global _bank_ready
    mem = getattr(_local, "memory", None)
    if mem is None:
        mem = _local.memory = IncidentMemory.connect(settings.hindsight_url, settings.hindsight_api_key, settings.bank_id)
    if not _bank_ready:
        with _bank_lock:
            if not _bank_ready:
                mem.ensure_bank()
                _bank_ready = True
    return mem


@lru_cache
def agent() -> IncidentAgent:
    llm = GroqLLM(settings.groq_api_key or "", settings.groq_model, settings.groq_fallback_model)
    return IncidentAgent(llm, lambda q, s: memory().recall(q, s), settings.groq_model)


def _require_config() -> None:
    missing = settings.missing()
    if missing:
        raise HTTPException(503, f"Missing configuration: {', '.join(missing)}. Copy .env.example to .env.")


SERVICE = r"^[a-z0-9][a-z0-9._-]{0,59}$"


class TriageRequest(BaseModel):
    alert: str = Field(min_length=5, max_length=8000)
    service: str | None = Field(None, pattern=SERVICE)
    mode: str = Field("memory", pattern="^(memory|no_memory|compare)$")


class ResolveRequest(BaseModel):
    incident_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,40}$")
    service: str = Field(pattern=SERVICE)
    alert: str = Field(min_length=5, max_length=8000)
    root_cause: str = Field(min_length=3, max_length=2000)
    fix: str = Field(min_length=3, max_length=2000)
    suggestion_verdict: str = Field("helped", pattern="^(helped|partial|wrong)$")
    time_to_mitigate_min: int | None = Field(None, ge=0, le=10080)
    notes: str | None = Field(None, max_length=2000)


@app.get("/api/health")
def health():
    """Config check plus a live, authenticated call to each service. Errors never include keys."""
    out = {"ok": False, "missing": settings.missing(), "bank_id": settings.bank_id,
           "model": settings.groq_model, "hindsight_url": settings.hindsight_url,
           "hindsight": "not checked", "llm": "not checked"}
    if out["missing"]:
        return out
    try:
        memory().ping()
        out["hindsight"] = "ok"
    except MemoryUnavailable as e:
        out["hindsight"] = str(e)
    try:
        agent().llm.ping()
        out["llm"] = "ok"
    except Exception as e:  # groq raises auth, network and not-found errors
        out["llm"] = f"LLM check failed: {e}"
    out["ok"] = out["hindsight"] == "ok" and out["llm"] == "ok"
    return out


@app.get("/api/demo-alerts")
def demo_alerts():
    return json.loads((DATA / "demo_alerts.json").read_text(encoding="utf-8"))


@app.post("/api/triage")
def triage(req: TriageRequest):
    _require_config()
    a = agent()
    try:
        if req.mode == "compare":
            # A fixed pool, so each worker thread keeps (and reuses) its own Hindsight client.
            without = _compare_pool.submit(a.triage, req.alert, req.service, False)
            with_mem = _compare_pool.submit(a.triage, req.alert, req.service, True)
            return {"without_memory": without.result().to_json(), "with_memory": with_mem.result().to_json()}
        result = a.triage(req.alert, req.service, req.mode == "memory")
        return {"with_memory" if result.memory_enabled else "without_memory": result.to_json()}
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from e


@app.post("/api/resolve")
def resolve(req: ResolveRequest):
    _require_config()
    try:
        content = memory().retain_resolution(req.model_dump())
    except MemoryUnavailable as e:
        raise HTTPException(502, str(e)) from e
    return {"retained": True, "incident_id": req.incident_id, "bank_id": settings.bank_id, "content": content}


@app.get("/api/memories")
def memories(q: str = Query(min_length=2, max_length=500), service: str | None = None):
    _require_config()
    try:
        return {"memories": [asdict(m) for m in memory().recall(q, service)]}
    except MemoryUnavailable as e:
        raise HTTPException(502, str(e)) from e


@app.get("/api/playbook")
def playbook():
    _require_config()
    try:
        return {"markdown": memory().playbook()}
    except MemoryUnavailable as e:
        raise HTTPException(502, str(e)) from e


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
