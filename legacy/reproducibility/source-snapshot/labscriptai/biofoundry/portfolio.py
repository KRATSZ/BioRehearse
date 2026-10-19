"""Natural-language authoring, reproducible examples, checked event playback and CLI service."""
import copy
import hashlib
import json
import math
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from .workflow import require, transfer, totals, validate, write_json, Run, complete
from .capabilities import catalog, ACTION_FOR, actions_for
from .methods import compile_graph
from .scheduling import compare, solve, replan, validate_schedule
from .reservations import Reservations

EXAMPLE = {'mode':'simulation','accept_demo_assumptions':True,'deadline_s':25200,'budget_cny':1500,
    'enabled_devices':['device:19','device:18','device:67','demo:ks4000:1','bench'],
    'unsupported_requests':[], 'experiments':[{'id':'GFP','method':'gfp','samples':1,'replicates':3},
        {'id':'BCA','method':'bca','samples':6,'replicates':2},{'id':'DNA','method':'picogreen','samples':6,'replicates':2}]}
LIVE_REQUEST = '请为同一天的三个独立实验编排并预演：GenScript CFXpress GFP 一个阳性模板加无模板对照，各3个重复；Pierce BCA 六个未知样本，各2个重复并保留厂家9个标准；Quant-iT PicoGreen 六个未知样本，各2个重复并保留5个标准。09:00开始，7小时内完成，运行预算1500元人民币。我明确接受数字演示的耗时、成本、温控载架及假设布局参数，cellfreeMIX和标准品由人配置，允许人工转运。只使用现有 device:19 Fluent1080、device:18 Fluent780、device:67 iD5、demo:ks4000:1 和 bench；请通过工具生成通用任务图，不改变注册方法条件。'


def carriers(graph,row):
    eid=row['experiment'];spec=next(e for e in graph['experiments'] if e['id']==eid)
    target=row.get('to_task',row['id']).split(':')[-1]
    if spec['method']=='gfp' and target not in ('read','prepare_plate'):
        ids=[c for c,v in graph['initial_containers'].items() if c.startswith(eid+':') and v['kind']=='reaction_tube']
    else:ids=[spec['plate_id']]
    if target=='assemble':ids += sorted({a for t in graph['tasks'] if t['id']==eid+':assemble' for a,b,v in t['transfers']})
    if target=='prepare_plate':ids += [c for c,v in graph['initial_containers'].items() if c.startswith(eid+':') and v['kind']=='reaction_tube']
    return list(dict.fromkeys(ids))


def events_for(plan):
    events=[]
    for r in plan['rows']:
        for phase,at in [('start',r['start_s']),('finish',r['end_s'])]:
            events.append({'time_s':at,'phase':phase,'task_id':r['id'],'experiment':r['experiment'],'kind':r['kind'],
                'resource':r['resource'],'source':r.get('source'),'destination':r.get('destination'),
                'container_ids':carriers(plan['graph'],r),'transfers':[],
                'simulated':True,'actor':'digital-rehearsal; human work represented, no physical acknowledgement','measurement':None})
        if r.get('transfers'):
            events.append({'time_s':r['process_end_s'],'phase':'liquid_complete','task_id':r['id'],'experiment':r['experiment'],
                'kind':r['kind'],'resource':r['resource'],'container_ids':carriers(plan['graph'],r),'transfers':r['transfers'],
                'simulated':True,'actor':'digital-rehearsal','measurement':None})
    # End events release a device before same-time starts acquire it.
    return sorted(events,key=lambda e:(e['time_s'],0 if e['phase']=='finish' else 1,e['task_id']))


def replay(plan,at_s=None):
    require(at_s is None or type(at_s) in (int,float) and math.isfinite(at_s) and 0<=at_s<=plan['makespan_s'],
            'REPLAY_TIME','Replay time must be finite and inside this plan')
    graph=plan['graph'];containers=copy.deepcopy(graph['initial_containers']);expected=totals(containers);active={};applied=[]
    for e in plan['events']:
        if at_s is not None and e['time_s']>at_s:break
        tid=e['task_id']
        if e['phase']=='start':
            active[tid]=e
            location=('transit:'+tid if e['kind']=='transfer' else e['resource'])
            for cid in e['container_ids']:containers[cid]['location']=location+':'+cid
            if tid.endswith(':incubate'):
                for cid in e['container_ids']:
                    if containers[cid]['kind']=='reaction_tube':containers[cid]['closure']='closed'
            if tid.endswith(':prepare_plate'):
                for cid in e['container_ids']:
                    if containers[cid]['kind']=='reaction_tube':containers[cid]['closure']='open'
        elif e['phase']=='finish':
            active.pop(tid,None)
            location='staging:'+e['destination'] if e['kind']=='transfer' else 'staging:'+e['resource']
            for cid in e['container_ids']:containers[cid]['location']=location+':'+cid
        for a,b,v in e['transfers']:transfer(containers,a,b,v)
        validate(containers,expected);applied.append(e)
    at=plan['makespan_s'] if at_s is None else at_s
    device_states=[]
    for row in plan['rows']:
        if row['kind']=='operation' and row['start_s']<=at<row['end_s']:
            phase='load' if at<row['process_start_s'] else 'run' if at<row['process_end_s'] else 'unload_clean'
            device_states.append({'resource':row['resource'],'task_id':row['id'],'action':ACTION_FOR[row['capability']],
                                  'phase':phase,'container_ids':carriers(graph,row)})
    # Wells keep the original ledger's local parent address; resolve custody for views.
    locations={cid:(containers[c['parent']]['location']+'/'+cid.rsplit(':',1)[-1] if c.get('parent') else c['location']) for cid,c in containers.items()}
    return {'plan_id':plan['id'],'time_s':at,'containers':containers,'locations':locations,'active':list(active.values()),'device_states':device_states,'event_count':len(applied),
            'component_totals_ul':totals(containers),'measurement':None,'scope':'digital ledger rehearsal; no biological measurement'}


