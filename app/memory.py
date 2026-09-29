"""Everything the agent knows lives in one Hindsight memory bank.

Three kinds of things get retained:
  * past incidents and post-mortems (seeded, then added as incidents close)
  * the outcome of each triage: did the agent's advice actually help?
  * tags per service, so recall can be scoped when the service is known

Recall pulls the most relevant of those back for a new alert, and reflect
turns the whole bank into a running "what keeps breaking" playbook.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from hindsight_client import Hindsight

BANK_MISSION = (
    "You are the institutional memory of the Paylane on-call team (a payments platform). "
    "Remember every production incident: the symptoms and exact error strings, the affected "
    "service, the root cause, which fixes worked, which fixes were tried and did NOT work, "
    "how long mitigation took, and any follow-up actions. Prefer precise, operational facts."
)

MAX_RECALLED = 14      # memories passed to the LLM (Groq free tier: 8k tokens/min)
MAX_PER_INCIDENT = 3   # facts from any single incident document
MAX_UNSOURCED = 2      # consolidated observations, which carry no document_id


class MemoryUnavailable(RuntimeError):
    """Hindsight could not be reached or rejected the request."""


def _guard(op: str):
    """Turn any client/transport error from a Hindsight call into MemoryUnavailable."""

    def wrap(fn):
        def inner(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except MemoryUnavailable:
                raise
            except Exception as e:  # the generated client raises many types (HTTP, timeout, validation)
                raise MemoryUnavailable(f"Hindsight {op} failed: {e}") from e

        inner.__name__, inner.__doc__ = fn.__name__, fn.__doc__
        return inner

    return wrap


RETAIN_INSTRUCTIONS = (
    "Keep exact error messages, metric names, versions, config keys and commands verbatim. "
    "Always record whether a remediation step worked or failed."
)


@dataclass
class Memory:
    id: str
    text: str
    type: str | None
    when: str | None
    document_id: str | None
    tags: list[str]

    def as_prompt_line(self) -> str:
        date = f"[{self.when[:10]}] " if self.when else ""
        return f"- {date}{self.text}"


class IncidentMemory:
    def __init__(self, client: Hindsight, bank_id: str):
        self.client = client
        self.bank_id = bank_id

    @classmethod
    def connect(cls, base_url: str, api_key: str | None, bank_id: str) -> "IncidentMemory":
        return cls(Hindsight(base_url=base_url, api_key=api_key, timeout=120.0), bank_id)

    @_guard("create_bank")
    def ensure_bank(self) -> None:
        """Create (or update) the bank with an incident-focused mission."""
        self.client.create_bank(
            bank_id=self.bank_id,
            name="Paylane on-call memory",
            mission=BANK_MISSION,
            retain_custom_instructions=RETAIN_INSTRUCTIONS,
            enable_observations=True,
        )

    # ---- retain -------------------------------------------------------------

    @_guard("retain")
    def retain_incident(self, incident: dict[str, Any], *, retain_async: bool = False) -> None:
        """Store a past incident / post-mortem as one document."""
        self.client.retain(
            bank_id=self.bank_id,
            content=format_incident(incident),
            timestamp=_parse_ts(incident.get("occurred_at")),
            context=f"post-mortem for {incident['id']} ({incident['service']})",
            document_id=incident["id"],
            metadata={"service": incident["service"], "severity": incident.get("severity", "")},
            tags=[f"service:{incident['service']}", "kind:incident"],
            retain_async=retain_async,
        )

    @_guard("retain")
    def retain_resolution(self, resolution: dict[str, Any]) -> str:
        """Close the loop: store what really happened and whether the agent's advice helped.

        Returns the exact text retained, so the UI can show what the agent just learned.
        """
        verdict = {
            "helped": "The agent's triage suggestion WORKED and led to the fix.",
            "partial": "The agent's triage suggestion was PARTIALLY right.",
            "wrong": "The agent's triage suggestion was WRONG and did not help.",
        }.get(resolution.get("suggestion_verdict", ""), "")
        lines = [
            f"Incident {resolution['incident_id']} on service {resolution['service']} was resolved.",
            f"Alert: {resolution['alert']}",
            f"Actual root cause: {resolution['root_cause']}",
            f"Fix that worked: {resolution['fix']}",
        ]
        if resolution.get("time_to_mitigate_min"):
            lines.append(f"Time to mitigate: {resolution['time_to_mitigate_min']} minutes.")
        if verdict:
            lines.append(verdict)
        if resolution.get("notes"):
            lines.append(f"Engineer notes: {resolution['notes']}")
        content = "\n".join(lines)
        self.client.retain(
            bank_id=self.bank_id,
            content=content,
            timestamp=datetime.now(timezone.utc),
            context=f"resolution of {resolution['incident_id']}",
            document_id=resolution["incident_id"],
            metadata={"service": resolution["service"]},
            tags=[f"service:{resolution['service']}", "kind:resolution"],
        )
        return content

    # ---- recall / reflect ---------------------------------------------------

    @_guard("recall")
    def recall(self, query: str, service: str | None = None, max_tokens: int = 3000) -> list[Memory]:
        """Recall memories relevant to an alert.

        If the service is known we try a service-scoped recall first, then fall back to
        the whole bank: cross-service incidents (a Postgres failover showing up as a
        checkout outage) are exactly the ones humans forget.

        Results are capped per source so one incident (or its consolidated observations)
        can't crowd out the rest: in live testing, near-duplicate observations about
        INC-2104/INC-2231 pushed the deploy-regression precedent INC-2291 out of the prompt.
        """
        seen: dict[str, Memory] = {}
        per_source: dict[str, int] = {}
        scopes: list[list[str] | None] = [[f"service:{service}"], None] if service else [None]
        for tags in scopes:
            resp = self.client.recall(
                bank_id=self.bank_id,
                query=query,
                max_tokens=max_tokens,
                budget="mid",
                tags=tags,
                tags_match="any",
            )
            for r in resp.results or []:
                if r.id in seen:
                    continue
                source = r.document_id or f"({r.type})"
                if per_source.get(source, 0) >= (MAX_PER_INCIDENT if r.document_id else MAX_UNSOURCED):
                    continue
                per_source[source] = per_source.get(source, 0) + 1
                seen[r.id] = Memory(
                    id=r.id,
                    text=r.text,
                    type=r.type,
                    when=r.occurred_start or r.mentioned_at,
                    document_id=r.document_id,
                    tags=list(r.tags or []),
                )
        return list(seen.values())[:MAX_RECALLED]

    @_guard("connection check")
    def ping(self) -> None:
        """Cheap authenticated call, so the UI's status reflects reality, not just config."""
        self.client.list_memories(bank_id=self.bank_id, limit=1)

    @_guard("reflect")
    def playbook(self) -> str:
        """Ask Hindsight to reason over everything it has seen so far."""
        resp = self.client.reflect(
            bank_id=self.bank_id,
            query=(
                "Write the on-call playbook this team has learned the hard way. For each service, "
                "list the recurring failure patterns, the fastest proven fix, and the fixes that "
                "look tempting but have NOT worked before. Cite incident IDs. Be concise, use markdown."
            ),
            budget="mid",
        )
        return resp.text

    def reset(self) -> None:
        self.client.delete_bank(bank_id=self.bank_id)


def format_incident(i: dict[str, Any]) -> str:
    parts = [
        f"Incident {i['id']} ({i.get('severity', 'SEV?')}) on service {i['service']}: {i['title']}",
        f"Alert that fired: {i['alert']}",
    ]
    if i.get("logs"):
        parts.append("Key log lines:\n" + "\n".join(i["logs"]))
    parts.append(f"Root cause: {i['root_cause']}")
    if i.get("tried_failed"):
        parts.append("Tried but did NOT help: " + "; ".join(i["tried_failed"]))
    parts.append(f"Fix that worked: {i['fix']}")
    if i.get("time_to_mitigate_min"):
        parts.append(f"Time to mitigate: {i['time_to_mitigate_min']} minutes.")
    if i.get("follow_up"):
        parts.append(f"Follow-up: {i['follow_up']}")
    return "\n".join(parts)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
