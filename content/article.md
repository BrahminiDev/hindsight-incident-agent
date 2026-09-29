# My incident agent remembers the fixes that made things worse

The most dangerous advice an on-call assistant can give is advice that sounds right. "Connection pool exhausted? The pool is too small, raise it, restart the pods." It's the obvious reading of the alert. In the incident history my agent is built on, that exact response is what turned a 6-minute rollback into a 26-minute outage.

So I built an incident response agent whose most important feature isn't what it knows. It's what it remembers: every past incident, every fix that worked, and every fix that didn't.

## What the system does

An alert fires (PagerDuty text, a Grafana panel, a few log lines) and the agent returns a structured triage. That means severity, likely root cause, similar past incidents with dates, ordered next steps, and an explicit **do-not-repeat** list.

The stack is small:

- **FastAPI**, with endpoints for triage, resolve, playbook and raw recall.
- **Groq** running `openai/gpt-oss-120b`, with `openai/gpt-oss-20b` as a fallback.
- **[Hindsight agent memory](https://github.com/vectorize-io/hindsight)** as the only source of institutional knowledge.
- A single-page ops console with no build step.

I don't run a vector database, an embedding pipeline or any chunking code. The whole memory lives in one Hindsight bank, and the application only calls `retain`, `recall` and `reflect`.

The history is 19 post-mortems for a payments platform I call Paylane: checkout, ledger, auth, Kafka, Postgres, Redis. They're written to be internally consistent, down to pool sizes, error strings and replica counts.

![Architecture: alert → recall → LLM → triage → resolve → retain](../docs/architecture.svg)

## Failed fixes are first-class data

Most "RAG over post-mortems" projects retrieve the *resolution*. That misses where incidents actually get expensive. The costly mistakes are the tempting steps that don't work: restarting pods into a reconnect storm, skipping a Kafka offset when the real problem is a rebalance storm, raising a memory limit that buys one more night.

So I made "what did NOT work" as prominent as the fix, starting with the bank's mission:

```python
BANK_MISSION = (
    "You are the institutional memory of the Paylane on-call team (a payments platform). "
    "Remember every production incident: the symptoms and exact error strings, the affected "
    "service, the root cause, which fixes worked, which fixes were tried and did NOT work, "
    "how long mitigation took, and any follow-up actions. Prefer precise, operational facts."
)
```

The retain instructions add one rule: keep error messages, config keys and commands verbatim. `QueuePool limit of size 8 overflow 0 reached` is a fingerprint. If memory paraphrases it into "database issues", recall gets vague and the agent goes generic again.

Each post-mortem is retained as one document, timestamped at the date it happened and tagged by service:

```python
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
```

The timestamp is what lets the agent say "three weeks ago" instead of just "before". In an incident channel, recency changes how much you trust a precedent.

## Recall: scoped first, then wide

My first version recalled only from the alerting service. It handled the easy cases and failed the interesting one: `cannot execute INSERT in a read-only transaction` on checkout-api. The history for that error lives under **postgres-primary**. A Patroni failover moved the leader, and pgbouncer still pointed at the old primary.

So recall runs twice, first scoped to the service tag and then across the whole bank, with duplicates dropped:

```python
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
```

The scoped pass puts the most specific history first in the prompt, and the wide pass catches cross-service causes. That ordering mattered more than any prompt tweak I tried.

## Closing the loop: the agent grades itself

Retrieval alone gives you a good search box. The resolve step is what makes it an agent that learns. When an engineer closes an incident, they record the real root cause, the fix, time to mitigate, and a verdict on the agent's own suggestion. That verdict goes straight into [Hindsight](https://hindsight.vectorize.io/):

```python
verdict = {
    "helped": "The agent's triage suggestion WORKED and led to the fix.",
    "partial": "The agent's triage suggestion was PARTIALLY right.",
    "wrong": "The agent's triage suggestion was WRONG and did not help.",
}.get(resolution.get("suggestion_verdict", ""), "")
```

The system prompt carries one rule that only makes sense with memory: *if memory says a previous agent suggestion was wrong, do not repeat it.* A stateless model will make the same wrong call forever. With memory, a wrong answer is a one-time cost.

## What it looks like

**Learning from zero.** Elasticsearch has no history in the bank. An alert says the cluster is RED with unassigned primaries on `merchants-v7`. The agent says plainly that nothing relevant was recalled and gives generic shard-allocation steps. It doesn't invent an incident ID.

I resolve it as INC-2331: a reindex left the old index behind, a data node crossed the flood-stage disk watermark, and restarting the node didn't help. I mark the agent's advice *partial*.

Later a second alert fires: RED again, a different index, "started after last night's reindex job". This time recall returns INC-2331. The triage cites it, starts with `GET _cat/allocation?v` to check disk usage, suggests deleting the leftover previous index, and warns that restarting a node without freeing disk space didn't help last time.

**Deep history.** The **Compare** button runs the same alert through the same model twice in parallel, once without memory and once with Hindsight recall:

> checkout-api 5xx rate 17%, p99 latency 6.8s. Started 4 minutes after deploy v2.44.
> `sqlalchemy.exc.TimeoutError: QueuePool limit of size 8 overflow 0 reached`

Without memory, the model reads a pool error the obvious way: pool too small or a connection leak. It starts by inspecting pgbouncer, and its do-not-repeat list is empty, because it has nothing to learn from.

With memory, it recalls INC-2291 (identical errors three weeks earlier, right after a deploy) alongside two older pool-exhaustion incidents. The root cause shifts to what INC-2291 taught: the new release holds connections longer, for example outbound calls inside DB transactions. The do-not-repeat list reads "increasing DB_POOL_MAX (made exhaustion worse in INC-2291)" and "rolling restart of checkout-api pods (worsened INC-2104)".

The first version of this didn't cite INC-2291 at all. Recall returned it, but near-duplicate facts about the two older incidents filled every slot in the prompt. Capping each incident at three facts fixed it. Retrieval that is technically correct can still starve the model of the one precedent that matters.

The model and the prompt skeleton are identical in both runs. The only difference is what Hindsight recalled.

## The playbook nobody writes

The **Learned playbook** tab calls `reflect`. It asks Hindsight to reason over the whole bank and write, per service, the recurring failures, the fastest proven fix and the traps, citing incident IDs. Nobody maintains the document. It changes as incidents are resolved, and after the demo above, the Elasticsearch lesson is in it.

## Lessons learned

1. **Retain the failures, not just the fixes.** Most of the value is in the do-not-repeat list. If your post-mortem template has no "tried, didn't help" field, add one before you add an AI.
2. **Tell the memory what matters.** A domain-specific bank mission and "keep error strings verbatim" did more for recall than any retrieval tuning.
3. **Timestamps are part of the answer.** "Three weeks ago" and "this happened twice" change how an engineer weighs a precedent.
4. **Scope, then widen.** Tag-scoped recall gives precision, and a bank-wide second pass catches the cross-service causes people miss.
5. **Be honest about limits.** The history is synthetic, and I haven't measured MTTR. The next step is ingesting real resolved incidents and tracking the *helped / wrong* verdicts over time. That would make it a measurement, not a demo claim.

The model will get swapped out many times. The memory bank, with every outage and every bad call in it, is the part worth protecting. That's why I think [agent memory](https://vectorize.io/what-is-agent-memory) is the product here, and the LLM is the replaceable part.

*The code, incident dataset and offline test suite are on GitHub: [GITHUB URL].*
