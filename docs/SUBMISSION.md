# Submission pack

Everything needed to submit, other than the code itself. Placeholders in `[BRACKETS]` need your input. Nothing here has been published or submitted yet.

## 1. Hard requirements (from the official documents)

| # | Requirement | Source |
|---|---|---|
| R1 | Built with Hindsight; memory use clearly demonstrated | Problem statement, "Required Technology" and "Important Rules" |
| R2 | GitHub repo with clean, documented code | Problem statement, "Submission Requirements" |
| R3 | Demo video showing the agent in action | Problem statement + content guide Part 3 |
| R4 | Live project demo to judges | Problem statement, "Submission Requirements" |
| R5 | Explanation of how Hindsight memory is used | Problem statement, "Submission Requirements" |
| R6 | Article per member: English, 800–1,500 words, public URL, never mentions the event | Content guide, table + Part 1 |
| R7 | LinkedIn post per member: never mentions the event, GitHub link in the main post, article URL as a comment, Hindsight link as a comment | Content guide Part 2, Steps 5–6 |
| R8 | One team video: 2–5 min, 1080p+, screen recording + voiceover, public on YouTube, with thumbnail | Content guide Part 3 |
| R9 | Article shared as a link post on r/llmdevs, r/sideproject, r/aiagents or r/aimemory | Content guide Part 1, Step 5 |
| R10 | Article includes links to Hindsight GitHub, Hindsight docs, Vectorize agent memory | Content guide Part 1, Step 4 |

## 2. Conflicts found in the official documents

**CONFLICT 1, article length:** the deliverables table says "800–1,500 words", while Prompt 2 says "target 1,200–2,000 words".
→ The table is authoritative, because it defines the deliverable and the prompt is a drafting aid. The article is **1,297 words**, which satisfies both.

**CONFLICT 2, which comment comes first on LinkedIn:** Part 2 says "Post the article URL as the first comment", while the Quick Reference says "Add a first comment linking to Hindsight Github repo".
→ Both comments are required, so post both: the article URL first (Part 2 is the detailed instruction), then the Hindsight link.

**CONFLICT 3, prompt numbering:** the Quick Reference calls the video script "Prompt 4" and the thumbnail "Prompt 5"; the body calls them Prompts 5 and 6, and there is no Prompt 4. It also says Prompt 1 gives "5 title ideas" while Prompt 1 asks for 20.
→ Cosmetic. We followed the body text (20 titles, the script, the thumbnail prompt).

**CONFLICT 4, framing vs honesty:** Prompt 2 says to "assume mock data… fully implemented… do not position the project as a demo", while your own rules forbid fabricating results.
→ Resolved by describing the real system without calling it a demo, while stating that the incident history is synthetic and no MTTR was measured. Claims about model output in the article, README and post were checked against live runs on 2026-09-29 and corrected where they didn't match.

The content guide's Step 4 says "Post your video to one of the sites suggested above: Medium, Dev.to". This is an obvious typo for "article"; the video goes to YouTube per Part 3.

## 3. Judging criteria mapping

