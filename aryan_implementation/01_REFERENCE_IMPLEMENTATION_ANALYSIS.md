# 01 — Reference Implementation Analysis: the Parvenu "Upwork Autopilot" (Patrick H.)

**Source:** `Upwork Analysis Agent Data/` (Notion export, 2026-10-04). 3,767 job rows, 28 state rows, 3 campaign rows, 11 instruction pages, 6 skill pages, 71 applied-job cover letters.
**Why it matters:** this is the only *working, in-production* Upwork acquisition agent in the inputs. It ran for ~14 weeks (2026-06-24 → 2026-10-02), submitted 76 proposals, spent ~1,330+ Connects, and left a full incident log. Everything below is read from the export; numbers were computed with a throwaway script (kept outside the repo) over `rows.json`.

**Verdict in one line:** adopt its *architecture* (campaign abstraction, deterministic hard filters + LLM judgment, closed state enum, dedup index, letter compliance gate, incident "eyeballs", evening rebake), adapt its *scoring* (weighted instead of hard floors; Upwork-MCP fields instead of Apify fields), and reject its *consent model* (instant auto-apply, standing auto-buy of Connects, no human gate).

---

## 1. Architecture (as actually run, rev 2026-10-01)

```
Scheduler (every 2h, 10:00–18:00 ET weekdays; 7 PM ET evening rebake; ad-hoc campaign editor)
   │
   ▼
upwork-01-combined-pass (one session)
   ├─ Step 0   Fetch LIVE instructions from Notion (OUTPUT_STYLE, phase_1_hunt, phase_2_apply, profile, phase_3_rebake_v2)
   ├─ Phase 1  HUNT:  Notion campaigns → campaigns.yaml (derived cache) → hunt_scrape.py (Apify; deterministic hard filters; dedupe via seen_ids.json)
   │                  → agent qualifies survivors (capability gate → fit 1–10) → writes cover letter (template-compliance check)
   │                  → Slack card (FYI only since 2026-08-26) → Notion Upwork_Jobs rows (qualified = full row; DQ = lean write-only row)
   ├─ Phase 2  APPLY: for each qualified job: find_jobs get → invitations check → manage_proposals create → confirm_preview IMMEDIATELY
   │                  (since 2026-10-01 via the official Upwork MCP connector; Chrome path retired after 12 blocked runs)
   │                  Connects short → auto-buy one 100-Connect bundle ($15) with "standing consent"
   └─ Phase 3  REBAKE (change-guarded): materialize state from Notion → write dashboard JSON (ArtifactData cockpit/state)

Side task: upwork-mcp-shadow-hunt (:40 past each slot) — finds jobs with the Upwork MCP, applies to good ones the Apify pipeline missed, logs Apify-vs-MCP comparison in mcp_shadow/ledger.json
```

**Separation of concerns that worked:**
- **Script owns scraping/dedupe/hard filters; agent owns judgment only** (restructured 2026-07-07 "after repeated context-compaction drift"). Scripts are immutable, SHA-256 pinned; a hash mismatch halts the run.
- **One source of truth per concern:** Notion `Upwork_Campaigns` (config), `Upwork_Jobs` (pipeline + human-readable log), `Upwork_State` (runtime state, stamps, incident flags). Local files are tiny caches: `last_run.json`, `seen_ids.json`, `notion_state_index.json`.
- **Change-guard + stamp-only guard** so the evening rebake exits in seconds when nothing changed (it failed every night from 07-31 to 09-06 until the stamp-only guard was added).
- **Incident-derived rules** written back into the canonical pages ("added 2026-07-14 after …"). The instructions are a living post-mortem log.

## 2. Data model

