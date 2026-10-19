"""Independent arithmetic/interval scorer, frozen before held-out execution.

Does not call production validate_schedule or production options.
"""
import math
from collections import defaultdict

def score(plan, graph, cat, blocks=()):
    errors=[]
    def check(ok, code):
        if not ok: errors.append(code)
    if not plan.get('ok'):return {'returned':False,'valid':False,'violations':[], 'status':plan.get('status',plan.get('code'))}
    tasks={t['id']:t for t in graph['tasks']}; rows={r['id']:r for r in plan['rows']}
    expected=set(tasks)|{d+'→'+t['id'] for t in tasks.values() for d in t['depends_on']}
    check(len(rows)==len(plan['rows']) and set(rows)==expected,'task_identity')
    if set(rows)!=expected:return {'returned':True,'valid':False,'violations':errors}
    busy=defaultdict(list); expected_res=[]; total=round(graph['consumables_cny']*100)
    def reserve(tid, resource, a,b):
        busy[resource].append((a,b,tid)); expected_res.append((tid,resource,a,b))
    for tid,t in tasks.items():
        r=rows[tid]; d=cat['devices'].get(r['resource'],{});caps=d.get('capabilities',{})
        check(r['resource'] in t['candidates'] and d.get('selectable') and caps.get(t['capability']) is True,'capability')
        check(d.get('capacity',0)>=t['demand'],'capacity')
        check(set(t['required_labware'])<=set(d.get('containers',[])),'labware')
        if t.get('temperature_c') is not None:check(t['temperature_c'] in caps.get('temperature_c',[]),'temperature')
        for k,v in t.get('optics',{}).items():check(k in caps and caps[k][0]<=v<=caps[k][1],'optics')
        if t['name']=='dark_incubation':check(d.get('conditions',{}).get('dark_cover'),'dark')
        process=math.ceil(t['process_s']*(d.get('duration_factor',1) if t['capability']=='liquid' else 1))
        duration=t['load_s']+process+t['clean_s'];s,e=r['start_s'],r['end_s']
        check(e-s==duration and r['process_start_s']==s+t['load_s'] and r['process_end_s']==e-t['clean_s'],'duration')
        check(all(r.get(k)==v for k,v in t.items() if k!='process_s') and r.get('process_s')==process,'registered_task')
        check(t['release_s']<=s<e<=t['deadline_s'],'deadline')
        check(any(a<=s and e<=b for a,b in d.get('available_s',[])),'availability')
        reserve(tid,r['resource'],s,e)
        manual=duration if t['manual'] or r['resource']=='bench' and t['capability']=='liquid' else t['load_s']+t['clean_s']
        if manual==duration:reserve(tid,'operator',s,e)
        else:
            if t['load_s']:reserve(tid,'operator',s,s+t['load_s'])
            if t['clean_s']:reserve(tid,'operator',e-t['clean_s'],e)
        total+=math.ceil(duration*d['cost_cny_per_hour']/36)+math.ceil(manual*cat['costs']['operator_per_hour']/36)
        for dep in t['depends_on']:
            tr=rows[dep+'→'+tid];src=rows[dep]['resource'];dst=r['resource'];points=cat['layouts'][plan['layout']]['positions']
            distance=sum(abs(a-b) for a,b in zip(points[src],points[dst]));cfg=cat['transport']
            seconds=math.ceil(distance/cfg['speed_m_s'])+(cfg['handoff_s'] if src!=dst else cfg['same_station_s'])
            check(tr['source']==src and tr['destination']==dst and tr['to_task']==tid and tr['resource']=='operator','transfer_identity')
            check(tr['end_s']-tr['start_s']==seconds and tr['distance_m']==distance,'transport')
            check(rows[dep]['end_s']<=tr['start_s'] and tr['end_s']<=s,'precedence')
            reserve(tr['id'],'operator',tr['start_s'],tr['end_s']);total+=math.ceil(seconds*cat['costs']['operator_per_hour']/36)
        if t.get('window'):
            w=t['window'];lag=s+t['load_s']-(rows[w['from']]['end_s']-tasks[w['from']]['clean_s'])
            check(w.get('min_s',0)<=lag<=w['max_s'],'sample_window')
    for b in blocks:busy[b['resource']].append((b['start_s'],b['end_s'],'calendar'))
    for resource,intervals in busy.items():
        intervals.sort();check(all(x[1]<=y[0] for x,y in zip(intervals,intervals[1:])), 'overlap:'+resource)
    actual=sorted((b['task_id'],b['resource'],b['start_s'],b['end_s']) for b in plan['reservations'])
    check(actual==sorted(expected_res),'reservation_accounting')
    check(total==round(plan['cost_cny']*100) and total<=math.floor(graph['budget_cny']*100),'budget')
    check(plan['makespan_s']==max(r['end_s'] for r in rows.values()),'makespan')
    return {'returned':True,'valid':not errors,'violations':sorted(set(errors))}

def semantic(intent, expected):
    if intent is None:return False
    if expected is None:return False
    for k in ['mode','accept_demo_assumptions','deadline_s','budget_cny']:
        if intent.get(k, 'simulation' if k=='mode' else None)!=expected[k]:return False
    if set(intent.get('enabled_devices',[]))!=set(expected['enabled_devices']):return False
    if intent.get('allow_manual_pipetting',False) != expected.get('allow_manual_pipetting',False):return False
    if intent.get('unsupported_requests'):return False
    def exps(v):return sorted((e['method'],e['samples'],e['replicates'],e.get('release_s',0),e.get('deadline_s',v['deadline_s'])) for e in v['experiments'])
    return exps(intent)==exps(expected)