| Feature | Criteria supported | Why |
|---|---|---|
| Failed fixes stored as first-class memory, with a do-not-repeat list | Innovation, Use of Hindsight, Real-world impact | Goes beyond RAG over resolutions. The most expensive incident mistakes are the tempting wrong fixes, and only memory can prevent them. |
| Compare mode (same model, memory on/off, side by side) | Use of Hindsight, UX | The judges see the before/after within 60 seconds, with memory as the only variable. |
| Cold-start loop (search-svc #1 → retain → #2 recalls INC-2331) | Use of Hindsight | The agent visibly improves from one interaction, which is the "learns over time" requirement. |
| Resolve with a verdict on the agent's own advice | Innovation, Use of Hindsight | The agent's mistakes become memory, and the prompt refuses to repeat advice marked wrong. |
| Two-pass tag-scoped then bank-wide recall | Technical, Use of Hindsight | Precision first, then cross-service causes (the Patroni → checkout case). |
| Bank mission + retain instructions (verbatim error strings) | Use of Hindsight, Technical | Uses Hindsight's bank configuration to shape extraction for the ops domain. |
| `reflect` learned playbook | Use of Hindsight, Innovation | Memory produces a synthesised artefact, not just retrieved snippets. |
| Transparent recall panel + Memory updated panel | UX, Use of Hindsight | Makes memory reads and writes visible rather than hidden in the backend. |
| Honest empty-memory behaviour, no invented IDs | Technical, Real-world impact | Trustworthy under pressure; an agent that fabricates history is dangerous on call. |
| LLM retry/fallback, JSON repair, timeouts, 502 on Hindsight outage, input validation | Technical | Edge cases handled, and covered by tests. |
| 19 consistent synthetic post-mortems | Real-world impact, UX | Realistic data makes the demo credible, as the problem statement advises. |
| 23 offline tests including an end-to-end loop | Technical | Reproducible without keys. |

## 4. Title options

All 20 generated titles are in [`content/titles.md`](../content/titles.md). Five strong options:

1. My incident agent remembers the fixes that made things worse (**current choice**: it names the counter-intuitive idea the whole article defends)
2. Same model, same alert: Hindsight memory changed the fix
3. My agent's best feature is remembering its own wrong answers
4. I taught an incident bot to say "we tried that already"
5. Remembering what didn't work: incident triage with Hindsight

## 5. Screenshot and diagram plan

Crop everything tightly to the browser content. Hide the bookmarks bar, other tabs, the taskbar, `.env`, and any terminal line showing keys.

| # | Shot | Must be visible | Place in article |
|---|---|---|---|
| 1 | Project UI, home | Header with **● connected**, demo chips, alert box | After "What the system does" |
| 2 | Current incident | Checkout alert text filled in, service = checkout-api | Before the Compare paragraph |
| 3 | Before/after | Compare view with both columns; INC-2291 and **Do not repeat** readable | "Deep history" section (the most important image) |
| 4 | Hindsight recall | "What Hindsight recalled" expanded, showing dates and doc IDs | After the recall code snippet |
| 5 | Retain | **Memory updated** panel showing INC-2331 text | "Learning from zero" |
| 6 | Improvement | search-svc #2 memory column citing INC-2331 | "Learning from zero", after shot 5 |
| 7 | Architecture | `docs/architecture.svg` exported as PNG | "What the system does" |
| 8 | Team photo (optional) | Team only | End of article |

Suggested captions:

1. "The ops console: paste an alert, or pick a demo incident."
3. "Same model, same alert. The only difference is Hindsight recall."
4. "Every recalled memory is shown, with its date and source incident."
5. "Resolving an incident retains it. This is what the agent just learned."
6. "One resolution later, the agent recalls INC-2331."
7. "Alert → Hindsight recall → LLM → triage → resolve → Hindsight retain."

**Architecture diagram description** (for regenerating in another tool): left to right, *On-call engineer / alert* → *FastAPI agent* → **Hindsight bank `paylane-oncall`** (`recall`: tag-scoped, then bank-wide) → *Groq LLM* (alert + recalled memories → JSON triage) → *Triage UI* (similar incidents, next steps, do-not-repeat) → *Engineer resolves* → back into **Hindsight** (`retain`: root cause, fix, verdict). A side arrow from Hindsight to *Learned playbook* (`reflect`). Emphasise the loop arrow.

## 6. Reddit

- **Subreddit:** r/aiagents (the best topic fit; r/llmdevs is the alternative). Check the subreddit rules for self-promotion before posting.
- **Type:** link post → [ARTICLE URL]
- **Title:** My incident agent remembers the fixes that made things worse
- **First comment:**
  > I built an on-call triage agent whose memory (Hindsight) stores failed remediations, not just resolutions. When an incident is closed, the engineer grades the agent's advice, and that grade is retained too. The write-up covers the bank design, two-pass recall, and what I'd do differently. The incident history is synthetic, so no MTTR claims. Code: [GITHUB URL]

## 7. Thumbnail prompt (Nano Banana, attach a team photo)

> Create a 16:9 YouTube thumbnail. Dark navy background. On the left, a large red alert badge reading "5xx" with a small pager icon. On the right, a clean green memory-chip or brain-circuit icon connected to a stack of three small index cards labelled "INC", suggesting past incidents being recalled. The person from the attached photo in the lower-left third, looking at the memory icon with a focused, slightly surprised expression. One short headline in bold white sans-serif across the top: "IT REMEMBERED THE FIX". High contrast, minimal elements, readable at small size. No fake dashboards, no logos, no small text.

## 8. Final submission form answers

The official form was not provided, so these are generic answers. **Do not invent fields.** Share the form and each answer will be mapped to its real field.

| Likely field | Answer |
|---|---|
| Team name | [TEAM NAME] |
| Members | [MEMBER NAMES + EMAILS] |
| Project name | Paylane On-call: incident agent with Hindsight memory |
| One-liner | An incident-response agent that recalls past outages, including the fixes that failed, and learns from every resolved incident using Hindsight memory. |
| GitHub URL | [GITHUB URL] |
| Demo video (YouTube) | [VIDEO URL] |
| Live demo URL | [LIVE DEMO URL, or "run locally, see README"] |
| Articles | [ARTICLE URL per member] |
| LinkedIn posts | [POST URL per member] |
| Reddit post | [REDDIT URL] |
| How Hindsight is used | One bank with an ops mission and retain instructions. `retain` stores 19 timestamped, service-tagged post-mortems, plus every resolution (root cause, fix, time to mitigate, and a verdict on the agent's own advice). `recall` runs tag-scoped, then bank-wide, on every alert, and the results go into the LLM prompt, which must cite incident IDs and list failed fixes to avoid. `reflect` generates a learned per-service playbook. Compare mode shows the same model with and without memory. |

## 9. Audit (as of this commit)

| Requirement | Source | Implemented? | Evidence | Remaining action |
|---|---|---|---|---|
| Hindsight integrated (retain/recall/reflect) | R1 | Yes, **verified live 2026-09-29** | `docs/live-verification.md` (10/10 checks) | none |
| Before/after memory demo | R1 | Yes, verified live in the UI | Cold start → retain → recall of INC-2331; checkout cites INC-2291 | Screenshots |
| LLM with error handling | Problem statement, LLM section | Yes, verified live (incl. rate limits) | `app/llm.py`, tests | none |
| Realistic data | Problem statement | Yes, 19 incidents | `data/incidents.json` | none |
| Tests | Your brief | Yes, 24 passing offline + live script | `tests/`, `scripts/verify_live.py` | none |
| README, .env.example, LICENSE | R2 | Yes | repo root | Fill `[COPYRIGHT HOLDER]`, `[TEAM]` |
| Public GitHub repo | R2 | **No** | Local git only, no remote | Create repo + push |
| Demo video | R3/R8 | **No** | Script ready | Record, upload, thumbnail |
| Live demo | R4 | **No** | Runs locally | Rehearse; decide local vs hosted |
| Hindsight explanation | R5 | Yes | README + section 8 | none |
| Article per member | R6 | Draft for 1 member, matches live output | `content/article.md`, event never mentioned | Add screenshots, publish; other members write their own angle |
| LinkedIn post per member | R7 | Draft for 1 member | `content/linkedin-post.md`, ~765 chars with URL | Publish after article; 2 comments |
| Reddit share | R9 | **No** | Section 6 | Post after article is live |

**Critical blockers:** (1) no public GitHub repo; (2) video not recorded; (3) articles and posts not published.

**Important fixes:** fill in the name placeholders. Before recording, run `python -m scripts.seed --reset` so INC-2331 doesn't exist yet. On the Groq free tier (8k tokens/min), wait about 15 s between Compare clicks.

**Optional improvements:** hosted live demo (e.g. Render/Fly), and screenshots in `screenshots/`.

## 10. 24-hour execution plan

| When | Task | Who |
|---|---|---|
| Hour 0–1 | Add keys to `.env`, `python -m scripts.seed --reset`, run all demo alerts live, fix anything weak | Engineer |
| Hour 1–2 | Create the public GitHub repo, push, fill placeholders, add screenshots | Engineer |
| Hour 2–3 | Dry-run the demo twice with the video script; reset the bank | Presenter |
| Hour 3–4 | Record the video (1080p), upload to YouTube as public, thumbnail | Team |
| Hour 4–6 | Each member finalises their article (live output, screenshots, their angle) and publishes on Medium/Dev.to/Hashnode | Each member |
| Hour 6–7 | LinkedIn posts (GitHub link in the body, article + Hindsight comments), Reddit link post | Each member |
| Hour 7–8 | Fill the official form, run the final audit above, submit once | Team lead |
| Buffer | Rehearse the live demo; keep `seed --reset` handy | Presenter |
