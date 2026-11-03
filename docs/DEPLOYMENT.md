# Deployment evidence
Repository: https://github.com/shawnslee1202/rec-occupancy
First successful manual collection: https://github.com/shawnslee1202/rec-occupancy/actions/runs/40245330693
Verified scheduled collection: https://github.com/shawnslee1202/rec-occupancy/actions/runs/40337021969
Dashboard: https://shawnslee1202.github.io/rec-occupancy/

A configured ten-minute cron is not evidence of ten-minute collection. Initial hosted runs were separated by hours. Examine poll timestamps and quality coverage, and use an always-on host if these gaps persist.

## Collector operation

1. The public repository above is created. Source, seed archives and workflows are versioned. Hosted raw data and SQLite are maintained by collection; do not overwrite them with an older local copy.
2. Allow GitHub Actions read/write repository contents. Review billing/minute limits for the chosen account and repository. Protect the data workflow from untrusted pull requests; it is not a `pull_request_target` workflow.
3. Manually run **Collect occupancy**. Confirm a new successful poll in SQLite, a new JSONL line, and a committed archive. Then confirm **two scheduled runs**. A configured cron alone is not proof of operation.
4. Manually run **Refresh hours and analysis**. The analysis job runs every six hours and shares the writer concurrency group with collection.
5. Check Actions weekly and inspect `polls.status`, gaps between captures, number of zones, raw-file growth and hours coverage. Schedules can be delayed or disabled; do not interpret scheduling as an availability guarantee. Failed pushes preserve recovery artifacts for 30 days.

The collection workflow requests every ten minutes at minute offsets 7,17,27,37,47,57. One commit per poll is simple but grows Git history; move raw archives to durable object storage and keep a compact analytical export if this becomes burdensome. Never rewrite archived history to make the dataset appear complete.


| Date / readiness | Deliverable |
|---|---|
| Now | Collection deployed; investigate observed multi-hour scheduling gaps |
| First week | Review gaps, resets, revisions and schedule coverage daily |
| Around November 19, 2026, if continuous data | First four-week profiles and cautious capacity comparison |
| Early December, after six eligible weeks | First baseline/ridge holdout comparison |
| After finals December 7-10 | Annotated control-chart review, if Phase I is defensible |
| Late February 2027 | January dynamics, decay diagnostics and final report |

