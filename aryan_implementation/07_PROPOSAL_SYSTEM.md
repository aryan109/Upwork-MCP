# 07 — Proposal System

Goal: 3–5 excellent proposals per working day, each one specific to the post, truthful, priced by the ladder, and **submitted only after Aryan reads it**. The agent drafts; Aryan reviews and clicks (or tells the agent to submit via `confirm_preview`). This file is the master prompt, the structure rules, and five complete example proposals.

## 1. Master drafting prompt (paste into the drafting agent; Skills version in `skills/upwork-proposal-draft/SKILL.md`)

```
You are drafting an Upwork cover letter on behalf of Aryan, an AI automation and Claude implementation freelancer (Top Rated, 100% JSS, 35 contracts). Facts about Aryan are in the aryan-profile-facts skill; use ONLY those facts. Never invent clients, numbers, certifications, years of experience, or tools.

Inputs: the full job payload (title, description, budget, screening_questions, client_record, preferred_qualifications), the lead score + reason list, and the proof inventory.

Write a cover letter that:
1. Opens with ONE sentence that proves you read the post: restate the client's situation or desired outcome in their words (no greeting, no "I am excited", no name of the client unless it is in the post).
2. Second sentence: the outcome Aryan will deliver, in business terms, and the rung of the ladder that fits (Sprint / Audit / Implementation / hourly).
3. "What I'd do" — 3 to 5 bullets, each a concrete step or component for THIS job. At least one bullet carries proof (a matching past build from the inventory, named by type not by client unless permitted). At least one bullet names a risk or a limit honestly ("X will need a human approval step because…").
4. "Price & timeline" — one or two lines applying the pricing rules; fixed price with milestones when possible; stay inside the client's budget or explain the Phase 1 split.
5. If the post explicitly asks for anything (portfolio, specific question, a word, availability), answer it in a short labelled block BEFORE the bullets.
6. Close with one question or one next step that is easy to say yes to; offer a recorded walkthrough; sign "Aryan".

Rules: 120–220 words (max 270 when there are screening questions or an explicit "detailed proposal" ask); plain English; no URLs, no email, no em dashes; no adjectives about yourself ("expert", "passionate", "seasoned"); no "I have 8+ years"; no claims of compliance certifications; no promises of outcomes ("will double your sales"); never mention automation of Upwork or this pipeline; never mention OpenClaw unless the post does. Write in first person singular. Use the client's nouns (their tool names, team names, document names).

Screening questions: answer each in ≤ 60 words in the `answers` field, not in the cover letter; the cover letter may reference "see answers".

Output JSON: { "cover_letter": "...", "answers": [...], "proposed_terms": { "type": "fixed|hourly", "amount": ..., "milestones": [...] }, "proof_used": [...], "risk_stated": "...", "word_count": n, "self_check": { ...the 12-point checklist below with true/false... } }
```

## 2. Structure (fixed order)

| # | Block | Length | Purpose |
|---|---|---|---|
| 0 | Explicit-asks block (only if the post asks) | ≤ 40 words | Pass the client's filter immediately (keyword, question, portfolio) |
| 1 | Mirror line | 1 sentence | Prove the letter is not a template |
| 2 | Outcome + rung | 1 sentence | What they get, how it is packaged |
| 3 | "What I'd do" | 3–5 bullets | Specific plan, ≥1 proof bullet, ≥1 risk bullet |
| 4 | Price & timeline | 1–2 lines | Ladder pricing, milestones |
| 5 | Close | 1–2 sentences + "Aryan" | One easy next step, offer a recorded walkthrough |

## 3. Proof-matching

Proof inventory lives in `skills/aryan-profile-facts/SKILL.md` and must be filled by Aryan before launch. Each proof item has: `id`, `type` (chatbot / scraping-warehouse / fine-tune / plugin / agent-mcp-engine / n8n-workflow / audit / training), `one_line` (what it did, measurable if available), `permission` (named / anonymised / internal), `asset` (case study / video / repo / screenshot).

