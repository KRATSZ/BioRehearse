"""Descriptive, case-clustered study-v2 analysis. No post-test selection."""
import json,csv,statistics as st
from collections import defaultdict,Counter
from pathlib import Path
import numpy as np
PAPER=Path(__file__).resolve().parents[2];OUT=PAPER/'source-data/v2'
def rows(p):return [json.loads(s) for s in p.read_text().splitlines() if s]
def ci(values):
 a=np.asarray(values,dtype=float);rng=np.random.default_rng(190026)
 means=np.mean(a[rng.integers(0,len(a),size=(10000,len(a)))],axis=1)
 return [float(a.mean()),*map(float,np.percentile(means,[2.5,97.5]))]
def dump(name,rows_):
 if not rows_:return
 with (OUT/name).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows_[0]));w.writeheader();w.writerows(rows_)
def main():
 records=rows(OUT/'heldout/scheduling.jsonl');assert len(records)==1080,len(records)
 summary={'scheduling':{},'language':{},'repair':{}};rates=[];pairs=[];raw=defaultdict(list)
 for r in records:raw[r['case'],r['objective'],r['method']].append(r)
 for obj in ['fastest','cheapest']:
  for method in ['cp_sat','parallel_greedy','serial_fifo']:
   rr=[r for r in records if r['objective']==obj and r['method']==method];group=defaultdict(list)
   for r in rr:group[r['case']].append(float(r['valid'] and r['material_valid'] and r['mass_valid']))
   estimate=ci([st.mean(v) for v in group.values()]);returned=[r for r in rr if r['returned']];valid=[r for r in rr if r['valid']]
   d={'runs':len(rr),'cases':len(group),'returned':len(returned),'valid':len(valid),'full_valid':sum(r['valid'] and bool(r['material_valid']) and bool(r['mass_valid']) for r in rr),'valid_rate_ci':estimate,'returned_violations':sum(not r['valid'] for r in returned),'material_failures':sum(r['material_valid'] is False for r in rr),'mass_failures':sum(r['mass_valid'] is False for r in rr),'exceptions':sum(bool(r['error']) for r in rr),'status':dict(Counter(r['status'] for r in rr)),'planning_s_median':st.median(r['planning_s'] for r in rr),'planning_s_max':max(r['planning_s'] for r in rr),'wall_s_median':st.median(r['wall_s'] for r in rr),'proven_optimal':sum(r['proven_optimal'] is True for r in rr)}
   summary['scheduling'][obj+'/'+method]=d
   for load in [1,3,6,9,12]:
    sub=[r for r in rr if r['load']==load];casevals=defaultdict(list)
    for r in sub:casevals[r['case']].append(float(r['valid'] and r['material_valid'] and r['mass_valid']))
    est=ci([st.mean(v) for v in casevals.values()]);rates.append({'objective':obj,'method':method,'load':load,'cases':len(casevals),'runs':len(sub),'valid':sum(r['valid'] for r in sub),'rate':est[0],'low':est[1],'high':est[2]})
  for baseline in ['parallel_greedy','serial_fifo']:
   for case in sorted({r['case'] for r in records}):
    a=raw[case,obj,'cp_sat'];b=raw[case,obj,baseline]
    # Pair the repeat and report only jointly valid runs, without substituting failures.
    shared=[(x,y) for x,y in zip(a,b) if x['valid'] and x['material_valid'] and y['valid'] and y['material_valid']]
    if not shared:continue
    pairs.append({'case':case,'objective':obj,'baseline':baseline,'load':a[0]['load'],'paired_repeats':len(shared),'makespan_gain_percent':st.mean(100*(y['makespan_s']-x['makespan_s'])/y['makespan_s'] for x,y in shared),'cost_gain_percent':st.mean(100*(y['cost_cny']-x['cost_cny'])/y['cost_cny'] for x,y in shared)})
   pp=[p for p in pairs if p['objective']==obj and p['baseline']==baseline];summary['scheduling'][obj+'/paired/'+baseline]={'paired_cases':len(pp),'makespan_gain_percent_ci':ci([p['makespan_gain_percent'] for p in pp]),'cost_gain_percent_ci':ci([p['cost_gain_percent'] for p in pp])}
 dump('scheduling-rate.csv',rates);dump('paired-effects.csv',pairs)
 (OUT/'summary-scheduling.json').write_text(json.dumps(summary['scheduling'],indent=2)+'\n')
 for path in sorted((OUT/'heldout/language').glob('*/scores.jsonl')):
  rr=rows(path);assert len(rr)==120,(path,len(rr));first=[r for r in rr if r['repeat']==0];assert len(first)==96
  model=path.parent.name;d={'runs':len(rr),'first_runs':len(first),'successes':sum(r['success'] for r in first),'extra_repeats':len(rr)-len(first),'extra_repeat_successes':sum(r['success'] for r in rr if r['repeat']>0),'accepted':sum(r['accepted'] for r in first),'errors':sum(bool(r['error']) for r in rr),'tokens':{k:sum(r[k] for r in rr) for k in ['input_tokens','cache_read_tokens','output_tokens','reasoning_tokens','total_tokens']},'latency_s_median':st.median(r['wall_s'] for r in first),'latency_s_p95':float(np.percentile([r['wall_s'] for r in first],95)),'groups':{}}
  for style in ['controlled','open','mixed','clarification','unsupported']:
   ss=[r for r in first if r['style']==style and r['decision']=='compile'];bycluster=defaultdict(list)
   for r in ss:bycluster[r['cluster']].append(float(r['success']))
   if ss:d['groups'][style]={'n':len(ss),'success':sum(r['success'] for r in ss),'rate_ci':ci([st.mean(v) for v in bycluster.values()])}
  for decision in ['compile','clarify','reject']:
   ss=[r for r in first if r['decision']==decision];bycluster=defaultdict(list)
   for r in ss:bycluster[r['cluster']].append(float(r['success']))
   if ss:d['groups'][decision]={'n':len(ss),'success':sum(r['success'] for r in ss),'rate_ci':ci([st.mean(v) for v in bycluster.values()])}
  summary['language'][model]=d
 rule=rows(OUT/'heldout/language/rules.jsonl');summary['language']['rules']={'n':len(rule),'success':sum(r['success'] for r in rule),'supported':sum(r['success'] for r in rule if r['decision']=='compile'),'coverage':dict(Counter(r['parser_decision'] for r in rule))}
 rr=rows(OUT/'repair/outcomes.jsonl');ff=rows(OUT/'repair/faults.jsonl');ii=rows(OUT/'repair/injections.jsonl');assert len(rr)==len(ff)==24 and len(ii)==120
 summary['repair']={'n':24,'schedule_valid':sum(r['valid'] for r in rr),'material_valid':sum(r['material_valid'] for r in rr),'mass_valid':sum(r['mass_valid'] for r in rr),'events':sum(r['event_count'] for r in rr),'replan_valid':sum(r['valid'] for r in ff),'preserved':sum(r['preserved'] for r in ff),'active_refused':sum(r['active_refusal']=='IN_FLIGHT_FAILURE' for r in ff),'outage_affected':sum(r['affected'] for r in ff),'added_makespan_s':dict(Counter(r['added_makespan_s'] for r in ff)),'injections':{label:{layer:sum(r[layer+'_detected'] for r in ii if r['error_type']==label) for layer in ['intent','schedule','mass','material']} for label in sorted({r['error_type'] for r in ii})}}
 (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
