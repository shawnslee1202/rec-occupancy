"""Portable HTML dashboard plus CSV exports for Power BI/Tableau."""
import base64
import html
import io
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from rec_occupancy.collection.poll_rec_counts import ROOT

def chart(fig):
    import matplotlib.pyplot as plt
    buffer=io.BytesIO(); fig.savefig(buffer,format='png',dpi=150,bbox_inches='tight'); plt.close(fig)
    return '<img alt="Occupancy analysis chart" src="data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()+'">'

def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    r=ROOT/'reports'; status=json.loads((r/'status.json').read_text())
    data=pd.read_csv(r/'latest_counts.csv')
    weight=data[data.location.str.contains('Strength|Conditioning',case=False,regex=True)]
    central=ZoneInfo('America/Chicago')
    captured=datetime.fromisoformat(status['last_poll']).astimezone(central)
    updated=captured.strftime('%b %d, %Y at %I:%M %p %Z')
    cards=''
    for row in weight.itertuples():
        cards+=f'<article><h3>{html.escape(row.facility)}</h3><strong>{row.last_count:,.0f} <small>/ {row.capacity:,.0f}</small></strong><p>{row.utilization:.1%} reported occupancy</p><p>{'CLOSED' if row.is_closed else 'Older reading' if row.age_at_snapshot_min>90 else ''}</p><p class="muted">Counted {html.escape(datetime.fromisoformat(row.last_updated).strftime('%b %d at %I:%M %p'))} CT</p></article>'
    fig,ax=plt.subplots(figsize=(9,3))
    ax.hist(data.age_min.dropna()/60,bins=[0,1,2,6,12,24,48,96,168,336],color='#671d32',edgecolor='white')
    ax.set(xlabel='Age at first capture (hours)',ylabel='Zones',title='Age of staff counts when first collected')
    quality_chart=chart(fig)
    heatmaps=''
    if (r/'profiles.csv').exists():
        p=pd.read_csv(r/'profiles.csv')
        for lid in weight.location_id:
            g=p[p.location_id==lid]
            if g.empty: continue
            pivot=g.pivot(index='weekday',columns='hour',values='mean_utilization').reindex(index=range(7),columns=range(24))
            fig,ax=plt.subplots(figsize=(10,2.7))
            image=ax.imshow(pivot,aspect='auto',vmin=0,vmax=1,cmap='YlOrRd')
            ax.set_yticks(range(7),['Mon','Tue','Wed','Thu','Fri','Sat','Sun']); ax.set_xticks(range(0,24,2))
            ax.set(xlabel='Hour, America/Chicago',title=g.location.iloc[0]+'')
            fig.colorbar(image,ax=ax,label='Count / capacity'); heatmaps+=chart(fig)
    forecasts=''
    for file in sorted(r.glob('forecast_predictions_*.csv')):
        g=pd.read_csv(file,parse_dates=['target_t']); fig,ax=plt.subplots(figsize=(10,3))
        for col in ['target','lag','weekly','ridge']: ax.plot(g.target_t,g[col],label=col,alpha=.7)
        ax.legend(); ax.set(title=file.stem,ylabel='People'); forecasts+=chart(fig)
    controls=''
    for file in sorted(r.glob('control_*.csv')):
        g=pd.read_csv(file,index_col=0,parse_dates=True); fig,axes=plt.subplots(2,1,figsize=(10,4),sharex=True)
        for col in ['peak','center','ucl','lcl']: axes[0].plot(g.index,g[col],label=col)
        for col in ['moving_range','mr_ucl']: axes[1].plot(g.index,g[col],label=col)
        events=pd.read_csv(ROOT/'config/events.csv')
        for e in events.itertuples():
            start=pd.Timestamp(e.start_date)
            if g.index.min()<=start<=g.index.max():
                axes[0].axvline(start,color='#671d32',alpha=.35)
                axes[0].annotate(e.event,(start,axes[0].get_ylim()[1]),rotation=90,va='top',fontsize=7)
        for ax in axes: ax.legend(fontsize=7)
        controls+=chart(fig)
    leveling=''
    lf=r/'leveling.csv'
    if lf.exists() and lf.stat().st_size>2:
        level=pd.read_csv(lf)
        if len(level):
            fig,ax=plt.subplots(figsize=(10,3))
            for (lid,weekday),g in level.groupby(['location_id','weekday']):
                ax.plot(g.fraction*100,g.peak_utilization*100,marker='o',label=f'{lid} / weekday {weekday}')
            ax.set(xlabel='Occupancy person-hours shifted (%)',ylabel='Profile peak (% capacity)',title='Leveling sensitivity - not an arrival model')
            ax.legend(fontsize=6); leveling=chart(fig)
    cols=['facility','location','last_count','capacity','utilization','age_at_snapshot_min','is_closed','is_reset','verified_open']
    table=data[cols].round({'age_at_snapshot_min':0}).rename(columns=dict(zip(cols, ['Center','Zone','People','Capacity','Occupancy','Age at collection (min)','Closed','Possible reset','Verified open']))).to_html(index=False,classes='zones',formatters={'Occupancy':'{:.1%}'.format},border=0,escape=True)
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Texas A&amp;M rec center occupancy</title>
    <style>body{margin:0;background:#f4f2ef;color:#262323;font:16px/1.5 system-ui,sans-serif}main{max-width:1180px;margin:auto;padding:36px}h1{font-size:40px;line-height:1.1;margin:8px 0 20px}h2{margin-top:40px}small,.muted{color:#736b69}small{font-size:20px}.eyebrow{color:#671d32;letter-spacing:2px;font-size:12px;font-weight:700}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}article,section{background:white;padding:24px;border-radius:12px;border:1px solid #e4ded8}article strong{font-size:42px}article h3{font-size:17px}article p{margin:8px 0}.notice{padding:16px 22px;background:#f4e6c9;border-left:4px solid #9d721e;margin:24px 0}img{max-width:100%;height:auto}table{border-collapse:collapse;font-size:12px;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #eee}th{position:sticky;top:0;background:#eee8e3}.scroll{overflow:auto;max-height:550px}input{padding:12px;width:60%;margin-bottom:20px;border:1px solid #ccc;border-radius:6px}.placeholder{padding:24px;border:1px dashed #aaa;color:#645c57}.metrics{display:flex;gap:28px;flex-wrap:wrap}footer{margin-top:32px;color:#746b65;font-size:13px}@media(max-width:700px){.cards{grid-template-columns:1fr}main{padding:20px}h1{font-size:30px}}</style><main>
    <div class="eyebrow">TEXAS A&amp;M REC SPORTS / INDEPENDENT ANALYSIS</div><h1>Rec center occupancy</h1>
    <p class="muted">Updated __UPDATED__</p>
    <div class="cards">__CARDS__</div><h2>Collection quality</h2><section><div class="metrics">__METRICS__</div>__QUALITY__<p>Age is calculated at the first poll that saw a reading. Closed zones and unverified hours are retained in the archive. Batch resets are a heuristic, not proof of a reset.</p></section>
    <p class="notice">__GAPS__</p><h2>Occupancy by day and hour</h2><section>__HEATMAPS__<p class="muted">Blank cells have no readings.</p></section>
    <h2>Forecast vs. actual</h2><section>__FORECAST__</section>
    <h2>Semester dynamics</h2><section>__CONTROL__</section>
    <h2>Shifting afternoon demand</h2><section>__LEVELING__</section>
    <h2>All zones</h2><input id="search" aria-label="Filter zones" placeholder="Filter by facility or zone"><div class="scroll">__TABLE__</div>
    <footer>Sources: <a href="https://recsports.tamu.edu/facilities/live-facility-count/">Rec Sports live counts</a> and <a href="https://recsports.tamu.edu/hours-of-operation/">published hours</a>. Manual counts; aggregate research. No affiliation implied.</footer></main>
    <script>document.getElementById('search').addEventListener('input',e=>{const q=e.target.value.toLowerCase();document.querySelectorAll('.zones tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q));});</script></html>'''
    replacements={'__UPDATED__':updated,'__CARDS__':cards,'__QUALITY__':quality_chart,
        '__GAPS__':f"Collection gaps over 30 minutes: {status['gaps_over_30_minutes']}. Largest gap: {status['max_collection_gap_minutes'] or 0:.0f} minutes. ",
        '__METRICS__':''.join(f'<p><b>{status[k]}</b><br>{label}</p>' for k,label in [('successful_polls','successful polls'),('zones','zones'),('distinct_observations','distinct readings'),('reset_rows','reset candidates'),('clean_rows','verified-open readings')]),
        '__HEATMAPS__':heatmaps or '<p class="placeholder">Awaiting verified open-hour observations.</p>',
        '__FORECAST__':forecasts or '<p class="placeholder">Forecast accuracy requires six weeks of usable readings.</p>',
        '__CONTROL__':controls or '<p class="placeholder">A baseline requires 21 ordinary days with enough readings.</p>',
        '__LEVELING__':leveling or '<p class="placeholder">The afternoon comparison needs four dates for each day and hour shown.</p>', '__TABLE__':table}
    for key,value in replacements.items(): page=page.replace(key,value)
    (r/'dashboard.html').write_text(page,encoding='utf-8')
    (ROOT/'dashboard').mkdir(exist_ok=True)
    (ROOT/'dashboard/index.html').write_text(page,encoding='utf-8')
    print(r/'dashboard.html')

if __name__=='__main__': main()
