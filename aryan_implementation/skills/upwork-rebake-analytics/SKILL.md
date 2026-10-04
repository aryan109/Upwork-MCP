---
name: upwork-rebake-analytics
description: Nightly reconciliation and analytics for Aryan's Upwork engine: pull proposal outcomes, invitations, messages, dashboard telemetry, Connects balance and contracts via the Upwork MCP; update job outcomes; reconcile the Connects ledger; compute funnel metrics by score band, campaign and rung; list incidents; set the kill switch when needed; write the daily digest and the Sunday weekly review. Use for "rebake", "evening review", "funnel report", or "reconcile".
---

# upwork-rebake-analytics

## Purpose
Close the loop the reference implementation never closed: outcomes. Runs at 22:30 IST (or on demand). Read-mostly; the only writes are to the state store and the digest. Drafts replies to client messages but never sends them.

## Procedure
1. **Proposal outcomes:** `list_freelancer_proposals` → `list` (active + archived if available). For each job with `status in {submitted, submitted_manually, viewed, replied, interview, offer}`: `get` → map Upwork status to our enum (`viewed`, `replied`, `interview`, `declined`, `withdrawn`, `expired`, `hired`) `[VERIFY LIVE: exact status values exposed]`; set `outcome.*_at` timestamps; on `hired`, link `contract_id` from `list_contracts`.
2. **Messages:** for `replied`/`interview` rooms, `get_room` / `get_messages`; if the last message is from the client and unanswered > 6 h → create a reply draft (≤ 80 words, plain, one next step) in the digest for Aryan. Never `send_message`.
3. **Invitations:** `list_freelancer_proposals` → `invitations`; score each with `upwork-vet`; present accept/decline recommendation.
4. **Telemetry:** `get_freelancer_dashboard check` (profile views, invites, proposals stats), `get_profile connects_balance`. Append to `state.telemetry[]` with date.
5. **Ledger reconciliation:** expected = yesterday's balance − Σ `submission.connects_spent` today + credits (Freelancer Plus, refunds). If |expected − actual| > 2 → incident `ledger` with both numbers.
6. **Contracts & money:** `list_contracts`, `list_offers`, `list_milestones`; list due/overdue milestones, unanswered offers, contracts idle > 30 days.
7. **Funnel metrics (09 §2):** today and running 30-day: discovered, qualified, drafted, approved, rejected (by reason), submitted, viewed, replied, interview, hired; reply rate by score band (70–79/80–89/90+), by campaign, by rung, by opener; Connects spent and cost per reply/hire. Produce the band × outcome table.
8. **Calibration notes:** campaigns with 0 qualified in 5 days; campaigns > 40% of Connects with 0 replies in 14 days; reject-reason distribution; threshold suggestion per 06 §6 (suggest only; Aryan + `upwork-campaign-editor` change it).
9. **Incidents:** list unresolved; if ≥ 3 unresolved or any `auth` → `state.kill_switch=true` and say so prominently.
10. **Housekeeping:** expire `hold` > 24 h; mark `submitted` > 30 days with no view as `expired`; back up state to `state/backup/YYYY-MM-DD/`; prune payloads > 90 days.
11. **Digest** (≤ 15 lines) to Aryan; on Sundays also fill `templates/weekly_funnel_review.md` and save as `reviews/YYYY-WW.md` outside the repo.

## Guardrails
- Never sends messages, accepts offers, withdraws proposals, or changes campaigns/scoring. Suggests only.
- Every MCP call through the logging wrapper; failures in one step never abort the others (try/except per step, incident per failure).
- Numbers in the digest must be reproducible from `jobs.json` and `runs.jsonl`.

## Digest format
```
REBAKE 2026-10-13 | submitted today 3 (total 21) | viewed 11 | replied 4 (19%) | interview 1 | hired 0 | connects 78 (−48 today, ledger OK)
Views 7d: 23 (+18) | invites 7d: 1 | badge ON day 9
Bands: 70–79: 9 sent / 1 reply · 80–89: 9 / 2 · 90+: 3 / 1
Campaigns: claude 9/3 · n8n 5/1 · agents 4/0 · mcp 1/0 · rag 2/0
Needs Aryan: 1 client message unanswered 7h (draft below) · 1 invitation (score 74, recommend accept-to-interview) · milestone due Fri
Incidents: 0 unresolved | kill_switch off
Suggestions: cut ai-training-coaching cap to 0 (0 qualified in 6 days); hold threshold at 70
```
