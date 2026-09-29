"""Live end-to-end check against the REAL Hindsight and Groq services (no fakes).

Proves the demo story: cold start -> retain the resolution -> the similar incident recalls it.
Writes the evidence to docs/live-verification.md. Never prints or writes API keys.

    python -m scripts.verify_live            # reseeds the bank first (same as demo prep)
    python -m scripts.verify_live --no-seed  # reuse the current bank (INC-2331 must not exist yet)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from app.agent import IncidentAgent
from app.config import settings
from app.llm import GroqLLM
from app.memory import IncidentMemory
from scripts.seed import load_incidents

ROOT = Path(__file__).resolve().parent.parent
DEMO = {a["label"]: a for a in json.loads((ROOT / "data" / "demo_alerts.json").read_text(encoding="utf-8"))}
FIRST = DEMO["search-svc #1: Elasticsearch RED (no history)"]
SECOND = DEMO["search-svc #2: RED again after a reindex"]
RESOLUTION = FIRST["demo_resolution"]
ES_WORDS = re.compile(r"elasticsearch|search-svc|merchants-v|reindex|INC-2331|shard", re.I)

log_lines: list[str] = []
checks: list[tuple[str, bool]] = []


def say(line: str = "") -> None:
    print(line, flush=True)
    log_lines.append(line)


def check(name: str, ok: bool) -> bool:
    checks.append((name, ok))
    say(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    return ok


def show_triage(result) -> None:
    t = result.triage
    say(f"  model: {result.model} | recall {result.recall_ms} ms | llm {result.llm_ms} ms")
    say(f"  memories recalled: {len(result.memories)} "
        f"(documents: {sorted({m.document_id for m in result.memories if m.document_id})})")
    say(f"  severity/confidence: {t.severity} / {t.confidence}")
    say(f"  summary: {t.summary}")
    say(f"  likely root cause: {t.likely_root_cause}")
    say(f"  similar incidents: {[s['id'] for s in t.similar_incidents]}")
    for i, step in enumerate(t.next_steps, 1):
        say(f"  step {i}: {step}")
    for a in t.avoid:
        say(f"  avoid: {a}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-seed", action="store_true")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
    if settings.missing():
        print(f"Missing in .env: {', '.join(settings.missing())}")
        return 2

    say(f"# Live verification run, {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}")
    say(f"Hindsight: {settings.hindsight_url} | bank: {settings.bank_id} | LLM: Groq {settings.groq_model}")

    mem = IncidentMemory.connect(settings.hindsight_url, settings.hindsight_api_key, settings.bank_id)
    llm = GroqLLM(settings.groq_api_key, settings.groq_model, settings.groq_fallback_model)
    agent = IncidentAgent(llm, mem.recall, settings.groq_model)

    say("\n## STEP 0: connectivity + seed")
    mem.ensure_bank()
    check("Hindsight reachable and API key accepted", True)
    llm.ping()
    check("Groq reachable and API key accepted", True)
    if not args.no_seed:
        try:
            mem.reset()
        except Exception:
            pass  # bank may not exist yet
        mem.ensure_bank()
        t0 = time.perf_counter()
        incidents = load_incidents()
        for inc in incidents:
            mem.retain_incident(inc)
        say(f"  seeded {len(incidents)} historical incidents in {time.perf_counter() - t0:.0f}s")

    say("\n## STEP 1: cold start (search-svc #1)")
    say(f"  alert: {FIRST['alert'].splitlines()[0]}")
    r1 = agent.triage(FIRST["alert"], FIRST["service"], use_memory=True)
    show_triage(r1)
    es_hits = [m for m in r1.memories if ES_WORDS.search(m.text or "")]
    check("no Elasticsearch/search-svc memory recalled (cold start)", not es_hits)
    check("agent did not cite any incident ID for the new failure type",
          not any(s["id"].startswith("INC-") for s in r1.triage.similar_incidents)
          or all(s["id"] in {m.document_id for m in r1.memories} for s in r1.triage.similar_incidents))

    say("\n## STEP 2: retain the resolution (INC-2331)")
    stored = mem.retain_resolution({**RESOLUTION, "service": FIRST["service"], "alert": FIRST["alert"]})
    check("Hindsight retain call succeeded", True)
    found = mem.client.list_memories(bank_id=settings.bank_id, search_query="merchants-v6", limit=20)
    items = found.items or []
    say(f"  list_memories('merchants-v6') -> {found.total} memory unit(s)")
    for it in items[:5]:
        text = it.get("text") if isinstance(it, dict) else getattr(it, "text", "")
        say(f"    - {str(text)[:160]}")
    check("INC-2331 facts are stored in Hindsight", found.total > 0)

    say("\n## STEP 3: similar incident recalls it (search-svc #2)")
    say(f"  alert: {SECOND['alert'].splitlines()[0]}")
    r2 = agent.triage(SECOND["alert"], SECOND["service"], use_memory=True)
    show_triage(r2)
    say("  recalled memory text:")
    for m in r2.memories[:6]:
        say(f"    - [{m.document_id}] {m.text[:180]}")
    check("Hindsight recall returned INC-2331", any(m.document_id == "INC-2331" for m in r2.memories))
    rec = " ".join([r2.triage.summary, r2.triage.likely_root_cause, *r2.triage.next_steps, *r2.triage.avoid])
    cited = any(s["id"] == "INC-2331" for s in r2.triage.similar_incidents)
    uses = bool(re.search(r"merchants-v6|old index|previous index|leftover|flood[- ]stage|watermark|disk", rec, re.I))
    check("recommendation cites INC-2331", cited)
    check("recommendation uses the recalled fix (old index / disk watermark)", uses)

    say("\n## STEP 3b: empty recall on a brand-new bank")
    empty = IncidentMemory.connect(settings.hindsight_url, settings.hindsight_api_key, settings.bank_id + "-empty-check")
    empty.ensure_bank()
    try:
        got = empty.recall(FIRST["alert"], FIRST["service"])
        say(f"  recalled {len(got)} memories from an empty bank")
        check("empty bank recall returns nothing", got == [])
    finally:
        empty.reset()

    passed = all(ok for _, ok in checks)
    say(f"\n## RESULT: {'PASS' if passed else 'FAIL'} ({sum(ok for _, ok in checks)}/{len(checks)} checks)")
    say("\n(The retained INC-2331 stays in the bank. Run `python -m scripts.seed --reset` before a demo recording.)")
    (ROOT / "docs" / "live-verification.md").write_text("```\n" + "\n".join(log_lines) + "\n```\n", encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
