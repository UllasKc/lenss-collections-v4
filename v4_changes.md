**LensS Collections v4: what changed and what's done**

v4 is a separate deployment of the same app, with a realistic, harder month. v3 is unchanged.

**The new story (as of 20 Oct 2026)**

| Metric | v3 (15 Sep) | v4 (20 Oct) |
|---|---|---|
| Achieved vs target | 90.2% at mid-month | **54.5%** with 65% of the month gone (₹41.2M of ₹75.7M) |
| Broken share of promises already due | 65% | **40%** (1,004 of 2,508) |
| Promises made | ₹168M | ₹88.3M (4,248 promises) |
| Expected from promises vs remaining gap | 5.2× | **0.62×** |
| Likelihood of hitting target | High | **Low** |
| Month-end outlook | 141% | 82.7% |
| Outlook if we act on chapters 4–5 | — | **~98%** (+₹11.6M) |

**What changed**

| Area | Change |
|---|---|
| Data | New October data pack from a seeded, reproducible generator. Same 11 sheets, 41 columns, IDs and dimension values. Every flag follows the business rules row by row |
| Problems built into the data | Personal Loan and Credit Card 31–60 behind target (42.3% / 48.2%); Kolkata hard to reach (31% right-party contact); Team F behind; Digital First over-contacting by SMS (6.6 attempts per customer); ₹26.3M promised in the next 7 days, ₹11.7M of it at risk |
| Hero tiles | Target · Achieved · Promises · Likelihood. The Low message now gives the way out ("acting on this week's priorities could add ₹11.6M, taking the outlook to 98% of target") |
| New certified view | `qry_cc_action_upside`: what acting on chapters 4–5 adds to the outlook. Also used by the executive summary and Genie |
| Observability | "i" info tips on every Gen-AI metric (groundedness, reconciliation, faithfulness, relevance, completeness, safety, latency, cache, tokens, evals): what it means and how it's computed |
| Dates | The as-of date is now one config setting, used by all SQL views and the app. No hard-coded dates |
| As-of cut-off | 20 Oct is "today": nothing in the data happens after it, and no promise falls due after 31 Oct (no November data) |
| Configs | Two configs: personal and org. v4 has its own schemas (`lenss_collections_v4_*`), Genie space, Lakebase database (`chatappv4`) and app |
| Docs | README and CHANGELOG (v4.0.0) updated |

**Status**

| Item | Status |
|---|---|
| Personal workspace | ✅ Live: data, views, Genie space, Lakebase and app `lenss-v4` |
| Figures checked | ✅ Command Center views, executive summary and app data all agree; Explorer reconciles with the hero |
| Free Edition app slot | ✅ Freed by removing the `lens-mlops` app, after confirming MLOps GitHub, local and Databricks were in sync. Its data, Genie space and database are kept |
| UI checked in a browser | ⏳ Pending |
| Org deployment (`lenss-collections-v4`) | ⏳ Waiting for go-ahead |
| GitHub repo `lenss-collections-v4` | ⏳ Remote not set yet; nothing pushed |
