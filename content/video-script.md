# Video script (about 3 min)

Record at 1080p. Zoom the browser to 125% and close notifications.
Before recording: `python -m scripts.seed --reset`, then `uvicorn app.main:app`.

## 1. Intro (0:00–0:30)

**On screen:** your face (webcam), then the app at http://localhost:8000.

> Hi, I'm [NAME]. I built an incident response agent for on-call engineers. When an
> alert fires, it tells you what's probably wrong, which past incident this looks
> like, and, most usefully, which fixes *didn't* work last time. It remembers all of
> that with Hindsight, which is an agent memory system from Vectorize.

## 2. The problem (0:30–1:00)

**On screen:** click the chip **"checkout-api: 5xx right after deploy"**, then **Without memory**.

> Here's a real-looking page: checkout is throwing 5xx, the connection pool is
> exhausted, and it started four minutes after a deploy. Without memory, the model
> says what every model says: make the pool bigger and restart the pods. It sounds
> right. On our system, three weeks ago, that exact advice made the outage worse.

**Point at:** "Increase DB_POOL_MAX", confidence medium, ETA 30–60 min.

## 3. Live demo (1:00–2:30)

**On screen:** click **Compare: without vs with memory**. Wait for both columns.

> Same alert, same model, same prompt. The right side just has Hindsight recall turned on.
> It found INC-2291 from three weeks ago: same errors, right after a deploy. The fix
> was a rollback in six minutes. And look at "Do not repeat": raising the pool made
> it worse, and restarting didn't help.

**On screen:** expand **"What Hindsight recalled"**.

> These are the raw memories recall returned. Each one has a real date and a service tag.
> I recall scoped to the service first, then across the whole bank.

**On screen:** optionally show `app/memory.py`, the `recall()` method, for 5 seconds.

**On screen:** scroll to **Close the loop**. Set the verdict to *Partially*, and put in notes:
"Rollback worked, but root cause was an N+1 query from eager loading in v2.44." Click **Resolve & retain**.

> Now I close the incident and tell it what really happened, including whether its own
> suggestion was right. That goes straight back into Hindsight with `retain`.

**On screen:** run **Compare** again on the same alert.

> Run it again, and now it cites the incident I just closed. It learned from one resolution.

**On screen:** **Learned playbook** tab → **Generate playbook**.

> Last thing: this playbook was written by Hindsight's `reflect` over every incident.
> Recurring failures per service, proven fixes, and the traps. Nobody wrote this document by hand.

**Optional (if time):** the **"search-svc: Elasticsearch RED"** chip, which has no history. The agent says so
and doesn't make anything up.

## 4. Takeaway (2:30–3:00)

**On screen:** back to your face, or the compare view.

> What surprised me: the most valuable memory wasn't the fixes, it was the *failed*
> fixes. A stateless model will repeat the same wrong advice forever. With memory, a
> wrong answer is a one-time cost. Links to the code and Hindsight are in the description.

---

## Titles

1. My AI on-call agent remembers the fixes that failed
2. Same LLM, same alert: memory changed the fix
3. I built an SRE agent that learns from every outage
4. Stop your AI from repeating last month's outage
5. Giving an incident agent long-term memory (Hindsight demo)

## Thumbnail prompt (Nano Banana, attach a team photo)

> Generate a viral YouTube thumbnail, 16:9. Left half: a red, chaotic dashboard with "5xx 17%"
> and a robot giving a thumbs-up next to the words "RESTART PODS?" crossed out in red. Right half:
> calm green terminal showing "INC-2291 · 3 weeks ago · ROLL BACK". The person from the attached
> photo in the center looking surprised. Big bold text at top: "IT REMEMBERED". Dark background,
> high contrast, clean.