def prepare_plan(plan,caps=None):
    plan['events']=events_for(plan)
    plan['device_calls']=[{'id':r['id'],'device_id':r['resource'],'action':ACTION_FOR[r['capability']],
        'mode':'digital','start_s':r['start_s'],'run_s':r['process_start_s'],'process_end_s':r['process_end_s'],'end_s':r['end_s'],
        'arguments':{'task_id':r['id'],'container_ids':carriers(plan['graph'],r),'container':r['container'],
                     'demand':r['demand'],'temperature_c':r.get('temperature_c'),'optics':r.get('optics',{}),
                     'transfers':r['transfers']},'measurement':None,'hardware_driver':None}
        for r in plan['rows'] if r['kind']=='operation']
    if caps is not None:
        used={r['resource'] for r in plan['rows'] if r['kind']=='operation'}
        plan['scene']={'schema':'biofoundry.plan-scene.v1','layout':copy.deepcopy(caps['layouts'][plan['layout']]),
            'devices':{k:copy.deepcopy(caps['devices'][k]) for k in sorted(used)},'transport':copy.deepcopy(caps['transport']),
            'transfer_mode':'manual','scope':'hypothetical layout and symbolic carriers; no robot reach or collision certification'}
    # Include recipes/counts, device descriptions and events, not merely start/end times.
    sealed={k:plan[k] for k in ('graph','rows','reservations','events','device_calls','scene','calendar_blocks') if k in plan}
    plan['id']=hashlib.sha256(json.dumps(sealed,sort_keys=True,allow_nan=False).encode()).hexdigest()[:24]
    plan['rehearsal']=replay(plan);return plan


def digital_call(plan,caps,task_id):
    """Replay an exact scheduled action; cannot send arbitrary commands or operate hardware."""
    validate_schedule(plan,caps)
    expected=prepare_plan(copy.deepcopy(plan),caps)
    require(all(expected.get(k)==plan.get(k) for k in ('id','events','device_calls','scene')),
            'ACTION_TAMPERED','Use the unchanged checked plan and scheduled calls')
    call=next((c for c in plan['device_calls'] if c['id']==task_id),None)
    require(call is not None,'UNKNOWN_ACTION',str(task_id))
    device=caps['devices'][call['device_id']]
    require(any(a['id']==call['action'] and a['mode']=='digital' for a in device['actions']),
            'UNKNOWN_ACTION','Device action is not declared')
    row=next(r for r in plan['rows'] if r['id']==task_id)
    require(call['action']==ACTION_FOR[row['capability']] and call['device_id']==row['resource'] and
            call['arguments']['transfers']==row['transfers'],'ACTION_TAMPERED','Use the checked scheduled call')
    return {'ok':True,'plan_id':plan['id'],'call':copy.deepcopy(call),
            'trace':[{'phase':phase,'at_s':at,'state':replay(plan,at)} for phase,at in
                     [('load',call['start_s']),('run',call['run_s']),('complete',call['end_s'])]],
            'measurement':None,'scope':'stateless digital replay; no reservation or physical command'}


def publish(result,output,*,latest=False):
    """Each browser keeps its own immutable comparison, including scene and device calls."""
    if not result.get('ok'):return result
    for d in result['catalog']['devices'].values():d['actions']=actions_for(d)
    for p in result['plans']:prepare_plan(p,result['catalog'])
    result['intent']=copy.deepcopy(result['plans'][0]['graph']['intent'])
    result['recommended_index']=next((i for i,p in enumerate(result['plans']) if p.get('label')=='折中'),0)
    identity={'plans':[p['id'] for p in result['plans']],'generation':result.get('generation')}
    result['comparison_id']=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:24]
    directory=Path(output)/'orchestration'
    path=directory/'comparisons'/(result['comparison_id']+'.json')
    # Reservation state changes independently of this immutable comparison.
    snapshot=copy.deepcopy(result);snapshot.pop('booking',None)
    if not path.exists():write_json(path,snapshot)
    if latest:write_json(directory/'latest.json',snapshot)
    return result


