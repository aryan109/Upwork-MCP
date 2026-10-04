# Aryan Upwork Implementation Package

Built 2026-10-04 from the decided 14-point consensus (Claude v2 plan as commercial base, Upwork MCP as acquisition OS, Gemini "Enterprise AI Architect" as Phase-6 destination only) and from a deep read of the reference autopilot in `../Upwork Analysis Agent Data/` (Patrick H., 3,767 jobs, 2026-06-24 → 2026-10-02). This package is the *how*, not a re-litigation of the *what*.

Conventions: `{{PLACEHOLDER}}` = fact only Aryan can supply (never fabricated). `[VERIFY LIVE]` = check on the live Upwork account/UI before acting. `[ASSUMPTION]` = planning target, not a forecast. Marketplace counts are attributed as "snapshot of 2026-10-04". Live state, logs and client data live **outside** this repo (`%USERPROFILE%\upwork_engine\`).

## Machine-readable tracker
`ARYAN_IMPLEMENTATION_PLAN.xml` is the single navigation and tracking document for executing this package: 73 tasks across phases P1–P6 (each with owner, day, tool, reference, acceptance criteria, rollback, `status` attribute), gates G0–G6, the offer ladder, the 7 campaigns, the scoring model, skills/runbooks, a `verify_live_registry` (35 items, `verified="false"` until checked) and a `placeholders_registry` (16 items). Update the `status`/`verified` attributes as work proceeds; validate with `[xml](Get-Content -Raw ARYAN_IMPLEMENTATION_PLAN.xml)` after edits.

## Read in this order

| File | What it is | Read when |
|---|---|---|
| `00_README.md` | This map | first |
| `ARYAN_IMPLEMENTATION_PLAN.xml` | Machine-readable plan map and living tracker | first; update continuously |
| `02_MASTER_IMPLEMENTATION_PLAN.md` | Day 1–30 daily, Day 31–90 weekly; owners (Aryan vs agent), tools (UI vs MCP), acceptance criteria, rollback, gates G0–G6 | Day 0, then every Sunday |
| `03_PROFILE_AND_STOREFRONT.md` | Paste-ready title (+2 alternates), overview, claims-hygiene checklist, skills order, rate, availability/consultation settings, 3 case-study templates, 2-minute video script, 3 Project Catalog listings in full, removal list | Day 2–5 |
| `04_OFFER_LADDER_AND_PRICING.md` | L1 consultation → L2 Sprint → L3 Audit → L4 Implementation → L5 Care Plan; pricing rules for proposals; fixed-price economics; rate gates | before any quote |
| `05_PAST_CLIENT_REACTIVATION.md` | Segments S1–S5, 10-day sequence, message templates, offers, tracker, success criteria | Day 1–14 |
| `06_LEAD_SCORING_RUBRIC.md` | 10 hard disqualifiers + 0–100 weighted score (fit 35 / client 25 / money 15 / competition 15 / risk 10), modifiers, thresholds, Connects rules, 6 worked examples, calibration plan | before the engine's first dry run |
| `07_PROPOSAL_SYSTEM.md` | Master drafting prompt, structure, proof-matching, length and forbidden-phrase rules, Q&A handling, 12-point review checklist, 5 complete example proposals | before the first draft |
| `08_MCP_ACQUISITION_ENGINE.md` | Pipeline Discover→Score→Telemetry→Conflict→Proof→Draft→Human review→Submit; MCP tool per step with known mismatches; state schema; 7 campaigns; IST cadence; dedup/conflict rules; logging/try-except wrapper; evening rebake | Day 3 build |
| `09_FUNNEL_METRICS_AND_EXPERIMENTS.md` | Funnel definition, metrics/targets/alarms, reassessment gate after 20–30 proposals, 8 experiments, weekly/monthly review | Day 14 onward |
| `10_PREMIUM_ASCENT.md` | Entry criteria for $120+/hr and $8K–$25K engagements, premium storefront, Upwork→Revedor handoff | Day 90+ |
| `01_REFERENCE_IMPLEMENTATION_ANALYSIS.md` | Deep analysis of the reference autopilot: architecture, data model, state machine, empirical results, ADOPT/ADAPT/REJECT, carry-over heuristics | background |
| `skills/*/SKILL.md` | 9 agent skills (YAML frontmatter): `upwork-hunt`, `upwork-vet`, `upwork-proposal-draft`, `upwork-human-review-submit`, `upwork-rebake-analytics`, `upwork-campaign-editor`, `upwork-state-and-debugging`, `aryan-profile-facts`, `past-client-reactivation` | install into the agent |
| `agent_instructions/` | `combined_pass.md` (hunt→vet→draft→queue), `evening_rebake.md`, `human_in_the_loop.md` (who may do what) | scheduler setup |
| `templates/` | `jobs.schema.json`, `jobs.csv`, `state.schema.json`, `campaigns.schema.json`, `campaigns.example.json`, `scoring.example.json`, `lead_score_worksheet.csv`, `proposal_review_checklist.md`, `reactivation_tracker.csv`, `weekly_funnel_review.md` | copy to the private state dir |

## The plan in ten lines
1. Reconnect the Upwork MCP connector **as Aryan** (it was authorised as "Patrick H." in the planning session) and fill `skills/aryan-profile-facts`.
2. Day 1–2: answer the open invitation, back up and rewrite the profile (title `AI Automation & Claude Implementation | Agents, n8n & Integrations`, $65/hr, new overview, skills), badge on, consultation $75.
3. Day 2–5: message the repeat enterprise client, the 5 idle open contracts, and the 5.0 clients (zero Connects).
4. Day 3–5: unpublish OpenClaw, publish Setup Sprint ($299/$599/$1,200) and Audit ($750/$1,500) listings.
5. Day 6–10: record the 2-minute demo, publish 3 case studies (one honestly labelled internal sample).
6. Day 4–7: engine dry-run (discover + score, no drafts); Aryan calibrates the rubric.
7. Day 8+: drafting on; 3 excellent proposals/day (max 5), each reviewed and submitted by Aryan via two-step confirm; never auto-submit, never auto-buy.
8. Nightly rebake records outcomes (the reference never did) and reconciles Connects.
9. Reassess after 20–30 qualified proposals (G2); rate $65 → $80 → $95 by gates; Care Plans for retention.
10. Phase 6 (≥ day 120, 8 criteria) → premium storefront; Upwork feeds Revedor.

## Install the skills
Copy each `skills/<name>/` directory into the agent's skills location (Claude Code: `~/.claude/skills/<name>/SKILL.md`; Cursor: `.cursor/skills/<name>/SKILL.md` or the user-level skills folder). Keep the repo copy as the source of truth; edits go through git.

## Non-negotiables carried into every file
Human approval before any submission · no fabricated credentials, clients or results · claims hygiene (no "8 years", no compliance absolutes) · no OpenClaw in the storefront · no mention of this engine in client-facing text · state and client data outside the repo · every MCP call logged with inputs and state · `[VERIFY LIVE]` before acting on any live number.
