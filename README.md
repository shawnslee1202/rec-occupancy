# Rec center occupancy: deployed collection and reproducible analysis

The first live capture on **October 22, 2026 at 6:31:59 pm Central** saved 71 zone records. At that capture, the reported weight-room counts were SRC 170/400 (42.5%), Southside 78/300 (26.0%), and Polo Road 57/250 (22.8%). These are asynchronous staff readings, aged approximately 23, 35, and 59 minutes respectively. **They do not establish a peak or bottleneck.**

## Current delivery status

- Implemented and live-tested: public-feed poller, append-only raw JSONL, SQLite, SQL cleaning views, replay, first capture, published-hours import for the three weight rooms.
- Implemented: hourly profiles, exposure bounds, last-value and weekly baselines, ridge model with calendar and lag features, chronological evaluation, I-MR calculation with explicit Phase I selection, January decay fit, occupancy-leveling sensitivity, offline HTML dashboard and CSV exports, automated tests.
- Included: GitHub Actions workflows, analysis notebook, initial two-page report, deployment instructions and honest resume wording.
- **Deployed:** https://github.com/shawnslee1202/rec-occupancy. One manual and three scheduled collection runs were verified on October 26. The requested ten-minute schedule has produced multi-hour gaps; inspect reports/polls.csv and status.json before assuming continuous coverage.
- **Dashboard:** https://shawnslee1202.github.io/rec-occupancy/ (published by the analysis workflow).
- **Data pending:** weeks of historical observations, Thanksgiving/finals observations, January-February data, and validated operating hours for the other zones.
- **Implemented extensions:** sourced home-game dates, archived Open-Meteo forecast vintages, forecast availability checks, current snapshot age, stale-report banner, polling-gap diagnostics, seed recovery and CI.
- **Still requires evidence:** normal-period selection for control limits and semester shifts after January. The delivered dashboard is portable HTML; a native Power BI/Tableau workbook is not included. Gradient boosting is deferred until ridge has enough data to evaluate.

## Run

