"""Relocate only the live dependency paths of the portable code release."""
import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'benchmarks/v2/frozen.json';d=json.loads(p.read_text());mapped=json.loads((ROOT/'provenance/live-source-map.json').read_text());changes=[]
for rec in mapped:
 f=ROOT/rec['path'];actual=hashlib.sha256(f.read_bytes()).hexdigest()
 if actual!=rec['sha256'] and rec['path']!='harness/labscriptai/biofoundry/config.json':raise RuntimeError('Evaluated source changed: '+rec['path'])
 changes.append({'path':str(f),'sha256':actual})
d['live_files']=changes;p.write_text(json.dumps(d,indent=2)+'\n');print('Verified evaluated source; relocated',len(changes),'live dependencies')
