```
# Live verification run, 2026-09-29 16:14 UTC
Hindsight: https://api.hindsight.vectorize.io | bank: paylane-oncall | LLM: Groq openai/gpt-oss-120b

## STEP 0: connectivity + seed
  [PASS] Hindsight reachable and API key accepted
  [PASS] Groq reachable and API key accepted
  seeded 19 historical incidents in 74s

## STEP 1: cold start (search-svc #1)
  alert: [PagerDuty] search-svc: Elasticsearch cluster health RED, 3 unassigned primary shards on index merchants-v7. Merchant search returning 503.
  model: openai/gpt-oss-120b | recall 919 ms | llm 2906 ms
  memories recalled: 14 (documents: ['INC-2104', 'INC-2118', 'INC-2185', 'INC-2211', 'INC-2231', 'INC-2240', 'INC-2280', 'INC-2291', 'INC-2310'])
  severity/confidence: SEV1 / high
  summary: Elasticsearch cluster health RED with 3 unassigned primary shards causing 503 on merchant search
  likely root cause: Unassigned primary shards on index merchants-v7, likely due to node loss, disk‑space watermark breach, or shard allocation filtering
  similar incidents: []
  step 1: Run `curl -s http://search-svc-es:9200/_cluster/health?pretty` and `curl -s http://search-svc-es:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason` to confirm RED status and see why shards are unassigned
  step 2: kubectl get pods -n search-svc -l app=elasticsearch && kubectl logs <pod> -c elasticsearch to check for OOM, disk‑full, or node‑failure messages
  step 3: If pods are down or in CrashLoopBackOff, delete the failing pod(s) so the StatefulSet recreates them, or add missing Elasticsearch nodes if the replica count is insufficient
  step 4: If disk watermarks triggered, free space on the affected node(s) or raise `cluster.routing.allocation.disk.watermark.low`/`high` in the Elasticsearch ConfigMap and reload the config
  step 5: Manually allocate the unassigned primary shards with `POST /_cluster/reroute` specifying `allocate_stale_primary` commands, then run `POST /merchants-v7/_refresh` and verify the search endpoint returns 200
  avoid: Do not restart checkout‑api without first updating pgbouncer configuration – that remediation failed in INC-2310
  avoid: Do not attempt to fix unrelated DNS issues by scaling CoreDNS replicas – that did not resolve the problem in INC-2240
  [PASS] no Elasticsearch/search-svc memory recalled (cold start)
  [PASS] agent did not cite any incident ID for the new failure type

## STEP 2: retain the resolution (INC-2331)
  [PASS] Hindsight retain call succeeded
  list_memories('merchants-v6') -> 2 memory unit(s)
    - Incident INC-2331 was mitigated by deleting the merchants-v6 index and rerouting failed shards, restoring cluster health in 9 minutes. | When: 2026-09-29
    - Root cause of INC-2331 was the nightly reindex leaving a 412 GB merchants-v6 index, causing es-data-2 to exceed the 95% flood-stage disk watermark. | When: 2026
  [PASS] INC-2331 facts are stored in Hindsight

## STEP 3: similar incident recalls it (search-svc #2)
  alert: [PagerDuty] search-svc: Elasticsearch cluster health RED since 03:12 UTC, 2 unassigned primary shards on index merchants-v8. Started after last night's merchants reindex job.
  model: openai/gpt-oss-120b | recall 1966 ms | llm 3193 ms
  memories recalled: 14 (documents: ['INC-2104', 'INC-2150', 'INC-2170', 'INC-2231', 'INC-2240', 'INC-2280', 'INC-2310', 'INC-2331'])
  severity/confidence: SEV1 / high
  summary: Elasticsearch cluster health RED due to unassigned primary shards on merchants‑v8, likely caused by disk‑watermark breach after the nightly reindex
  likely root cause: Nightly merchants reindex created a large merchants‑v8 index that pushed the data node(s) past the 95% flood‑stage disk watermark, preventing shard allocation
  similar incidents: ['INC-2331']
  step 1: Run `curl -s http://es-cluster:9200/_cat/nodes?v&h=name,disk.used_percent,store.size` to verify which node(s) are above the flood‑stage watermark
  step 2: Execute `curl -s http://es-cluster:9200/_cat/allocation?v` and `GET _cluster/allocation/explain` for the unassigned shards to confirm allocation is blocked by disk limits
  step 3: If old merchant indices (e.g., merchants‑v6) are no longer needed, delete them: `curl -XDELETE http://es-cluster:9200/merchants-v6` or close them with `curl -XPOST http://es-cluster:9200/merchants-v6/_close` to free space
  step 4: If the index must be kept, free space by deleting unnecessary data or adding disk; then trigger shard allocation retry: `curl -XPOST http://es-cluster:9200/_cluster/reroute?retry_failed=true`
  step 5: Optionally, temporarily raise the flood‑stage watermark (not recommended long‑term): `curl -XPUT http://es-cluster:9200/_cluster/settings -H 'Content-Type: application/json' -d '{"persistent":{"cluster.routing.allocation.disk.watermark.flood_stage":"98%"}}'`
  step 6: Verify cluster health returns to yellow/green: `curl -s http://es-cluster:9200/_cluster/health?wait_for_status=yellow&timeout=30s`
  avoid: Restarting Elasticsearch pods without first freeing disk space – this did not resolve the issue in INC-2331
  recalled memory text:
    - [INC-2331] Incident INC-2331 on search-svc caused 503 errors in merchant search due to Elasticsearch cluster health being RED with 3 unassigned primary shards. | When: 2026-09-29
    - [INC-2331] Incident INC-2331 was mitigated by deleting the merchants-v6 index and rerouting failed shards, restoring cluster health in 9 minutes. | When: 2026-09-29
    - [INC-2331] Root cause of INC-2331 was the nightly reindex leaving a 412 GB merchants-v6 index, causing es-data-2 to exceed the 95% flood-stage disk watermark. | When: 2026-09-29
    - [INC-2310] The incident was mitigated by pointing pgbouncer to the postgres-primary.db.svc endpoint and reloading the configuration. | When: 2026-09-20 | Previous attempts to restart checkout
    - [None] Incident INC-2310 was mitigated by pointing pgbouncer to the postgres-primary.db.svc endpoint and reloading the configuration.
    - [INC-2280] Implemented a safety check where ledger-svc refuses to start reconciliation if RECON_BATCH_SIZE is unset. | To prevent future regressions of this type.
  [PASS] Hindsight recall returned INC-2331
  [PASS] recommendation cites INC-2331
  [PASS] recommendation uses the recalled fix (old index / disk watermark)

## STEP 3b: empty recall on a brand-new bank
  recalled 0 memories from an empty bank
  [PASS] empty bank recall returns nothing

## RESULT: PASS (10/10 checks)

(The retained INC-2331 stays in the bank. Run `python -m scripts.seed --reset` before a demo recording.)
```
