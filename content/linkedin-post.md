Your on-call AI will confidently suggest the fix that made your last outage worse.

It has no idea it already happened.

"Pool exhausted? Raise DB_POOL_MAX, restart pods." Every LLM says it. On our checkout service that exact advice turned a 6-min rollback into a 26-min outage.

So I built an incident agent on Hindsight agent memory. What I'd copy tomorrow:

1. Retain failed fixes, not just the resolution
2. Retain with real timestamps: "3 weeks ago" changes trust
3. Recall scoped to the service, then bank-wide
4. After each incident, record whether the agent's advice was right
5. Let reflect write the playbook

Before: "increase the pool". After: "matches INC-2291, roll back, do NOT raise the pool".

Code: [GitHub repo link]

#AIAgents #AgentMemory #Hindsight #LLM
