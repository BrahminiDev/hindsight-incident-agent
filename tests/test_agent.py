"""Offline tests: no Hindsight or Groq calls, both are replaced with fakes."""

import json
from types import SimpleNamespace

import pytest

from app.agent import IncidentAgent, Triage, build_user_prompt, parse_json_object
from app.memory import IncidentMemory, Memory, format_incident
from scripts.seed import load_incidents

TRIAGE_JSON = {
    "severity": "SEV1",
    "summary": "Connection hold time regression after deploy",
    "likely_root_cause": "DB transaction held across Stripe call",
    "confidence": "high",
    "similar_incidents": [{"id": "INC-2291", "when": "3 weeks ago", "why_similar": "same errors after deploy"}],
    "next_steps": ["argocd app rollback checkout-api"],
    "avoid": ["Raising DB_POOL_MAX (INC-2291)"],
    "estimated_time_to_mitigate": "~6 min",
}


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def complete(self, system, user):
        self.prompts.append(user)
        return self.replies.pop(0)


MEM = Memory(id="m1", text="INC-2291: rollback fixed pool exhaustion", type="experience",
             when="2026-09-06T10:00:00+00:00", document_id="INC-2291", tags=["service:checkout-api"])


def test_parse_json_handles_think_blocks_and_fences():
    reply = "<think>hmm {not json}</think>\n```json\n" + json.dumps(TRIAGE_JSON) + "\n```"
    assert parse_json_object(reply)["severity"] == "SEV1"


def test_parse_json_rejects_prose():
    with pytest.raises(ValueError):
        parse_json_object("I think it is the database.")


def test_triage_from_dict_tolerates_sloppy_types():
    t = Triage.from_dict({"next_steps": "restart", "similar_incidents": ["INC-1"], "confidence": "HIGH"})
    assert t.next_steps == ["restart"]
    assert t.similar_incidents[0]["id"] == "INC-1"
    assert t.confidence == "high"


def test_prompt_distinguishes_disabled_empty_and_recalled_memory():
    assert "memory disabled" in build_user_prompt("a", "x", None)
    assert "nothing relevant" in build_user_prompt("a", "x", [])
    p = build_user_prompt("a", "checkout-api", [MEM])
    assert "[2026-09-06] INC-2291" in p and "service: checkout-api" in p


def test_memory_mode_calls_recall_and_no_memory_mode_does_not():
    calls = []
    llm = FakeLLM([json.dumps(TRIAGE_JSON)] * 2)
    agent = IncidentAgent(llm, lambda q, s: calls.append((q, s)) or [MEM], "test-model")

    r = agent.triage("pool errors", "checkout-api", use_memory=False)
    assert calls == [] and r.memories == [] and "memory disabled" in llm.prompts[0]

    r = agent.triage("pool errors", "checkout-api", use_memory=True)
    assert calls == [("pool errors", "checkout-api")]
    assert r.memories == [MEM] and "INC-2291" in llm.prompts[1]
    assert r.triage.similar_incidents[0]["id"] == "INC-2291"


def test_agent_repairs_invalid_json_once():
    llm = FakeLLM(["sorry, here you go", json.dumps(TRIAGE_JSON)])
    r = IncidentAgent(llm, lambda q, s: [], "m").triage("x" * 10, None, use_memory=False)
    assert r.triage.severity == "SEV1" and len(llm.prompts) == 2


class FakeHindsight:
    def __init__(self):
        self.retained, self.recalls = [], []

    def retain(self, **kw):
        self.retained.append(kw)

    def recall(self, **kw):
        self.recalls.append(kw)
        r = SimpleNamespace(id=f"r{len(self.recalls)}", text="t", type="world", occurred_start=None,
                            mentioned_at=None, document_id="INC-1", tags=[])
        dup = SimpleNamespace(**{**vars(r), "id": "shared"})
        return SimpleNamespace(results=[r, dup])


def test_recall_scopes_by_service_then_widens_and_dedupes():
    fake = FakeHindsight()
    mems = IncidentMemory(fake, "bank").recall("q", "ledger-svc")
    assert [c["tags"] for c in fake.recalls] == [["service:ledger-svc"], None]
    assert sorted(m.id for m in mems) == ["r1", "r2", "shared"]


def test_resolution_is_retained_with_verdict_and_tags():
    fake = FakeHindsight()
    IncidentMemory(fake, "bank").retain_resolution({
        "incident_id": "INC-2401", "service": "checkout-api", "alert": "a", "root_cause": "rc",
        "fix": "rollback", "suggestion_verdict": "wrong", "notes": "it was the ORM",
    })
    kw = fake.retained[0]
    assert "WRONG" in kw["content"] and "it was the ORM" in kw["content"]
    assert kw["document_id"] == "INC-2401" and "kind:resolution" in kw["tags"]


def test_seed_data_is_well_formed():
    incidents = load_incidents()
    assert len({i["id"] for i in incidents}) == len(incidents) >= 15
    for i in incidents:
        text = format_incident(i)
        assert i["id"] in text and "Root cause:" in text and "Fix that worked:" in text
        assert i["occurred_at"]
