"""Plate protocol -> checked ledger -> central-arm island animation, simulation only."""
import copy
import json
import math
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from .workflow import Blocked,require,transfer,totals,validate,write_json

ACTIONS={'dispense':'bravo','incubate':'incubator','wash':'washer','pcr':'pcr','read':'reader','wait':'input'}
LABELS={'dispense':'Dispense','incubate':'Incubate & shake','wash':'Wash plate','pcr':'PCR program preview','read':'Read plate','wait':'Wait at input'}
EXAMPLES={
 'linked':{'mode':'simulation','accept_demo_assumptions':True,'title':'Multi-device workflow','plate_type':'clear96','wells':8,'initial_ul':50,
   'steps':[{'id':'dispense','action':'dispense','duration_s':90,'volume_ul':100},{'id':'incubate','action':'incubate','duration_s':1800,'temperature_c':37},
            {'id':'wash','action':'wash','duration_s':120,'volume_ul':100},{'id':'read','action':'read','duration_s':60,'wavelength_nm':562}],'unsupported_requests':[]},
 'bca':{'mode':'simulation','accept_demo_assumptions':True,'title':'Pierce BCA preview','plate_type':'clear96','wells':30,'initial_ul':25,
   'steps':[{'id':'add_WR','action':'dispense','duration_s':120,'volume_ul':200},{'id':'incubate','action':'incubate','duration_s':1800,'temperature_c':37},
            {'id':'equilibrate','action':'wait','duration_s':300},{'id':'read','action':'read','duration_s':60,'wavelength_nm':562}],'unsupported_requests':[]},
 'picogreen':{'mode':'simulation','accept_demo_assumptions':True,'title':'PicoGreen DNA preview','plate_type':'black96','wells':24,'initial_ul':100,
   'steps':[{'id':'add_dye','action':'dispense','duration_s':60,'volume_ul':100},{'id':'develop','action':'wait','duration_s':300},
            {'id':'read','action':'read','duration_s':60,'excitation_nm':480,'emission_nm':520}],'unsupported_requests':[]},
 'pcr':{'mode':'simulation','accept_demo_assumptions':True,'title':'PCR to fluorescence preview','plate_type':'pcr96','wells':8,'initial_ul':50,
   'steps':[{'id':'thermal_program','action':'pcr','duration_s':3600,'temperature_c':95},{'id':'read','action':'read','duration_s':60,'excitation_nm':488,'emission_nm':525}],
   'unsupported_requests':[]},
}


