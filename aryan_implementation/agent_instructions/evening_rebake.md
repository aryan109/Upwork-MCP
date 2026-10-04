# Runbook — Evening Rebake (22:30 IST daily; Sunday adds weekly review)

Skill: `upwork-rebake-analytics`. Read-mostly. Never sends messages, never submits, never buys. Produces the digest Aryan reads before bed and the data the Sunday review uses.

## Steps (each in its own try/except; log every call with inputs and state_before)
1. **Preflight:** `list_accounts` (identity), load state, `run_id = <UTC ISO>-rebake`.
2. **Outcomes:** `list_freelancer_proposals list` → for each of ours with open status: `get` → update `outcome.*` and `status`. Count today's views/replies/interviews/declines. `[VERIFY LIVE: exact status strings]`
3. **Messages:** `get_room` / `get_messages` for `replied`/`interview` rooms; unanswered client messages > 6 h → reply draft (≤ 80 words) in the digest, marked **DRAFT — Aryan sends**.
4. **Invitations:** `list_freelancer_proposals invitations` → vet each → recommend accept-to-interview / decline with one-line reason.
5. **Telemetry:** `get_freelancer_dashboard check`, `get_profile connects_balance` → append to `telemetry[]`.
6. **Ledger:** expected vs actual Connects; |Δ| > 2 → incident `ledger`.
7. **Contracts:** `list_contracts`, `list_offers`, `list_milestones` → due/overdue milestones, unanswered offers (`finalize_url` is Aryan's to open), idle contracts > 30 days.
8. **Funnel (09 §2):** today + 30-day running; band × outcome table; by campaign; by rung; by opener; reject-reason distribution; cost per reply/hire.
9. **Calibration suggestions:** campaigns with 0 qualified in 5 days; Connects-heavy with 0 replies in 14 days; threshold ±5 recommendation (06 §6). Suggest only.
10. **Incidents & kill switch:** list unresolved; ≥ 3 unresolved or any `auth` → `kill_switch=true`, headline it.
11. **Housekeeping:** expire holds > 24 h; `submitted` > 30 days unviewed → `expired`; backup state to `state/backup/YYYY-MM-DD/`; prune payloads > 90 days; set `applies_today=0` for tomorrow.
12. **Digest** to Aryan (≤ 15 lines; format in the skill). **Sunday:** also fill `templates/weekly_funnel_review.md` → save to `reviews/YYYY-WW.md` (outside repo) and list proposed campaign edits for `upwork-campaign-editor`.

## Aryan's evening actions (from the digest, ≤ 15 minutes)
- Send the reply drafts (edit freely).
- Decide invitations.
- Note any manual Connects purchase so the ledger matches tomorrow.
- Say `clear kill switch` only after reading the incidents.
