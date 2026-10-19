"""Prospective v2 design. Development and held-out specifications are disjoint."""
import copy,random,json,shutil
from common import PAPER,PROJECT,write,read
BASE={'mode':'simulation','accept_demo_assumptions':True,'deadline_s':28800,'budget_cny':10000,'enabled_devices':['device:19','device:18','device:67','demo:ks4000:1','bench'],'unsupported_requests':[]}

def workload(i,load,tight,deadline,split):
 rng=random.Random((41017 if split=='heldout' else 17291)+i*193);it=copy.deepcopy(BASE);it['deadline_s']=deadline;it['handling_policy']='tight' if tight else 'standard'
 methods=['gfp']+(['bca','picogreen']*((load+1)//2))[:load-1] if load>1 else [rng.choice(['gfp','bca','picogreen'])]
 rng.shuffle(methods);it['experiments']=[{'id':f'E{j+1}','method':m,'samples':1 if m=='gfp' else rng.choice([8,15,23,31]),'replicates':rng.choice([1,2]),'release_s':rng.choice([0,60,180])} for j,m in enumerate(methods)]
 return {'id':f'{split}-{i:03}','split':split,'load':load,'handling_policy':'tight' if tight else 'standard','intent':it,'layout':['compact','linear','separated'][i%3],'bookings':[{'task_id':'external-reader','resource':'device:67','start_s':600,'end_s':1200}] if i%4==1 else []}

def main():
 target=PAPER/'benchmarks/v2/workloads.json'
 if target.exists():raise RuntimeError('Do not overwrite prospective design')
 cap=read(PAPER/'source-data/catalog.json');cap['consumables_inventory'].update(tips200ul=4608,black96=12,clear96=12,tube_1p5ml=96,reservoir_50ml=24)
 write(PAPER/'source-data/v2/catalog.json',cap)
 dev=[workload(i,n,i%2==1,28800,'development') for i,n in enumerate([1,3,6,9,12,3])]
 held=[]
 for load in [1,3,6,9,12]:
  for tight in [False,True]:
   for horizon in [28800,21600]:
    for rep in range(3):held.append(workload(len(held),load,tight,horizon,'heldout'))
 write(target,{'development':dev,'heldout':held,'seed_policy':'independent fixed development/heldout streams; no selection by solver outcome'})
 # Freeze the repair set separately from the larger load benchmark.
 repair=[workload(i+200,3 if i%3 else 6,i%2==0,28800,'repair') for i in range(24)]
 for i,c in enumerate(repair):c['id']=f'repair-{i:03}'
 write(PAPER/'benchmarks/v2/repair.json',repair)
 snap=PAPER/'reproducibility/source-v2/labscriptai';snap.mkdir(parents=True,exist_ok=True);shutil.copy2(PROJECT/'labscriptai/__init__.py',snap/'__init__.py')
 for folder in ['biofoundry','planir']:shutil.copytree(PROJECT/'labscriptai'/folder,snap/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'),dirs_exist_ok=True)
 print('design',len(dev),len(held),len(repair))
if __name__=='__main__':main()
