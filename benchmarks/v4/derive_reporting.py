"""Recreate the v4 paired-capacity, utilization and water-recovery source tables.
No solver calls, prices or physical observations are introduced here.
"""
from pathlib import Path
import json,csv,statistics,math,argparse
from collections import defaultdict

def main(paper):
    p=Path(paper).resolve();root=p/'source-data/v4';rr=[json.loads(l) for l in (root/'capacity/raw.jsonl').read_text().splitlines()]
    by={(r['case'],r['scenario']):r for r in rr};assert len(by)==180
    pairs=[]
    for case in sorted({r['case'] for r in rr}):
        b=by[case,'baseline']
        for sc in ['add_shaker','add_reader']:
            r=by[case,sc]
            if b['valid'] and r['valid']:
                pairs.append({'case':case,'load':r['load'],'scenario':sc,'makespan_reduction_pct':100*(1-r['makespan_s']/b['makespan_s']),'cost_change_cny':r['cost_cny']-b['cost_cny'],'EPI_reduction_pct':100*(1-math.sqrt(r['makespan_s']*r['cost_cny']/(b['makespan_s']*b['cost_cny'])))})
    with (root/'capacity/paired-economics.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(pairs[0]));w.writeheader();w.writerows(pairs)
    uu=defaultdict(list)
    with (root/'economics/utilization.csv').open() as f:
        for r in csv.DictReader(f):
            if r['method']=='cp_sat' and r['objective']=='fastest' and r['valid']=='True' and r['repeat']=='0' and r['resource'] in ['demo:ks4000:1','device:67','operator']:
                uu[r['resource']].append(float(r['utilization_fraction']))
    util={k:{'n':len(v),'median':statistics.median(v),'min':min(v),'max':max(v)} for k,v in uu.items()}
    (root/'economics/utilization-summary.json').write_text(json.dumps(util,indent=2))
    e=json.loads((p/'source-data/v2/example.json').read_text())['plan'];rows=[r for r in e['rows'] if 'stage_dilution_water' in r['id']]
    assert sum(r['duration_s'] for r in rows)==34
    out={'basis':'conditional recovery scenario, no realized savings','water_branch':{'operator_seconds':sum(r['duration_s'] for r in rows),'nominal_cost_cny':sum(r['cost_cents'] for r in rows)/100,'source':'source-data/v2/example.json','rows':rows},'expected_avoided_cost_formula':'prevalence * probability_unrecoverable * repeat_cost - rehearsal_and_review_cost','unobserved':['natural error prevalence','late recovery success','actual reagent invoices','real tariffs','operator measurement','biological failure probability'],'do_not_assume':'Missing dilution water can be manually staged; it does not by itself imply loss of the preceding 3-hour expression incubation.'}
    (root/'economics/recovery-scenarios.json').write_text(json.dumps(out,indent=2))
    print(json.dumps({'capacity_paired_rows':len(pairs),'utilization':util,'water_branch_seconds':34,'nominal_water_branch_CNY':out['water_branch']['nominal_cost_cny']},indent=2))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--paper',type=Path,default=Path(__file__).resolve().parents[2]);main(ap.parse_args().paper)
