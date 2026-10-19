"""Two-model v2 harness evaluation with a shared conservative account budget gate."""
import argparse,json,os,re,subprocess,time,threading,math
from concurrent.futures import ThreadPoolExecutor
from common import PAPER,PROJECT,read,write,emit,frozen,digest
from scorer import semantic
from labscriptai.biofoundry.methods import METHODS
LOCK=threading.Lock()
ACCOUNT_ORIGIN=None
ALLOWED_DECREASE=None

def provider(path):
 code="import {loadDemoEnv} from './server/src/env.ts';const e=loadDemoEnv();if(new URL(e.baseUrl).hostname!=='api.deepseek.com')throw Error('Unknown billing host');const r=await fetch(e.baseUrl+process.argv[1],{headers:{Authorization:'Bearer '+e.apiKey},signal:AbortSignal.timeout(20000)});if(!r.ok)throw Error('Provider HTTP '+r.status);console.log(JSON.stringify(await r.json()));"
 p=subprocess.run(['node','--import','tsx','--input-type=module','-e',code,path],cwd=PROJECT/'labscriptai/webdemo',capture_output=True,text=True,timeout=30,check=True)
 return json.loads(p.stdout)
def balance():return float(next(r for r in provider('/user/balance')['balance_infos'] if r['currency']=='CNY')['total_balance'])
def rule(text):
 # The pre-existing controlled grammar, without a special negative-case marker.
 budget=re.search(r'Operating budget CNY (\d+)',text);duration=re.search(r'finish within (\d+) hours',text)
 if not budget or not duration:return None
 experiments=[]
 for m in re.finditer(r'CFXpress GFP with one positive template and NTC, (\d+) replicates per group|Pierce BCA with (\d+) unknown samples, (\d+) replicates|Quant-iT PicoGreen with (\d+) unknown samples, (\d+) replicates',text):
  g,b,br,p,pr=m.groups();experiments.append({'id':f'J{len(experiments)+1}','method':'gfp' if g else 'bca' if b else 'picogreen','samples':1 if g else int(b or p),'replicates':int(g or br or pr),'release_s':3600 if 'No experiment may start before 10:00.' in text else 0})
 if not experiments:return None
 return {'mode':'simulation','accept_demo_assumptions':True,'deadline_s':int(duration.group(1))*3600,'budget_cny':int(budget.group(1)),'enabled_devices':['device:19','device:18','device:67','demo:ks4000:1','bench'],'unsupported_requests':[],'experiments':experiments}
def correct(case,data,error):
 if error:return False
 if case['decision']=='compile':return bool(data.get('ok')) and semantic(data.get('generated',{}).get('graph',{}).get('intent'),case['expected'])
 if case['decision']=='clarify':
  fields=data.get('clarification',{}).get('missing_fields',[]) if data.get('clarification') else []
  aliases={'budget_cny':['budget_cny','budget','operating_budget'],'deadline_s':['deadline_s','deadline','completion_deadline'],'samples':['samples','sample_count','unknown_samples'],'replicates':['replicates','replicate_count'],'conflicting_constraints':['conflicting_constraints','deadline_s','deadline','time_reference'],'accept_demo_assumptions':['accept_demo_assumptions','assumption_acceptance','assumptions']}
  return data.get('code')=='CLARIFICATION_REQUIRED' and any(f in aliases[case['missing_field']] for f in fields) and bool(data.get('clarification',{}).get('question'))
 if data.get('code')!='BLOCKED' or data.get('ok'):return False
 starts={e['toolCallId']:e.get('args',{}) for e in data.get('trace',[]) if e.get('type')=='tool_execution_start' and e.get('toolName')=='compile_experiment_graph'}
 reasons={'bca_temperature':r'25|bca.*temperature','gfp_temperature':r'45|gfp.*temperature','pcr':r'\bpcr\b','manual_assembly':r'manual.*assembl|hand.*pipett|人工|手工','unknown_device':r'device:99|unregistered.*reader','raman':r'raman|拉曼','elisa':r'elisa','light':r'bright|light|光','no_control':r'no.template|ntc|对照','mix_recipe':r'mix|composition|成分','no_standards':r'standard|标准','volume':r'500|volume|体积'}
 for event in data.get('trace',[]):
  if event.get('type')!='tool_execution_end' or event.get('toolName')!='compile_experiment_graph':continue
  args=starts.get(event.get('toolCallId'),{});payload=event.get('result',{}).get('details',{}).get('payload',{})
  text=' '.join(args.get('unsupported_requests',[]))
  if payload.get('ok') is False and payload.get('code') in ['UNSUPPORTED_REQUEST','UNKNOWN_DEVICE'] and text and re.search(reasons[case['unsupported_reason']],text,re.I):return True
 return False
