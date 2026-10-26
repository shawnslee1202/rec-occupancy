"""Reproducible, readiness-gated analysis. No fabricated history or gap interpolation."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from poll_rec_counts import ROOT, connect

def hourly_bins(clean):
    if clean.empty:
        return pd.DataFrame()
    x=clean.copy()
    x['hour_bin']=pd.to_datetime(x.last_updated).dt.floor('h')
    h=x.groupby(['location_id','location','hour_bin'],as_index=False).agg(
        utilization=('utilization','mean'),people=('last_count','mean'),
        capacity=('capacity','last'),n_readings=('last_count','size'))
    h['weekday']=h.hour_bin.dt.dayofweek; h['hour']=h.hour_bin.dt.hour
    return h

def constraint_bounds(db, quality, max_age=90):
    """LOCF exposure, capped at freshness window and next ANY observation.
    Uncovered open minutes stay unknown. Return lower/upper exceedance bounds.
    """
    intervals=pd.read_sql_query('SELECT * FROM open_intervals',db)
    if intervals.empty or quality.empty:
        return pd.DataFrame()
    out=[]
    collection_start=pd.Timestamp(db.execute("SELECT MIN(polled_at_utc) FROM polls WHERE status='ok'").fetchone()[0])
    collection_end=pd.Timestamp(db.execute("SELECT MAX(polled_at_utc) FROM polls WHERE status='ok'").fetchone()[0])
    for lid, opening in intervals.groupby('location_id'):
        g=quality[quality.location_id==lid].copy()
        g['t']=pd.to_datetime(g.last_updated_utc,utc=True)
        g=g.dropna(subset=['t']).sort_values('t')
        g['next_t']=g.t.shift(-1)
        total=covered=mid=high=0.0
        for o in opening.itertuples():
            a=max(pd.Timestamp(o.opens_at_utc),collection_start)
            b=min(pd.Timestamp(o.closes_at_utc),collection_end)
            if b<=a: continue
            total+=(b-a).total_seconds()/60
            for r in g.itertuples():
                if r.is_reset or r.is_closed or r.has_revision or r.capacity<=0 or r.last_count<0 or r.age_min < -5: continue
                stop=min(r.t+pd.Timedelta(minutes=max_age),b)
                if not pd.isna(r.next_t): stop=min(stop,r.next_t)
                start=max(r.t,a)
                duration=max(0,(stop-start).total_seconds()/60)
                covered+=duration
                mid+=duration*(r.utilization>r.min_threshold/100)
                high+=duration*(r.utilization>r.max_threshold/100)
        if total:
            unknown=max(0,total-covered)
            out.append(dict(location_id=lid,location=g.location.iloc[-1] if len(g) else str(lid),
                scheduled_hours=total/60,covered_hours=covered/60,coverage=covered/total,
                above_min_hours=mid/60,above_max_hours=high/60,
                above_max_lower=high/total,above_max_upper=(high+unknown)/total,
                above_min_lower=mid/total,above_min_upper=(mid+unknown)/total))
    return pd.DataFrame(out)

def forecast_room(g, db=None):
    """Fixed model, 14-day holdout, common seasonal-baseline evaluation support."""
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.linear_model import Ridge
    g=g.sort_values('last_updated_utc').copy().reset_index(drop=True)
    g['t']=pd.to_datetime(g.last_updated_utc,utc=True)
    g['origin']=pd.to_datetime(g.polled_at_utc,utc=True)
    g['target_t']=g.t.shift(-1); g['target_available']=g.origin.shift(-1)
    g['target']=g.last_count.shift(-1)
    g['target_capacity']=g.capacity.shift(-1)
    if 'eligible' not in g: g['eligible']=True
    g['pair_eligible']=g.eligible & g.eligible.shift(-1,fill_value=False)
    g['horizon_min']=(g.target_t-g.origin).dt.total_seconds()/60
    expected=(g.origin+pd.Timedelta(hours=1)).dt.tz_convert('America/Chicago')
    g['slot']=(expected.dt.dayofweek*24+expected.dt.hour).astype(str)
    g['week']=(expected.dt.tz_localize(None)-pd.Timestamp('2026-08-24')).dt.days/7
    g['lag']=g.last_count
    features=['slot','week','lag','age_min']
    games=pd.read_csv(ROOT/'config/games.csv')
    known=pd.to_datetime(games.verified_at_utc,utc=True).max()
    game_dates=set(games.date)
    local_days=expected.dt.strftime('%Y-%m-%d')
    g['home_game']=[int(d in game_dates) for d in local_days]
    g['game_schedule_unknown']=(g.origin<known).astype(int)
    g.loc[g.game_schedule_unknown==1,'home_game']=0
    features+=['home_game','game_schedule_unknown']
    if db is not None:
        from weather import features as weather_features
        weather=weather_features(g.origin,db)
        for col in weather.columns:
            g[col+'_missing']=weather[col].isna().astype(int)
            g[col]=weather[col].fillna(0).to_numpy()
            features += [col,col+'_missing']
    events=pd.read_csv(ROOT/'config/events.csv')
    for e in events.itertuples():
        col='days_to_'+e.event
        g[col]=(pd.Timestamp(e.start_date)-expected.dt.tz_localize(None).dt.normalize()).dt.days
        features.append(col)
    # Weekly baseline uses the nominal forecast hour, not a future observed timestamp.
    # Pre-group observed bins once, rather than scanning every prior reading for each row.
    local_bins=g.t.dt.tz_convert('America/Chicago').dt.tz_localize(None).dt.floor('h')
    buckets={key:group for key,group in g.assign(bin=local_bins).groupby('bin')}
    weekly=[]
    for r in g.itertuples():
        nominal=(r.origin+pd.Timedelta(hours=1)).tz_convert('America/Chicago').tz_localize(None).floor('h')
        bucket=buckets.get(nominal-pd.Timedelta(days=7))
        if bucket is None:
            weekly.append(np.nan)
        else:
            vals=bucket.loc[(bucket.origin<=r.origin)&(bucket.t<r.t)&bucket.eligible,'last_count']
            weekly.append(vals.mean() if len(vals) else np.nan)
    g['weekly']=weekly
    valid=g[g.pair_eligible & (g.horizon_min>=30)&(g.horizon_min<=120)&g.target.notna()].copy()
    if valid.empty or (valid.origin.max()-valid.origin.min()).days<42:
        return None,None,'Need at least 42 days of eligible next-reading pairs'
    cutoff=valid.origin.max()-pd.Timedelta(days=14)
    train=valid[(valid.origin<cutoff)&(valid.target_available<cutoff)]
    test=valid[valid.origin>=cutoff].dropna(subset=['weekly'])
    if len(train)<100 or len(test)<30:
        return None,None,'Need 100 training pairs and 30 common-support holdout pairs'
    transform=ColumnTransformer([('slot',OneHotEncoder(handle_unknown='ignore'),['slot']),
        ('numeric',StandardScaler(),[f for f in features if f!='slot'])])
    model=make_pipeline(transform,Ridge(alpha=10,solver='lsqr'))
    model.fit(train[features],train.target)
    test['ridge']=np.maximum(0,model.predict(test[features]))
    metrics=[]
    for name,col in [('last_value','lag'),('same_hour_last_week','weekly'),('ridge','ridge')]:
        err=(test[col]-test.target).abs()
        metrics.append(dict(model=name,n=len(test),mae_people=err.mean(),
            mae_pct_capacity=(err/test.target_capacity*100).mean(),
            median_horizon_min=test.horizon_min.median(),cutoff=str(cutoff),
            eligible_holdout_n=int((valid.origin>=cutoff).sum())))
    return pd.DataFrame(metrics),test[['origin','target_t','target','lag','weekly','ridge','horizon_min']],None

def level_profile(profile, fraction):
    """Conserve occupancy person-hours; deliberately NOT a model of arrivals."""
    if not 0<=fraction<=1: raise ValueError('Fraction must be between 0 and 1')
    p=profile.copy()
    if not {14,15,17,18} <= set(p.index): raise ValueError('Missing donor or receiving hours')
    shifted=p.loc[[17,18]].sum()*fraction
    p.loc[[17,18]]*=1-fraction
    p.loc[[14,15]]+=shifted/2
    return p

def run(root=ROOT):
    out=Path(root)/'reports'; out.mkdir(exist_ok=True)
    db=connect(root)
    q=pd.read_sql_query('SELECT * FROM quality_counts',db)
    clean=pd.read_sql_query('SELECT * FROM clean_counts',db)
    last_poll=db.execute("SELECT MAX(polled_at_utc) FROM polls WHERE status='ok'").fetchone()[0]
    latest=pd.read_sql_query('''SELECT q.*,s.polled_at_utc snapshot_at_utc,
        s.last_count snapshot_count,s.capacity snapshot_capacity,s.is_closed snapshot_closed
        FROM sightings s JOIN quality_counts q
        ON s.location_id=q.location_id AND s.last_updated=q.last_updated
        WHERE s.polled_at_utc=?''',db,params=(last_poll,))
    for col,source in [('last_count','snapshot_count'),('capacity','snapshot_capacity'),('is_closed','snapshot_closed')]:
        latest[col]=latest[source]
    latest['utilization']=latest.last_count/latest.capacity.where(latest.capacity>0)
    latest['age_at_snapshot_min']=(pd.Timestamp(last_poll)-pd.to_datetime(latest.last_updated_utc,utc=True)).dt.total_seconds()/60
    # Remove obsolete analytical exports when current input fails a readiness check.
    for pattern in ('forecast_metrics_*.csv','forecast_predictions_*.csv','hourly.csv','profiles.csv','daily_peaks.csv','leveling.csv','peaks_and_slack.csv'):
        for stale in out.glob(pattern): stale.unlink()

    q.to_csv(out/'observations_quality.csv',index=False)
    latest.to_csv(out/'latest_counts.csv',index=False)
    clean.to_csv(out/'clean_counts.csv',index=False)
    status={'distinct_observations':len(q),'zones':int(q.location_id.nunique()),
        'reset_rows':int(q.is_reset.sum()),'closed_rows':int(q.is_closed.sum()),
        'verified_open_rows':int(q.verified_open.sum()),'clean_rows':len(clean),
        'age_min_quantiles':q.age_min.quantile([0,.5,.9,.95,1]).to_dict(),
        'first_poll':db.execute("SELECT MIN(polled_at_utc) FROM polls WHERE status='ok'").fetchone()[0],
        'last_poll':db.execute("SELECT MAX(polled_at_utc) FROM polls WHERE status='ok'").fetchone()[0],
        'successful_polls':db.execute("SELECT COUNT(*) FROM polls WHERE status='ok'").fetchone()[0],
        'failed_polls':db.execute("SELECT COUNT(*) FROM polls WHERE status='error'").fetchone()[0],
        'days_with_polls':db.execute("SELECT COUNT(DISTINCT substr(polled_at_utc,1,10)) FROM polls WHERE status='ok'").fetchone()[0],
        'forecast_status':{},'control_status':{},'limitations':[
            'No verified hours means no utilization inference; snapshot ratios remain descriptive.',
            'Manual headcounts are not arrivals. Leveling is an occupancy person-hour sensitivity scenario.',
            'Threshold exposure uses capped carry-forward; unknown hours remain unknown.',
            'Weather uses only archived forecast vintages available at each origin; game dates are sourced and availability-gated.']}
    polls=pd.read_sql_query("SELECT * FROM polls ORDER BY polled_at_utc",db)
    polls.to_csv(out/'polls.csv',index=False)
    ok_times=pd.to_datetime(polls.loc[polls.status=='ok','polled_at_utc'],utc=True)
    gaps=ok_times.diff().dt.total_seconds()/60
    status['max_collection_gap_minutes']=float(gaps.max()) if len(gaps)>1 else None
    status['gaps_over_30_minutes']=int((gaps>30).sum())
    status['collection_warning']='Scheduled cadence is requested, not guaranteed. Missing intervals are not recovered.'
    h=hourly_bins(clean)
    if not h.empty:
        h.to_csv(out/'hourly.csv',index=False)
        profiles=h.groupby(['location_id','location','weekday','hour'],as_index=False).agg(
            mean_utilization=('utilization','mean'),mean_people=('people','mean'),
            n_hours=('hour_bin','size'),n_readings=('n_readings','sum'))
        profiles.to_csv(out/'profiles.csv',index=False)
        daily=h.assign(date=h.hour_bin.dt.date).groupby(['location_id','location','date'],as_index=False).agg(peak=('utilization','max'),observed_hours=('hour','nunique'))
        daily.to_csv(out/'daily_peaks.csv',index=False)
        peaks=[]
        wp=profiles[profiles.location.str.contains('Strength|Conditioning',case=False,regex=True)]
        for lid,group in wp.groupby('location_id'):
            stable=group[group.n_hours>=4]
            if stable.empty: continue
            peak=stable.loc[stable.mean_utilization.idxmax()]
            matching=wp[(wp.weekday==peak.weekday)&(wp.hour==peak.hour)&(wp.n_hours>=4)]
            for other in matching.itertuples():
                caps=clean.loc[clean.location_id==other.location_id,'capacity']
                if caps.nunique()!=1: continue
                peaks.append(dict(peak_room=lid,weekday=int(peak.weekday),hour=int(peak.hour),
                    compared_room=other.location_id,mean_utilization=other.mean_utilization,
                    slack_people=float(caps.iloc[0]-other.mean_people),observed_hours=other.n_hours))
        pd.DataFrame(peaks).to_csv(out/'peaks_and_slack.csv',index=False)
        eligible_keys=set(zip(clean.location_id,clean.last_updated))
        weights=q[q.location.str.contains('Strength|Conditioning',case=False,regex=True)].copy()
        weights['eligible']=[(lid,t) in eligible_keys for lid,t in zip(weights.location_id,weights.last_updated)]
        for lid,g in weights.groupby('location_id'):
            metrics,pred,reason=forecast_room(g,db)
            status['forecast_status'][str(lid)]=reason or 'Evaluated on common-support holdout'
            if metrics is not None:
                metrics.to_csv(out/f'forecast_metrics_{lid}.csv',index=False)
                pred.to_csv(out/f'forecast_predictions_{lid}.csv',index=False)
            d=daily[daily.location_id==lid]
            status['control_status'][str(lid)]='Pending approved Phase I window and 21 normal days with adequate coverage'
        scenarios=[]
        for (lid,weekday),group in profiles.groupby(['location_id','weekday']):
            if group.n_hours.min()<4: continue
            p=group.set_index('hour').mean_people
            if not {14,15,17,18} <= set(p.index): continue
            capacity=clean.loc[clean.location_id==lid,'capacity']
            if capacity.nunique()!=1: continue
            cap=capacity.iloc[0]
            for fraction in (0,.1,.2,.3):
                leveled=level_profile(p,fraction)
                scenarios.append(dict(location_id=lid,weekday=weekday,fraction=fraction,
                    peak_utilization=leveled.max()/cap,hours_above_90=int((leveled/cap>.9).sum()),
                    hours_in_profile=len(p),person_hours=float(leveled.sum())))
        pd.DataFrame(scenarios).to_csv(out/'leveling.csv',index=False)
    bounds=constraint_bounds(db,q)
    bounds.to_csv(out/'constraint_bounds.csv',index=False)
    status['constraint_status']='No covered intervals yet' if bounds.empty else 'Compare coverage and uncertainty bounds before ranking'
    (out/'status.json').write_text(json.dumps(status,indent=2,default=str),encoding='utf-8')
    db.close()
    return status

if __name__=='__main__':
    print(json.dumps(run(),indent=2,default=str))