Matching rule: pick the proof whose `type` is closest to the job's A1 cluster; if none is closer than "adjacent", say so honestly ("I have not built X specifically; the closest is Y, which shares the Z part") rather than stretching. Never cite a proof whose `permission` is `internal` as a client result; cite it as "a system I run for my own company".

## 4. Length rules
- Default **120–220 words** (reference letters: 150–220; applied letters in the dataset averaged ~180).
- **≤ 270** when screening questions exist or the post says "detailed".
- Cover letter field limit 5,000 chars (MCP schema) — irrelevant; brevity is the constraint.
- Bullets ≤ 25 words each. No bullet starts with "I".

## 5. Forbidden phrases and patterns
"I am excited", "I am confident", "perfect fit", "expert in", "seasoned", "passionate", "Dear Hiring Manager", "Hi there!", "8+ years", "10+ years", "guarantee", "100%", "cutting-edge", "state-of-the-art", "leverage", "synergy", "ninja", "rockstar", "world-class", "as an AI", "I have read your job description carefully", "I can start immediately", "please check my portfolio" (link instead via attachments), any URL, any email, any phone, em dashes (—), emojis, lists of 10 technologies, "fully automated" without a human-approval qualifier, "OpenClaw", "Upwork MCP", "my automation pipeline", client names from other contracts without permission, "GxP/HIPAA compliant", "enterprise-grade", "zero downtime".

## 6. Screening question handling
- Answer in the `answers` field; one short paragraph each (≤ 60 words); first sentence is the direct answer; second is the proof or the caveat.
- If a question asks for something Aryan has not done: say so, then the nearest relevant thing (never invent).
- "What is your rate?" → ladder price with the fixed alternative. "Are you available for a call?" → yes, propose two IST-evening windows in the client's time zone. "Share examples" → name the case study titles that are on the profile; attach via `portfolio_project_ids`.

## 7. Pricing rules (from `04_OFFER_LADDER_AND_PRICING.md` §3)
Fixed: inside budget; ≥$1,200 needs milestones; Phase-1 split if under-budgeted. Hourly: sticker $65, or the ceiling if ≥$45 and score ≥80; always a fixed alternative on ≤10 h/week posts. Never above $25 Connects on a sub-$500 job. Never bid $1,000 on a $600 post.

## 8. Human review checklist (Aryan, before submit; also the agent's `self_check`)

1. [ ] First sentence is specific to this post (could not be pasted into another job).
2. [ ] The rung and the price match the budget and the ladder; milestones listed if ≥$1,200.
3. [ ] Every fact about Aryan is in `aryan-profile-facts`; every proof item exists and has `permission`.
4. [ ] At least one risk/limit is stated plainly.
5. [ ] Every explicit ask in the post is answered (keywords, questions, availability).
6. [ ] Screening questions answered in the `answers` field.
7. [ ] 120–220 words (≤270 with Q&A); no bullet > 25 words.
8. [ ] No forbidden phrases, URLs, em dashes, emojis.
9. [ ] Tone: plain, confident, no adjectives about self.
10. [ ] Connects cost and boost are acceptable for this job's value (≤25 on sub-$500).
11. [ ] No conflict: no open proposal/contract with this client; not applied before.
12. [ ] I would be comfortable if the client pasted this letter back to me in an interview.

If any box is unchecked → edit or reject; the agent logs the reason for calibration.

## 9. Five complete example proposals

Placeholders `{{PROOF_…}}` must be replaced with real inventory items; the sentences around them are final.

### 9.1 Claude integration — post: "Claude Implementation Expert: set up Claude for our 12-person marketing agency, connect Google Workspace and HubSpot, train the team" (hourly $30–45, client $430K spent, avg paid $5/hr)