def load_comparison(output,comparison_id=None):
    import re
    directory=Path(output)/'orchestration'
    require(comparison_id is None or isinstance(comparison_id,str) and re.fullmatch(r'[a-f0-9]{24}',comparison_id),
            'COMPARISON_ID','Invalid comparison identity')
    path=directory/'comparisons'/(comparison_id+'.json') if comparison_id else directory/'latest.json'
    require(path.exists(),'COMPARISON_ID','Plan snapshot does not exist')
    data=json.loads(path.read_text());data.pop('booking',None)
    return publish(data,output)


def build(intent,output,*,with_bookings=False,time_limit_s=2):
    directory=Path(output)/'orchestration';directory.mkdir(parents=True,exist_ok=True)
    caps=catalog(output);compiled=compile_graph(intent,caps)
    if not compiled['ok']:return compiled
    snapshot=Reservations(directory/'reservations.sqlite').snapshot() if with_bookings else {'revision':0,'bookings':[]}
    result=compare(compiled['graph'],caps,snapshot['bookings'],time_limit_s=time_limit_s)
    if result['ok']:
        for p in result['plans']:prepare_plan(p,caps)
    return publish({**result,'checks':compiled['checks'],'catalog':caps,'reservation_revision':snapshot['revision'],
            'calendar':{'timezone':'Asia/Shanghai','start':'09:00','offsets':'relative seconds within a hypothetical shared workday'},
            'model_api_development_cost':{'usage':None,'cost':None,'basis':'separate from nominal operating budget; never infer a catalog price'}},output)


def generate(request,output):
    from .app import ROOT
    from .methods import METHODS
    require(isinstance(request,str) and 0<len(request)<=12000,'INVALID_REQUEST','1–12000 character request required')
    directory=Path(output)/'orchestration'/'generations'/str(uuid.uuid4());directory.mkdir(parents=True)
    write_json(directory/'request.json',{'request':request})
    try:
        process=subprocess.run([shutil.which('node') or 'node','--import','tsx','server/src/biofoundry-author.ts'],cwd=ROOT/'labscriptai/webdemo',
            input=json.dumps({'request':request,'sources':{'methods':METHODS,'catalog':catalog(output)},'mode':'portfolio'}),capture_output=True,text=True,timeout=240)
        result=json.loads(process.stdout) if process.returncode==0 else {'ok':False,'code':'MODEL_ERROR','detail':process.stderr[-1800:]}
    except subprocess.TimeoutExpired:result={'ok':False,'code':'MODEL_TIMEOUT','detail':'240s model deadline exceeded'}
    write_json(directory/'generation.json',result)
    if result.get('ok'):
        comparison=build(result['generated']['graph']['intent'],output,with_bookings=True)
        result['comparison']=comparison;result['ok']=comparison['ok']
        comparison['generation']={'provider':result.get('provider'),'model':result.get('model'),'attempts':result.get('attempts'),
            'trace_reference':str(directory.relative_to(Path(output)/'orchestration')/'generation.json'),'request':request}
        usage=[e.get('message',{}).get('usage') for e in result.get('trace',[]) if e.get('type')=='message_end' and e.get('message',{}).get('role')=='assistant']
        comparison['model_api_development_cost']={'usage':usage,'cost':None,'basis':'actual provider token usage; any zero/absent price is unknown, not free; separate from operating cost'}
        result['directory']=str(directory)
        if result['ok']:publish(comparison,output,latest=True)
        write_json(directory/'result.json',result)
    result['directory']=str(directory);return result


def demo(output):
    directory=Path(output)/'orchestration';directory.mkdir(parents=True,exist_ok=True)
    write_json(directory/'example-intent.json',EXAMPLE);write_json(directory/'capabilities.json',catalog(output))
    singles={}
    for exp in EXAMPLE['experiments']:
        intent={**copy.deepcopy(EXAMPLE),'experiments':[exp]};r=build(intent,output,time_limit_s=.5);write_json(directory/f'example-{exp["method"]}.json',r)
        singles[exp['method']]={'ok':r['ok'],'status':r['plans'][0]['status'] if r['ok'] else r}
        if exp['method']=='gfp':
            # Existing nine-step compiler AND its manual-gated state machine remain independently exercised.
            complete(Run(r['plans'][0]['graph']['experiments'][0]['legacy']['plan'])).save(directory/'legacy-gfp')
    shared=copy.deepcopy(EXAMPLE);shared['enabled_devices']=['device:19','device:67','demo:ks4000:1','bench']
    one=build(shared,output,time_limit_s=1);write_json(directory/'shared-workstation.json',one)
    result=build(EXAMPLE,output,time_limit_s=1);write_json(directory/'latest.json',result)
    write_json(directory/'demo-summary.json',{'ok':all(r['ok'] for r in singles.values()) and result['ok'] and one['ok'],'singles':singles,
        'shared_workstation':{'ok':one['ok'],'fifo':one.get('fifo'),'best':[{k:p.get(k) for k in ('label','status','makespan_s','cost_cny')} for p in one.get('plans',[])]},
        'plans':[{k:p.get(k) for k in ('label','status','makespan_s','cost_cny','transport_seconds','bottleneck')} for p in result.get('plans',[])]})
    return result
