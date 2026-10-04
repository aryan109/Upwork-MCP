# 06 — Lead Scoring Rubric (weighted)

Replaces the reference implementation's hard floors (spend ≥ $1,000, hire rate ≥ 50%, avg hourly ≥ $15, proposals ≤ 20) with a **0–100 weighted score** plus a short list of true disqualifiers. The reference data showed the hard floors threw away 97.3% of scraped jobs (3,666 of 3,767), with "client spend < $1,000" alone removing 1,145, of which ≥590 were *unknown* spend treated as $0. For a profile that needs volume of good-fit opportunities rather than only "safe" ones, that is too blunt.

Two outputs per job: **Score** (0–100) and **Decision** (`APPLY` / `REVIEW` / `SKIP`) plus a reason list. The agent computes it; Aryan can override on review.

## 1. Hard disqualifiers (any one → `SKIP`, score not computed)

| ID | Rule | MCP field (`find_jobs` → `get`) | Why |
|---|---|---|---|
| D1 | Already applied / invitation exists / cannot apply | `applied == true` or `can_apply == false`; also `manage_proposals` error `VJ-JA-10` | Duplicate proposals are impossible; wasted call |
| D2 | Location-restricted and Aryan is not eligible (India) | `preferred_locations.location_required == true` and India not in `preferred_locations.locations` `[VERIFY LIVE field names]` | Proposal is ignored or rejected |
| D3 | Capability gate: job requires a stack Aryan does not deliver (iOS/Android native, Unity, SAP/Salesforce Apex dev, blockchain contracts, video editing, pure UI design, pure copywriting, voice acting, data entry) | title + description keyword match | Never-claim rule |
| D4 | Off-platform or policy violations (asks to pay/communicate outside Upwork, academic work, account sharing, "post reviews", scraping of Upwork itself) | description keyword match | ToS |
| D5 | Pure staffing/agency/"join our team of 50 freelancers" or commission-only / revenue-share / equity-only | description match; `budget` missing and text says "commission" | No cash |
| D6 | Payment unverified **and** client has 0 spend **and** 0 hires | `client_record.payment_verified == false` and `total_spent == 0` and `activityStat.jobActivity.totalHired == 0` | Three zeros together, not any one alone |
| D7 | Fixed budget < $100 or hourly ceiling < $25/hr | `budget.amount` / `hourly_budget.max` `[VERIFY LIVE field names]` | Below any rung; exception: deliberate Week-1–3 re-entry jobs (manual) |
| D8 | Job posted > 72 h ago **and** proposals ≥ 50 **and** `interviewing == 0` | `posted_on`, `proposals_tier`/count, `activityStat.jobActivity.totalInvitedToInterview` | Dead post |
| D9 | Asks for a free sample/test task of > 1 hour before hire | description match | Policy of this plan |
| D10 | Conflict: same client already in pipeline with an open proposal or active contract (see `08_MCP_ACQUISITION_ENGINE.md` §7) | state store lookup on `client_id`/client name | Avoid two concurrent proposals to one client |

Everything else is scored.

## 2. Weighted features (max 100)

Weights sum to 100. Each feature is scored on its own scale then multiplied by the weight. Field names refer to the `find_jobs` `get` payload; where uncertain they are marked `[VERIFY LIVE]`.

### A. Fit to Aryan's positioning — 35 points
| Feature | Scale | Points | Source |
|---|---|---|---|
| A1 Core-term match in **title** (Claude, Claude Code, Anthropic, AI agent, n8n, Make, Zapier→AI, MCP, RAG, automation, integration, LLM, chatbot, workflow) | strong (Claude/agent/n8n/MCP/RAG) = 1.0; adjacent (automation/integration/LLM/chatbot/API) = 0.6; none = 0 | 15 | `title` |
| A2 Description describes a **business workflow** to automate/integrate (not a research paper, not a model-training task, not "build me ChatGPT") | clear = 1.0; partial = 0.5; vague = 0.2 | 8 | `description` |
| A3 Offer-ladder match: maps cleanly to Sprint / Audit / Implementation / Care Plan | exact rung = 1.0; needs bespoke scope = 0.5; none = 0 | 7 | agent judgment |
| A4 Proof match: Aryan has a case study, repo or past contract directly on point (chatbot, scraping/warehouse, GPT fine-tune, plugin dev, agent/MCP engine, n8n) | direct = 1.0; adjacent = 0.5; none = 0 | 5 | `skills/aryan-profile-facts` |

