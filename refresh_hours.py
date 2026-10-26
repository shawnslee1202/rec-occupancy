"""Archive and parse published weight-room building hours for the coming week.
Only the three strength rooms are mapped; other zones need their own schedules.
Unexpected summaries or formats fail closed for that day.
"""
import csv
from datetime import datetime, timedelta, timezone
import html
import re
from urllib.request import Request, urlopen
from poll_rec_counts import ROOT, CENTRAL, connect

MAPPING={574:9276,575:9274,576:9275}

def parse(text, today):
    result=[]
    for fragment in text.split('<div class="lw_events_day')[1:]:
        date_match=re.search(r'header_date">\w+, (\w+ \d+):',fragment)
        time_match=re.search(r'events_time">(.*?)</span><div',fragment)
        summary=re.search(r'events_summary">(.*?)</div>',fragment)
        if not date_match or not time_match: continue
        note=html.unescape(re.sub('<[^>]+>','',summary.group(1))) if summary else ''
        if note.strip(): continue  # special events require human interpretation
        times=re.findall(r'\d{1,2}:\d{2}[ap]m',time_match.group(1))
        if len(times)!=2: continue
        dates=[datetime.strptime(f'{year} {date_match.group(1)}','%Y %b %d') for year in (today.year-1,today.year,today.year+1)]
        day=min(dates,key=lambda d:abs((d.date()-today).days))
        if not 0<=(day.date()-today).days<=14: continue
        start=datetime.combine(day.date(),datetime.strptime(times[0],'%I:%M%p').time(),CENTRAL)
        end=datetime.combine(day.date(),datetime.strptime(times[1],'%I:%M%p').time(),CENTRAL)
        if end<=start: end+=timedelta(days=1)
        result.append((start.astimezone(timezone.utc).isoformat(),end.astimezone(timezone.utc).isoformat()))
    return result

def refresh():
    now=datetime.now(timezone.utc); today=now.astimezone(CENTRAL).date()
    folder=ROOT/'sources'; folder.mkdir(exist_ok=True)
    rows=[]
    for widget,lid in MAPPING.items():
        url=f'https://calendar.tamu.edu/live/widget/{widget}'
        with urlopen(Request(url,headers={'User-Agent':'TAMURecOccupancyResearch/1.0'}),timeout=45) as response:
            content=response.read().decode()
        (folder/f'hours-{widget}-{today}.html').write_text(content,encoding='utf-8')
        if 'lw_events_day' not in content:
            raise ValueError(f'Hours schema changed for {widget}; prior schedules retained')
        for start,end in parse(content,today):
            rows.append([lid,start,end,url,now.isoformat()])
    path=ROOT/'config/open_intervals.csv'
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f); writer.writerow(['location_id','opens_at_utc','closes_at_utc','source_url','verified_at_utc']); writer.writerows(rows)
    db=connect()
    cutoff=datetime.combine(today,datetime.min.time(),CENTRAL).astimezone(timezone.utc).isoformat()
    with db:
        for lid in MAPPING.values():
            db.execute('DELETE FROM open_intervals WHERE location_id=? AND julianday(opens_at_utc)>=julianday(?)',(lid,cutoff))
        db.executemany('INSERT INTO open_intervals VALUES (?,?,?,?,?)',rows)
    count=len(rows); db.close()
    print(f'Imported {count} published intervals; unmapped zones remain unverified')

if __name__=='__main__': refresh()