```
You have twelve people who should be using Claude for client reporting and proposals, and today it is a few browser tabs and copy-paste.

I would set this up as a fixed-scope Setup Sprint rather than open hourly, so you know the number before we start.

What I'd do
• Connect Claude to Google Drive, Gmail and HubSpot through official connectors, with a permissions guide so account managers only see their clients.
• Write three Skills in your team's own words: monthly client report draft, proposal first draft from a HubSpot deal, and meeting notes to tasks.
• Test each Skill on two real accounts with your team lead, then record a 45-minute training and a written handover.
• One honest limit: HubSpot write-backs stay behind an approval step for the first month; silent CRM edits are where these setups go wrong.
• Closest past build: {{PROOF_CLAUDE_OR_CHATBOT: e.g. "an AI chatbot and data pipeline for a services client, 2023, still in use"}}.

Price and timeline: $1,200 fixed (Team tier, up to five seats, three connectors), five working days, two revision rounds, 14 days of support. Additional seats quoted after.

If useful, I will record a five-minute walkthrough of how the reporting Skill would work on one of your accounts before you decide.

Aryan
```
(190 words; proof bullet; risk bullet; pricing rule: avg paid $5/hr → fixed, not hourly.)

### 9.2 n8n automation — post: "n8n expert: connect Typeform → HubSpot → Slack → Gmail for inbound leads, with AI qualification" (fixed $800, 3 screening questions)

```
Answers to your three questions are in the Q&A section below.

Right now a Typeform lead waits until someone sees it; you want it scored, in HubSpot, and announced in Slack within a minute, with a first reply drafted.

I would build this in n8n with Claude doing the qualification, and hand it over documented so your ops lead can change the rules.

What I'd do
• n8n workflow: Typeform webhook → dedupe against HubSpot → Claude scores fit against your ICP rules → HubSpot contact + deal → Slack card with Approve/Edit buttons → Gmail draft.
• The reply is a draft, not a send, until you have watched it for two weeks; auto-sending to inbound leads is how trust gets burned.
• Error handling and a run log in a Google Sheet so a failed step is visible, not silent.
• Scoring rules live in one editable prompt file; you will not need me to change a threshold.
• Comparable: {{PROOF_N8N_OR_INTEGRATION: e.g. "a scraping-and-warehousing pipeline with scheduled runs and alerting, 2023"}}.

Price and timeline: $800 fixed, two milestones ($400 workflow live in test / $400 production + docs + 30-minute handover call), six working days from access.

Which HubSpot properties define a qualified lead for you today? That is the one thing I need before day one.

Aryan
```
Answers: Q1 (n8n cloud vs self-hosted?) "Either; I recommend n8n Cloud for a 4-node flow unless you already self-host. I document credentials and ownership so you are never locked to me." Q2 (experience with HubSpot API?) "Yes, contacts, deals and timeline events via the v3 API and the native n8n node; custom properties are mapped in a single config node." Q3 (timeline?) "Six working days from access; milestone 1 on day three."

### 9.3 AI agent build — post: "Build an AI research agent that monitors competitors, summarises weekly, posts to Notion" (fixed $2,500, client $14K spent)

```
You want a weekly competitor brief in Notion that someone actually reads, produced without a person spending Friday afternoon on it.

I would build an agent that collects, scores and drafts, with you approving the brief before it is published, delivered as a fixed implementation with three milestones.

What I'd do
• Sources: competitor sites, changelogs, LinkedIn pages and news via scheduled fetches; each item stored with source and timestamp so claims are traceable.
• Claude agent with a written brief template: what changed, why it matters to you, suggested response; ranked by your relevance rules.
• Notion database with a review view; the brief publishes only after a one-click approval, and every run logs inputs, decisions and errors.
• Limit to state up front: sites with aggressive bot protection need a licensed data source; I will list which ones on day two, not surprise you at the end.
• Closest past build: {{PROOF_AGENT_OR_SCRAPING: e.g. "scheduled scraping and warehousing system for a client, 2023" or "an agent system I run for my own company that discovers, scores and drafts with human approval"}}.

Price and timeline: $2,500 fixed; milestones $750 (architecture, sources, acceptance criteria), $1,250 (agent live on test data), $500 (rollout, docs, recorded walkthrough). Three weeks.

Would you share the last brief your team wrote by hand? Matching its shape is the fastest way to a useful first version.

Aryan
```

