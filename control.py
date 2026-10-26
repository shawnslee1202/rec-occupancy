"""Explicit Phase I selection; never auto-label the first 21 days normal."""
import argparse
import json
import numpy as np
import pandas as pd
from poll_rec_counts import ROOT

def imr(series, phase_start, phase_end):
    series=series.sort_index()
    phase=series.loc[phase_start:phase_end]
    if len(phase)<21: raise ValueError('Need 21 accepted normal days in Phase I')
    diffs=phase.diff().abs()
    consecutive=phase.index.to_series().diff().dt.days.eq(1)
    mr=diffs[consecutive].mean()
    if not np.isfinite(mr) or mr==0: raise ValueError('Insufficient Phase I variation')
    center=phase.mean()
    result=pd.DataFrame({'peak':series})
    result['moving_range']=series.diff().abs().where(series.index.to_series().diff().dt.days.eq(1))
    result['center']=center; result['ucl']=center+2.66*mr; result['lcl']=max(0,center-2.66*mr)
    result['mr_ucl']=3.267*mr
    result['signal']=(result.peak>result.ucl)|(result.peak<result.lcl)|(result.moving_range>result.mr_ucl)
    return result

def decay(daily, baseline, return_date='2027-01-19'):
    from scipy.optimize import curve_fit
    d=daily.loc[return_date:pd.Timestamp(return_date)+pd.Timedelta(days=41)]
    if len(d)<28: raise ValueError('Need at least 28 adequately covered return-period days')
    x=(d.index-pd.Timestamp(return_date)).days.to_numpy()
    y=d.to_numpy()-baseline
    if y[:7].mean()<=0: raise ValueError('No positive initial January excess')
    params,cov=curve_fit(lambda t,a,k:a*np.exp(-k*t),x,y,p0=[max(y.max(),.01),.05],bounds=([0,.00001],[10,3]))
    a,k=params
    return {'excess_amplitude':float(a),'half_life_days':float(np.log(2)/k),
        'n_days':len(d),'warning':'Descriptive fit; no causal attribution. Inspect residuals and weekly seasonality.'}

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--phase-start',required=True); p.add_argument('--phase-end',required=True)
    p.add_argument('--min-observed-hours',type=int,default=10)
    a=p.parse_args()
    data=pd.read_csv(ROOT/'reports/daily_peaks.csv',parse_dates=['date'])
    for lid,g in data.groupby('location_id'):
        s=g[g.observed_hours>=a.min_observed_hours].set_index('date').peak
        try:
            result=imr(s,a.phase_start,a.phase_end)
            result.to_csv(ROOT/f'reports/control_{lid}.csv')
            try:
                fit=decay(s,result.center.iloc[0])
                (ROOT/f'reports/decay_{lid}.json').write_text(json.dumps(fit,indent=2))
            except ValueError as exc: print(lid,'Decay pending:',exc)
        except ValueError as exc: print(lid,'Control limits pending:',exc)
