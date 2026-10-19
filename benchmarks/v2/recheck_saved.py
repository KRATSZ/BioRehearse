"""Re-score every saved primary schedule without rerunning a planner or an API."""
import gzip,json
from common import PAPER,read,write
from scorer import score,states

def main():
 cases={x['id']:x for x in read(PAPER/'benchmarks/v2/workloads.json')['heldout']};cap=read(PAPER/'source-data/v2/catalog.json');n=0;returned=0;errors=[]
 with gzip.open(PAPER/'source-data/v2/heldout/plans.jsonl.gz','rt') as f:
  for line in f:
   rec=json.loads(line);p=rec['plan'];n+=1
   if not p.get('ok'):continue
   returned+=1;case=cases[rec['case']];check=score(p,p['graph'],cap,case['bookings']);state=states(p)
   if not check['valid'] or not state['material_valid'] or not state['mass_valid']:errors.append({'case':rec['case'],'method':rec['method'],'repeat':rec['repeat'],'violations':check['violations'],'location_issues':state['location_issues'],'mass_issues':state['mass_issues']})
 assert n==1080
 result={'primary_outcomes':n,'returned':returned,'errors':errors,'note':'All stored returned plans independently re-scored; planners/models not rerun.'};write(PAPER/'audit/v2/SAVED_PLAN_RECHECK.json',result);print(json.dumps(result))
 assert not errors
if __name__=='__main__':main()
