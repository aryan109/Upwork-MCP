# Human-in-the-Loop Contract

What the agent may do alone, what needs Aryan's word, and what Aryan does himself. This applies to every skill and runbook in this package.

| Action | Agent alone | Agent after Aryan says so | Aryan only (UI) |
|---|---|---|---|
| Search/read jobs, profiles, proposals, contracts, dashboard, messages | ✓ | | |
| Score jobs, write drafts, compute metrics, write state/logs | ✓ | | |
| Create proposal preview (`manage_proposals create`) | | ✓ `submit` | |
| Confirm proposal (`confirm_preview`) | | ✓ second `confirm` after seeing the preview | |
| Boost a proposal (≤ 10 Connects, score ≥ 80) | | ✓ shown in preview | |
| Accept / decline invitation | | ✓ per invitation | |
| Send a client message | | | ✓ (agent drafts) |
| Accept an offer (`finalize_url`), sign contracts, milestones | | | ✓ |
| Buy Connects, Freelancer Plus, badge, Profile Boost | | | ✓ |
| Edit profile, title, rate, catalog, portfolio | | | ✓ (agent drafts text) |
| Change campaigns/scoring | | ✓ via `upwork-campaign-editor` with `apply` | |
| Set kill switch | ✓ (on incident rules) | ✓ clear only on Aryan's word | |
| Withdraw a proposal | | ✓ | |
| Delete state records | never | never | never (mark instead) |

Explicit words the agent listens for: `submit`, `submit with edits:`, `confirm`, `cancel`, `skip:`, `hold`, `manual`, `apply`, `clear kill switch`, `accept invitation`, `decline invitation`, `withdraw`.

Anything ambiguous is treated as "no".
