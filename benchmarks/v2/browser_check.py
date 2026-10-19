"""Secondary cross-language state-field check, distinct from geometric validation."""
import copy,gzip,json,hashlib,subprocess,shutil
from common import PAPER,VLAB,read,write
from labscriptai.biofoundry.portfolio import replay

def main():
 src=VLAB/'web/plan-state.js';dst=PAPER/'reproducibility/plan-state-v2.mjs';shutil.copy2(src,dst)
 runner="import fs from 'node:fs';const {replay}=await import(process.argv[1]);const p=JSON.parse(fs.readFileSync(0,'utf8'));for(const t of p.times)console.log(JSON.stringify(replay(p.plan,t)));"
 result=[]
 with gzip.open(PAPER/'source-data/v2/browser-states.jsonl.gz','wt') as output:
  for path in sorted((PAPER/'source-data/v2/repair/plans').glob('*.json')):
   p=read(path);boundaries=sorted({0,p['makespan_s']}|{e['time_s'] for e in p['events']});times=sorted(set(boundaries+[(a+b)/2 for a,b in zip(boundaries,boundaries[1:])]))
   proc=subprocess.run(['node','--input-type=module','-e',runner,dst.as_uri()],input=json.dumps({'plan':p,'times':times}),text=True,capture_output=True,check=True)
   states=[json.loads(line) for line in proc.stdout.splitlines()];assert len(states)==len(times);error=0;locations=0;actions=0;identity=0
   for t,actual in zip(times,states):
    expected=replay(p,t);identity+=actual['plan_id']!=expected['plan_id'] or actual['event_count']!=expected['event_count'];locations+=actual['locations']!=expected['locations'];actions+=actual['device_states']!=expected['device_states']
    for cid,c in expected['containers'].items():
     a=actual['containers'][cid];error=max(error,abs(a['volume_ul']-c['volume_ul']),*[abs(a['components_ul'].get(k,0)-c['components_ul'].get(k,0)) for k in set(a['components_ul'])|set(c['components_ul'])])
    output.write(json.dumps({'case':path.stem,'time_s':t,'javascript':actual},ensure_ascii=False)+'\n')
   result.append({'case':path.stem,'timestamps':len(times),'max_volume_component_difference_ul':error,'location_differences':locations,'action_differences':actions,'identity_differences':identity})
 summary={'scope':'Post-study secondary audit of state fields, not pixels, collisions or hardware','source':'web/plan-state.js','sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'plans':len(result),'timestamps':sum(r['timestamps'] for r in result),'max_volume_component_difference_ul':max(r['max_volume_component_difference_ul'] for r in result),'location_differences':sum(r['location_differences'] for r in result),'action_differences':sum(r['action_differences'] for r in result),'identity_differences':sum(r['identity_differences'] for r in result),'results':result};write(PAPER/'source-data/v2/browser-summary.json',summary);print(json.dumps(summary))
if __name__=='__main__':main()