### 2.1 `Upwork_Jobs` (32 properties) — what was tracked per job
| Group | Fields |
|---|---|
| Identity | `Job` (title), `JobID` (numeric Upwork id; dedupe key), `URL`, `Campaign`, `Type` (HOURLY/FIXED) |
| Money | `Budget` (label), `Hourly Min`, `Hourly Max`, `Fixed Price`, `Bid`, `Connects Needed`, `Connects Spent` |
| Client | `Client Country`, `Client Spend`, `Client Rating`, `Proposals`, `Crowded?` |
| Judgment | `ICP` (checkbox), `Fit Score` (1–10), `Why It Fits`, `Why Not ICP` |
| Pipeline | `Status` (closed enum), `Status Note`, `Apply Error`, `Deadline` (retired), `SlackTS`, `SlackChannel` |
| Time | `Job Date` (posted on Upwork), `Scraped At`, `Posted At` (card time), `Applied At` |
| Content | `Description` (truncated ~1,800 chars); page body = `## Cover letter`, `## Screening Q&A` |

**Status enum (closed):** `posted → approved → applied`, plus `rejected`, `needs_human`, `error`, `closed`, `expired_cap`, `skipped_dq`.

**What was NOT tracked (the single biggest gap):** no `Viewed`, `Replied`, `Interview`, `Offer`, `Hired`, `Contract value`, `Outcome` fields. The system measures *activity* (scraped/qualified/applied/Connects) and never *results*. With 76 applications there is no way to compute a view rate, reply rate or win rate from this export. Aryan's schema must add outcome fields from day one (see `08_MCP_ACQUISITION_ENGINE.md` §5 and `templates/jobs_schema.json`).

### 2.2 `Upwork_Campaigns` (26 properties) — the campaign abstraction
Per campaign: `Key`, `Enabled`, `Title Keywords` (each run as a precise Upwork *title* search), `Categories` (Upwork category slugs), `Title Must Contain`, `Exclude Words`, `Job Types`, `Experience Levels` (2=intermediate, 3=expert), `Min Hourly`, `Min Fixed`, `Payment Verified`, `Min Client Spend`, `Min Client Avg Hourly`, `Min Client Hire Rate`, `Max Proposals` (above → `pileon` flag needs fit ≥ 9; >40 always dropped), `Posted Within Minutes` (lookback floor, widened to cover gaps up to 72h), `Limit Per Search`, `Min Fit Score`, `Bid Hourly Rate`, `Max Applies Per Day`, `Client Locations`, `Previous Clients Only`, `Notes`. Page body holds `## Qualify prompt` and `## Pitch angle`.

**Live values (all 3 campaigns identical on floors):** payment verified = true; min client spend $1,000; min avg hourly $15; min hire rate 50%; max proposals 10; min hourly $20; min fixed $500; experience {2,3}; min fit 7; bid $100/hr; max applies/day 5; posted-within 135 min; limit/search 20.

| Campaign | Title keywords | Exclusions | Note |
|---|---|---|---|
| `ai-automation` "AI Automation / Agents" | AI automation, AI agent, AI workflow, Claude, n8n, Make.com, Zapier, GoHighLevel + category `ai-apps-and-integration` | WordPress plugin, game, NFT | Rebuilt 2026-09-06 from loose keywords that returned Canva/Power BI/UX jobs |
| `outreach-infrastructure` | cold email, email deliverability, Smartlead, Instantly, Clay, Apollo, outbound, lead generation | appointment setter, cold calling, commission, telemarketing, Klaviyo, Meta/Facebook/Google Ads, media buyer | Exclusions strip the main noise |
| `linkedin-outreach` | LinkedIn outreach, LinkedIn lead generation, Sales Navigator | ghostwriting, content writer, profile optimization, LinkedIn Ads | "roughly 8 real jobs a week exist" |

### 2.3 `Upwork_State` (5 properties: `Key`, `Category`, `Status`, `Severity`, `UpdatedAt`, `ValueJSON`)
Row kinds: `settings` (`slack`, `connects`, `counters`), `last_run.<hunt|apply|rebake>` stamps, `log` (`run_history`, newest-first one-liners ≤200 chars, keep ≤20), and `eyeball-<date>-<task>-<slug>` incident flags (open/resolved, severity high/medium/low, plain-English headline + message). 28 rows total; 17 are eyeballs.

## 3. Phases and the state machine

