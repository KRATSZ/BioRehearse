"""Existing independent arithmetic scorer plus an independent material-state pass."""
import copy
from common import PAPER
# Load by path to keep the frozen v1 scorer byte-for-byte unchanged.
import importlib.util
spec=importlib.util.spec_from_file_location('arithmetic_v1',PAPER/'benchmarks/scorer.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
score=mod.score;semantic=mod.semantic

def states(plan,strict_location=True):
 c=copy.deepcopy(plan['graph']['initial_containers']);initial={};issues=[];mass=[];events=plan['events']
 def top(cid):
  while c[cid].get('parent'):cid=c[cid]['parent']
  return cid
 def at(cid,station):
  loc=c[top(cid)]['location'];return loc.startswith(station+':') or loc.startswith('staging:'+station+':')
 for x in c.values():
  for k,v in x['components_ul'].items():initial[k]=initial.get(k,0)+v
 snapshots=[]
 for event in events:
  tid=event['task_id'];station=event['source'] if event['kind']=='transfer' else event['resource']
  if event['phase']=='start':
   for cid in event['container_ids']:
    if strict_location and not at(cid,station) and not(tid.endswith(':manual_inputs') and c[top(cid)]['location'].startswith('prep:')):issues.append({'task':tid,'container':cid,'actual':c[top(cid)]['location'],'required':station,'at_s':event['time_s']})
    c[top(cid)]['location']=('transit:'+tid if event['kind']=='transfer' else event['resource'])+':'+top(cid)
  elif event['phase']=='finish':
   for cid in event['container_ids']:c[top(cid)]['location']=('staging:'+event['destination'] if event['kind']=='transfer' else 'staging:'+event['resource'])+':'+top(cid)
  for a,b,v in event.get('transfers',[]):
   for cid in [a,b]:
    if strict_location and not at(cid,event['resource']):issues.append({'task':tid,'container':cid,'actual':c[top(cid)]['location'],'required':event['resource'],'at_s':event['time_s']})
   src,dst=c[a],c[b];old=src['volume_ul']
   if v<0 or v>old-src.get('dead_volume_ul',0)+1e-8 or dst['capacity_ul'] and dst['volume_ul']+v>dst['capacity_ul']+1e-8:mass.append({'task':tid,'source':a,'destination':b,'requested_ul':v});continue
   for k,val in list(src['components_ul'].items()):
    moved=val*v/old if old else 0;src['components_ul'][k]-=moved;dst['components_ul'][k]=dst['components_ul'].get(k,0)+moved
   src['volume_ul']-=v;dst['volume_ul']+=v
  totals={}
  for x in c.values():
   for k,v in x['components_ul'].items():totals[k]=totals.get(k,0)+v
  if any(abs(totals.get(k,0)-v)>1e-7 for k,v in initial.items()):mass.append({'task':tid,'reason':'component total changed'})
  snapshots.append({'time_s':event['time_s'],'task_id':tid,'phase':event['phase'],'volumes_ul':{k:v['volume_ul'] for k,v in c.items()},'locations':{k:c[top(k)]['location'] for k in c}})
 return {'material_valid':not issues,'mass_valid':not mass,'location_issues':issues,'mass_issues':mass,'event_count':len(events),'snapshots':snapshots}