### B. Client quality — 25 points
| Feature | Scale | Points | Source |
|---|---|---|---|
| B1 Total spent | ≥$10K = 1.0; $1K–10K = 0.8; $100–1K = 0.5; $0 but verified = 0.3; unknown = 0.4 (**unknown ≠ zero**) | 8 | `client_record.total_spent` |
| B2 Hire rate | ≥70% = 1.0; 40–70% = 0.7; <40% = 0.3; unknown/new = 0.5 | 5 | `client_record.hire_rate_percent` |
| B3 Rating | ≥4.8 = 1.0; 4.5–4.8 = 0.7; <4.5 = 0.2; none = 0.6 | 4 | `client_record.rating` |
| B4 Avg hourly paid vs Aryan's sticker | ≥$50 = 1.0; $30–50 = 0.7; $15–30 = 0.3; <$15 = 0 (the "$430K spent, $5.04 avg" trap); unknown = 0.5 | 5 | `client_record.avg_hourly_rate_paid` `[VERIFY LIVE]` |
| B5 Payment verified | yes = 1.0; no = 0.3 | 3 | `client_record.payment_verified` |

### C. Money — 15 points
| Feature | Scale | Points | Source |
|---|---|---|---|
| C1 Fixed budget | ≥$3K = 1.0; $1K–3K = 0.9; $500–1K = 0.7; $250–500 = 0.5; $100–250 = 0.2 | 10 (fixed) | `budget` |
| C1' Hourly ceiling | ≥$80 = 1.0; $60–80 = 0.9; $45–60 = 0.7; $30–45 = 0.4; $25–30 = 0.1 | 10 (hourly) | `hourly_budget.max` |
| C2 Duration/size signal | >3 months or "ongoing" = 1.0; 1–3 months = 0.8; <1 month = 0.5; one-off <1 week = 0.3 | 5 | `duration`, `engagement` |

### D. Competition & timing — 15 points
| Feature | Scale | Points | Source |
|---|---|---|---|
| D1 Proposals so far | <5 = 1.0; 5–10 = 0.9; 10–15 = 0.7; 15–20 = 0.5; 20–50 = 0.25; 50+ = 0.05 | 7 | `proposals` / tier |
| D2 Freshness | <6 h = 1.0; 6–24 h = 0.8; 1–3 days = 0.5; >3 days = 0.2 | 4 | `posted_on` |
| D3 Client engagement | `totalInvitedToInterview > 0` or `invitesSent > 0` within 24 h = 1.0 (active buyer); hires already = 0 (`totalHired > 0` → probably filled) ; else 0.5 | 4 | `activityStat.jobActivity` |

### E. Risk & friction — 10 points (scored as *absence* of risk)
| Feature | Scale | Points | Source |
|---|---|---|---|
| E1 Screening questions | 0–2 = 1.0; 3–4 = 0.6; 5+ = 0.3 (Q&A letters ran 331 words in the reference) | 3 | `screening_questions` |
| E2 Red-flag language ("ninja", "rockstar", "simple task should take 1 hour", "unlimited revisions", "ASAP today", "I know exactly what I want and it's easy") | none = 1.0; one = 0.5; two+ = 0 | 3 | `description` |
| E3 Scope clarity (deliverable nameable in one sentence) | clear = 1.0; medium = 0.6; vague = 0.2 | 2 | agent judgment |
| E4 Connects cost | ≤12 = 1.0; 13–18 = 0.7; ≥19 = 0.4 | 2 | `connects_cost` |

## 3. Thresholds and decision

| Score | Decision | Action |
|---|---|---|
| **≥ 70** | `APPLY` | Draft proposal; goes to human review queue (never auto-submits) |
| **55–69** | `REVIEW` | Draft a *short* proposal only if daily slot is free; Aryan decides |
| **< 55** | `SKIP` | Log with top-3 reasons; no draft |

**Modifiers (applied after the base score):**
- +5 if the client has an **open related job** or active contracts (`client_record.open_jobs`, `active_contracts`) — platform-committed buyer.
- +5 if the post explicitly names **Claude / Anthropic** (highest-fit, lowest competition cluster: 313 Claude-title jobs vs 404 "AI agent" on 2026-10-04 with far fewer 50+ proposal piles: 109 vs 205).
- +3 if the client posted the job in a **time zone overlapping IST evening** (EU/UK/ME) — easier calls.
- −10 if the job is **"pile-on"** (50+ proposals) **and** Aryan would be bidding above the client's avg hourly paid.
- −5 if the post asks for **US/UK only "preferred"** (not required) locations.
- Daily cap: max **5 `APPLY` drafts/day** across all campaigns; target **3 excellent**. If more than 5 qualify, rank by score, then by freshness.

## 4. Connects awareness

- Balance check every run (`get_profile` → `connects_balance`). Reference ledger: mean 17.4 Connects/apply, 785 Connects across 45 applies; bundle 100 Connects = $15 + $0.90 fee (observed).
- Budget: **~250 Connects/month** (≈ 15 proposals + badge) in P1–P2; raise to 400 in P3 if conversion justifies. Starting balance 110 + Freelancer Plus 100/month `[VERIFY LIVE]`.
- Rules: if balance < 2× the job's `connects_cost` + boost → `REVIEW` instead of `APPLY`. **Never auto-buy** Connects; the agent reports the balance and Aryan buys.
- Boost: follow `boost.recommendation`; if `skip`, do not boost. If recommended, cap boost at min(`boost.recommended_connects`, 10) and only for score ≥ 80.

