# Power BI / Tableau handoff

The delivered dashboard is portable HTML. A native PBIX or Tableau workbook is not included.

Import reports CSVs as data tables. Join on `location_id`; use a distinct zone dimension from `latest_counts.csv`. Preserve `hour_bin` as America/Chicago local time and poll/timestamp UTC columns as UTC. Do not join raw polls to observations and then sum counts: this multiplies readings.

Recommended pages:

1. Current snapshot: latest count, capacity, reported ratio, staff update timestamp, capture timestamp, age and closed/reset flags. Label stale values explicitly.
2. Profiles: weekday x hour matrix from profiles.csv; conditional color on mean_utilization; tooltip n_hours and n_readings.
3. Constraints: coverage and lower/upper threshold shares from constraint_bounds.csv. Filter comparable dates and adequate coverage before ranking.
4. Forecast: actual, last-value, weekly and ridge series from forecast_predictions_ID.csv; separate MAE cards from forecast_metrics_ID.csv. Do not average room MAEs without stating the weighting.
5. Control chart: plot daily peak and limits from control_ID.csv; annotate the sourced calendar events. Pending files mean insufficient data, not zero.

Disable automatic summation of utilization ratios and capacity fields. Ratios are not additive across time. Use a freshness banner showing the latest successful `polls` timestamp, and visibly distinguish report refresh from staff count updates.
