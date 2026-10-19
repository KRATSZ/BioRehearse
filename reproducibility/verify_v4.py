"""Independently replay all saved v4 sensitivity plans, without re-solving."""
from pathlib import Path
import argparse,json,gzip,sys,hashlib

def check_metrics(record, plan, graph):
    """Tie reported numerical outcomes to the independently scored saved plan.

    The arithmetic scorer checks plan makespan and cost from task intervals and
    rates. This additional link rejects edits to the raw outcomes table, and
    independently checks the two rounded throughput fields.
    """
    key=(record['case'],record['scenario'])
    for name in ('makespan_s','cost_cny','samples_per_hour','wells_per_hour'):
        assert record.get(name)==plan.get(name), (key,name,'raw/plan mismatch')
    if plan.get('ok'):
        duration=max(row['end_s'] for row in plan['rows'])
        assert duration==record['makespan_s'], (key,'makespan_s','interval mismatch')
        for name,count in [('samples_per_hour',graph['input_samples']),
                           ('wells_per_hour',len(graph['plate_map']))]:
            assert record[name]==round(count*3600/duration,2), (key,name,'throughput mismatch')

def main(paper):
    p=Path(paper).resolve();sys.path[:0]=[str(p/'benchmarks/v4'),str(p/'benchmarks/v2'),str(p/'reproducibility/source-v2')]
    from capacity_sensitivity import modify
    from labscriptai.biofoundry.methods import compile_graph
    from labscriptai.biofoundry.portfolio import prepare_plan
    from scorer import score,states
    records=[json.loads(l) for l in (p/'source-data/v4/capacity/raw.jsonl').read_text().splitlines()];cases={c['id']:c for c in json.loads((p/'benchmarks/v2/workloads.json').read_text())['heldout']};cat=json.loads((p/'source-data/v2/catalog.json').read_text())
    expected={(c,s) for c in cases for s in ['baseline','add_shaker','add_reader']};by={(r['case'],r['scenario']):r for r in records};assert len(by)==len(records)==180 and set(by)==expected
    checked=[];seen=set()
    with gzip.open(p/'source-data/v4/capacity/plans.jsonl.gz','rt') as f:
        for line in f:
            item=json.loads(line);key=(item['case'],item['scenario']);assert key not in seen;seen.add(key);r=by[key];case=cases[key[0]];intent,catalog,_=modify(case['intent'],cat,key[1]);comp=compile_graph(intent,catalog);assert comp['ok'];plan=item['plan'];sc=score(plan,comp['graph'],catalog,case['bookings']);valid=False
            check_metrics(r,plan,comp['graph'])
            if plan.get('ok'):
                prepare_plan(plan,catalog);st=states(plan);valid=bool(sc['valid'] and st['material_valid'] and st['mass_valid'])
            assert valid==r['valid'],key
            assert plan.get('status')==r['status'],key
            checked.append({'case':key[0],'scenario':key[1],'returned':bool(plan.get('ok')),'valid':valid,'status':plan.get('status')})
    assert seen==expected
    summary={s:{'n':sum(r['scenario']==s for r in checked),'valid':sum(r['valid'] for r in checked if r['scenario']==s)} for s in ['baseline','add_shaker','add_reader']}
    print(json.dumps({'outcomes_checked':len(checked),'summary':summary,'all_saved_validity_matches':True,'all_saved_numerical_metrics_match':True,'raw_sha256':hashlib.sha256((p/'source-data/v4/capacity/raw.jsonl').read_bytes()).hexdigest()},indent=2))
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--paper',type=Path,default=Path(__file__).resolve().parents[1]);main(a.parse_args().paper)