```
[scrape] ──hard filters fail──▶ skipped_dq (lean row; never read back)
   │
   ▼ survivors
[capability gate] ──needs code/ML/mobile/never-claim──▶ skipped_dq ("capability: needs X")
   │
   ▼
[fit 1–10 vs campaign qualify prompt] ──< min_fit (7), or < 9 if pileon──▶ skipped_dq ("fit_score=N: reason")
   │
   ▼
[cover letter + screening answers] ──unanswerable without inventing──▶ needs_human / skipped_dq ("screening: Q")
   │  (5-point template compliance; check_letter.py hard gate on connector path)
   ▼
posted  (Slack card = FYI record since 2026-08-26)
   │
   ▼
approved (automatic; veto flow retired)
   │
   ├─ daily cap hit ──▶ expired_cap
   ├─ find_jobs get: applied=true ──▶ applied (already) ; totalHired>0 / can_apply=false / private ──▶ closed
   ├─ invitation exists ──▶ accept_invitation path
   ├─ Connects short ──▶ auto-buy 100 ($15) ──▶ retry ; blocked ──▶ stays approved + high eyeball
   ├─ Loom/video/bespoke artifact required ──▶ needs_human
   └─ manage_proposals create → confirm_preview ──▶ applied (Applied At, Connects Spent) ; error ──▶ error (retry ≤2)
```

**Idempotency & dedupe:** `seen_ids.json` (flat array of every job id ever scraped, including DQ) is the only dedupe source; `last_run.json` stamps stop duplicate triggers (<5 min) and stale catch-up runs (>90 min past slot → exit); `hunt_last_finalized.json` prevents re-scraping within 20 min of a finalized batch (2026-07-16 duplicate-cards incident).

## 4. Qualification / scoring logic (what it actually did)
1. **Hard filters (script):** job type, excluded words (title+description), hourly max ≥ min_hourly (missing passes), fixed ≥ min_fixed (missing passes), experience level, payment verified (unknown = unverified since v2.6), known client spend ≥ $1,000 (unknown on a verified client passes with `spend_unknown` flag — this rule flipped 3 times), optional avg-hourly and hire-rate floors (missing passes), proposals >40 drop / >10 `pileon`, location, `applied=true`.
2. **Detail check (MCP path):** `client_record` spend/hire rate; `activityStat.jobActivity.totalHired>0` or `totalOffered>0` → DQ "already hiring"; `totalInvitedToInterview>0` → flag `interviewing`; `preferred_locations.location_required` → DQ if not in countries.
3. **Capability gate (LLM):** core deliverable must live in one of four capability buckets; never reframe a hand-coding job as no-code.
4. **Fit score 1–10 (LLM)** with a one-sentence reason against the campaign `qualify_prompt`; threshold 7 (9 when crowded).
5. **Proof-demand detection:** postings that say "show don't tell / real numbers" get a letter that mirrors their list with hard numbers.

## 5. Empirical results from the 3,767-row dataset (2026-06-24 → 2026-10-02)

### 5.1 Funnel
| Stage | Count | % of scraped |
|---|---|---|
| Scraped (rows) | 3,767 | 100% |
| Hard-filter or agent DQ (`skipped_dq`) | 3,666 | 97.3% |
| Qualified (`ICP` = true) | 99 | 2.6% |
| Applied | 76 | 2.0% (77% of qualified) |
| `needs_human` | 9 | — (Loom/video interview/bespoke artifact/private listing) |
| `posted` (never applied; Chrome blocked) | 8 | — |
| `closed` (hired/offer made/suspended) | 4 | — |
| `rejected` (human veto) | 2 | — |
| `expired_cap` (daily cap) | 2 | — |
| **Views / replies / interviews / hires** | **not recorded** | — |

### 5.2 Volume over time (qualification rate fell as filters tightened)
| Month | Scraped | Qualified | Qual. rate | Applied |
|---|---|---|---|---|
| 2026-07 | 1,644 | 54 | 3.3% | 40 |
| 2026-08 | 1,288 | 19 | 1.5% | 17 |
| 2026-09 | 771 | 19 | 2.5% | 10 |
| 2026-10 (2 days) | 63 | 6 | 9.5% | 5 (connector) |

