"""Versioned, source-bound methods -> task DAG and the existing component ledger."""
import copy
import math
import re
from .baseline import SOURCES
from .planning import compile_intent
from .workflow import require, Blocked, transfer, totals, validate, liquid_plan
from labscriptai.planir.schema import load_plan
from labscriptai.planir.virtual_deck import evaluate_virtual_deck

METHODS = {
 'gfp':{'id':'genscript.cfxpress.gfp/demo-v2','version':'2.0.0','source':SOURCES['sop'],
    'parameters':{'reaction_ul':50,'mix_ul':45,'DNA_or_water_ul':5,'temperature_c':30,'incubation_s':10800,'excitation_nm':488,'emission_nm':525},
    'basis':'manufacturer incubation and wavelengths; 45+5 recipe, DNA100ng/uL and 5x read dilution are retained demo assumptions'},
 'bca':{'id':'pierce.bca.microplate/v1','version':'1.0.0',
    'source':{'url':'https://assets.thermofisher.com/TFS-Assets/LSG/manuals/MAN0011430_Pierce_BCA_Protein_Asy_UG.pdf','version':'MAN0011430 Rev D','pages':[2,3],'accessed':'2026-10-16'},
    'parameters':{'sample_ul':25,'working_reagent_ul':200,'reagent_A_B_ratio':[50,1],'mix_s':30,'temperature_c':37,'incubation_s':1800,'absorbance_nm':562,
                  'standards_ug_ml':[2000,1500,1000,750,500,250,125,25,0]},
    'basis':'manufacturer microplate protocol; equilibration 300s and post-equilibration read window 600s are conservative planning assumptions (10min note is for tubes)'},
 'picogreen':{'id':'quantit.picogreen.highrange/v2','version':'2.0.0',
    'source':{'url':'https://documents.thermofisher.com/TFS-Assets/LSG/manuals/mp07581.pdf','version':'MAN0001931 Rev A.0','pages':[3,4],'accessed':'2026-10-16'},
    'parameters':{'prediluted_sample_ul':100,'working_reagent_ul':100,'reagent_dilution':200,'incubation_range_s':[120,300],
                  'excitation_nm':480,'emission_nm':520,'standards_final_ng_ml':[1000,100,10,0],'protected_from_light':True},
    'basis':'manufacturer 200uL microplate format, 1:1 addition; all standards pre-diluted manually, avoiding unqualified sub-5uL robot transfers'},
}


def well(i): return f'{chr(65+i//12)}{i%12+1}'


