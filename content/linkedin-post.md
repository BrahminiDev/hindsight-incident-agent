# LinkedIn post (under 800 characters, not counting the heading)

Your on-call AI will confidently suggest the fix that made your last outage worse.

It has no memory that it already happened.

So I built an incident agent on Hindsight agent memory. What I'd copy tomorrow:

1. Retain failed fixes, not just the resolution
2. Retain with real timestamps: "3 weeks ago" changes trust
3. Recall scoped to the service first, then bank-wide
4. On resolve, record whether the agent's advice was right
5. Let reflect write the playbook

Before: "pool too small or a leak." Nothing to avoid.
After: "matches INC-2291. Do NOT raise DB_POOL_MAX, it made that outage worse."

A new failure type? It admits it has no history. One resolution later, it recalls it.

Code: [GITHUB URL]

#AIAgents #AgentMemory #Hindsight #LLM

---

## First comment (article link)

I wrote up how the memory bank is designed, and why failed fixes matter more than fixes: [ARTICLE URL]

## Second comment (Hindsight link)

Here's Hindsight if you want to try agent memory yourself: https://github.com/vectorize-io/hindsight

---

## Per-member variants (each member needs their own post and article)

Suggested article angles, so the team's articles aren't identical:

- **Member A:** "My incident agent remembers the fixes that made things worse" (content/article.md): failed fixes as data.
- **Member B:** "Watching an incident agent learn from a single resolution": the cold-start loop (search-svc #1 → retain → #2), and the resolve/verdict design.
- **Member C:** "Why my agent recalls twice: scoped vs bank-wide memory in Hindsight": tags, the Patroni cross-service case, and timestamps.

Generate each member's article from their angle using Prompt 2 of the content guide, in this repo.
