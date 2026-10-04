# Runbook — Combined Pass (Hunt → Vet → Draft → Review queue)

Runs at 08:30, 12:30, 18:30 (and optionally 21:30) IST on working days. Human-in-the-loop: this pass ends with a review queue; it never submits.

## 0. Preflight (abort the pass on any failure; raise incident)
1. Load `state.json`. If `run_in_progress` is true and `last_run_at` < 90 min ago → exit ("overlap"). Else set `run_in_progress=true`, create `run_id = <UTC ISO>-<slot>`.
2. `list_accounts` → account must be Aryan's; log the name. Otherwise incident `auth`, `kill_switch=true`, exit.
3. If `kill_switch` is true → run discovery only (steps 1–2), skip drafting, say so in the summary.
4. `get_profile connects_balance` → `state.connects_balance`. If balance < 20 → drafting continues but every draft is marked `connects_low`; tell Aryan.
5. Load `campaigns.json` and `scoring.json`; log their versions in the first `runs.jsonl` line of the run.

## 1. Hunt — Skill `upwork-hunt`
Lookback from `last_run_at − 15 min` (cap 72 h). ≤ 20 searches. ≤ 25 detail fetches. Write discovered records. Report counts.

## 2. Vet — Skill `upwork-vet`
Score every `discovered` record (and refreshed ones). Apply caps: global 5 submits/day, campaign `max_drafts_per_day`, Connects gate. Produce APPLY / REVIEW / SKIP lists with reasons.

## 3. Draft — Skill `upwork-proposal-draft`
- Slots available today = 5 − `applies_today` − drafts already `in_review`.
- Draft APPLY jobs by score desc until slots are filled. If slots remain and it is the 18:30 pass, draft up to 2 REVIEW jobs (score ≥ 60) marked `review_tier`.
- Each draft must pass the 12-point self-check or be marked `needs_edit`.
- If `aryan-profile-facts` has unresolved `{{}}` in §1–§3, do not draft; tell Aryan which fields are missing.

## 4. Review queue — Skill `upwork-human-review-submit` (presentation only)
Post the queue to Aryan: one block per draft, ranked, with the pre-filled checklist. Ask for `submit | submit with edits | skip: reason | hold`. Do **not** call `manage_proposals` in this pass. Submission happens in Aryan's reply turn, with the two-step confirm.

## 5. Close
- `state.last_run_at = now`, `run_in_progress=false`, `runs_today += 1`.
- Summary (≤ 10 lines): hunt counts, vet counts, drafts, slots left, Connects, incidents, mismatches seen.
- Append nothing to the repo; all state lives in `%USERPROFILE%\upwork_engine\state\`.

## Failure handling
Each step in its own try/except; a failure logs an incident with input params and `state_before` and the pass continues to the next step where safe (a Hunt failure still allows vetting of previously discovered jobs; a Draft failure for one job does not stop others). `auth` failures stop everything.

## Summary template
```
PASS 2026-10-13 18:30 IST (run 2026-10-13T13:00Z-evening) | connector: Aryan | campaigns v1.4 | scoring v1.2
Hunt: searches 18/20 · new 23 · refreshed 4 · pre-filtered 9 · detail 14 · mismatches: 0
Vet: APPLY 3 · REVIEW 4 · SKIP 7 (top: spend_unknown 3, pile_on 2, title_no_match 2)
Draft: 3 drafted (self-check 12/12 ×2, needs_edit ×1: forbidden phrase) · slots left today 1
Connects: 94 · applies today 1/5 · kill_switch off · incidents 0
→ Review queue posted below. Reply per job: submit | submit with edits | skip: reason | hold
```