Use Python 3.12 or later, from this directory:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
python poll_rec_counts.py
python refresh_hours.py
python weather.py
python analyze.py
python build_dashboard.py
python -m unittest discover -s tests -v
```

Open `reports/dashboard.html`. It includes all zones, a searchable table, preliminary heatmaps, and forecast/control-chart panels that remain explicitly pending until data exists. Charts are embedded; no external JavaScript or CDN is required. It is regenerated, not a continuously updating display.

Rebuild a fresh database from archives with `python poll_rec_counts.py --replay raw/YYYY-MM-DD.jsonl --root /path/to/rebuilt`. Replay each file in chronological order. Import the corresponding hours afterward. The poller only needs Python and `tzdata`; analytical dependencies are separate.

## Deployment and operations

1. The public repository above is created. Source, seed archives and workflows are versioned. Hosted raw data and SQLite are maintained by collection; do not overwrite them with an older local copy.
2. Allow GitHub Actions read/write repository contents. Review billing/minute limits for the chosen account and repository. Protect the data workflow from untrusted pull requests; it is not a `pull_request_target` workflow.
3. Manually run **Collect occupancy**. Confirm a new successful poll in SQLite, a new JSONL line, and a committed archive. Then confirm **two scheduled runs**. A configured cron alone is not proof of operation.
4. Manually run **Refresh hours and analysis**. The analysis job runs every six hours and shares the writer concurrency group with collection.
5. Check Actions weekly and inspect `polls.status`, gaps between captures, number of zones, raw-file growth and hours coverage. Schedules can be delayed or disabled; do not interpret scheduling as an availability guarantee. Failed pushes preserve recovery artifacts for 30 days.

The collection workflow requests every ten minutes at minute offsets 7,17,27,37,47,57. One commit per poll is simple but grows Git history; move raw archives to durable object storage and keep a compact analytical export if this becomes burdensome. Never rewrite archived history to make the dataset appear complete.

## Storage and data quality

`raw/`: complete response body and UTC fetch time for each successful HTTP response, archived before schema validation. `polls`: successful and failed poll attempts. `counts`: first-seen observation keyed by location and staff timestamp. `sightings`: poll-level state, preserving closed-flag changes and same-timestamp count/capacity revisions. Revised observations are excluded from analysis pending resolution; they are not silently overwritten.

`quality_counts` flags batches with at least ten distinct zones in a facility at the same timestamp second and all zero counts. This is the brief's conservative reset heuristic; partial resets may be missed, and true coincident zeros may be flagged. Raw archives allow the rule to be revised.

SQLite does not natively understand IANA daylight-saving rules. Conversion therefore happens **once during ingestion** with `zoneinfo`, preserving the original local timestamp. SQL calculates age and utilization from the normalized UTC value. Ambiguous fall-back and nonexistent spring-forward local times are quarantined, rather than assigned an arbitrary UTC instant. This is an intentional implementation change from the brief's proposed view-only conversion.

Staff count timestamps can be old even on the first capture. The first capture's median age across all zones is about 352 minutes; some records are many days old. This distribution includes closed and inactive zones and must not be generalized to weight-room measurement cadence. Nonpositive capacities, negative counts, closed flags, reset candidates, revisions and materially future timestamps are excluded from utilization. Values above capacity are retained and should be investigated, not clipped away.

Published hours come from the LiveWhale widgets embedded in the official Rec Sports hours page. `refresh_hours.py` archives each response and maps only SRC, Southside and Polo Road building schedules to their strength rooms. Explicit special-event summaries are skipped for manual review. It preserves the published 11:59 pm end literally. No hours are invented for other zones. Recheck room-specific closures; building hours are only an upper bound if a room has a separate closure. Additional zone schedules go into `config/open_intervals.csv` with sources and verification timestamps, then `python import_hours.py config/open_intervals.csv`.

## Analytical interpretation

**Profiles:** one mean per observed hour first, then equal-weighted hourly means across dates. CSVs retain counts of hours and readings. No interpolation across gaps. Current bins are preliminary; require four weeks and inspect cell-level coverage before calling an hour a recurring peak. To compare slack across rooms, use matching weekday/hour cells and disclose that asynchronous counts are not a simultaneous headcount.

**Constraints:** carry each observation forward only until the next observation of any quality or 90 minutes, whichever comes first. Intersect with verified opening intervals and the collection window. Excluded observations terminate carry-forward. Report covered versus scheduled hours and lower/upper shares above each record's thresholds; all unknown minutes can be below or above the threshold. Compare 60/90/120-minute sensitivity windows. Rank only comparable high-coverage periods; overlapping uncertainty bounds do not identify a unique system bottleneck. Staff `IsClosed` signals remain in the data, but do not establish a historical operating schedule alone.

**Forecast:** origin is the first poll when the current reading became available; target is the next recorded reading. Evaluate only target horizons 30-120 minutes after origin and disclose their distribution. Features use nominal origin+1-hour time, never the future actual reading timestamp. Training labels must already be available before the holdout cutoff. The final 14 days are held out after at least 42 days of eligible pairs; weekly baseline, last-value and ridge are evaluated on the same seasonal-baseline-supported rows. Report common-support coverage. Weather uses the latest archived forecast vintage available at each origin, never realized weather fetched later. Missing weather is explicitly indicated. Home-game flags are unknown before their verification timestamp. Ridge regularization is fixed in advance; future tuning must use earlier rolling folds, never the final holdout. The evaluation tests next observed reading, not a guaranteed clock-hour forecast. Never claim it beats both baselines unless the measured results do.

**I-MR:** after reviewing the first three normal weeks and coverage, run `python control.py --phase-start YYYY-MM-DD --phase-end YYYY-MM-DD`. Require 21 accepted Phase I days; moving ranges use consecutive calendar days only. Default daily inclusion is at least ten observed hourly bins; inspect scheduled-hour coverage manually and choose a defensible threshold. Limits use I = mean +/- 2.66 MR-bar and MR UCL = 3.267 MR-bar. Daily maxima depend on sampling frequency and weekday seasonality; investigate signals before claiming process changes. January return is January 19, 2027 in the academic calendar. Decay uses a fixed Phase I baseline and at least 28 return-period days; inspect residuals, weekday effects and baseline sensitivity before reporting the half-life.

**Leveling:** shifts a chosen fraction of average occupancy person-hours from [17:00,19:00) to [14:00,16:00), equally divided between the two receiving bins. Requires four observed days in every included profile bin, required donor/receiving bins and a constant room capacity. It conserves person-hours, not arrivals; no behavioral or causal claim is justified. Observed profile hours may not cover the entire opening day. A real arrival-shift model needs arrivals, departures and visit-duration distributions.

## Milestones

| Date / readiness | Deliverable |
|---|---|
| Now | Collection deployed; investigate observed multi-hour scheduling gaps |
| First week | Review gaps, resets, revisions and schedule coverage daily |
| Around November 19, 2026, if continuous data | First four-week profiles and cautious capacity comparison |
| Early December, after six eligible weeks | First baseline/ridge holdout comparison |
| After finals December 7-10 | Annotated control-chart review, if Phase I is defensible |
| Late February 2027 | January dynamics, decay diagnostics and final report |

## Sources

- Live feed authority: https://recsports.tamu.edu/facilities/live-facility-count/
- Published hours: https://recsports.tamu.edu/hours-of-operation/
- Hours widgets: https://calendar.tamu.edu/live/widget/574 (SRC), /575 (Southside), /576 (Polo Road)
- Fall calendar: https://registrar.tamu.edu/academic-calendar/fall-2026.html
- Spring calendar: https://registrar.tamu.edu/academic-calendar/spring-2027.html

Source retrieval: October 22-26, 2026. Archived calendar downloads are in `sources/`. Calendar events and game dates can change; verify before final analysis.

Weather: https://open-meteo.com/ (CC BY 4.0). Game schedule: https://12thman.com/sports/football/schedule/season/2026. Weather is sampled near the College Station campus (30.61, -96.34).
