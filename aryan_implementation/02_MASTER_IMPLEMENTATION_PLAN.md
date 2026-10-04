# 02 — Master Implementation Plan (Day 1–30 daily, Day 31–90 monthly)

Day 1 = the first working day after Aryan approves this package (planned 2026-10-06, Monday). Owners: **A** = Aryan (anything that touches the live Upwork UI, money, clients, or identity); **G** = agent (reading, drafting, computing, state files, runbooks); **A+G** = agent prepares, Aryan executes. Tools column names the Upwork UI page or the MCP tool. Every item has acceptance criteria. `[VERIFY LIVE]` marks figures/limits to confirm on the live account before acting.

Phases: **P1 Reactivate & reposition (D1–14)** · **P2 Proof & first contracts (D15–45)** · **P3 Engine at full cadence (D45–75)** · **P4 Scale & retain (D75–120)** · **P5 Calibrate & rate step (D90–150)** · **P6 Premium ascent (≥D120, gated)**.

## 0. Prerequisites (before Day 1)
| # | Item | Owner | Acceptance |
|---|---|---|---|
| 0.1 | Upwork MCP connector re-authorised as **Aryan** (`claude mcp add --transport http upwork https://mcp.upwork.com/mcp`); `list_accounts` returns Aryan's account | A+G | Log line with account name; the previous "Patrick H." authorisation is gone |
| 0.2 | `tools/list` captured; count logged (doc says 51, XML lists 48) | G | `state.mcp_tool_count_observed` set |
| 0.3 | Private state directory outside the repo (`%USERPROFILE%\upwork_engine\state\`) with `jobs.json`, `state.json`, `campaigns.json` from `templates/` | G | Files exist; `campaigns.json` validates against schema |
| 0.4 | Aryan fills `skills/aryan-profile-facts/SKILL.md` (proof inventory, permissions, exact live numbers) | A | No `{{}}` left in the facts section |
| 0.5 | Aryan confirms the title, rate ($65), ladder prices and the "never auto-submit" rule in writing | A | Decision recorded in `project_development_logs.md` |
| 0.6 | Freelancer Plus: decide renew (100 Connects/month + profile visibility) `[VERIFY LIVE price]` | A | Decision logged |

## 1. Days 1–30 (daily)

| Day | Phase | Task | Owner | Tool | Acceptance | Rollback |
|---|---|---|---|---|---|---|
| **1 (Mon)** | P1 | Live audit: capture exact numbers (JSS, earnings, jobs, hours, Connects, badge, catalog, portfolio, invitation status, open contracts) into `aryan-profile-facts` | A+G | Profile page; `get_profile get`, `connects_balance`, `get_freelancer_dashboard check`, `list_contracts`, `list_freelancer_proposals invitations` | Facts file updated with date stamp; all `[VERIFY LIVE]` items in 03 resolved or listed | — |
| 1 | P1 | Reply to the 2026-08-31 invitation (accept-to-interview or decline per 05 §1 S5) | A | Messages/Invitations UI | Invitation no longer "pending" | — |
| 1 | P1 | Build reactivation tracker from contracts list | A+G | `list_contracts`; `templates/reactivation_tracker.csv` | 16 clients segmented S1–S4 | — |
| **2** | P1 | Profile rewrite: title (primary), overview (03 §3) with claims-hygiene checklist, skills tags (03 §4), rate $65 | A | Profile edit UI | Saved; screenshot stored outside repo; checklist all ticked | Previous overview text saved to `%USERPROFILE%\upwork_engine\backup\profile_2026-10-04.md` before edit; revert by paste |
| 2 | P1 | Turn **availability badge ON**; set consultation 30 min = $75 | A | Profile settings; Consultations | Badge visible; consultation listing shows $75 | Toggle off |
| 2 | P1 | Send S1 message (enterprise client) | A | Messages | Sent; logged in tracker | — |
| **3** | P1 | Unpublish OpenClaw catalog projects; decide AI Launchpad Blueprint | A | Project Catalog | 0 OpenClaw listings live | Re-publish from drafts |
| 3 | P1 | S2 messages (5 idle contracts) | A | Contract rooms | 5 sent, logged | — |
| 3 | P1 | Engine: implement logging wrapper + state files; read-only smoke tests (`find_jobs search/smart_search/get`, `get_profile`, `list_freelancer_proposals list`) | G | MCP | `runs.jsonl` has ≥ 10 successful read calls; `filters_ignored`/mismatch incidents logged | — |
| **4** | P1 | Draft catalog Listing 1 (Setup Sprint) in Upwork from 03 §6.1; submit for review | A | Project Catalog | Status "under review" | — |
| 4 | P1 | S3 messages (batch 1, ≤ 4) | A | Messages | Sent, logged | — |
| 4 | P1 | Engine dry-run day 1: discovery + scoring across all 7 campaigns, **no drafts**; output SKIP/REVIEW/APPLY lists | G | MCP + rubric | ≥ 50 jobs scored; Aryan eyeballs 20 and marks agree/disagree in the worksheet | — |
| **5** | P1 | Draft catalog Listing 2 (Audit); submit | A | Project Catalog | Under review | — |
| 5 | P1 | S3 messages (batch 2) | A | Messages | All S1–S3 messaged | — |
| 5 | P1 | Engine dry-run day 2; rubric adjustments from Aryan's disagreements (log as `scoring_version 1.1`) | G | rubric | Agreement ≥ 80% on APPLY/SKIP | Revert to 1.0 |
| **6 (Sat)** | P1 | Record the 2-minute demo video (03 §8) on the internal system; edit; captions | A | Screen recorder | File < 2:10, redacted, captions | — |
| 6 | P1 | Write case study 2 (internal agent/MCP system, labelled honestly) using 03 §7 template | A+G | Portfolio | Draft text complete, diagram made | — |
| **7 (Sun)** | P1 | Case study 1 and 3 drafts (`{{}}` from real contracts; permission check for client mentions) | A+G | Portfolio | Two drafts, assets listed | — |
| 7 | P1 | Weekly review #1 (template); decide Freelancer Plus if not yet | A+G | `templates/weekly_funnel_review.md` | Filled | — |
| **8** | P1 | Publish case study 2 + video to portfolio; attach video to catalog Listing 1 gallery | A | Portfolio / Catalog | Live | Unpublish |
| 8 | P1 | **Engine drafting ON** (max 3 drafts/day for week 2); first review queue at 19:00 IST | G → A | runbook `agent_instructions/combined_pass.md` | 3 drafts with self-check; Aryan approves/edits/rejects with reasons | Set `kill_switch` |
| 8 | P1 | First 1–3 proposals **submitted by Aryan** (via `confirm_preview` after explicit confirm, or UI) | A | `manage_proposals create` → `confirm_preview` | `proposal_id` logged; Connects reconciled | Withdraw within 24 h if a mistake `[VERIFY LIVE refund]` |
| **9** | P1 | Reactivation follow-ups (non-responders) | A | Messages | Sent | — |
| 9 | P1 | 3 proposals; evening rebake live for the first time (`agent_instructions/evening_rebake.md`) | G/A | MCP | Rebake digest produced; outcomes fields populated | — |
| **10** | P1 | 3 proposals; publish case studies 1 and 3 if assets are ready | A | Portfolio | Live or dated TODO | — |
| 10 | P1 | Catalog listings approved? fix review notes if not | A | Catalog | Both live | — |
| **11** | P1 | 3–4 proposals; check `get_freelancer_dashboard` for first views/invites | G/A | MCP | Telemetry trend row added | — |
| **12** | P1 | 3–4 proposals; respond to any client replies within 12 h (agent drafts, Aryan sends) | A | Messages | Response time < 24 h | — |
| **13 (Sat)** | P1 | Optional 2 proposals (weekend posts get fewer competitors); write Listing 3 text (next-step offer) | A+G | Catalog | Draft | — |
| **14 (Sun)** | P1 | **Gate G1** (see §4): reactivation results, ≥ 15 proposals submitted, first replies; weekly review #2; calibration v1.2 | A+G | review template | Gate decision logged | — |
| **15** | P2 | Raise to 3–5 drafts/day; enable `best_match` daily per campaign | G | campaigns.json | Cap 5 in state | Lower cap |
| 15 | P2 | Any booked calls: prepare 1-page call notes (agent) 2 h before | G | — | Notes delivered | — |
| **16** | P2 | Proposals; first consultation or Sprint sale → follow delivery checklist (04 §2) | A | Contracts | Milestone funded before work | — |
| **17** | P2 | Proposals; weekly campaign editor pass (query hygiene, 0-yield campaigns) | G | `upwork-campaign-editor` Skill | Changes versioned | Revert version |
| **18** | P2 | Proposals; check Connects ledger vs balance; buy Connects **only by Aryan** if < 40 | A | Connects page | Balance ≥ 2 days' need | — |
| **19** | P2 | Proposals; Specialized profile A ("AI Agent & Automation Development") drafted | A+G | Specialized profiles UI `[VERIFY LIVE limit]` | Draft | — |
| **20 (Sat)** | P2 | Deliverable work (Sprint/Audit) if sold; otherwise proof: record a second short demo (RAG or n8n) | A | — | Asset exists | — |
| **21 (Sun)** | P2 | Weekly review #3; **G1b**: ≥ 1 paid milestone/new contract from reactivation or proposals? | A+G | template | Logged | — |
| **22–26** | P2 | Daily: 3–5 proposals; deliver sold work; ask for review at completion the same day; agent drafts follow-ups at 72 h for viewed-no-reply | A/G | MCP, Messages | 15–25 proposals this week; replies logged; any contract delivered with recorded walkthrough | — |
| 24 | P2 | Publish Specialized profile A | A | UI | Live | Unpublish |
| **27 (Sat)** | P2 | Case-study refresh with any newly completed work | A+G | Portfolio | Updated | — |
| **28 (Sun)** | P2 | Weekly review #4; experiment E1 (badge) interim read; start E3 or E4 | A+G | template | Experiment logged | — |
| **29–30** | P2 | Proposals; **Gate G2 prep**: funnel export by score band/campaign/rung (should be ≥ 20–30 qualified proposals submitted) | G | `upwork-rebake-analytics` | Report produced | — |

Weekly volume targets: W1 0–3 proposals (profile first), W2 ≈ 12, W3 ≈ 15–20, W4 ≈ 15–25. Connects: ≈ 250 in month 1 `[ASSUMPTION]`.

## 2. Days 31–60 (P2 → P3)

| Week | Focus | Tasks | Owner | Acceptance |
|---|---|---|---|---|
| 5 (D31–35) | **Gate G2** reassessment after 20–30 proposals | Reply/hire rate by band, campaign, rung; threshold ±5; campaign Connects reallocation; letter opener decision; keep/cut `ai-training-coaching` | A+G | Written decision; `scoring_version 2.0`, `campaigns v2` |
| 5–6 | Delivery | Deliver Sprints/Audits sold; convert ≥ 1 Audit to L4 quote within 48 h of readout | A | Quote sent as fixed 3-milestone contract |
| 6 (D36–42) | Proof | Case study from first delivered Sprint/Audit (with permission); second video if needed | A+G | Portfolio ≥ 3 real items |
| 6 | Engine | Rebake calibration automation: band × outcome table auto-generated; incidents trend | G | Table in digest nightly |
| 7 (D43–49) | Volume + quality | Steady 3–5/day; follow-up discipline; decline low-fit invitations politely; consultation price test (E6) if ≥ 2 bookings | A/G | ≥ 60 cumulative proposals; reply rate ≥ 15% or corrective action taken |
| 7 | Retainer seed | Offer Care Plan Keep-alive to every completed client | A | ≥ 1 Care Plan proposal sent |
| 8 (D50–56) | **Gate G3** (rate $65 → $80) if 3 completed contracts at ≥ 4.8 + 2 case studies + JSS 100% | A | Rate changed; consultation $100; ladder doc updated |
| 8 | Specialized profile B ("AI Training & Coaching") only if training posts show ≥ 10% reply | A+G | Live or dropped |
| 8–9 (D57–60) | Monthly review (D60) | Revenue, effective hourly, Connects cost per hire, experiments E1–E4 results; Revedor candidates list | A+G | Monthly report; next-month campaign plan |

## 3. Days 61–90 (P3 → P4/P5)

| Week | Focus | Tasks | Owner | Acceptance |
|---|---|---|---|---|
| 9–10 (D61–70) | L4 pipeline | ≥ 1 Implementation in delivery; milestone discipline (architecture funded first); twice-weekly written updates | A | Milestone 1 accepted in writing |
| 9–10 | Engine | SQLite migration if `jobs.json` > 2,000 rows; Notion mirror optional; monthly scoring re-weight (one block only) | G | Migration log; `scoring_version 2.x` |
| 11 (D71–77) | Retention | First Care Plan live; monthly health report template delivered | A | Contract active |
| 11 | Market re-scan | Re-run the 2026-10-04 marketplace snapshot queries (Claude/AI agent/n8n/MCP counts, proposal distributions, competitor rates) and diff | G | "snapshot of 2026-12-xx" table appended to 01/09 |
| 12 (D78–84) | **Gate G4** ($80 → $95) if 3 more completed, 1 Care Plan active, 3 case studies, demo video live | A | Decision logged |
| 12 | Experiments | E2 title test if views plateau; E5 boost test on ≥ 85 band | A+G | Results in weekly review |
| 13 (D85–90) | **Gate G5** (Day 90 review) | Funnel totals; 12-month earnings trajectory; decide P5 cadence (hold / grow Connects to 400 / trim campaigns); check P6 entry criteria (10 §1) | A+G | 90-day report; P6 checklist started |

## 4. Decision gates

| Gate | When | Question | Pass → | Fail → |
|---|---|---|---|---|
| G0 | Pre-day 1 | Connector as Aryan? facts filled? rules agreed? | Start | Do not start the engine |
| G1 | D14 | Profile/catalog live, ≥ 15 proposals, reactivation messages all sent, ≥ 1 reply anywhere? | P2 | Extend P1 one week; audit letters against checklist |
| G1b | D21 | ≥ 1 paid milestone or new contract ≥ $251? | continue | Lower Sprint default to $299 in proposals for 2 weeks; add 3 deliberate re-entry jobs |
| G2 | after 20–30 qualified proposals (~D30–35) | reply ≥ 15%, hire ≥ 4%? | P3 caps; scoring v2 | 48-h pause; rewrite openers; reduce to 2 campaigns; reassess after 15 more |
| G3 | ~D50 | rate gate 1 (04 §7) | $80 | hold $65; recheck fortnightly |
| G4 | ~D80 | rate gate 2 | $95 | hold |
| G5 | D90 | trajectory to ≥ $15K/12 mo? P6 criteria progress? | P5 plan | Restructure campaigns/offers; consider pausing engine to focus on delivery |
| G6 | ≥ D120 | all 8 criteria in 10 §1 | Premium storefront | $95 + Alt B title; wait |

## 5. Rollback plan (any time)
- **Profile:** restore from the pre-edit backup text; rate back to previous value (changes apply to new proposals only).
- **Catalog:** unpublish new listings; OpenClaw listings can be re-published from drafts if ever wanted (not recommended).
- **Engine:** `kill_switch=true` stops drafting and submitting instantly; discovery can keep running for data. Withdraw any erroneous proposal within 24 h `[VERIFY LIVE: Connects refund policy on withdrawal]`.
- **Badge/consultations:** toggle off; no residual cost beyond Connects already spent.
- **Data:** state directory is outside the repo and backed up daily by the rebake (`state/backup/YYYY-MM-DD/`).

## 6. Owner summary
Aryan: all profile edits, all client messages and replies, all submits/confirms, all purchases, all offers/contracts, recording the video, writing proof facts. Agent: discovery, scoring, drafting, state, logs, rebake, analytics, runbooks, campaign hygiene, reminders, call-prep notes, draft replies.