def compile_protocol(intent):
    try:
        require(isinstance(intent,dict),'INVALID_PROTOCOL','Provide one plate protocol as a JSON object')
        require(set(intent)<={'mode','accept_demo_assumptions','title','plate_type','wells','initial_ul','steps','unsupported_requests'},'UNSUPPORTED_PARAMETER','Unknown top-level protocol field')
        require(intent.get('mode')=='simulation' and intent.get('accept_demo_assumptions') is True,'SIMULATION_ONLY','Accept explicit digital interface, timing and carrier assumptions')
        require(not intent.get('unsupported_requests'),'UNSUPPORTED_REQUEST',str(intent.get('unsupported_requests')))
        require(isinstance(intent.get('title'),str) and 0<len(intent['title'])<=200,'INVALID_TITLE','Protocol title required')
        count=intent.get('wells');volume=intent.get('initial_ul');plate_type=intent.get('plate_type')
        require(type(count) is int and 1<=count<=96,'CAPACITY','One plate, 1–96 wells supported')
        require(type(volume) in (int,float) and math.isfinite(volume) and 0<=volume<=200,'VOLUME','initial_ul must be 0–200')
        require(plate_type in ('clear96','black96','pcr96'),'CONTAINER','Unsupported plate type')
        require(isinstance(intent.get('steps'),list) and 1<=len(intent['steps'])<=16,'CAPACITY','1–16 sequential operations supported')
        containers={};plate_map=[]
        def container(cid,kind,capacity,amount=0,component=None,parent=None):
            containers[cid]={'id':cid,'kind':kind,'location':cid if parent else 'input:'+cid,'capacity_ul':capacity,'volume_ul':amount,
                'components_ul':{component:amount} if component and amount else {},'sample_ids':[cid] if kind=='well' else [],'parent':parent,
                'dead_volume_ul':0,'closure':'open' if kind=='stock_tube' else None}
        container('P01','read_plate',0);container('WASTE','stock_tube',1000000)
        for i in range(count):
            w=f'{chr(65+i//12)}{i%12+1}';cid='P01:'+w;container(cid,'well',200 if plate_type=='pcr96' else 360,volume,'sample:'+w,parent='P01');plate_map.append({'well':w,'sample_id':'sample:'+w,'container':cid})
        steps=[];seen=set();running=volume
        for spec in intent['steps']:
            require(isinstance(spec,dict) and set(spec)<={'id','action','duration_s','volume_ul','temperature_c','wavelength_nm','excitation_nm','emission_nm'},'UNSUPPORTED_PARAMETER','Unregistered step field')
            sid=spec.get('id');action=spec.get('action');duration=spec.get('duration_s')
            require(isinstance(sid,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,30}',sid) and sid not in seen and sid != 'return','IDENTITY','Unique simple step IDs required');seen.add(sid)
            require(action in ACTIONS,'UNKNOWN_ACTION',str(action))
            require(type(duration) in (int,float) and math.isfinite(duration) and 0<duration<=21600,'DURATION','Explicit operation duration in seconds required')
            temp=spec.get('temperature_c');v=spec.get('volume_ul');transfers=[]
            if action=='incubate':require(temp in (30,37),'TEMPERATURE','Prototype KS4000 carrier is explicitly configured only at 30 or 37°C')
            elif action=='pcr':
                require(plate_type=='pcr96','CONTAINER','PCR action needs pcr96 plate; do not relabel an assay plate')
                require(type(temp) in (int,float) and math.isfinite(temp) and 4<=temp<=100,'TEMPERATURE','Provide a temperature within the explicit 4–100°C digital preview range')
            else:require(temp is None,'UNSUPPORTED_PARAMETER','Temperature field is only valid for incubation/PCR')
            if action in ('dispense','wash'):
                require(type(v) in (int,float) and math.isfinite(v) and 5<=v<=200,'PIPETTING_RANGE','Explicit 5–200 µL addition/replacement per well required')
                if action=='wash':require(5<=running<=200,'WASH_VOLUME','Digital washer requires 5–200 µL starting volume to preserve waste ledger')
                stock=sid+':REAGENT';container(stock,'stock_tube',50000,count*v+50,stock)
                for row in plate_map:
                    if action=='wash':transfers.append([row['container'],'WASTE',running])
                    transfers.append([stock,row['container'],v])
                running=v if action=='wash' else running+v
                require(running<=containers['P01:A1']['capacity_ul'],'OVERFLOW','Well capacity exceeded by the protocol')
            else:require(v is None,'UNSUPPORTED_PARAMETER','Volume field applies only to dispense/wash')
            optical=[spec.get(k) for k in ('wavelength_nm','excitation_nm','emission_nm')]
            if action=='read':
                wavelength,ex,em=optical
                require((type(wavelength) in (int,float) and math.isfinite(wavelength) and 230<=wavelength<=1000 and ex is None and em is None) or
                        (wavelength is None and all(type(x) in (int,float) and math.isfinite(x) and 250<=x<=850 for x in (ex,em))),'OPTICS','Provide absorbance wavelength OR excitation/emission, within digital preview limits')
            else:require(all(x is None for x in optical),'UNSUPPORTED_PARAMETER','Optical settings only apply to read')
            steps.append({**copy.deepcopy(spec),'station':ACTIONS[action],'label':LABELS[action],'transfers':transfers,'depends_on':[steps[-1]['id']] if steps else []})
        initial=copy.deepcopy(containers);expected=totals(initial)
        for step in steps:
            for a,b,v in step['transfers']:transfer(containers,a,b,v)
            validate(containers,expected)
        return {'ok':True,'protocol':{'schema':'biofoundry.island.protocol.v1','intent':copy.deepcopy(intent),'title':intent['title'],
            'plate':{'id':'P01','type':plate_type,'wells':count},'steps':steps,'initial_containers':initial,'plate_map':plate_map,
            'mode':'simulation','scope':'digital integration preview; sample/reagent premix manual; no calibrated instrument method, collision or hardware certification',
            'unknowns':['Exact facility robot identity and device loading coordinates','Robot mounts, plate adapters and gripper load/force','Complete assay calibration or PCR thermal program','Physical collision and biological performance']},
            'checks':{'passed':True,'ledger_conserved':True,'final_well_ul':running,'measurement':None,'hardware_validated':False}}
    except (Blocked,KeyError,TypeError,ValueError,OverflowError) as exc:return {'ok':False,'code':getattr(exc,'code','INVALID_PROTOCOL'),'detail':str(exc)}


def build(intent,output):
    compiled=compile_protocol(intent)
    if not compiled['ok']:return compiled
    from .app import settings
    virtual=settings()[1];sys.path.insert(0,str(virtual))
    from sim.island_preview import motion_plan
    try:plan=motion_plan(output,compiled['protocol'])
    except (ValueError,AssertionError) as exc:return {'ok':False,'code':'MOTION_BLOCKED','detail':str(exc)}
    containers=copy.deepcopy(plan['protocol']['initial_containers']);expected=totals(containers)
    def ledger():return {'well_ul':containers['P01:A1']['volume_ul'],'waste_ul':containers['WASTE']['volume_ul'],'component_totals_ul':totals(containers),'conserved':True}
    plan['initial_ledger']=ledger()
    for event in plan['events']:
        if 'liquid_start_s' in event:event['ledger_before']=ledger()
        for a,b,v in event.get('transfers',[]):transfer(containers,a,b,v)
        validate(containers,expected)
        if event['kind']=='operation_complete':event['ledger']=ledger()
    plan['example_key']=next((name for name,example in EXAMPLES.items() if intent==example),None)
    plan['ledger_checks']=compiled['checks'];plan['id']=str(uuid.uuid4());directory=Path(output)/'island'/'runs'/plan['id'];directory.mkdir(parents=True)
    write_json(directory/'plan.json',plan);(directory/'events.jsonl').write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in plan['events']))
    write_json(Path(output)/'island/latest.json',plan);return plan


