"""Reproduce v1 liquid-use location audit, not v2's stronger start/edge checks."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'legacy/reproducibility/source-snapshot'))
from labscriptai.biofoundry.portfolio import prepare_plan,replay
plans=sorted((ROOT/'legacy/source-data/heldout/plans').glob('*.json'));failed=[]
cap=json.loads((ROOT/'source-data/catalog.json').read_text())
for path in plans:
 p=json.loads(path.read_text());prepare_plan(p,cap);issues=[]
 for row in p['rows']:
  if not row.get('transfers'):continue
  state=replay(p,row['process_end_s']-.001)
  for cid in sorted({c for a,b,v in row['transfers'] for c in [a,b]}):
   loc=state['locations'][cid];resource=row['resource']
   if not (loc.startswith(resource+':') or loc.startswith('staging:'+resource+':')):issues.append({'task':row['id'],'container':cid,'location':loc,'required_resource':resource})
 if issues:failed.append({'case':path.stem,'issues':issues})
print(json.dumps({'scope':'Original v1 pre-liquid-use audit; v2 additionally checks operation/edge starts','plans':len(plans),'location_failures':len(failed),'cases':failed},indent=2))
assert len(plans)==24 and len(failed)==16
