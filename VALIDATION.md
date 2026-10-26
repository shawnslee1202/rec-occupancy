# Validation - October 26, 2026

- GitHub repository created and collector deployed. First manual run and three scheduled runs succeeded.
- Scheduled runs observed at October 25 20:39, October 26 02:01 and October 26 09:09 Central. This is not ten-minute coverage; the requested schedule is delayed. No missing observations were fabricated.
- Local and hosted captures merged without replacing remote data: 219 distinct observations across 71 zones at initial October 26 verification.
- Twelve automated tests pass, including out-of-order seed replay, nonfinite values and refusal to use future weather forecast vintages.
- Snapshot age uses the latest poll, including unchanged staff timestamps. Closed flags come from the current sighting.
- Hours refresh replaces future intervals atomically, clearing obsolete schedules when dates become closed or uncertain.
- Forecast targets do not jump over invalid raw observations; training labels must be available before the holdout cutoff.
- Weather fetch and published-hours refresh were live-tested; six-hour analysis and Pages publication are part of deployment.
- The October 22 initial PDF is retained as a historical artifact. progress-report.pdf is regenerated from current data.
- Synthetic test fixtures never enter live archives. Forecast accuracy, bottleneck claims and January decay remain unmeasured.