### 9.4 RAG / knowledge workflow — post: "Internal knowledge assistant over 2,000 SOP documents in SharePoint for a logistics company" (hourly $50–70, ongoing, 10–15 proposals)

```
Two thousand SOPs in SharePoint and the real answer is "ask Maria": you want staff to get the right procedure, with the source, in seconds.

I would start with a paid Audit of the document estate and access model, then quote the build with a fixed number.

What I'd do
• Audit (week one): document inventory, permission mapping (who may see what), five representative questions tested against a prototype retrieval setup, written findings and cost.
• Build: retrieval over SharePoint with permission-aware filtering, Claude answering with citations to the exact SOP section, and a "not found" path that routes to a person instead of guessing.
• Evaluation set of 50 real questions with expected answers; we track accuracy weekly, because a knowledge assistant without an eval set drifts quietly.
• Honest limit: scanned PDFs without text layers need OCR first; I will size that in the Audit.
• Comparable: {{PROOF_RAG_OR_CHATBOT: e.g. "AI chatbot over business documents, 2023" }}.

Price and timeline: Audit $1,500 fixed, five days, credited against the build. Build typically $4,500 to $6,000 fixed in three milestones, or at $65/hr if you prefer hourly with a weekly cap.

Could you grant read-only access to one SOP library for the Audit? That alone answers most of the open questions.

Aryan
```

### 9.5 Broken-workflow repair — post: "Our Zapier/Make + OpenAI automation keeps failing and double-posting; need someone to fix and stabilise it" (hourly $40–60, client avg paid $45, <5 proposals)

```
The automation worked in the demo and now it double-posts and dies on odd inputs, and nobody is sure which of the twelve Zaps is the culprit.

I would stabilise it in two steps: a short paid review to find every failure path, then fixes at a fixed price so you are not paying by the hour for debugging.

What I'd do
• Day one: read-only access to Make/Zapier run history and the OpenAI prompts; map every trigger, every retry and every place a duplicate can enter.
• Written findings within 48 hours: root causes, quick fixes, and what should be rebuilt versus patched.
• Fixes: idempotency keys so a retry can never double-post, structured error handling with a Slack alert, and a run log you can read.
• What I will not do: silently rewrite the whole thing in a different tool; if a rebuild is the right call you will see the case in writing first.
• Comparable: {{PROOF_REPAIR_OR_INTEGRATION: e.g. "plugin and integration fixes on existing client codebases, 2024"}}.

Price and timeline: Focused Audit $750 fixed (findings in three days), then fixes quoted per item, usually $600 to $1,500 total. Or hourly at $60 with a 10-hour first-week cap if you prefer.

Can you paste the error from the last failed run? I can usually tell from that whether it is a retry issue or an input issue.

Aryan
```

## 10. Letter variants and tone
- Only **two** openers are allowed: mirror-the-situation (default) or answer-the-explicit-ask-first. The reference project drifted into a third variant and a freeform letter; both were incidents.
- "Show, don't tell": a sentence about how you work beats a sentence about who you are.
- One risk statement per letter is mandatory (direct response to the 3.8 review that said risks should have been disclosed in the proposal).

## 11. After submit
- Log `proposal_id`, score, rung, price, word count, proof used, Connects spent in the state store.
- Set a follow-up reminder at 72 h: if `list_freelancer_proposals` → `get` shows `viewed` but no reply, one short follow-up message (≤ 50 words) with one new piece of value (a Loom or a diagram), then stop.
- Withdraw proposals older than 14 days with no view if Connects are refundable in that state `[VERIFY LIVE]`; otherwise leave them.
