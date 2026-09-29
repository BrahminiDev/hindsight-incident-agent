"""Load the past-incident history into Hindsight.

Timestamps are relative to today (days_ago), so "this happened 3 weeks ago"
stays true whenever the demo is run.

    python -m scripts.seed           # retain all incidents
    python -m scripts.seed --reset   # delete the bank first
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import settings
from app.memory import IncidentMemory

DATA = Path(__file__).resolve().parent.parent / "data" / "incidents.json"


def load_incidents(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    incidents = json.loads(DATA.read_text(encoding="utf-8"))
    for inc in incidents:
        # Incidents fire at varied, realistic times of day.
        at = now - timedelta(days=inc["days_ago"])
        at = at.replace(hour=(inc["days_ago"] * 7) % 24, minute=(inc["days_ago"] * 13) % 60, second=0, microsecond=0)
        inc["occurred_at"] = at.isoformat()
    return incidents


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="delete the bank before seeding")
    args = parser.parse_args()

    missing = settings.missing()
    if missing:
        raise SystemExit(f"Missing configuration: {', '.join(missing)} (see .env.example)")

    mem = IncidentMemory.connect(settings.hindsight_url, settings.hindsight_api_key, settings.bank_id)
    if args.reset:
        try:
            mem.reset()
            print(f"Deleted bank {settings.bank_id}")
        except Exception as e:  # bank may not exist yet
            print(f"(reset skipped: {e})")
    mem.ensure_bank()

    incidents = load_incidents()
    for i, inc in enumerate(incidents, 1):
        mem.retain_incident(inc)
        print(f"[{i:2}/{len(incidents)}] retained {inc['id']} {inc['service']:<17} {inc['title']}")
    print(f"\nDone. {len(incidents)} incidents in bank '{settings.bank_id}'.")
    mem.client.close()  # otherwise aiohttp prints "Unclosed client session" on exit


if __name__ == "__main__":
    main()
