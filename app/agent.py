"""The triage agent: alert in, structured triage out.

With memory on, the prompt carries what Hindsight recalled about similar past
incidents; with memory off it gets nothing but the alert. Same model, same
prompt skeleton, so the difference in output is the memory.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Protocol

from .memory import Memory

SYSTEM_PROMPT = """You are the on-call incident response agent for Paylane, a payments platform
(services: checkout-api, ledger-svc, auth-gateway, notif-worker, payout-scheduler,
postgres-primary, redis-cache, kafka). A new alert just fired. Produce a triage.

Rules:
- If PAST INCIDENT MEMORY is provided, use it. Cite incident IDs (e.g. INC-2291) for every
  claim that comes from memory. Say how long ago it happened when that is known.
- Recall can return unrelated incidents. Use a memory only if it matches this alert's service,
  error messages or failure mode; silently ignore the rest.
- Explicitly warn against remediation steps that memory says did NOT work before, for a
  similar failure. Leave "avoid" empty rather than listing lessons from unrelated incidents.
- If memory says a previous agent suggestion was wrong, do not repeat it.
- If there is no relevant memory, say so plainly and give sound generic steps. Never invent
  incident IDs, dates, or history.
- Be concrete: exact commands, config keys, dashboards. No filler.

Respond with ONLY a JSON object with these keys:
{
  "severity": "SEV1" | "SEV2" | "SEV3",
  "summary": "one sentence: what is most likely happening",
  "likely_root_cause": "string",
  "confidence": "low" | "medium" | "high",
  "similar_incidents": [{"id": "INC-xxxx", "when": "e.g. 3 weeks ago", "why_similar": "string"}],
  "next_steps": ["3 to 6 ordered, concrete actions; the first is the fastest diagnostic or mitigation"],
  "avoid": ["steps that failed before, with incident ID"],
  "estimated_time_to_mitigate": "string"
}"""


class ChatLLM(Protocol):
    def complete(self, system: str, user: str) -> str: ...


@dataclass
class Triage:
    severity: str = "SEV2"
    summary: str = ""
    likely_root_cause: str = ""
    confidence: str = "low"
    similar_incidents: list[dict[str, str]] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)
    estimated_time_to_mitigate: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Triage":
        def as_list(v: Any) -> list:
            if v is None:
                return []
            return v if isinstance(v, list) else [v]

        sims = []
        for s in as_list(d.get("similar_incidents")):
            if isinstance(s, dict):
                sims.append({k: str(s.get(k, "")) for k in ("id", "when", "why_similar")})
            elif s:
                sims.append({"id": str(s), "when": "", "why_similar": ""})
        return cls(
            severity=str(d.get("severity") or "SEV2"),
            summary=str(d.get("summary") or ""),
            likely_root_cause=str(d.get("likely_root_cause") or ""),
            confidence=str(d.get("confidence") or "low").lower(),
            similar_incidents=sims,
            next_steps=[str(x) for x in as_list(d.get("next_steps"))],
            avoid=[str(x) for x in as_list(d.get("avoid"))],
            estimated_time_to_mitigate=str(d.get("estimated_time_to_mitigate") or ""),
        )


def build_user_prompt(alert: str, service: str | None, memories: list[Memory] | None) -> str:
    parts = [f"NEW ALERT (service: {service or 'unknown'}):\n{alert}"]
    if memories is None:
        parts.append("PAST INCIDENT MEMORY: (memory disabled for this run)")
    elif not memories:
        parts.append("PAST INCIDENT MEMORY: nothing relevant was recalled.")
    else:
        parts.append(
            "PAST INCIDENT MEMORY (recalled from Hindsight, most relevant first):\n"
            + "\n".join(m.as_prompt_line() for m in memories)
        )
    return "\n\n".join(parts)


def parse_json_object(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model reply (tolerates <think> blocks and fences)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("model reply contained no JSON object")
    return json.loads(text[start : end + 1])


@dataclass
class TriageResult:
    triage: Triage
    memories: list[Memory]
    memory_enabled: bool
    recall_ms: int
    llm_ms: int
    model: str

    def to_json(self) -> dict[str, Any]:
        return {
            "triage": asdict(self.triage),
            "memories": [asdict(m) for m in self.memories],
            "memory_enabled": self.memory_enabled,
            "recall_ms": self.recall_ms,
            "llm_ms": self.llm_ms,
            "model": self.model,
        }


class IncidentAgent:
    def __init__(self, llm: ChatLLM, recall: Callable[[str, str | None], list[Memory]], model_name: str):
        self.llm = llm
        self.recall = recall
        self.model_name = model_name

    def triage(self, alert: str, service: str | None, use_memory: bool) -> TriageResult:
        memories: list[Memory] | None = None
        t0 = time.perf_counter()
        if use_memory:
            memories = self.recall(alert, service)
        t1 = time.perf_counter()

        user = build_user_prompt(alert, service, memories)
        reply = self.llm.complete(SYSTEM_PROMPT, user)
        try:
            data = parse_json_object(reply)
        except (ValueError, json.JSONDecodeError):
            # One repair attempt: the open models occasionally wrap or truncate JSON.
            reply = self.llm.complete(
                SYSTEM_PROMPT, user + "\n\nYour previous reply was not valid JSON. Reply with ONLY the JSON object."
            )
            data = parse_json_object(reply)
        t2 = time.perf_counter()

        return TriageResult(
            triage=Triage.from_dict(data),
            memories=memories or [],
            memory_enabled=use_memory,
            recall_ms=int((t1 - t0) * 1000),
            llm_ms=int((t2 - t1) * 1000),
            model=self.model_name,
        )
