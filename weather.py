"""Archive weather forecast vintages; never use future realized weather. Open-Meteo CC BY 4.0."""
import json
from datetime import datetime,timezone
from urllib.request import Request,urlopen
import pandas as pd
from poll_rec_counts import ROOT,connect
URL='https://api.open-meteo.com/v1/forecast?latitude=30.61&longitude=-96.34&hourly=temperature_2m,precipitation&forecast_days=2&timezone=UTC'
def setup(db):
    db.execute("CREATE TABLE IF NOT EXISTS weather_forecasts(fetched_at_utc TEXT,valid_at_utc TEXT,temperature_c REAL,precipitation_mm REAL,PRIMARY KEY(fetched_at_utc,valid_at_utc))")
def refresh(root=ROOT):
    with urlopen(Request(URL,headers={'User-Agent':'TAMURecOccupancyResearch/1.0'}),timeout=45) as r:
        body=r.read().decode()
    fetched=datetime.now(timezone.utc).isoformat(timespec='microseconds')
    folder=root/'sources/weather'; folder.mkdir(parents=True,exist_ok=True)
    with (folder/f'{fetched[:10]}.jsonl').open('a',encoding='utf-8') as f:
        f.write(json.dumps({'fetched_at_utc':fetched,'source_url':URL,'response_body':body})+'\n')
    payload=json.loads(body)['hourly']
    rows=[(fetched,t+':00+00:00',temp,rain) for t,temp,rain in zip(payload['time'],payload['temperature_2m'],payload['precipitation'])]
    db=connect(root); setup(db)
    with db: db.executemany('INSERT OR IGNORE INTO weather_forecasts VALUES (?,?,?,?)',rows)
    db.close(); print(f'Archived {len(rows)} Open-Meteo forecast hours')
def features(origins,db):
    setup(db); rows=[]
    for origin in origins:
        t=pd.Timestamp(origin); valid=(t+pd.Timedelta(hours=1)).floor('h').isoformat()
        row=db.execute("SELECT temperature_c,precipitation_mm FROM weather_forecasts WHERE julianday(valid_at_utc)=julianday(?) AND julianday(fetched_at_utc)<=julianday(?) ORDER BY julianday(fetched_at_utc) DESC LIMIT 1",(valid,t.isoformat())).fetchone()
        rows.append(row if row else (float('nan'),float('nan')))
    return pd.DataFrame(rows,columns=['temperature_c','precipitation_mm'])
if __name__=='__main__': refresh()
