"""Targeted pre-freeze regressions; development cases only."""
import sys,copy
from common import PROJECT,PAPER,read
# Exercise actual production, not the still-staged offline snapshot.
sys.path.insert(0,str(PROJECT))
from labscriptai.biofoundry.methods import compile_graph
from labscriptai.biofoundry.scheduling import solve,replan
from labscriptai.biofoundry.portfolio import prepare_plan
from scorer import score,states

def test_outage_over_existing_booking():
 case=read(PAPER/'benchmarks/v2/workloads.json')['development'][1];cat=read(PAPER/'source-data/v2/catalog.json')
 graph=compile_graph(case['intent'],cat)['graph'];p=solve(graph,cat,case['layout'],bookings=case['bookings'],time_limit_s=2)
 assert p['ok']
 q=replan(p,cat,1,'device:67',3600,case['bookings']);assert q['ok'],q
 assert [(r['start_s'],r['end_s']) for r in q['calendar_blocks']]==[(1,600),(1200,3600)]
 assert score(q,graph,cat,case['bookings']+q['calendar_blocks'])['valid']
 prepare_plan(q,cat);assert states(q)['material_valid']
 for old in p['rows']:
  if old['start_s']<=1:
   new=next(r for r in q['rows'] if r['id']==old['id']);assert all(old[k]==new[k] for k in ['resource','start_s','end_s'])

def test_missing_water_has_distinct_state_error():
 case=read(PAPER/'benchmarks/v2/workloads.json')['development'][1];cat=read(PAPER/'source-data/v2/catalog.json')
 graph=compile_graph(case['intent'],cat)['graph'];p=prepare_plan(solve(graph,cat,case['layout'],bookings=case['bookings']),cat)
 gfp=next(e for e in graph['experiments'] if e['method']=='gfp');water=gfp['id']+':WATER';end=next(r for r in p['rows'] if r['id']==gfp['id']+':assemble')['end_s']
 for event in p['events']:
  if event['time_s']>end:event['container_ids']=[c for c in event['container_ids'] if c!=water]
 assert score(p,graph,cat,case['bookings'])['valid']
 audit=states(p);assert audit['mass_valid'] and not audit['material_valid']
 assert any(water in str(issue) for issue in audit['location_issues'])
