"""New repair holdout and controlled, layer-specific fault injections."""
import copy,gzip,json,time
from common import PAPER,read,write,emit,frozen
from scorer import score,states,semantic
from labscriptai.biofoundry.methods import compile_graph
from labscriptai.biofoundry.scheduling import solve,replan
from labscriptai.biofoundry.portfolio import prepare_plan
from labscriptai.biofoundry.workflow import Blocked

def main():
 frozen();out=PAPER/'source-data/v2/repair';out.mkdir(exist_ok=True)
 if (out/'outcomes.jsonl').exists():raise RuntimeError('Repair evidence exists')
 cap=read(PAPER/'source-data/v2/catalog.json')
 for case in read(PAPER/'benchmarks/v2/repair.json'):
  started=time.perf_counter();comp=compile_graph(case['intent'],cap);p=solve(comp['graph'],cap,case['layout'],'fastest',case['bookings'],time_limit_s=2) if comp['ok'] else comp
  if not p.get('ok'):
   emit(out/'outcomes.jsonl',{'case':case['id'],'returned':False,'status':p.get('status',p.get('code'))});continue
  prepare_plan(p,cap);audit=states(p);sc=score(p,p['graph'],cap,case['bookings']);write(out/'plans'/f'{case["id"]}.json',p)
  emit(out/'outcomes.jsonl',{'case':case['id'],**sc,**{k:audit[k] for k in ['material_valid','mass_valid','event_count']},'location_issues':audit['location_issues'],'makespan_s':p['makespan_s'],'wall_s':time.perf_counter()-started})
  # Inject changes into an already compiled artifact; each affected field is kept.
  variants={'unchanged':copy.deepcopy(p),'intent_mismatch':copy.deepcopy(p),'resource_overlap':copy.deepcopy(p),'liquid_overdraw':copy.deepcopy(p),'missing_water_movement':copy.deepcopy(p)}
  variants['intent_mismatch']['graph']['intent']['deadline_s']-=60
  q=variants['resource_overlap'];operations=[r for r in q['rows'] if r['kind']=='operation'];a,b=next((a,b) for a in operations for b in operations if a['id']!=b['id'] and a['resource']==b['resource']);delta=a['start_s']-b['start_s']
  for key in ['start_s','end_s','process_start_s','process_end_s']:b[key]+=delta
  for reservation in q['reservations']:
   if reservation['task_id']==b['id']:reservation['start_s']+=delta;reservation['end_s']+=delta
  event=next(e for e in variants['liquid_overdraw']['events'] if e.get('transfers'));event['transfers'][0][2]=100000
  gfp=next(e for e in p['graph']['experiments'] if e['method']=='gfp');water=gfp['id']+':WATER';assembled=next(r for r in p['rows'] if r['id']==gfp['id']+':assemble')['end_s']
  for e in variants['missing_water_movement']['events']:
   if e['time_s']>assembled:e['container_ids']=[cid for cid in e['container_ids'] if cid!=water]
  for label,mutated in variants.items():
   check=score(mutated,mutated['graph'],cap,case['bookings']);state=states(mutated)
   emit(out/'injections.jsonl',{'case':case['id'],'error_type':label,'intent_detected':not semantic(mutated['graph']['intent'],case['intent']),'schedule_detected':not check['valid'],'mass_detected':not state['mass_valid'],'material_detected':not state['material_valid'],'location_issues':state['location_issues'],'mass_issues':state['mass_issues'],'schedule_violations':check['violations']})
  rp={};error=None
  try:rp=replan(p,cap,1,'device:67',3600,case['bookings'])
  except Exception as exc:error=repr(exc)
  if rp.get('ok'):prepare_plan(rp,cap);ra=states(rp);rs=score(rp,p['graph'],cap,case['bookings']+rp.get('calendar_blocks',[]));write(out/'replans'/f'{case["id"]}.json',rp)
  else:ra={'material_valid':None,'mass_valid':None};rs={'returned':False,'valid':False,'violations':[]}
  frozen_rows=[r for r in p['rows'] if r['start_s']<=1];nr={r['id']:r for r in rp.get('rows',[])};preserved=all(r['id'] in nr and all(r[k]==nr[r['id']][k] for k in ['resource','start_s','end_s']) for r in frozen_rows) if rp.get('ok') else None
  reader=next(r for r in p['rows'] if r['kind']=='operation' and r['resource']=='device:67');active_code=None
  try:replan(p,cap,reader['start_s']+1,'device:67',reader['end_s']+600,case['bookings']);active_code='UNEXPECTED_RETURN'
  except Blocked as exc:active_code=exc.code
  emit(out/'faults.jsonl',{'case':case['id'],**rs,'material_valid':ra['material_valid'],'mass_valid':ra['mass_valid'],'status':rp.get('status'),'error':error,'affected':any(r['kind']=='operation' and r['resource']=='device:67' and r['start_s']<3600 and r['end_s']>1 for r in p['rows']),'frozen_count':len(frozen_rows),'preserved':preserved,'added_makespan_s':rp['makespan_s']-p['makespan_s'] if rp.get('ok') else None,'active_refusal':active_code})
  print(case['id'],'repair',sc['valid'],audit['material_valid'],'replan',rs['valid'],flush=True)
if __name__=='__main__':main()
