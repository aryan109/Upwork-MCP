---
name: past-client-reactivation
description: Prepare and track Aryan's past-client reactivation campaign on Upwork: build the segmented client list from contracts, personalise the S1–S5 message templates with the actual system/contract names, schedule sends and one follow-up, log replies and outcomes in the tracker, and recommend the right offer (milestone, Sprint, Audit, Care Plan). Aryan sends every message in the Upwork UI; this skill never sends.
---

# past-client-reactivation

## Purpose
Zero-Connects pipeline from warm clients in Week 1–2. Playbook: `05_PAST_CLIENT_REACTIVATION.md` (authoritative). Tracker: `templates/reactivation_tracker.csv`.

## Procedure
1. **Build the list:** `list_contracts` (all statuses) via MCP `[VERIFY LIVE: fields returned]`; Aryan completes from the Contracts page: client first name, contract title, dates, value, type, rating, room link. Segment: S1 repeat enterprise client; S2 idle open contracts (5 known: Finetune GPT-3 $590 · Scraping and warehousing $1,175 · AI chat-bot $900 · AI Solutions Designer $175 · Web App Scraper Phase 1 $120); S3 completed 5.0 clients in the last 24 months; S4 older/sub-5; S5 the 2026-08-31 invitation.
2. **Personalise:** for each S1–S3 client fill the template with `{{FIRST_NAME}}`, `{{SYSTEM/CONTRACT_TITLE}}`, `{{MONTH YEAR}}`, and one specific idea (S3) derived from the original contract. ≤ 110 words, no links, no "any work?", no mention of automation of Upwork. Present each message for Aryan's edit.
3. **Schedule:** Day 1 S5; Day 2 S1; Day 2–3 S2; Day 4–5 S3 (≤ 4/day); Day 8–10 one follow-up to non-responders with a new piece of value; stop at Day 14.
4. **Track:** after Aryan confirms a send, write `msg1_sent_at`, `msg1_template`; on reply, `reply_at`, `reply_summary`; set `outcome` from the enum (`no_reply`, `declined`, `call_booked`, `milestone`, `new_contract`, `care_plan`), `value_won`.
5. **Recommend the offer** per reply: idle system in production → new milestone or Care Plan Keep-alive; "not sure what's possible" → Audit Focused $750 (credited); "we want Claude for the team" → Sprint Standard $599; substantial scope (> $1,000) → ask for a new contract so it counts as a new job and review `[VERIFY LIVE: JSS treatment of milestones vs new contracts]`.
6. **Report** on Day 7 and Day 14: messaged / replied / calls / milestones / value; feed into Gate G1.

## Guardrails
- Never send; never bulk; never promise outcomes; never offer discounts beyond the Audit credit.
- Do not propose closing idle open contracts (JSS risk, no benefit).
- Skip S4 sub-5 clients unless Aryan explicitly opts in; the 3.8 WordPress client gets the "lessons learned" note only on Aryan's call.
- Client names and details stay in the tracker outside the repo.

## Output
```
REACTIVATION Day 5 | messaged 11/12 (S1 1, S2 5, S3 5) | replied 3 | calls 1 | milestones 0 | follow-ups due Day 9: 8
Reply: {{FIRST_NAME}} (S2, chatbot 2023) — "still running, wants logging + Claude upgrade" → recommend milestone $600–$900 in existing contract; draft reply attached
```