def compile_graph(intent, catalog):
    try:
        require(isinstance(intent,dict),'INVALID_INTENT','JSON object required')
        require(not set(intent)-{'mode','accept_demo_assumptions','deadline_s','budget_cny','enabled_devices','unsupported_requests','experiments','allow_manual_pipetting','handling_policy'},'UNSUPPORTED_REQUEST','Unregistered global method overrides')
        policy=intent.get('handling_policy','standard')
        require(policy in ('standard','tight'),'UNSUPPORTED_REQUEST','Unknown handling policy')
        require(intent.get('accept_demo_assumptions') is True,'MISSING_PARAMETER','Explicit acceptance of simulation costs, timing, carriers and layout assumptions required')
        require(not intent.get('unsupported_requests'), 'UNSUPPORTED_REQUEST',str(intent.get('unsupported_requests')))
        require(isinstance(intent.get('experiments'),list) and 1<=len(intent['experiments'])<=12,'CAPACITY','1–12 experiments')
        deadline=intent.get('deadline_s');budget=intent.get('budget_cny')
        require(type(deadline) is int and 1<=deadline<=28800,'DEADLINE','deadline_s must be 1..28800 seconds after 09:00 Asia/Shanghai (t=0)')
        require(type(budget) in (int,float) and math.isfinite(budget) and 0<budget<=100000,'BUDGET','positive finite CNY budget required')
        require(intent.get('mode','simulation')=='simulation','SIMULATION_ONLY','No hardware scheduler')
        enabled=intent.get('enabled_devices',['device:19','device:18','device:67','demo:ks4000:1','bench'])
        require(isinstance(enabled,list) and all(k in catalog['devices'] for k in enabled),'UNKNOWN_DEVICE','Enabled devices must be existing instances')
        tasks=[]; experiments=[]; containers={}; maps=[]; used=set(); consumables=0; input_samples=0
        def add_container(cid,kind,capacity,volume=0,component=None,parent=None):
            containers[cid]={'id':cid,'kind':kind,'capacity_ul':capacity,'volume_ul':volume,'components_ul':{component:volume} if component else {},
                'sample_ids':[cid] if component and not component.endswith(':WR') else [],'location':cid if parent else 'prep:'+cid,'parent':parent,
                'dead_volume_ul':5 if kind=='stock_tube' else 0,'closure':'open' if kind in ('stock_tube','reaction_tube') else None}
        for spec in intent['experiments']:
            eid=spec.get('id');method=spec.get('method');n=spec.get('samples');rep=spec.get('replicates',1)
            require(isinstance(eid,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}',eid) and eid not in used,'IDENTITY','Unique simple experiment id required');used.add(eid)
            require(method in METHODS,'UNKNOWN_METHOD',str(method))
            require(type(n) is int and n>0 and type(rep) is int and 1<=rep<=4,'CAPACITY','Positive sample count, 1–4 replicates')
            allowed_keys={'id','method','samples','replicates','deadline_s','release_s'}
            require(not set(spec)-allowed_keys,'UNSUPPORTED_REQUEST',f'Unregistered method overrides: {set(spec)-allowed_keys}')
            end=spec.get('deadline_s',deadline);release=spec.get('release_s',0)
            require(type(end) is int and type(release) is int and 0<=release<end<=deadline,'DEADLINE',eid)
            count=2*rep if method=='gfp' else (n+len(METHODS[method]['parameters']['standards_ug_ml' if method=='bca' else 'standards_final_ng_ml']))*rep
            require(n==1 if method=='gfp' else True,'CAPACITY','GFP retains one positive template plus NTC; samples=1, replicates=1..4')
            require(count<=96,'CAPACITY',f'{eid}: {count} wells exceed one 96-well batch; splitting is not yet qualified')
            plate='black96' if method!='bca' else 'clear96';pid=eid+':P01';transfers=[];read_transfers=[];legacy=None
            add_container(pid,'read_plate',0)
            if method=='gfp':
                legacy=compile_intent({'replicates':rep,'accept_demo_defaults':True,'DNA_stock_ng_per_ul':100,'temperature_c':30,'duration_s':10800,'excitation_nm':488,'emission_nm':525,'unsupported_requests':[]})
                require(legacy['ok'],'LEGACY_REGRESSION',str(legacy))
                # Preserve the exact frozen recipe and source reserve, namespaced per experiment.
                for cid,c in legacy['plan']['initial_containers'].items():
                    cc=copy.deepcopy(c);cc['id']=eid+':'+cid;cc['location']='prep:'+cc['id'] if not c['parent'] else cc['id'];cc['parent']=eid+':'+c['parent'] if c['parent'] else None
                    cc['components_ul']={eid+':'+k:v for k,v in c['components_ul'].items()};cc['sample_ids']=[eid+':'+s for s in c['sample_ids']];containers[cc['id']]=cc
                transfers=[[eid+':'+a,eid+':'+b,v] for a,b,v in legacy['plan']['steps'][2]['transfers']]
                read_transfers=[[eid+':'+a,eid+':'+b,v] for a,b,v in legacy['plan']['steps'][6]['transfers']]
                maps.extend([{**w,'experiment':eid,'container':eid+':P01:'+w['well'],'sample_id':eid+':'+w['sample_id']} for w in legacy['plan']['plate_map']])
                consumables+=count*catalog['costs']['gfp_reaction']+15+len(transfers+read_transfers)*catalog['costs']['tip']
            else:
                levels=METHODS[method]['parameters']['standards_ug_ml' if method=='bca' else 'standards_final_ng_ml']
                labels=[(f'std-{v}',v) for v in levels]+[(f'sample-{i+1}',None) for i in range(n)]
                samplevol=25 if method=='bca' else 100;wrvol=200 if method=='bca' else 100
                wr=eid+':WR';add_container(wr,'stock_tube',50000,wrvol*count+50,wr);containers[wr]['labware']='reservoir_50ml'
                for j,(label,level) in enumerate(labels):
                    src=eid+':'+label;add_container(src,'stock_tube',1500,samplevol*rep+20,src)
                    for r in range(rep):
                        w=well(j*rep+r);cid=pid+':'+w;add_container(cid,'well',360,parent=pid)
                        transfers.extend([[src,cid,samplevol],[wr,cid,wrvol]])
                        maps.append({'experiment':eid,'container':cid,'well':w,'sample_id':src,'group':'standard' if level is not None else 'unknown', 'standard_value':level,'replicate':r+1})
                consumables+=catalog['costs'][plate]+catalog['costs']['reservoir_50ml']+count*catalog['costs'][method+'_well']+len(transfers)*catalog['costs']['tip']
            exp={'id':eid,'method':method,'method_id':METHODS[method]['id'],'samples':n,'replicates':rep,'wells':count,'plate':plate,
                 'plate_id':pid,'release_s':release,'deadline_s':end,'legacy':legacy,'manual_inputs':'cellfreeMIX stays opaque and human-prepared' if method=='gfp' else 'human-prepared standards and working reagent; sample matrix compatibility unverified'}
            experiments.append(exp);input_samples+=n*rep
            previous=None
            def task(name,cap,duration,*,container=plate,temperature=None,manual=False,liquid=None,load=30,clean=30,window=None):
                nonlocal previous
                tid=eid+':'+name
                candidates=[k for k in enabled if catalog['devices'][k].get('selectable') and catalog['devices'][k].get('capabilities',{}).get(cap) is True]
                if cap=='liquid' and not intent.get('allow_manual_pipetting',False):candidates=[k for k in candidates if k!='bench']
                item={'id':tid,'experiment':eid,'name':name,'capability':cap,'depends_on':[previous] if previous else [],'candidates':candidates,
                    'container':container,'load_s':load,'process_s':duration,'clean_s':clean,'temperature_c':temperature,'manual':manual,
                    'demand':count,'transfers':liquid or [],'window':window,'plate_id':pid,'release_s':release,'deadline_s':end}
                if cap in ('FI','ABS'):item['optics']={k:v for k,v in METHODS[method]['parameters'].items() if k in ('excitation_nm','emission_nm','absorbance_nm')}
                tasks.append(item);previous=tid;return tid
            task('manual_inputs','manual',180+count*3,manual=True,container='tube_1p5ml' if method=='gfp' else plate,load=0,clean=0)
            assembled=task('assemble','liquid',45+count*8+(30 if method=='bca' else 0),container='tube_1p5ml' if method=='gfp' else plate,liquid=transfers)
            if method=='gfp':
                water_staged=task('stage_dilution_water','manual',5,manual=True,container='tube_1p5ml',load=0,clean=0)
                previous=assembled
            if method in ('gfp','bca'):
                heated=task('incubate','incubate',10800 if method=='gfp' else 1800,container='tube_1p5ml' if method=='gfp' else plate,temperature=30 if method=='gfp' else 37,load=180,clean=60,
                    window={'from':assembled,'max_s':600,'basis':'explicit conservative planning assumption: begin incubation within 10min of assembly completion'})
                task('stop_on_ice' if method=='gfp' else 'equilibrate','manual',60 if method=='gfp' else 300,manual=True,load=0,clean=0,
                    window={'from':heated,'max_s':120 if method=='gfp' else 300,'basis':'explicit planning assumption for prompt cold stop or room-temperature handoff'})
                if method=='gfp':
                    prepared=task('prepare_plate','manual',60+count*12,manual=True,liquid=read_transfers,load=0,clean=0)
                    next(t for t in tasks if t['id']==prepared)['depends_on'].append(water_staged)
                window={'from':previous,'max_s':1800 if method=='gfp' else 600,'basis':'explicit planning assumption; not measured sample stability'}
            else:
                # Room-temperature covered dwell overlaps no instrument; bounded from reagent completion through read start.
                task('dark_incubation','manual',120,manual=False,load=0,clean=0)
                window={'from':assembled,'max_s':300,'min_s':120,'basis':'manufacturer 2–5min dark incubation; read begins within this bound'}
            task('read','ABS' if method=='bca' else 'FI',45+count*2,window=window)
        # Bind physical carriers to each dependency, not merely the next action.
        # In particular dilution water leaves the liquid station on its own edge.
        for exp in experiments:
            eid=exp['id'];own={cid:c for cid,c in containers.items() if cid.startswith(eid+':')}
            tubes=[cid for cid,c in own.items() if c['kind']=='reaction_tube']
            stocks=sorted({a for t in tasks if t['id']==eid+':assemble' for a,b,v in t['transfers']})
            plate_id=exp['plate_id'];water=eid+':WATER'
            for t in (t for t in tasks if t['experiment']==eid):
                name=t['name']
                if name=='manual_inputs':ids=[cid for cid,c in own.items() if not c.get('parent')]
                elif name=='assemble':ids=(tubes if exp['method']=='gfp' else [plate_id])+stocks
                elif name=='stage_dilution_water':ids=[water]
                elif name=='prepare_plate':ids=tubes+[plate_id,water]
                elif exp['method']=='gfp' and name!='read':ids=tubes
                else:ids=[plate_id]
                t['carrier_ids']=list(dict.fromkeys(ids));t['dependency_carriers']={}
                for dep in t['depends_on']:
                    if name=='prepare_plate':carried=[water] if dep.endswith(':stage_dilution_water') else tubes
                    else:carried=t['carrier_ids']
                    t['dependency_carriers'][dep]=carried
        graph={'schema':'biofoundry.taskgraph.v3','mode':'simulation','intent':copy.deepcopy(intent),'methods':copy.deepcopy(METHODS),
            'experiments':experiments,'tasks':tasks,'initial_containers':containers,'plate_map':maps,'budget_cny':budget,'deadline_s':deadline,
            'consumables_cny':round(consumables,2),'input_samples':input_samples,'scope':catalog['scope'],
            'assumptions':['All costs and handling times are estimates, not quotes or benchmarks','Existing library KS4000 is one demo instance, not a verified installed facility device','No measured assay output; manual MIX/standards/carriers require qualification']}
        graph['consumable_usage']={'tips200ul':sum(len(t['transfers']) for t in tasks),'black96':sum(e['plate']=='black96' for e in experiments),
            'clear96':sum(e['plate']=='clear96' for e in experiments),'tube_1p5ml':sum(c['kind']=='reaction_tube' for c in containers.values()),
            'reservoir_50ml':sum(e['method']!='gfp' for e in experiments)}
        for t in tasks:
            if policy=='tight' and t.get('window') and t['name']!='read':
                t['window']['max_s']=min(t['window']['max_s'],360 if t['name']=='incubate' else 110 if t['name']=='stop_on_ice' else 120)
                t['window']['basis']='Explicit tight handling-policy scenario; unmeasured engineering window'
            t['required_labware']=sorted({t['container']}|{containers[a].get('labware','tube_1p5ml') for a,b,v in t['transfers'] if containers[a]['kind']=='stock_tube'})
        for item,amount in graph['consumable_usage'].items():
            require(type(catalog.get('consumables_inventory',{}).get(item)) is int and amount<=catalog['consumables_inventory'][item],
                    'INSUFFICIENT_CONSUMABLES',f'{item}: need {amount}, staged {catalog.get("consumables_inventory",{}).get(item)}')
        # Reuse the original component-balanced liquid ledger without redefining its conservation rules.
        rehearsal=copy.deepcopy(containers);expected=totals(rehearsal)
        planir_batches=0
        for t in tasks:
            for offset in range(0,len(t['transfers']),96):
                batch=t['transfers'][offset:offset+96]
                check=evaluate_virtual_deck(load_plan(liquid_plan(batch,rehearsal,t['id']+f':batch-{offset//96}'))).to_logicpass()
                require(check['outcome']=='pass','PLANIR_CHECK_FAILED',str(check))
                for a,b,v in batch:transfer(rehearsal,a,b,v)
                planir_batches+=1
            validate(rehearsal,expected)
        return {'ok':True,'graph':graph,'checks':{'passed':True,'ledger_conserved':True,'legacy_gfp_preserved':True,'PlanIR_batches_passed':planir_batches,'wells':len(maps),'measurement':None}}
    except (Blocked,KeyError,TypeError,ValueError) as exc:
        return {'ok':False,'code':getattr(exc,'code','INVALID_INTENT'),'detail':str(exc)}


def validate_graph(graph,catalog):
    result=compile_graph(graph.get('intent'),catalog)
    require(result['ok'],result.get('code','INVALID_GRAPH'),result.get('detail',''))
    require(graph==result['graph'],'GRAPH_TAMPERED','Task graph must match the registered method compiler, including recipe, dependencies and claims')
    return result['checks']
