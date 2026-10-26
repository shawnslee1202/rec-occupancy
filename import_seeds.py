"""Idempotently merge the original local captures without replacing hosted history."""
import gzip,json,hashlib,csv
from poll_rec_counts import ROOT,ingest,connect
def restore():
    db=connect()
    db.execute("CREATE TABLE IF NOT EXISTS seed_imports(name TEXT PRIMARY KEY)")
    done=db.execute("SELECT 1 FROM seed_imports WHERE name='initial-v1'").fetchone()
    db.close()
    if done: return
    for source in sorted((ROOT/'seeds').glob('*.jsonl.gz')):
        with gzip.open(source,'rt',encoding='utf-8') as f: records=[json.loads(line) for line in f]
        for record in sorted(records,key=lambda r:r['polled_at_utc']):
            stamp=record['polled_at_utc']
            ingest(json.loads(record['response_body']),stamp)
            folder=ROOT/'raw'; folder.mkdir(exist_ok=True)
            path=folder/f'{stamp[:10]}.jsonl'
            existing=path.read_text().splitlines() if path.exists() else []
            if not any(json.loads(line)['polled_at_utc']==stamp for line in existing):
                existing.append(json.dumps(record))
                existing.sort(key=lambda line:json.loads(line)['polled_at_utc'])
                path.write_text('\n'.join(existing)+'\n',encoding='utf-8')
    db=connect()
    with db:
        with (ROOT/'seeds/open_intervals.csv').open(newline='') as f:
            for row in csv.DictReader(f):
                db.execute('INSERT OR IGNORE INTO open_intervals VALUES (?,?,?,?,?)',tuple(row.values()))
        db.execute("INSERT OR IGNORE INTO seed_imports VALUES ('initial-v1')")
    db.close()
if __name__=='__main__': restore()
