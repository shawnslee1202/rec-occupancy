import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile
import unittest
import pandas as pd
from datetime import date
from poll_rec_counts import connect,ingest,utc_stamp,validate
from analyze import level_profile,constraint_bounds,forecast_room
from refresh_hours import parse
from control import imr

def row(lid=1,count=20,time='2026-10-22T15:00:00',closed=False):
    return dict(LocationId=lid,LocationName='Strength',FacilityId=1,FacilityName='Test',
        LastCount=count,TotalCapacity=100,LastUpdatedDateAndTime=time,IsClosed=closed,
        MinCapacityRange=60,MaxCapacityRange=90)

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def test_dedup_and_revision(self):
        self.assertEqual(ingest([row()], '2026-10-22T20:10:00+00:00',self.root),1)
        self.assertEqual(ingest([row(count=25)], '2026-10-22T20:20:00+00:00',self.root),0)
        db=connect(self.root)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM sightings').fetchone()[0],2)
        self.assertEqual(db.execute('SELECT has_revision FROM quality_counts').fetchone()[0],1)
        db.close()
    def test_reset_subseconds_and_mixed_group(self):
        ingest([row(i,0,f'2026-10-22T12:40:00.{i:03d}') for i in range(10)],'2026-10-22T18:00:00+00:00',self.root)
        db=connect(self.root)
        self.assertEqual(db.execute('SELECT SUM(is_reset) FROM quality_counts').fetchone()[0],10)
        db.close()
    def test_out_of_order_replay(self):
        ingest([row()], '2026-10-22T20:20:00+00:00',self.root)
        ingest([row()], '2026-10-22T20:10:00+00:00',self.root)
        db=connect(self.root)
        self.assertEqual(db.execute('SELECT polled_at_utc FROM counts').fetchone()[0],'2026-10-22T20:10:00+00:00')
        db.close()
    def test_weather_never_uses_future_vintage(self):
        from weather import setup,features
        db=connect(self.root); setup(db)
        db.execute("INSERT INTO weather_forecasts VALUES ('2026-10-22T20:10:00+00:00','2026-10-22T21:00:00+00:00',25,0)")
        self.assertTrue(features(['2026-10-22T20:05:00+00:00'],db).temperature_c.isna().all())
        self.assertEqual(features(['2026-10-22T20:15:00+00:00'],db).temperature_c.iloc[0],25)
        db.close()
    def test_nonfinite_feed(self):
        with self.assertRaises(ValueError): validate([row(count=float('nan'))])
    def test_timezone(self):
        self.assertIn('20:00:00',utc_stamp('2026-10-22T15:00:00')[0])
        self.assertIsNone(utc_stamp('2026-11-01T01:30:00')[0])
        self.assertIsNone(utc_stamp('2027-03-14T02:30:00')[0])
    def test_schema_and_closed(self):
        with self.assertRaises(ValueError): validate([])
        ingest([row(closed=True)],'2026-10-22T20:10:00+00:00',self.root)
        db=connect(self.root)
        db.execute("INSERT INTO open_intervals VALUES (1,'2026-10-22T11:00:00+00:00','2026-10-23T01:00:00+00:00','test','2026-10-22')")
        self.assertEqual(db.execute('SELECT COUNT(*) FROM clean_counts').fetchone()[0],0)
        db.close()
    def test_exposure_stops_at_closed_observation(self):
        ingest([row(count=95)],'2026-10-22T20:00:00+00:00',self.root)
        ingest([row(count=0,time='2026-10-22T15:30:00',closed=True)],'2026-10-22T21:00:00+00:00',self.root)
        db=connect(self.root)
        db.execute("INSERT INTO open_intervals VALUES (1,'2026-10-22T20:00:00+00:00','2026-10-22T21:00:00+00:00','test','2026-10-22')")
        result=constraint_bounds(db,pd.read_sql_query('SELECT * FROM quality_counts',db)).iloc[0]
        self.assertAlmostEqual(result.coverage,.5)
        self.assertAlmostEqual(result.above_max_lower,.5)
        self.assertAlmostEqual(result.above_max_upper,1)
        db.close()
    def test_leveling_conserves_volume(self):
        profile=pd.Series({14:20.,15:30.,17:80.,18:100.})
        shifted=level_profile(profile,.25)
        self.assertAlmostEqual(shifted.sum(),profile.sum())
        self.assertEqual(shifted.loc[18],75)
        with self.assertRaises(ValueError): level_profile(profile,1.5)
    def test_hours_year_rollover(self):
        text='<div class="lw_events_day"><h4 class="lw_events_header_date">Friday, Jan 1:</h4><span class="lw_events_time">6:00am<span> - </span>11:00pm</span><div class="lw_events_summary"></div></div>'
        self.assertTrue(parse(text,date(2026,12,30))[0][0].startswith('2027-01-01'))
    def test_imr_minimum_and_gaps(self):
        with self.assertRaises(ValueError): imr(pd.Series([.2,.3],index=pd.date_range('2026-10-22',periods=2)),'2026-10-22','2026-11-01')
        s=pd.Series([.2,.3,.25]*10,index=pd.date_range('2026-10-22',periods=30))
        result=imr(s,'2026-10-22','2026-11-11')
        self.assertTrue((result.ucl>result.center).all())
    def test_forecast_common_support(self):
        # Synthetic fixture exists only in memory, never mixed with live data.
        times=pd.date_range('2026-08-24',periods=24*56,freq='h',tz='UTC')
        g=pd.DataFrame({'last_updated_utc':times.astype(str),'polled_at_utc':(times+pd.Timedelta(minutes=5)).astype(str),
            'last_count':[30+(i%24) for i in range(len(times))],'capacity':100,'age_min':5})
        metrics,pred,reason=forecast_room(g)
        self.assertIsNone(reason)
        self.assertEqual(metrics.n.nunique(),1)
        self.assertTrue((pd.to_datetime(pred.origin,utc=True)<pd.to_datetime(pred.target_t,utc=True)).all())
        self.assertAlmostEqual(metrics.loc[metrics.model=='same_hour_last_week','mae_people'].iloc[0],0)

if __name__=='__main__': unittest.main()
