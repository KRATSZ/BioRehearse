"""Select illustrative case repair-001 for illustrative state-linked panels."""
import sys,copy
from pathlib import Path
PAPER=Path(__file__).resolve().parents[3];sys.path.insert(0,str(PAPER/'benchmarks/v2'))
from common import read,write
from labscriptai.biofoundry.portfolio import replay
p=read(PAPER/'source-data/v2/repair/plans/repair-001.json')
ids=['E3:assemble','E2:read','E3:prepare_plate','E1:read']
times=[next(r for r in p['rows'] if r['id']==key)['process_end_s' if key.endswith(('assemble','prepare_plate')) else 'process_start_s'] for key in ids]
states=[{'task':key,'time_s':t,'state':replay(p,t)} for key,t in zip(ids,times)]
write(PAPER/'source-data/v2/example.json',{'case':'repair-001','plan':p,'frames':states,'note':'Illustrative states selected by named task milestones; no best-case selection.'})
# A missing-water injection is rendered at the last valid state before dilution.
gfp='E3';water=gfp+':WATER';task=next(r for r in p['rows'] if r['id']==gfp+':prepare_plate');before=replay(p,task['process_end_s']-1)
wrong=copy.deepcopy(before);wrong['containers'][water]['location']='device:19';wrong['locations'][water]='device:19'
write(PAPER/'source-data/v2/material-example.json',{'case':'repair-001','time_s':task['process_end_s']-1,'stock':water,'task':task['id'],'correct':before,'injected':wrong,'station_required':'bench','station_wrong':'device:19','note':'Controlled removal of the recorded water movement, preserving all volume transfers.'})
print(times)