def worker(model,split,cases,repeats):
 out=PAPER/'source-data/v2'/split/'language'/model;out.mkdir(parents=True,exist_ok=True);target=out/'scores.jsonl'
 if target.exists():raise RuntimeError('Language evidence exists; do not overwrite')
 for case in cases:
  for repeat in range(3 if split=='heldout' and case['id'] in repeats else 1):
   if split=='heldout':frozen(live=True)
   with LOCK:
    current=balance()
    # Public release: caller supplies a fresh budget; no private account balance.
    if ACCOUNT_ORIGIN is None or ALLOWED_DECREASE is None:raise RuntimeError('Set an explicit fresh study budget through main')
    if ACCOUNT_ORIGIN-current>=ALLOWED_DECREASE:raise RuntimeError('Explicit inference budget reached; offline work continues')
   started=time.perf_counter();data={};error=None;environment=os.environ.copy();environment.update(LABSCRIPTAI_DEEPSEEK_MODEL=model,DEEPSEEK_MODEL=model)
   payload={'mode':'portfolio','request':case['request'],'sources':{'methods':METHODS,'catalog':read(PAPER/'source-data/catalog.json')}}
   try:
    r=subprocess.run(['node','--import','tsx','server/src/biofoundry-author.ts'],cwd=PROJECT/'labscriptai/webdemo',input=json.dumps(payload),capture_output=True,text=True,timeout=180,env=environment)
    if r.returncode:raise RuntimeError(r.stderr[-1000:])
    data=json.loads(r.stdout)
   except Exception as exc:error=repr(exc)
   raw=out/f'{case["id"]}-r{repeat}.json';write(raw,{'result':data,'error':error,'wall_s':time.perf_counter()-started})
   usages=[e['message']['usage'] for e in data.get('trace',[]) if e.get('type')=='message_end' and e.get('message',{}).get('role')=='assistant' and e['message'].get('usage')]
   rec={'case':case['id'],'cluster':case['cluster'],'style':case['style'],'decision':case['decision'],'model':model,'repeat':repeat,'success':correct(case,data,error),'accepted':bool(data.get('ok')),'code':data.get('code'),'wall_s':time.perf_counter()-started,'error':error,'raw_file':str(raw.relative_to(PAPER)),'model_responses':len(usages),'tool_proposals':sum(1 for e in data.get('trace',[]) if e.get('type')=='tool_execution_start')}
   rec.update({k:sum(u.get(v,0) for u in usages) for k,v in [('input_tokens','input'),('cache_read_tokens','cacheRead'),('output_tokens','output'),('reasoning_tokens','reasoning'),('total_tokens','totalTokens')]})
   rec['response_models']=sorted({e['message']['responseModel'] for e in data.get('trace',[]) if e.get('type')=='message_end' and e.get('message',{}).get('responseModel')})
   emit(target,rec);print(model,case['id'],repeat,rec['success'],rec['code'],flush=True)
 return model

def main():
 global ACCOUNT_ORIGIN,ALLOWED_DECREASE
 ap=argparse.ArgumentParser();ap.add_argument('--max-spend-cny',type=float,required=True);ap.add_argument('--split',choices=['development','heldout'],required=True);ap.add_argument('--model',choices=['deepseek-flash','deepseek-v4-pro','both'],default='both');ap.add_argument('--development-limit',type=int,default=0);args=ap.parse_args()
 if not math.isfinite(args.max_spend_cny) or args.max_spend_cny<=0:raise ValueError('Budget must be positive')
 ALLOWED_DECREASE=args.max_spend_cny-min(1,args.max_spend_cny/10)
 if args.split=='heldout':frozen(live=True)
 spec=read(PAPER/'benchmarks/v2/language.json');cases=spec[args.split]
 if args.split=='development' and args.development_limit:cases=cases[:args.development_limit]
 models=spec['models'] if args.model=='both' else [args.model];available={r['id'] for r in provider('/models')['data']};assert set(models)<=available
 before=balance();ACCOUNT_ORIGIN=before;write(PAPER/'.aris/v2-private-balance-before.json',{'balance_cny':before,'models':models})
 rulefile=PAPER/'source-data/v2'/args.split/'language/rules.jsonl'
 if not rulefile.exists():
  rulefile.parent.mkdir(parents=True,exist_ok=True)
  for case in cases:
   intent=rule(case['request']);emit(rulefile,{'case':case['id'],'cluster':case['cluster'],'style':case['style'],'decision':case['decision'],'parser_decision':'compile' if intent else 'abstain','success':case['decision']=='compile' and intent is not None and semantic(intent,case['expected']),'accepted':intent is not None})
 with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda m:worker(m,args.split,cases,spec['extra_repeat_ids']),models))
 write(PAPER/'.aris/v2-private-balance-after.json',{'balance_cny':balance()})
if __name__=='__main__':main()
