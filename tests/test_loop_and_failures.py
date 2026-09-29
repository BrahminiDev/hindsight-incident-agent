"""The learning loop end to end, plus the failure paths. Still fully offline."""

import json
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent import IncidentAgent
from app.config import Settings
from app.llm import GroqLLM
from app.memory import IncidentMemory, MemoryUnavailable

DEMO = {a["label"]: a for a in json.loads((main.DATA / "demo_alerts.json").read_text(encoding="utf-8"))}


class InMemoryHindsight:
    """Stands in for the Hindsight client: retain stores text, recall matches on shared words.

    Real Hindsight does fact extraction and semantic retrieval; this only has to
    prove that what the app retains is what it later recalls and sends to the LLM.
    """

    def __init__(self):
        self.docs = {}

    def retain(self, *, bank_id, content, document_id, tags, **_):
        self.docs[document_id] = SimpleNamespace(text=content, tags=tags)

    def recall(self, *, bank_id, query, tags=None, **_):
        words = set(re.findall(r"[a-z0-9-]{4,}", query.lower()))
        hits = []
        for doc_id, d in self.docs.items():
            if tags and not set(tags) & set(d.tags):
                continue
            if len(words & set(re.findall(r"[a-z0-9-]{4,}", d.text.lower()))) >= 3:
                hits.append(SimpleNamespace(id=f"{doc_id}-f", text=d.text, type="experience",
                                            occurred_start=None, mentioned_at="2026-09-27T03:40:00+00:00",
                                            document_id=doc_id, tags=d.tags))
        return SimpleNamespace(results=hits)


class GroundedLLM:
    """Fake LLM that only cites incident IDs it was actually shown in the prompt."""

    def __init__(self):
        self.prompts = []

    def complete(self, system, user):
        self.prompts.append(user)
        ids = sorted(set(re.findall(r"\bINC-\d{4}\b", user)))
        return json.dumps({
            "severity": "SEV2",
            "summary": "matches a past incident" if ids else "no history for this",
            "likely_root_cause": "see memory" if ids else "unknown",
            "confidence": "high" if ids else "low",
            "similar_incidents": [{"id": i, "when": "today", "why_similar": "same symptoms"} for i in ids],
            "next_steps": ["check disk usage"],
            "avoid": [],
            "estimated_time_to_mitigate": "",
        })


def test_end_to_end_incident_recall_recommend_retain_then_improve():
    """Incident #1 has no history; after it is resolved and retained, incident #2 recalls it."""
    mem = IncidentMemory(InMemoryHindsight(), "bank")
    llm = GroundedLLM()
    agent = IncidentAgent(llm, mem.recall, "fake")
    first = DEMO["search-svc #1: Elasticsearch RED (no history)"]
    second = DEMO["search-svc #2: RED again after a reindex"]

    # 1. cold start: nothing recalled, and the agent says so instead of inventing history
    r1 = agent.triage(first["alert"], "search-svc", use_memory=True)
    assert r1.memories == [] and r1.triage.similar_incidents == []
    assert "nothing relevant was recalled" in llm.prompts[-1]

    # 2. resolve: the real outcome goes back into memory
    res = first["demo_resolution"]
    retained = mem.retain_resolution({**res, "service": "search-svc", "alert": first["alert"]})
    assert "merchants-v6" in retained and "PARTIALLY" in retained

    # 3. a similar incident: recall finds the resolution and the prompt carries it to the LLM
    r2 = agent.triage(second["alert"], "search-svc", use_memory=True)
    assert [m.document_id for m in r2.memories] == ["INC-2331"]
    assert "Restarting es-data-2 did NOT help" in llm.prompts[-1]
    assert r2.triage.similar_incidents[0]["id"] == "INC-2331"


def test_empty_bank_recall_returns_nothing():
    assert IncidentMemory(InMemoryHindsight(), "bank").recall("anything at all", "kafka") == []


def test_hindsight_outage_becomes_memory_unavailable():
    class Down:
        def recall(self, **_):
            raise ConnectionError("connection refused")

    with pytest.raises(MemoryUnavailable, match="Hindsight recall failed: connection refused"):
        IncidentMemory(Down(), "bank").recall("q", "svc")


# ---- LLM failure handling -------------------------------------------------------

def _llm_with(behaviour, monkeypatch):
    monkeypatch.setattr("app.llm.time.sleep", lambda s: None)
    llm = GroqLLM("key", "primary", "fallback")
    calls = []

    def create(model, **_):
        calls.append(model)
        return behaviour(model)

    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return llm, calls


def test_llm_retries_then_falls_back_to_second_model(monkeypatch):
    def behaviour(model):
        if model == "primary":
            raise RuntimeError("json_validate_failed")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])

    llm, calls = _llm_with(behaviour, monkeypatch)
    assert llm.complete("s", "u") == "{}"
    assert calls == ["primary", "primary", "fallback"]


def test_llm_gives_up_with_clear_error(monkeypatch):
    def behaviour(model):
        raise TimeoutError("read timeout")

    llm, calls = _llm_with(behaviour, monkeypatch)
    with pytest.raises(RuntimeError, match="LLM unavailable after retries: read timeout"):
        llm.complete("s", "u")
    assert len(calls) == 3


