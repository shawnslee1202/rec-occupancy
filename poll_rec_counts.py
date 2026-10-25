"""Archive public aggregate counts; idempotent observations, full poll history."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
URL = os.environ.get('REC_COUNTS_URL', 'https://goboardapi.azurewebsites.net/api/FacilityCount/GetCountsByAccount?AccountAPIKey=99563b55-ae4f-4001-b384-648e0ebeaeb5')
CENTRAL = ZoneInfo('America/Chicago')

def utc_stamp(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        a, b = dt.replace(tzinfo=CENTRAL, fold=0), dt.replace(tzinfo=CENTRAL, fold=1)
        if a.utcoffset() != b.utcoffset():
            return None, 'ambiguous_or_nonexistent_local_time'
        dt = a
    return dt.astimezone(timezone.utc).isoformat(timespec='microseconds'), None

def connect(root=ROOT):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / 'rec_counts.sqlite', timeout=30)
    db.executescript('''
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS polls (
      polled_at_utc TEXT PRIMARY KEY, n_records INTEGER, n_new INTEGER,
      status TEXT NOT NULL, error TEXT, payload_sha256 TEXT);
    CREATE TABLE IF NOT EXISTS counts (
      location_id INTEGER, last_updated TEXT, last_updated_utc TEXT,
      polled_at_utc TEXT, facility_id INTEGER, facility TEXT, location TEXT,
      last_count REAL, capacity REAL, is_closed INTEGER,
      min_threshold REAL, max_threshold REAL, time_issue TEXT,
      PRIMARY KEY(location_id,last_updated));
    CREATE TABLE IF NOT EXISTS sightings (
      polled_at_utc TEXT, location_id INTEGER, last_updated TEXT,
      last_count REAL, capacity REAL, is_closed INTEGER,
      PRIMARY KEY(polled_at_utc,location_id));
    CREATE TABLE IF NOT EXISTS open_intervals (
      location_id INTEGER, opens_at_utc TEXT, closes_at_utc TEXT,
      source_url TEXT NOT NULL, verified_at_utc TEXT NOT NULL,
      PRIMARY KEY(location_id,opens_at_utc),
      CHECK(closes_at_utc > opens_at_utc));
    ''')
    sql = ROOT / 'sql' / 'views.sql'
    if sql.exists():
        db.executescript(sql.read_text(encoding='utf-8'))
    return db

def validate(payload):
    if not isinstance(payload, list) or not payload:
        raise ValueError('Expected a nonempty JSON array')
    required = {'LocationId','LocationName','FacilityId','FacilityName',
                'LastCount','TotalCapacity','LastUpdatedDateAndTime','IsClosed',
                'MinCapacityRange','MaxCapacityRange'}
    ids = set()
    for row in payload:
        if not isinstance(row, dict) or not required <= row.keys():
            raise ValueError('Feed schema changed: missing required fields')
        if row['LocationId'] in ids:
            raise ValueError('Duplicate LocationId in poll')
        ids.add(row['LocationId'])
        if not isinstance(row['IsClosed'], bool):
            raise ValueError('IsClosed must be boolean')
        for key in ('LastCount','TotalCapacity','MinCapacityRange','MaxCapacityRange'):
            if not isinstance(row[key], (int,float)) or isinstance(row[key],bool):
                raise ValueError(f'{key} must be numeric')
        utc_stamp(row['LastUpdatedDateAndTime'])

def ingest(payload, polled, root=ROOT):
    validate(payload)
    db = connect(root)
    new = 0
    with db:
        for r in payload:
            stamp, issue = utc_stamp(r['LastUpdatedDateAndTime'])
            local = datetime.fromisoformat(r['LastUpdatedDateAndTime']).replace(tzinfo=None).isoformat(timespec='microseconds')
            cur = db.execute('INSERT OR IGNORE INTO counts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (r['LocationId'],local,stamp,polled,r['FacilityId'],r['FacilityName'],r['LocationName'],
                 r['LastCount'],r['TotalCapacity'],int(r['IsClosed']),r['MinCapacityRange'],r['MaxCapacityRange'],issue))
            new += cur.rowcount
            db.execute('INSERT OR IGNORE INTO sightings VALUES (?,?,?,?,?,?)',
                (polled,r['LocationId'],local,r['LastCount'],r['TotalCapacity'],int(r['IsClosed'])))
        digest = hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        db.execute('INSERT OR IGNORE INTO polls VALUES (?,?,?,?,?,?)', (polled,len(payload),new,'ok',None,digest))
    db.close()
    return new

def poll(root=ROOT):
    root = Path(root)
    polled = datetime.now(timezone.utc).isoformat(timespec='microseconds')
    try:
        request = Request(URL,headers={'User-Agent':'TAMURecOccupancyResearch/1.0 (aggregate research; polling every 10 minutes)','Accept':'application/json'})
        with urlopen(request,timeout=45) as response:
            raw = response.read().decode('utf-8-sig')
        # Archive before validation so even a changed feed can be reprocessed.
        folder = root / 'raw'
        folder.mkdir(exist_ok=True)
        with (folder / f'{polled[:10]}.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps({'polled_at_utc':polled,'source_url':URL,'response_body':raw})+'\n')
        payload = json.loads(raw)
        new = ingest(payload,polled,root)
        print(json.dumps({'polled_at_utc':polled,'n_records':len(payload),'n_new':new}))
    except Exception as exc:
        db = connect(root)
        with db:
            db.execute('INSERT OR REPLACE INTO polls VALUES (?,?,?,?,?,?)',(polled,0,0,'error',str(exc),None))
        db.close()
        raise

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--replay',type=Path,help='Replay archived JSONL without network access')
    args = parser.parse_args()
    if args.replay:
        for line in args.replay.read_text(encoding='utf-8').splitlines():
            record = json.loads(line)
            ingest(json.loads(record['response_body']),record['polled_at_utc'],args.root)
    else:
        poll(args.root)