Scrape volume per working day ranged 4–200 (median ≈ 40). The last fortnight of September shows many runs with "0 qualified of 20 scraped" — the title-only searches plus $1,000-spend floor plus $15 avg-hourly floor starved the pipeline. Patrick's answer was the MCP shadow hunt (smart_search feed + title searches), which produced 6 qualified in its first 2 days.

### 5.3 Why jobs were disqualified (3,666 DQ rows, bucketed from `Why Not ICP`)
| Reason | Count | Share of DQ |
|---|---|---|
| Client spend below $1,000 floor | 1,145 | 31% (≥ 590 of these were *unknown* spend treated as $0) |
| Client average hourly paid < $15 | 463 | 13% |
| Too many proposals (>40, or pileon without fit 9) | 380 | 10% |
| Capability gate (needs hand-written code / ML / mobile / wrong stack) | 375 | 10% |
| Client hire rate < 50% | 290 | 8% |
| Payment not verified / unknown | 182 | 5% |
| Fit score < 7 | 145 | 4% |
| Location requirement | 80 | 2% |
| Rate/budget floor | 54 | 1.5% |
| Other (job type, experience, excluded word, screening, misc.) | ~550 | — |

**Reading for Aryan:** half of all rejections came from *client-history floors*, not from job fit. Three of the top five reasons are rigid thresholds that the reviewers of Aryan's plan explicitly want replaced with weighted scoring. The "unknown spend = $0" rule alone threw away ~16% of everything scraped, including new clients with detailed briefs.

### 5.4 Marketplace shape (all rows, Apify + connector)
- **Job type:** 72.5% hourly, 26.1% fixed.
- **Posted hourly ceiling** (n=2,513): median **$40/hr**. Buckets: $15–25: 292 · $25–40: 884 · $40–60: 700 · $60–100: 420 · $100+: 211 (8.4%). → A $65 displayed rate sits inside the ceiling of ~25% of hourly jobs; $100+ inside 8%.
- **Fixed budgets** (n=870, ≥$500 floor already applied upstream): median **$1,000**. $500–1k: 377 · $1k–2.5k: 294 · $2.5k–5k: 93 · $5k+: 98.
- **Client lifetime spend** (n=1,081 with data): median $8,074; 16% under $1,000; 17% over $100k.
- **Proposal count at scrape** (n=3,171): median **15**. <5: 702 (22%) · 5–10: 517 · 10–15: 346 · 15–20: 285 · 20–50: 788 · 50+: 533 (17%). → 38% of jobs still had ≤10 proposals when found within ~2h of posting; speed matters.
- **Client country:** United States ≈ 943 (US + USA labels), UK 127, Canada 78, India 54, Australia 47, Germany 31.
- **Title words (all):** automation 578, developer 474, engineer 370, marketing 338, email 285, gohighlevel 200, **claude 174**, **ai agent 152**, **n8n 94**, voice 93, python 77, rag 49, chatbot 34, **mcp 13**.

### 5.5 What got applied to (76 applications)
- **By campaign:** outreach/cold-email 37 (49%), AI automation/agents 32 (42%), LinkedIn 7 (9%).
- **By type:** hourly 59, fixed 15.
- **Bid policy:** $100/hr on 47 of 50 hourly applications regardless of the client's posted range (posted hourly max at apply: median $50). Fixed bids = client's budget: median $1,000 (range $500–$4,500).
- **Connects per application:** n=45 recorded, total 785, **mean 17.4, median 17, range 10–27**. Ledger `spent_total` reached 1,330 by 2026-09-14 (incl. earlier unrecorded). Bundle purchases: 100 Connects for $15 (+$0.90 fee → $15.90) on at least 2026-07-07, 2026-07-22, 2026-09-02, 2026-10-01. → **~$2.60 per proposal in Connects at $0.15/Connect; a 3–5/day cadence costs ~$8–13/day.**
- **Client quality of applied jobs:** spend median $14,059 (mean $70k; max $705k); rating mean 4.80; proposals at apply median 9.5 (mean 14.1); 20 of 76 (26%) were `Crowded?`.
- **Fit scores:** applied mean 7.92 (7: ~35%, 8: ~40%, 9: ~25%); every DQ'd-by-fit row averaged 2.37.
- **Title term → application rate** (applications ÷ scraped titles containing the term): clay 6/19 (32%), cold email 10/59 (17%), deliverability 7/48 (15%), apollo 5/22 (23%), **claude 12/174 (6.9%)**, n8n 3/94 (3.2%), gohighlevel 3/198 (1.5%), ai agent 1/152 (0.7%), rag 0/49, mcp 0/13, python 0/77. → Patrick's edge was outbound tooling; for Aryan the Claude/agent/RAG/MCP clusters are the under-served ones, and the dataset shows they exist (174 + 152 + 49 + 13 titles in 14 weeks from title-only searches).