# ---- HTTP API -------------------------------------------------------------------

CONFIGURED = Settings(groq_api_key="g", hindsight_api_key="h", hindsight_url="https://api.hindsight.vectorize.io")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "settings", CONFIGURED)
    return TestClient(main.app)


def test_missing_configuration_is_reported():
    s = Settings(groq_api_key=None, hindsight_api_key=None, hindsight_url="https://api.hindsight.vectorize.io")
    assert s.missing() == ["GROQ_API_KEY", "HINDSIGHT_API_KEY"]
    local = Settings(groq_api_key="g", hindsight_api_key=None, hindsight_url="http://localhost:8888")
    assert local.missing() == []


def test_api_refuses_to_run_unconfigured(monkeypatch):
    monkeypatch.setattr(main, "settings", Settings(groq_api_key=None, hindsight_api_key=None))
    r = TestClient(main.app).post("/api/triage", json={"alert": "checkout 5xx", "mode": "memory"})
    assert r.status_code == 503 and "GROQ_API_KEY" in r.json()["detail"]


@pytest.mark.parametrize("body", [
    {"alert": "hi"},                                      # too short
    {"alert": "x" * 8001},                                # too long
    {"alert": "checkout 5xx", "mode": "yolo"},            # unknown mode
    {"alert": "checkout 5xx", "service": "Bad Service!"}, # invalid service name
])
def test_triage_input_validation(client, body):
    assert client.post("/api/triage", json=body).status_code == 422


def test_triage_returns_502_when_hindsight_is_down(client, monkeypatch):
    def recall(q, s):
        raise MemoryUnavailable("Hindsight recall failed: 503")

    monkeypatch.setattr(main, "agent", lambda: IncidentAgent(GroundedLLM(), recall, "fake"))
    r = client.post("/api/triage", json={"alert": "checkout 5xx", "service": "checkout-api", "mode": "memory"})
    assert r.status_code == 502 and "Hindsight recall failed" in r.json()["detail"]


def test_compare_mode_returns_both_columns(client, monkeypatch):
    mem = IncidentMemory(InMemoryHindsight(), "bank")
    monkeypatch.setattr(main, "agent", lambda: IncidentAgent(GroundedLLM(), mem.recall, "fake"))
    r = client.post("/api/triage", json={"alert": "checkout 5xx after deploy", "mode": "compare"})
    body = r.json()
    assert r.status_code == 200
    assert body["without_memory"]["memory_enabled"] is False and body["with_memory"]["memory_enabled"] is True


def test_resolve_endpoint_retains_and_echoes_what_was_stored(client, monkeypatch):
    fake = InMemoryHindsight()
    monkeypatch.setattr(main, "memory", lambda: IncidentMemory(fake, "bank"))
    r = client.post("/api/resolve", json={
        "incident_id": "INC-2331", "service": "search-svc", "alert": "ES cluster RED",
        "root_cause": "disk flood-stage watermark", "fix": "deleted old index", "suggestion_verdict": "partial",
    })
    assert r.status_code == 200 and r.json()["retained"] is True
    assert "disk flood-stage watermark" in r.json()["content"]
    assert "INC-2331" in fake.docs


def test_rate_limit_switches_model_then_waits_and_retries(monkeypatch):
    import httpx
    from groq import RateLimitError

    slept = []
    monkeypatch.setattr("app.llm.time.sleep", slept.append)
    limited = RateLimitError("429", response=httpx.Response(429, headers={"retry-after": "12"},
                             request=httpx.Request("POST", "https://api.groq.com")), body=None)
    replies = iter([limited, limited, "{}"])  # primary limited, fallback limited, primary after waiting

    def create(model, **_):
        r = next(replies)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=r))])

    llm = GroqLLM("key", "primary", "fallback")
    calls = []
    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda model, **kw: calls.append(model) or create(model, **kw))))
    assert llm.complete("s", "u") == "{}"
    assert calls == ["primary", "fallback", "primary"]  # no pointless same-model retry
    assert slept == [12.0]  # honoured retry-after


def test_password_protects_every_page_when_set(monkeypatch):
    import base64 as b64

    monkeypatch.setattr(main, "settings", Settings(groq_api_key="g", hindsight_api_key="h", app_password="s3cret"))
    c = TestClient(main.app)
    auth = lambda pw: {"Authorization": "Basic " + b64.b64encode(f"judge:{pw}".encode()).decode()}

    assert c.get("/").status_code == 401
    assert "Basic" in c.get("/").headers["www-authenticate"]  # browser shows its login box
    assert c.get("/api/demo-alerts", headers=auth("wrong")).status_code == 401
    assert c.get("/api/demo-alerts", headers=auth("s3cret")).status_code == 200
    assert c.get("/healthz").status_code == 200  # hosting health check stays open


def test_no_password_configured_means_open_access(monkeypatch):
    monkeypatch.setattr(main, "settings", Settings(groq_api_key="g", hindsight_api_key="h", app_password=None))
    assert TestClient(main.app).get("/api/demo-alerts").status_code == 200
