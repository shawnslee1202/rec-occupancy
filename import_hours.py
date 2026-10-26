"""Import verified per-zone UTC opening intervals; never guess missing hours."""
import argparse
import csv
from datetime import datetime
from poll_rec_counts import connect

def load(path, db):
    rows = list(csv.DictReader(open(path,encoding='utf-8-sig',newline='')))
    with db:
        for row in rows:
            start,end = (datetime.fromisoformat(row[k]) for k in ('opens_at_utc','closes_at_utc'))
            if start.tzinfo is None or end.tzinfo is None or end <= start:
                raise ValueError('Opening intervals need explicit timezone offsets and positive duration')
            if not row['source_url'] or not row['verified_at_utc']:
                raise ValueError('Source and verification date required')
            overlaps = db.execute('''SELECT 1 FROM open_intervals WHERE location_id=?
                AND opens_at_utc<>? AND julianday(opens_at_utc)<julianday(?)
                AND julianday(closes_at_utc)>julianday(?)''',
                (int(row['location_id']),row['opens_at_utc'],row['closes_at_utc'],row['opens_at_utc'])).fetchone()
            if overlaps:
                raise ValueError('Overlapping opening intervals')
            db.execute('INSERT OR REPLACE INTO open_intervals VALUES (?,?,?,?,?)',
                tuple(row[k] for k in ('location_id','opens_at_utc','closes_at_utc','source_url','verified_at_utc')))
    return len(rows)

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('csv'); a=p.parse_args()
    db=connect(); print(f'Imported {load(a.csv,db)} verified intervals'); db.close()
