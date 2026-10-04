# 04 — Offer Ladder & Pricing

The ladder is the commercial spine of the plan. Every proposal, catalog listing and past-client message sells **one rung** and names the next. Fixed price wherever the scope can be written down; hourly only for retainers and open-ended advisory.

## 1. The ladder at a glance

| Rung | Offer | Price | Duration | Buyer | Purpose in the funnel |
|---|---|---|---|---|---|
| L1 | **Paid consultation** (Upwork Consultations) | $75 / 30 min → $100 → $125 with the rate ladder `[VERIFY LIVE: allowed prices, fee]` | 30 min | Anyone evaluating | Lowest-friction paid first contact; turns "can we talk?" into a booked, paid call |
| L2 | **Claude / AI Workflow Setup Sprint** | $299 / $599 / $1,200 | 2–5 days | SMB teams with a Claude seat or intent to buy | Fast, low-risk first contract; creates a JSS-weighted job (≥$251 tier) and a review |
| L3 | **AI Operations & Automation Audit** | $750 / $1,500 | 3–5 days | Teams with an existing AI/automation estate; founders pre-launch | Diagnoses; produces the written quote for L4; high trust, low delivery risk |
| L4 | **Done-For-You Implementation** | $3,000–$7,500+ (3 milestones) | 2–4 weeks | L2/L3 graduates; direct for clients with $10K+ spend and clear scope | Main revenue rung; builds the case studies |
| L5 | **AI Operations Care Plan (retainer)** | $1,000 / $1,500 / $2,500 per month | monthly, 3-month minimum | L4 graduates | Predictable revenue; keeps profile active; source of referrals |
| — | **Hourly rate** (visible sticker) | $65 → $80 → $95 → $120+ | — | Hourly-only postings, retainers, advisory | Visibility and anchoring; not the main economics |

Not on the ladder (decided): DIY products/templates, OpenClaw-branded services, "enterprise architect" offers (Phase 6 only).

## 2. Rung definitions

### L1 — Paid consultation ($75 / 30 min)
- **Deliverable:** live call; within 24 h a 1-page written note: understanding of the problem, recommended approach, cost range, proposed first milestone.
- **Rule:** never free. If a buyer wants a "quick call" before hiring, point to the consultation or offer a 5-minute recorded Loom answer instead (free, asynchronous, scalable).
- **Upsell line:** "If we go ahead with a Sprint or Audit within 14 days, the $75 is credited."

### L2 — Setup Sprint ($299 / $599 / $1,200)
Full tier table, requirements and FAQ: `03_PROFILE_AND_STOREFRONT.md` §6.1.
- **Scope lock:** written list of Skills/connectors/users before funding; anything else is a change request at the Standard tier price.
- **Delivery checklist:** kickoff call recorded → Skills written and tested with buyer data → connector permissions documented → training recorded → handover PDF → ask for review on day of completion → log in `templates/` tracker.
- **Pricing floor:** $299 is the floor; never discount below. $599 is the default to propose. Push $1,200 when ≥3 users or ≥2 connectors are mentioned.
- **Upsell:** "Most teams book an Audit or an Implementation within a month of the Sprint; here is what I noticed we could do next: …" (two bullets, max).

### L3 — Audit ($750 / $1,500)
Full text: `03_PROFILE_AND_STOREFRONT.md` §6.2.
- **Credit rule:** 100% of the Audit fee is credited against an L4 Implementation signed within 30 days. This makes the Audit a no-brainer and anchors L4.
- **Deliverable discipline:** the report must include a cost-and-time roadmap table; the roadmap *is* the L4 proposal.
- **Where it wins:** jobs like "AI Operations Auditor: Assess Our Claude-Based Business OS" ($245K client, 2026-10-04) and any "fix/review our existing agents/automation" post.

### L4 — Implementation ($3,000–$7,500+)
| Band | Scope | Price | Milestones |
|---|---|---|---|
| Core | 1 system, 3 workflows/agents, 1–2 connectors, ≤5 users | $3,000–$4,000 | 30% architecture & acceptance criteria / 50% build & test / 20% rollout, training, docs |
| Standard | 2 systems, 3–5 workflows, up to 3 connectors, knowledge base (RAG), ≤15 users | $4,500–$6,000 | same split |
| Extended | multi-system, agents with approvals, custom API work, ≤30 users, 30-day hypercare | $6,500–$7,500+ | same split; hypercare as 4th milestone |

- **Milestone rule:** Milestone 1 (architecture + acceptance criteria) must be funded before any build; it is the "risks stated up front" artifact that fixes the 3.8-review pattern.
- **Scope changes:** written change request, priced from the band table; never absorbed silently.
- **Hourly equivalence check:** quote so that expected hours × $95 ≤ price (your internal target; $65 is the sticker, $95 is the real floor).
- **Phase-6 version:** $8K–$25K "AI Operating System" builds, only after 3 case studies and 2 completed L4s.

