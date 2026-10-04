---
name: upwork-vet
description: Score discovered Upwork jobs with Aryan's weighted lead-scoring rubric (hard disqualifiers, 0–100 score across fit, client quality, money, competition, risk; APPLY/REVIEW/SKIP), check conflicts against open proposals and contracts, and enforce daily caps and Connects budget. Use after upwork-hunt or when asked to "vet", "score", or "qualify" jobs.
---

# upwork-vet

## Purpose
Deterministic, explainable qualification. Input: job records with detail payloads. Output: `score`, `score_breakdown`, `decision`, `reasons[]`, `disqualifiers[]`, `rung_suggested`, `pricing_hint`. Full rubric: `06_LEAD_SCORING_RUBRIC.md` (authoritative); `scoring.json` holds the current weights/thresholds and `scoring_version`.

## Procedure
1. **Hard disqualifiers D1–D10** (06 §1). Evaluate in order; the first hit sets `decision="SKIP"`, `disqualifiers=[Dx]`, `status="scored"`; do not compute the score. D10 (conflict) requires: look up `client.hash` in `jobs.json` for `status in {submitted, viewed, replied, interview, offer, hired}`; and check `list_freelancer_proposals list` cache (refreshed by rebake) and `list_contracts` cache for the same client.
2. **Score blocks A–E** (06 §2) using the detail payload. Unknown values use the "unknown" scale value, never 0, except where 06 says otherwise. Record each feature's raw value and points in `score_breakdown`.
3. **Modifiers** (06 §3): +5 open related jobs/active contracts; +5 Claude/Anthropic named; +3 IST-friendly time zone; −10 pile-on × bidding above avg paid; −5 preferred-location soft mismatch.
4. **Decision:** ≥ threshold (default 70) → `APPLY`; 55–69 → `REVIEW`; else `SKIP`. Campaign-specific `score_threshold` overrides the default.
5. **Caps:** if `applies_today ≥ 5` or the campaign's `max_drafts_per_day` reached → decision stays but `queued_for_next_day=true`. If `connects_balance < 2 × (connects_cost + planned boost)` → downgrade `APPLY` to `REVIEW` with reason `connects_low`.
6. **Rung & pricing hint** (04 §3): fixed post → rung by budget (<$1,200 Sprint/Audit; ≥$1,200 Implementation Phase 1); hourly post → sticker $65 or ceiling if ≥$45 and score ≥80; always note the fixed alternative for ≤10 h/week. Flag `avg_hourly_paid < $15` with "propose fixed, not hourly".
7. **Write** `status="scored"`, fields above, `scoring_version`. Log one `score` event per job with inputs `{job_id}` and result `{score, decision, reasons}`.
8. **Return** ranked lists: `APPLY` (by score desc, then freshness), `REVIEW`, `SKIP` (with top-3 reasons each).

## Reasons vocabulary (use these strings so the rebake can aggregate)
`title_strong_match`, `title_adjacent`, `title_no_match`, `workflow_clear`, `rung_sprint`, `rung_audit`, `rung_impl`, `proof_direct`, `proof_adjacent`, `proof_none`, `spend_high`, `spend_unknown`, `spend_zero_verified`, `hire_rate_low`, `avg_paid_low`, `rating_low`, `unverified`, `budget_strong`, `budget_low`, `ceiling_low`, `pile_on`, `fresh`, `stale`, `client_interviewing`, `client_hired_already`, `many_questions`, `red_flag_language`, `scope_vague`, `connects_expensive`, `connects_low`, `same_client_open`, `location_soft_mismatch`, `claude_named`, `open_related_jobs`.

## Guardrails
- Never change weights or thresholds at run time. Proposed changes go to the rebake notes for Aryan and the `upwork-campaign-editor` skill.
- Any payload missing `client_record` → score with unknowns and add reason `data_missing`; never SKIP solely for missing data.
- Output must be reproducible: same payload + same `scoring_version` → same score.

## Output format
```
VET <run_id> | scored 14 | APPLY 3 | REVIEW 4 | SKIP 7 | queued 0 | connects 94
APPLY  88  ~01…  "Claude Implementation Expert"          claude-implementation  fixed $1,200 Sprint   reasons: title_strong_match, claude_named, spend_high, avg_paid_low→fixed
APPLY  81  ~01…  "n8n expert: Typeform→HubSpot→Slack"     n8n-automation         fixed $800 in-budget  reasons: …
REVIEW 63  ~01…  …
SKIP   D6  ~01…  "Build me an app like ChatGPT"           unverified + $0 + 0 hires
```
