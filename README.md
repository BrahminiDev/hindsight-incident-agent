# Paylane On-call: an incident agent that remembers every outage

When production breaks at 3am, the fix is usually sitting in a post-mortem nobody
re-reads. This agent triages new alerts using the team's full incident history,
stored in [Hindsight](https://github.com/vectorize-io/hindsight) agent memory. It
cites the past incident that matches, warns you off the fixes that failed last time,
and gets better every time an incident is closed.

![Architecture](docs/architecture.svg)

## Why memory is the point

Same alert, same model (`openai/gpt-oss-120b` on Groq), same prompt. The only difference is memory:

| | Without memory | With Hindsight memory |
|---|---|---|
| Diagnosis | "Pool too small for traffic" | "Same signature as **INC-2291** 3 weeks ago: a deploy moved an outbound call inside the DB transaction" |
| First step | Increase `DB_POOL_MAX`, restart pods | `argocd app rollback checkout-api` |
| Warnings | none | "Do **not** raise `DB_POOL_MAX` (made INC-2291 worse). Rolling restart didn't help in INC-2104." |
| ETA | 30-60 min | ~6 min (INC-2291 took 6 min after rollback) |

The generic answer is the one that made the real outage worse.

## How Hindsight is used

All three Hindsight operations are load-bearing. The code is in [`app/memory.py`](app/memory.py).

| Operation | Where | What it does |
|---|---|---|
| `create_bank` | on startup | One bank (`paylane-oncall`) with an ops-focused `mission` and retain instructions to keep exact error strings, and to always record whether a fix worked. |
| `retain` | `scripts/seed.py` | Loads 19 past post-mortems, each timestamped at its real date and tagged `service:<name>`, so recall can say "3 weeks ago". |
| `recall` | every triage | Two-pass: first scoped to the alerting service's tag, then bank-wide. Cross-service incidents (a Patroni failover showing up as checkout errors) are the ones people forget. |
| `retain` | **Close the loop** form | When an engineer resolves an incident, the real root cause, the fix, time-to-mitigate and a verdict on the agent's own advice (*helped / partial / wrong*) go back into memory. A wrong suggestion is remembered as wrong. |
| `reflect` | **Learned playbook** tab | Hindsight reasons over the whole bank to produce a per-service playbook of recurring failures, proven fixes and traps. Nobody writes or maintains it. |

### The learning loop you can demo

1. Pick **"checkout-api: 5xx right after deploy"** and click **Compare**. The left column is generic; the right cites INC-2291 and says to roll back.
2. Resolve it: say the rollback worked, but the real cause this time was an N+1 query from ORM eager loading in v2.44.
3. Fire a similar alert again. The agent now cites *your* incident alongside INC-2291.
4. Open **Learned playbook**. The new lesson is in it.

Another good one: **"notif-worker: consumer lag climbing"**. A naive agent says "skip the poison message" (INC-2118). Memory knows that INC-2302 looked the same, but skipping offsets was the *wrong* call and lost 2k notifications. The real cause was a rebalance storm.

**"search-svc: Elasticsearch RED"** has no history at all. The agent says so plainly and doesn't invent incident IDs.

## Run it

Needs Python 3.11+, a [Hindsight Cloud](https://ui.hindsight.vectorize.io) API key (or a local Hindsight server), and a [Groq](https://console.groq.com/keys) API key.

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # macOS/Linux: .venv/bin/pip
cp .env.example .env                               # fill in HINDSIGHT_API_KEY and GROQ_API_KEY
python -m scripts.seed --reset                     # load incident history into Hindsight
uvicorn app.main:app --reload
```

Open http://localhost:8000.

Tests run fully offline (Hindsight and Groq are faked):

```bash
python -m pytest -q
```

## Layout

```
app/
  memory.py    Hindsight bank: mission, retain (incidents + resolutions), scoped recall, reflect
  agent.py     prompt, JSON triage schema, memory on/off, JSON repair retry
  llm.py       Groq client with retry + fallback model (open models do fail on format)
  main.py      FastAPI: /api/triage, /api/resolve, /api/playbook, /api/memories
data/
  incidents.json    19 realistic post-mortems across 8 services, including recurring patterns
  demo_alerts.json  new alerts for the demo, including one with no history
scripts/seed.py     retains the history with real relative timestamps
static/             single-page ops console (no build step)
tests/              offline tests with fake Hindsight + fake LLM
```

## Design notes

- **"What did NOT work" is first-class data.** Every post-mortem records failed remediations, and the prompt requires an explicit *avoid* list. Remembering what failed is where most of the value is.
- **Honest when memory is empty.** The prompt distinguishes "memory disabled", "nothing recalled" and "recalled N memories", and forbids invented incident IDs.
- **The same model with and without memory.** Compare mode runs both in parallel, so any difference between the two answers comes from memory.
- **Open-model resilience.** JSON mode, a one-shot JSON repair, `<think>`-block stripping, and a fallback model on Groq errors.

## Links

- [Hindsight on GitHub](https://github.com/vectorize-io/hindsight)
- [Hindsight documentation](https://hindsight.vectorize.io/)
- [What is agent memory?](https://vectorize.io/what-is-agent-memory)
