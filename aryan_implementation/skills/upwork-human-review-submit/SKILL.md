---
name: upwork-human-review-submit
description: Present drafted Upwork proposals to Aryan for review, capture approve/edit/skip/hold decisions with reasons, and—only after an explicit "submit" followed by a second explicit "confirm" of the preview—submit via manage_proposals create and confirm_preview, then log proposal_id and Connects. Use whenever drafts are waiting or Aryan says submit/skip. Never auto-submits, never buys Connects, never boosts above 10.
---

# upwork-human-review-submit

## Purpose
The only skill allowed to call `manage_proposals` and `confirm_preview`, and only on Aryan's explicit instruction. Two-step confirmation is mandatory.

## Review presentation
For each `status="drafted"` job (ranked by score), present the block from `upwork-proposal-draft` plus:
- Job title, link, budget/ceiling, proposals tier, posted age, client spend / hire rate / rating / avg paid / verified.
- Score + top-3 reasons; rung and terms; Connects cost and boost recommendation (`boost.recommendation`, `recommended_connects`).
- Self-check result; any `needs_edit` items first.
- The 12-point human checklist (`templates/proposal_review_checklist.md`) pre-filled with the agent's answers for Aryan to confirm.

Ask one question: `submit | submit with edits: <text> | skip: <reason> | hold`.

## Decision handling
- **submit / submit with edits:** apply edits verbatim (re-run self-check; warn if a rule breaks, but Aryan's text wins), then step 1 of submission.
- **skip: <reason>:** `status="rejected_by_aryan"`, `review.reject_reason` = reason (use vocabulary: `price`, `fit`, `client`, `letter_quality`, `scope`, `competition`, `connects`, `other:<text>`). Log. These reasons feed calibration.
- **hold:** stays `in_review`; expires to `skipped` (`hold_expired`) after 24 h.

## Submission (two explicit confirmations)
1. `manage_proposals` → `create` with `job_reference`, `charged_amount` (hourly rate or fixed total), `cover_letter` (≤ 5,000 chars), `answers`, `portfolio_project_ids` (from proof inventory), `boost_connects` (0 unless score ≥ 80 **and** `boost.recommendation != "skip"`; cap `min(recommended_connects, 10)`). If the response demands `acknowledge_policy`, show the policy text to Aryan and wait.
2. Receive `preview_id`. **Re-display the exact preview** (terms, amount, Connects to be charged incl. boost, letter, answers). Ask: `confirm` or `cancel`.
3. On `confirm`: `confirm_preview(preview_id)`. On success: store `submission.{proposal_id, submitted_at, connects_spent, boost, charged_amount}`, `status="submitted"`, `applies_today += 1`, update `connects_balance` via `get_profile connects_balance`. Log `submit` event with inputs and result.
4. On `VJ-JA-10`: `status="duplicate"`, tell Aryan, no retry. On validation error: show the error, `status="error"`, no retry without a fix. On transient error: retry ≤ 3 with backoff; then incident.
5. Manual path: if Aryan says `manual`, output the letter and answers as plain text; after Aryan confirms submission in the UI, set `status="submitted_manually"`; the rebake reconciles with `list_freelancer_proposals`.

## Guardrails
- No submission without both `submit` and `confirm` in this session for this `job_id`.
- Never purchase Connects; if balance is insufficient, report and stop.
- Never submit to a job with `applied=true`, `can_apply=false`, or an open conflict (`same_client_open`).
- Never edit the cover letter after Aryan's confirm.
- Daily cap 5 submits; refuse the sixth and explain.
- Never accept offers or invitations here; those are separate explicit instructions (invitations: `accept_invitation`/`decline_invitation`; offers via `finalize_url` in the UI).

## Output
```
REVIEW QUEUE 2026-10-13 19:02 IST | drafts 3 | connects 94 | submitted today 1/5
[1] score 88 … (block)
[2] …
Awaiting: submit | submit with edits | skip: reason | hold
---
SUBMITTED ~01…  proposal_id ~02…  charged $1,200 fixed  connects 16 (+0)  balance 78  status submitted
```