### 5.6 Operational reliability (from eyeballs, run_history, counters)
- **Apply blocked 12 consecutive runs** (2026-09-24 → 2026-10-01) because the Chrome browser id went stale; two fit-9 jobs sat `posted/approved` for a week and one closed (client hired someone else). Fix: switch to the official Upwork MCP connector (works since 2026-09-30).
- **Login walls** (2026-07-14, 2026-08-18/19, 2026-09-24) stopped all applies for a slot.
- **Sandbox issues:** EDEADLK file locks, bash timeouts (~45 s), script hangs; a 2026-09-11 run burned 2h45m chasing locks for 0 survivors → mandatory mechanical preflight.
- **Notion query plan-gated** (2026-07-04) → all row access via a local page-id index.
- **Letter incidents:** fabricated Calendly URL shipped (2026-07-18; ToS risk) → no-URL hard rule + self-check; a third letter variant composed at submit time (2026-08-26) → one-canonical-letter rule; a freeform letter skipped the template (2026-08-26) → 5-point compliance check; first connector letter answered 5 questions in 5 paragraphs, 331 words (2026-09-30) → `check_letter.py` hard gate.
- **Bidding incidents:** $1,000 bid on a $600 fixed job (2026-06-24 "overbid") → fixed = client budget, never above; "Schedule a rate increase" form field required → always "Never".
- **Duplicate cards/applications** (2026-07-16) from reading script-internal progress mid-loop → never read `hunt_progress.json`; stale-batch guard.
- **Consent drift:** the apply page grew ~1,500 words of escalating "THIS IS YOUR APPROVAL, DO NOT ASK" text after two runs refused to auto-buy Connects. This is the clearest signal that fully autonomous money/Connects actions fight the model's safety priors and produce brittle behaviour. Aryan's design keeps the human gate and therefore never needs this text.