### L5 — Care Plan ($1,000 / $1,500 / $2,500 per month)
| Tier | Includes |
|---|---|
| Keep-alive $1,000 | monitoring + fixes, monthly health report, 2 h of changes, 48 h response |
| Improve $1,500 | the above + 5 h of improvements, monthly roadmap call, prompt/Skill tuning |
| Partner $2,500 | the above + 10 h, weekly check-in, new workflow per quarter, priority response |
- Sold as **hourly contract with weekly limit** or **recurring fixed milestone** `[VERIFY LIVE: Upwork's recurring-payment options]`; prefer fixed monthly milestones for cash predictability.
- 3-month minimum; cancel with 30 days' notice.

## 3. Pricing rules for proposals (used by the proposal system)

1. **Fixed-price post → bid in the client's budget band, never above the stated budget without saying why.** Reference incident: a $1,000 bid on a $600 post. If the real scope is larger, bid the budget for a defined Phase 1 and name Phase 2.
2. **Hourly post → bid at the sticker rate** ($65 now). If the client's ceiling is below the sticker, bid the ceiling only when it is ≥ $45/hr *and* the job is a strong proof-building opportunity (score ≥ 80 in `06_LEAD_SCORING_RUBRIC.md`); otherwise propose a fixed-price Sprint/Audit instead.
3. **Always offer a fixed alternative** on hourly posts ≤ 10 h/week: "or, as a fixed $599 Sprint if you prefer a known number."
4. **Never bid above $1,200 fixed without a milestone table** in the cover letter.
5. **Minimums:** no fixed job under $250 unless it is a deliberate JSS/review re-entry job in Week 1–3 (max 3 such jobs, each ≥ $100 and ≥ $65/hr equivalent).
6. **Connects discipline:** a proposal's Connects cost (16–20 typical) is part of the bid math: do not spend >25 Connects (incl. boost) on a job under $500.
7. **No "rate increase" field left at default** (reference incident); set the expected rate increase to "every 6 months" or leave blank, consciously.

## 4. Fixed-price economics (why this works at $65/hr sticker)

Assumptions `[ASSUMPTION — track and correct in 09]`: Sprint Standard $599 takes 6–8 h → $75–$100/hr effective. Audit Full $1,500 takes 12–15 h → $100–$125/hr. Implementation Standard $5,000 takes 45–55 h → $90–$110/hr. Care Plan Improve $1,500 for ≤8 h/month → $190/hr effective.

Upwork fee: 10% flat on earnings `[VERIFY LIVE]`. Payment release: 5 days after approval for fixed, ~10 days for hourly (observed). Net targets per month, by phase:

| Phase | Mix | Gross | Net (after 10%) |
|---|---|---|---|
| P2 (days 15–45) | 2 Sprints + 1 Audit + 2 consultations | ≈ $2,100 | ≈ $1,900 |
| P3 (days 45–75) | 2 Sprints + 2 Audits + 1 Core Implementation | ≈ $6,700 | ≈ $6,000 |
| P4 (days 75–120) | 1 Sprint + 1 Audit + 1 Standard Implementation + 1 Care Plan | ≈ $9,000 | ≈ $8,100 |

These are planning targets, not forecasts.

## 5. Ladder transitions (scripts)

- **Consultation → Sprint/Audit:** the follow-up note ends: "Recommended next step: {{Sprint tier / Audit tier}} at ${{price}}, {{days}} days; your consultation fee is credited."
- **Sprint → Audit/Implementation:** in the handover doc, a one-page "What I'd do next" with 2–3 items, each with price band and effect.
- **Audit → Implementation:** the roadmap table *is* the quote; send the L4 proposal as a new fixed-price contract with 3 milestones within 48 h of the readout.
- **Implementation → Care Plan:** offered in Milestone 3's rollout meeting; first month at the Keep-alive tier is proposed by default.
- **Any rung → referral:** at review time, ask: "Who else in your network has a process like this?" (one line, in the completion message).

## 6. Objection handling (short)

| Objection | Response |
|---|---|
| "Your rate is $65 but your history shows $3–30/hr." | "Earlier contracts were small scoped tasks priced accordingly. These packages are fixed-price so you pay for an outcome, not hours." |
| "Can we start hourly to test?" | Yes: a 5-hour capped first week at the sticker rate, with a written goal. Or the $299 Sprint. |
| "Another freelancer quoted $35/hr." | "Happy to send the Audit so you can compare plans, not rates. The report is yours either way." |
| "Do you guarantee results?" | "I guarantee scope, acceptance criteria and that risks are written down before you fund a milestone. Outcomes depend on inputs we agree on day 1." (never promise outcomes) |
| "Can you do it cheaper if we skip the docs/training?" | No. Docs and training are what make the handover safe; they are not optional. |

## 7. Rate ladder gates

| Step | Sticker | Gate (all must be true) | Owner |
|---|---|---|---|
| 0 | $65 | Day 1 of P1 | Aryan |
| 1 | $80 | 3 completed contracts at $65+ with ≥4.8 feedback **and** 2 case studies published **and** JSS still 100% `[VERIFY LIVE]` | Aryan (decision gate G3 in `02_MASTER_IMPLEMENTATION_PLAN.md`) |
| 2 | $95 | 3 more completed contracts, 1 Care Plan active, 3 case studies, demo video live | Aryan (G4) |
| 3 | $120+ | Phase 6 criteria (`10_PREMIUM_ASCENT.md`) | Aryan (G6) |

Rate changes apply to new proposals only; consultation price moves in lockstep ($75 → $100 → $125 → $150).
