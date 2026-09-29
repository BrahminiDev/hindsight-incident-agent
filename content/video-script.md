# Team video: script + shot list (target 3:30, hard limit 5:00)

**Setup, done once before recording**

1. Record at 1920×1080 minimum (OBS: Settings → Video → Base and Output 1920x1080). Browser zoom 125%, notifications off, only one tab open.
2. `python -m scripts.seed --reset`. This rebuilds the bank so INC-2331 does **not** exist yet, which the cold-start moment depends on.
3. `uvicorn app.main:app`, then open http://localhost:8000. Check the top-right shows **● connected**.
4. Do one full dry run, then run `seed --reset` again before the real take.

---

## 1. Intro (0:00–0:30)

| Screen | Narration |
|---|---|
| Webcam (optional), then the app | "Hi, I'm [NAME], and with [TEAMMATES] I built an incident response agent for on-call engineers. When an alert fires, it tells you what's probably wrong, which past incident this looks like, and which fixes *didn't* work last time. Its memory is Hindsight, from Vectorize, and it gets better every time an incident is closed." |

## 2. The problem (0:30–1:00)

| Screen | Narration |
|---|---|
| Click chip **checkout-api: 5xx right after deploy**, then **Without memory** | "Here's a realistic page: checkout is throwing 5xx, the DB pool is exhausted, and it started four minutes after a deploy." |
| Point at the next steps | "Without memory, the model reads it the obvious way: the pool is too small, or there's a connection leak. And look, its do-not-repeat list is empty. It has no history to learn from." |

## 3. Live demo (1:00–3:00)

**3a. Same alert with memory (1:00–1:40)**

| Screen | Narration |
|---|---|
| Click **Compare: without vs with memory** and wait for both columns | "Same alert, same model, same prompt. The right side has Hindsight recall turned on." |
| Point at **Similar past incidents** / **Do not repeat** | "It found INC-2291 from three weeks ago: same errors, right after a deploy, caused by connections being held too long. And under do-not-repeat: raising DB_POOL_MAX made it worse, and a rolling restart made an earlier one worse." |
| Expand **What Hindsight recalled** | "These are the raw memories recall returned, each with a date and a service tag." |

**3b. Learning from zero (1:40–2:45)**, the most important moment

| Screen | Narration |
|---|---|
| Click **search-svc #1: Elasticsearch RED (no history)** → **Compare** | "Now something the agent has never seen: Elasticsearch going red. Memory has nothing, and it says so. It doesn't make up an incident ID." |
| Scroll to **Close the loop**. The form is pre-filled with INC-2331 and verdict *Partially* | "We fixed it: a reindex left the old index behind, the disk hit flood-stage, and restarting the node didn't help. I'll mark the agent's advice as only partially right." |
| Click **Resolve & retain to Hindsight**. Hold on the **Memory updated** panel | "That's a Hindsight retain. This is exactly what it just learned." |
| Click **search-svc #2: RED again after a reindex** → **Compare** | "A few weeks later it happens again, on a different index." |
| Point at INC-2331 in the memory column | "This time it recalls INC-2331, goes straight to the leftover index and disk usage, and warns that restarting the node didn't help. It learned that from one resolution." |

**3c. The playbook (2:45–3:00)**

| Screen | Narration |
|---|---|
| **Learned playbook** tab → **Generate playbook** | "Last thing: Hindsight's reflect writes a playbook over every incident. Nobody maintains this by hand, and the lesson we just taught it is already in there." |

## 4. Takeaway (3:00–3:30)

| Screen | Narration |
|---|---|
| Back to the compare view, or webcam | "What surprised me was that the most valuable memory wasn't the fixes, it was the *failed* fixes. A stateless model repeats the same wrong advice forever. With memory, a wrong answer is a one-time cost. The code and Hindsight links are in the description." |

---

## Shot list (checklist while recording)

1. [ ] App home, **● connected** visible
2. [ ] Without-memory card for checkout (generic advice)
3. [ ] Compare view, both columns; zoom on INC-2291 and **Do not repeat**
4. [ ] "What Hindsight recalled" expanded
5. [ ] search-svc #1: memory column shows nothing recalled
6. [ ] Close-the-loop form → **Memory updated** panel (hold 3 seconds)
7. [ ] search-svc #2: memory column cites INC-2331
8. [ ] Playbook generated
9. [ ] Optional 5-second cut: `app/memory.py`, `recall()` in the editor

If a live LLM answer comes out weak on a take, re-run it. Don't narrate claims that aren't on screen.

## YouTube titles

1. My on-call AI remembers the fixes that failed
2. Same LLM, same alert: memory changed the fix
3. Watch an incident agent learn from one outage
4. Stop your AI from repeating last month's outage
5. Giving an SRE agent long-term memory with Hindsight

## Description template

> An incident-response agent that recalls past outages, including the fixes that didn't work, using Hindsight agent memory, and learns from every resolved incident.
> Code: [GITHUB URL]
> Article: [ARTICLE URL]
> Hindsight: https://github.com/vectorize-io/hindsight