### 5.7 Cover-letter system (what the 71 exported letters show)
- **Template (rev 2026-09-06):** varied opener (a: "You said it yourself: <their phrase>", b: their goal + closest proof, c: "Hi, great to connect!" fallback; never the same opener twice in a row) → answers to explicit asks (2–5 short lines, in their order, before bullets; real cost/timeline ranges, never "on the call") → `Here's how I'd handle it` / `A few things I can do` + 3–5 outcome bullets with ≥1 real proof item (number, client name, case study) → plain confident close, no put-down, no hype → mandatory CTA "book a meeting at the link above" (Upwork's own consultation link, never a typed URL) → first-name sign-off. 150–220 words; up to ~270 for Claude letters.
- **"Built with Claude" structure (added 2026-07-20, "beat the generic version"):** quote their worry back → `Some of what I've built with Claude:` → 4–5 artifact bullets, each (a) concrete thing built, (b) mechanism proving it is real, (c) bridge clause to *their* world → close + CTA. Rationale: "every bidder claims to be an expert in Claude; almost no competing bidder can name systems actually built with it."
- **Hard bans:** no URLs; no em/en dashes; no "I'm excited", "delve", "leverage"; no tech-list soup; no programming-language claims (Patrick is no-code); never mention the Upwork automation itself; never invent facts; screening questions answered only from the profile page or `needs_human`.
- **Quality control:** 5-point compliance check; `check_letter.py` (length, one bullet block, no numbered Q&A, no long paragraphs, CTA, sign-off, no URL/dash, banned phrases, no sentence shared with a letter sent in the last 24h); no two letters per day share an opener or close.
- **Retired phrasing (2026-09-06 audit):** "That's just the beginning!", "Don't hire anyone who can just…", "hire me and I'll show you" — judged cocky. (The 2026-09-01 "Claude Enterprise Consultant" letter still contains all three — evidence the audit was triggered by real letters.)
- **Observed in exported letters:** a specific client-named artifact in the first two lines; posting's format instructions honoured ("start your proposal with the word Cowork"); first-milestone proposal mirrored from the client's own suggestion; NDA offered pre-access on an audit job.

### 5.8 Cadence and budgets
- 5 combined passes/day (10, 12, 14, 16, 18 ET) + 7 PM ET rebake + :40 shadow MCP hunt, weekdays only. Lookback 135 min, widened to the gap since last finalized batch (max 72h) so Monday sees the weekend.
- 20 searches per pass (title keywords + categories), ≤20 results each. Detail check capped at 25 jobs/run on the connector path.
- Max 5 applies/day/campaign (hit only twice in 14 weeks). Shadow hunt: `max_applies_per_day` per campaign, 24h candidate window.
- Connects: no boosting ever; auto-buy exactly one 100-Connect bundle when short, max N/day.

## 6. ADOPT / ADAPT / REJECT for Aryan

### ADOPT (as-is, with Aryan's names)
1. **Three-table model** — `jobs` (one row per job seen, lean rows for DQ), `state` (stamps, counters, incidents), `campaigns` (config as data; edit the row, next run uses it).
2. **Closed status enum**, with explicit terminal states and a `needs_human` state.
3. **Deterministic-first pipeline**: hard disqualifiers computed mechanically before any LLM judgment; LLM owns only capability gate, fit, and drafting.
4. **Dedup index of every job id ever seen** + idempotency stamps + stale-run guard + change-guarded rebake.
5. **Capability gate before fit score**; **never-claim list**; **screening answers only from the profile-facts file or `needs_human`**.
6. **Letter compliance gate** (structural check + banned phrases + no URL + no duplicate opener/close in 24h) run *before* the human sees the draft, so review time is spent on judgment, not hygiene.
7. **"Built with Claude" artifact-bullet structure** for Claude/agent/MCP jobs — Aryan's proof assets map to it directly.
8. **Proof-demand detection** (mirror their list with hard numbers).
9. **Incident flags ("eyeballs") with plain-English headline + severity + resolution**, and the discipline of writing the rule back into the runbook with the date and the incident.
10. **Campaign `Notes`/`Pitch angle`/`Qualify prompt` living next to the config.**
11. **Honour the posting's own application format** ("start with the word X") and **answer explicit asks inside the letter, in their order**.
12. **Fixed-price bid = client budget, never above; hourly bid is policy, not per-job judgment** (for Aryan: the campaign's bid, but *within* the step-up ladder, see `04_OFFER_LADDER_AND_PRICING.md`).

### ADAPT
1. **Scoring:** replace hard floors ($1,000 spend, $15 avg hourly, 50% hire rate, 10 proposals) with the weighted rubric in `06_LEAD_SCORING_RUBRIC.md`; keep only payment-verification, policy red flags, impossible scope and location exclusion as hard gates. Keep `pileon` as a *penalty* with a higher bar, not a drop.
2. **Discovery source:** Apify scraping → **Upwork MCP only** (`find_jobs smart_search most_recent` + `search title=` per campaign keyword + optional `subcategory`). No scraping, no third-party actors (ToS risk and the Forbidden-keyword incidents of 2026-07-06).
3. **Fields:** map Apify `buyer.*` fields to MCP `client_record.*` / `activityStat.jobActivity.*` / `preferred_qualifications` / `client_feedback` / `connects_cost` / `applied` / `can_apply` (see `08_MCP_ACQUISITION_ENGINE.md` §3, with `[VERIFY LIVE]` on every field name).
4. **Cadence:** 10:00–18:00 ET weekday slots → Aryan's **18:30–23:30 IST window** (US morning) with 2–3 passes, plus one morning IST sweep for overnight EU postings; weekends optional.
5. **Letter template:** keep the shape; change the proof library to Aryan's assets; change the CTA from "book a meeting at the link above" to the **"message me one process → recorded walkthrough"** offer plus the fixed first milestone (v2 plan template); keep the no-URL rule; **allow** Upwork-native attachments (portfolio_project_ids) since the MCP supports them.
6. **Bid policy:** Patrick bid $100/hr flat and above client ranges by design. Aryan bids the *campaign rate within the current ladder step* ($65 → $80 → $95 → $120) and prefers converting hourly posts into a fixed first milestone where the post allows it.
7. **Daily caps:** 5/day/campaign → **3–5 total/day across campaigns, quality-first**, with a hard Connects cap (80/day per v2 plan) and a weekly budget.
8. **Rebake:** dashboard refresh → **analytics loop** that also pulls `list_freelancer_proposals` to record views/replies/interviews/offers per proposal (the missing outcome layer), computes funnel KPIs per campaign/offer/opener, and writes the weekly review template.
9. **State store:** Notion with page-id index (because their Notion plan blocked queries) → for Aryan, **SQLite or JSON files in the repo-adjacent data folder** (queryable, versionable) with optional Notion mirror; schema in `templates/`.
10. **Slack cards:** FYI cards → **review cards that *are* the gate** (card shows draft, bid, Connects cost, boost recommendation, unmet qualifications, score breakdown; human replies approve/edit/skip). If no Slack, a local review queue file + CLI prompt.

### REJECT
1. **Instant auto-apply / "standing consent".** Every submission goes through `confirm_preview` only after Aryan has read the draft, price, Connects cost and boost in that session. Non-negotiable (consensus item 7; MCP safety model).
2. **Automatic purchase of Connects.** Aryan buys Connects manually; the agent reports balance and projected runway only.
3. **Auto-accepting invitations** without review (invites still cost 0 Connects but commit a proposal).
4. **Bidding above the client's hourly range by default.** Aryan's whole strategy is to fit *inside* the ceiling at $65 and earn the premium via fixed packages.
5. **Client-name inference from third-party reviews** (the MCP docs suggest it; GPT-5.6 review rejected it as error-prone and intrusive). Use a name only when the posting or invitation gives it.
6. **Scraping via Apify / any non-official source.**
7. **Browser automation of upwork.com** for applying (fragile: 12 blocked runs; login walls).
8. **Fetching instructions from Notion at runtime as the only source** — keep skills in the repo (`skills/`, `agent_instructions/`) under git; a Notion mirror is optional.
9. **The $1,000 lifetime-spend hard floor** and **"unknown spend = $0"** rule.
10. **Separate dashboard artifact plumbing** (ArtifactData/cockpit) — a weekly markdown/CSV review is enough for one freelancer.

## 7. Facts and heuristics worth carrying over verbatim
- Hourly jobs are ~3× fixed jobs in volume; fixed medians sit at $1,000 — the Setup Sprint ($299/$599/$1,200) and Audit ($750–$1,500) land exactly in the fixed sweet spot.
- Proposal count at first sight is ≤10 for 38% of jobs if you look within ~2 hours; Aryan's 18:30–23:30 IST window covers US 09:00–14:00 ET, where most postings land.
- Connects per proposal: plan on **17 average (10–27)**; 15–20 is Upwork's stated range for the Claude-title jobs in v2.
- `needs_human` was triggered 9 times in 14 weeks, mostly by "Loom video required" and "video interview required" — Aryan's 2-minute demo video and the "recorded walkthrough" offer convert this from a blocker into a differentiator.
- The one letter that explicitly "beat the generic version" was the artifact-bullet "Built with Claude" letter — Aryan's entire positioning is Claude implementation, so this is the default structure, not the exception.
- Posted jobs die fast: of 8 jobs left `posted/approved` for a week, 1 closed with another hire and 1 had an offer out. **Draft and decide same-session.**