## 5. Worked examples (from live posts observed 2026-10-04 and reference dataset)

### Example 1 — "Claude Implementation Expert" (observed 2026-10-04): hourly, client $430K spent, avg hourly paid $5.04, verified, 20–50 proposals, posted ~1 day
- D-checks: none triggered (B4 is a weight, not a disqualifier).
- A: A1 strong 15; A2 clear 8; A3 Sprint/Implementation 7; A4 direct (Claude/MCP engine) 5 → **35**
- B: B1 1.0×8=8; B2 (say 75%) 5; B3 (4.9) 4; **B4 $5.04 → 0**; B5 3 → **20**
- C: hourly ceiling e.g. $40 → 0.4×10=4; duration ongoing 5 → **9**
- D: proposals 20–50 → 0.25×7=1.75; freshness 1 day → 0.5×4=2; no interviews yet 0.5×4=2 → **5.75**
- E: 2 questions 3; no red flags 3; scope medium 1.2; connects 16 → 1.4 → **8.6**
- Base **78.4**; modifiers: +5 (names Claude), −10 (pile-on × bidding above avg paid) → **73 → APPLY**, reason list must say: "client pays $5/hr on average; propose fixed Sprint ($599) not hourly."

### Example 2 — "AI Operations Auditor: Assess Our Claude-Based Business OS" (observed 2026-10-04): hourly $30–40, 5–10 hrs/week, client $245K spent, avg $41.87/hr, 10–15 proposals, fresh
- A: 15+8+7 (Audit) +5 → **35**
- B: 8+5+4+ (0.7×5=3.5) +3 → **23.5**
- C: ceiling $40 → 4; duration 1–3 mo → 4 → **8**
- D: 0.7×7=4.9; <24 h 3.2; 0.5×4=2 → **10.1**
- E: 3+3+1.2+1.4 → **8.6**
- Base **85.2** +5 (Claude) → **90 → APPLY**; pricing rule: bid the ceiling $40/hr capped **or** fixed Audit at $750 (preferred; explain why in letter).

### Example 3 — "Build a Fully Automated AI Outbound Sales System" (reference dataset, applied by Patrick): fixed $2,500, client $14K spent, verified, 15–20 proposals, 2 days old
- A: A1 adjacent (automation) 9; A2 clear 8; A3 Implementation 7; A4 adjacent 2.5 → **26.5**
- B: 8+ (50% → 3.5) + 4 + (unknown 2.5) + 3 → **21**
- C: $2.5K → 9; 1–3 mo 4 → **13**
- D: 0.5×7=3.5; 2 days 2; 2 → **7.5**
- E: 0 questions 3; "fully automated" one yellow flag 1.5; medium 1.2; 1.4 → **7.1**
- Base **75.1 → APPLY**, with letter pointing out that "fully automated" outbound needs a human approval step (risk stated up front).

### Example 4 — "Build me an app like ChatGPT for my students" fixed $150, client new, unverified, 0 hires, 50+ proposals
- D6 (unverified + $0 + 0 hires) → **SKIP** (even before D7: $150 < $250 soft floor but ≥$100 so D7 alone would not trigger).

### Example 5 — "n8n Automation Expert for HubSpot ↔ Slack ↔ Gmail" hourly $25–45, client $3,200 spent, 60% hire rate, 4.6 rating, avg paid $28, <5 proposals, 3 hours old, 1 question
- A: 15+8+7 (Sprint/Implementation) +2.5 → **32.5**
- B: 6.4 + 3.5 + 2.8 + 1.5 + 3 → **17.2**
- C: ceiling $45 → 0.7×10=7; <1 month 2.5 → **9.5**
- D: 7 + 4 + 2 → **13**
- E: 3+3+2+1.4 → **9.4**
- Base **81.6 → APPLY**; pricing: bid $45/hr (≥$45 and score ≥80) **and** offer fixed $599 Sprint alternative.

### Example 6 — "GoHighLevel funnel build" (198 titles in the reference dataset; Patrick applied to 3)
- A1 none → 0; A2 0.5×8=4; A3 none → 0; A4 none → 0 → **4**; even with perfect B–E (65) the max is **69 → REVIEW at best**, typically SKIP. Correct: GHL is not Aryan's lane.

## 6. Calibration plan
- Weeks 1–4: log score + decision + outcome (viewed / replied / interviewed / hired) for every proposal in `templates/lead_score_worksheet.csv`.
- After 20–30 qualified proposals (reassessment gate): compute reply rate by score band (70–79 / 80–89 / 90+) and by A1 cluster. If 55–69 `REVIEW` jobs that Aryan approved manually convert as well as `APPLY` jobs, lower the threshold to 65; if 70–79 convert < half as well as 80+, raise to 75.
- Re-weight only one block per month; record every change in `campaigns.json` → `scoring_version`.
