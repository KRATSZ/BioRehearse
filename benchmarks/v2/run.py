"""Frozen v2 schedule evaluation; all failures and complete returned plans retained."""
import argparse,copy,gzip,json,time
from common import PAPER,read,write,emit,frozen
from scorer import score,states
from greedy import solve_greedy
from labscriptai.biofoundry.methods import compile_graph
from labscriptai.biofoundry.scheduling import solve,replan
from labscriptai.biofoundry.portfolio import prepare_plan

def main(split):
 if split=='heldout':frozen()
 cases=read(PAPER/'benchmarks/v2/workloads.json')[split];cat=read(PAPER/'source-data/v2/catalog.json');root=PAPER/'source-data/v2'/split;root.mkdir(parents=True,exist_ok=True)
 target=root/'scheduling.jsonl'
 if target.exists():raise RuntimeError('Evidence exists; do not overwrite')
 with gzip.open(root/'plans.jsonl.gz','wt') as out:
  for case in cases:
   comp=compile_graph(case['intent'],cat)
   for obj in ['fastest','cheapest']:
    for repeat in range(3 if split=='heldout' else 1):
     for method in ['cp_sat','parallel_greedy','serial_fifo']:
      started=time.perf_counter();p={};err=None;material=None;mass=None;state_errors=[];arithmetic_s=0;rehearsal_s=0
      try:
       if not comp['ok']:p={'ok':False,'status':'COMPILER_REJECT','code':comp['code']}
       elif method=='parallel_greedy':p=solve_greedy(comp['graph'],cat,case['layout'],obj,case['bookings'],time_limit_s=2)
       else:p=solve(comp['graph'],cat,case['layout'],obj,case['bookings'],time_limit_s=2,fifo=method=='serial_fifo')
       planning_s=time.perf_counter()-started;scoring_started=time.perf_counter();sc=score(p,comp['graph'],cat,case['bookings']) if comp['ok'] else {'returned':False,'valid':False,'violations':[]}
       arithmetic_s=time.perf_counter()-scoring_started
       if p.get('ok'):
        rehearsal_started=time.perf_counter();prepare_plan(p,cat);audit=states(p);material=audit['material_valid'];mass=audit['mass_valid'];state_errors=audit['location_issues'];p['independent_state_audit']={k:v for k,v in audit.items() if k!='snapshots'};rehearsal_s=time.perf_counter()-rehearsal_started
      except Exception as e:err=repr(e);planning_s=time.perf_counter()-started;sc={'returned':bool(p.get('ok')),'valid':False,'violations':['exception']}
      rec={'case':case['id'],'split':split,'load':case['load'],'handling_policy':case['handling_policy'],'horizon_s':case['intent']['deadline_s'],'layout':case['layout'],'objective':obj,'method':method,'repeat':repeat,'planning_s':planning_s,'arithmetic_scoring_s':arithmetic_s,'rehearsal_scoring_s':rehearsal_s,'wall_s':time.perf_counter()-started,**sc,'material_valid':material,'mass_valid':mass,'state_errors':state_errors,'error':err,**{k:p.get(k) for k in ['status','code','makespan_s','cost_cny','proven_optimal','best_bound','objective_value','solve_seconds','model_construction_s','planner_output_s','planner_validation_s','transport_distance_m','utilization']}}
      emit(target,rec);out.write(json.dumps({'case':case['id'],'objective':obj,'method':method,'repeat':repeat,'plan':p},ensure_ascii=False)+'\n');out.flush()
      if p.get('ok') and method=='cp_sat' and obj=='fastest' and repeat==0:write(root/'plans'/f'{case["id"]}.json',p)
   print(case['id'],'load',case['load'],'compiler',comp['ok'],flush=True)

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--split',choices=['development','heldout'],required=True);main(ap.parse_args().split)
