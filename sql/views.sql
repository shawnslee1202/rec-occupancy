DROP VIEW IF EXISTS clean_counts;
DROP VIEW IF EXISTS quality_counts;
CREATE VIEW quality_counts AS
WITH resets AS (
 SELECT facility_id, substr(last_updated,1,19) second_stamp
 FROM counts GROUP BY facility_id, substr(last_updated,1,19)
 HAVING COUNT(DISTINCT location_id) >= 10 AND MIN(last_count)=0 AND MAX(last_count)=0
)
SELECT c.*,
 CASE WHEN r.facility_id IS NOT NULL THEN 1 ELSE 0 END is_reset,
 (julianday(polled_at_utc)-julianday(last_updated_utc))*1440 age_min,
 CASE WHEN capacity > 0 THEN last_count*1.0/capacity END utilization,
 CASE WHEN EXISTS (SELECT 1 FROM open_intervals o WHERE o.location_id=c.location_id
 AND julianday(c.last_updated_utc)>=julianday(o.opens_at_utc)
 AND julianday(c.last_updated_utc)<julianday(o.closes_at_utc)) THEN 1 ELSE 0 END verified_open,
 CASE WHEN EXISTS (SELECT 1 FROM sightings s WHERE s.location_id=c.location_id
 AND s.last_updated=c.last_updated AND (s.last_count<>c.last_count OR s.capacity<>c.capacity OR s.is_closed<>c.is_closed))
 THEN 1 ELSE 0 END has_revision
FROM counts c LEFT JOIN resets r ON c.facility_id=r.facility_id
 AND substr(c.last_updated,1,19)=r.second_stamp;

CREATE VIEW clean_counts AS
SELECT * FROM quality_counts WHERE is_reset=0 AND is_closed=0
 AND verified_open=1 AND capacity>0 AND last_count>=0 AND age_min>=-5
 AND time_issue IS NULL AND has_revision=0;