def replay(plan,at):
    from sim.island_preview import sample_motion
    state=sample_motion(plan,at);at=state['t'];containers=copy.deepcopy(plan['protocol']['initial_containers']);expected=totals(containers)
    for event in plan['events']:
        if event['t']>at:
            start=event.get('liquid_start_s');end=event.get('liquid_end_s')
            if start is not None and at>start:
                fraction=min(1.,(at-start)/(end-start))
                for a,b,v in event.get('transfers',[]):transfer(containers,a,b,v*fraction)
                validate(containers,expected)
            break
        if event['kind'] in ('grasp','release'):containers['P01']['location']=event['owner']+':P01'
        for a,b,v in event.get('transfers',[]):transfer(containers,a,b,v)
        validate(containers,expected)
    return {**state,'containers':containers,'measurement':None,'component_totals_ul':totals(containers),
        'ledger':{'well_ul':containers['P01:A1']['volume_ul'],'waste_ul':containers['WASTE']['volume_ul'],'component_totals_ul':totals(containers),'conserved':True}}


def generate(request,output):
    from .app import ROOT
    require(isinstance(request,str) and 0<len(request)<=12000,'INVALID_REQUEST','Provide a protocol of 1–12000 characters')
    directory=Path(output)/'island/generations'/str(uuid.uuid4());directory.mkdir(parents=True)
    try:
        p=subprocess.run([shutil.which('node') or 'node','--import','tsx','server/src/biofoundry-author.ts'],cwd=ROOT/'labscriptai/webdemo',
            input=json.dumps({'mode':'island','request':request,'sources':{'actions':ACTIONS,'scope':'single 96-well plate protocol; digital integration, existing assets only'}}),capture_output=True,text=True,timeout=240)
        result=json.loads(p.stdout) if p.returncode==0 else {'ok':False,'detail':p.stderr[-1800:]}
    except subprocess.TimeoutExpired:result={'ok':False,'detail':'Model timeout after 240 seconds'}
    write_json(directory/'generation.json',result)
    if result.get('ok'):
        plan=build(result['generated']['protocol']['intent'],output);result['ok']=plan['ok'];result['plan']=plan
        if plan['ok']:
            plan['request_text']=request
            plan['generation']={'model':result['model'],'provider':result['provider'],'directory':str(directory),'attempts':result['attempts']}
            write_json(Path(output)/'island/latest.json',plan);write_json(directory/'preview.json',plan)
    result['directory']=str(directory);return result
