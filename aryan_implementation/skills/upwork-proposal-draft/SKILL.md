---
name: upwork-proposal-draft
description: Draft an Upwork cover letter, screening-question answers and proposed terms for a vetted job on Aryan's behalf, using only verified facts from aryan-profile-facts, the offer ladder pricing rules, proof-matching and a 12-point self-check. Use when a job has decision APPLY (or REVIEW with a free slot) and needs a draft for human review. Never submits.
---

# upwork-proposal-draft

## Purpose
Produce one review-ready draft per job: `cover_letter`, `answers[]`, `proposed_terms`, `proof_used[]`, `risk_stated`, `word_count`, `self_check`. The master prompt, structure, forbidden list and five worked examples live in `07_PROPOSAL_SYSTEM.md` (authoritative).

## Inputs
- Job record (`jobs.json`) with detail payload, `score`, `reasons`, `rung_suggested`, `pricing_hint`.
- `skills/aryan-profile-facts/SKILL.md` (facts + proof inventory + never-claim list). If the inventory still contains `{{}}`, stop and tell Aryan which items are missing.
- `04_OFFER_LADDER_AND_PRICING.md` §3 pricing rules.

## Procedure
1. **Explicit asks:** scan description and `screening_questions` for required words, questions, portfolio requests, availability. List them; each must be answered.
2. **Proof match:** choose ≤ 2 proof items whose `type` is closest to the job cluster. If none ≥ adjacent, plan an honest "closest thing I've built" sentence. Never cite `permission=internal` items as client results; label as "a system I run for my own company".
3. **Risk statement:** identify the one real risk/limit for this job (approval steps, bot-protected sources, OCR, vendor connector gaps, data residency, scope creep) and write it plainly.
4. **Terms:** apply 04 §3. Fixed: in budget; ≥ $1,200 → milestone table (3 lines). Hourly: $65 sticker, or client ceiling if ≥ $45 and score ≥ 80; add fixed alternative for ≤ 10 h/week. Never exceed the stated budget without a Phase-1 split explanation. Never propose > 25 Connects (incl. boost) on a sub-$500 job.
5. **Write the letter** in the fixed order: explicit-asks block (if any) → mirror line → outcome + rung → 3–5 "What I'd do" bullets (≥ 1 proof, ≥ 1 risk, ≤ 25 words each, none starting with "I") → price & timeline → one easy next step + offer of a recorded walkthrough → "Aryan".
6. **Answers:** one per screening question, ≤ 60 words, direct answer first, proof/caveat second. Never invent.
7. **Self-check (12 points, 07 §8):** compute each as true/false. Any false → revise once; still false → mark `needs_edit` with the failing items.
8. **Word count:** 120–220; ≤ 270 only with Q&A or an explicit "detailed" ask.
9. **Write** `draft` object to the job record, `status="drafted"`, `draft_version` incremented; log `draft` event.

## Hard rules
- Only facts in `aryan-profile-facts`. No client names from past contracts unless `permission=named`.
- No URLs, emails, em dashes, emojis, "8+ years", "guarantee", "100%", compliance claims, "expert", "excited", "fully automated" without a human-approval qualifier, "OpenClaw" (unless the post uses it), any mention of Upwork automation or this engine.
- Two openers only: mirror-the-situation (default) or explicit-ask-first.
- One risk statement per letter is mandatory.

## Output (per job, to the review queue)
```
DRAFT ~01…  score 88  claude-implementation  rung: Sprint Team  terms: fixed $1,200 (5 days)  connects 16 (+0 boost)
Explicit asks: ["start with the word 'Pineapple'", "share a similar project"]  → answered: yes
Proof used: [P2 agent-mcp-engine (internal), P1 chatbot-2023 (anonymised)]
Risk stated: "HubSpot write-backs stay behind approval for month one"
Words: 191   Self-check: 12/12
--- cover letter ---
<text>
--- answers ---
Q1: …
```
