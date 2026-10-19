"""Parallel serial-schedule-generation heuristic with multi-start dispatch.

No CP solver is called. All resource, operator, transfer, window and cost
constraints apply; incomplete attempts are retained as non-returned plans.
"""
import copy, itertools, math, time, random
from collections import defaultdict
from labscriptai.biofoundry.scheduling import options, transport

def insert_time(earliest, spans, busy, available, duration, latest):
    s=earliest
    for _ in range(10000):
        choices=[max(s,a) for a,b in available if max(s,a)+duration<=b]
        if not choices:return None
        s=min(choices)
        if s>latest:return None
        move=s
        for resource,offset,length in spans:
            for a,b in busy[resource]:
                if s+offset<b and a<s+offset+length:move=max(move,b-offset)
        if move==s:return s
        s=move
    return None

def one(graph,cat,layout,objective,order,policy,blocks,stop,delays):
    busy=defaultdict(list);rows={};reservations=[];cost=round(graph['consumables_cny']*100)
    for b in blocks:busy[b['resource']].append((b['start_s'],b['end_s']))
    pending={t['id']:t for t in graph['tasks']};tasks=dict(pending)
    def reserve(tid,resource,a,b):
        busy[resource].append((a,b));reservations.append({'task_id':tid,'resource':resource,'start_s':a,'end_s':b})
    while pending:
        if time.perf_counter()>stop:return None
        ready=[t for t in pending.values() if all(d in rows for d in t['depends_on'])]
        candidates=[];repairs=[]
        for t in ready:
            for opt in options(t,cat):
                local=copy.deepcopy(busy);transit=None;earliest=max(t['release_s'],delays.get(t['experiment'],0));extra=0
                transits=[];transport_failed=False
                for dep in t['depends_on']:
                    seconds,distance=transport(cat,layout,rows[dep]['resource'],opt['resource'])
                    ts=insert_time(rows[dep]['end_s'],[('operator',0,seconds)],local,[[0,graph['deadline_s']]],seconds,graph['deadline_s']-seconds)
                    if ts is None:transport_failed=True;break
                    local['operator'].append((ts,ts+seconds));earliest=max(earliest,ts+seconds)
                    fee=math.ceil(seconds*cat['costs']['operator_per_hour']/36);extra+=fee
                    transits.append({'id':dep+'→'+t['id'],'kind':'transfer','name':'manual_transfer','experiment':t['experiment'],'resource':'operator','source':rows[dep]['resource'],'destination':opt['resource'],'to_task':t['id'],'depends_on':[dep],'start_s':ts,'end_s':ts+seconds,'duration_s':seconds,'distance_m':distance,'cost_cents':fee,'transfers':[],'manual':True,'plate_id':t['plate_id']})
                if transport_failed:continue
                latest=t['deadline_s']-opt['duration_s']
                if t.get('window'):
                    w=t['window'];reference=rows[w['from']]['end_s']-tasks[w['from']]['clean_s']
                    earliest=max(earliest,reference+w.get('min_s',0)-t['load_s']);latest=min(latest,reference+w['max_s']-t['load_s'])
                lower=sum(min((o['cost_cents'] for o in options(z,cat)),default=10**9) for z in pending.values() if z['id']!=t['id'])
                if cost+opt['cost_cents']+extra+lower>math.floor(graph['budget_cny']*100):continue
                spans=[(opt['resource'],0,opt['duration_s'])]
                if opt['operator_s']==opt['duration_s']:spans.append(('operator',0,opt['duration_s']))
                else:
                    if t['load_s']:spans.append(('operator',0,t['load_s']))
                    if t['clean_s']:spans.append(('operator',opt['duration_s']-t['clean_s'],t['clean_s']))
                s=insert_time(earliest,spans,local,cat['devices'][opt['resource']]['available_s'],opt['duration_s'],latest)
                if s is None:
                    # Backtrack the experiment release when a downstream resource
                    # would miss a maximum sample wait. This preserves all hard
                    # constraints instead of dispatching a known-invalid assay.
                    if t.get('window'):
                        later=insert_time(earliest,spans,local,cat['devices'][opt['resource']]['available_s'],opt['duration_s'],t['deadline_s']-opt['duration_s'])
                        if later is not None and later>latest:repairs.append((later-latest,t['experiment']))
                    continue
                e=s+opt['duration_s'];rank=order.index(t['experiment'])
                device_key=(opt['cost_cents']+extra,e) if objective=='cheapest' else (e,opt['cost_cents']+extra)
                priority=(rank,*device_key) if policy=='experiment' else (latest-e,e,rank,*device_key) if policy=='urgency' else (e,rank,*device_key)
                candidates.append((priority,t,opt,s,e,transits,spans,extra))
        if not candidates:
            return {'retry_shift':min(repairs)} if repairs else None
        _,t,opt,s,e,tr,spans,extra=min(candidates,key=lambda v:v[0])
        for transit in tr:
            rows[transit['id']]=transit;reserve(transit['id'],'operator',transit['start_s'],transit['end_s'])
        rows[t['id']]={**copy.deepcopy(t),**opt,'kind':'operation','start_s':s,'end_s':e,'process_start_s':s+t['load_s'],'process_end_s':e-t['clean_s']}
        for resource,offset,length in spans:reserve(t['id'],resource,s+offset,s+offset+length)
        cost+=opt['cost_cents']+extra;del pending[t['id']]
    return {'ok':True,'status':'HEURISTIC','graph':graph,'layout':layout,'objective':objective,'rows':sorted(rows.values(),key=lambda r:(r['start_s'],r['id'])),'reservations':reservations,'makespan_s':max(r['end_s'] for r in rows.values()),'cost_cny':cost/100,'proven_optimal':False}

def solve_greedy(graph,cat,layout,objective,blocks=(),time_limit_s=1):
    start=time.perf_counter();stop=start+time_limit_s;best=None;attempts=0
    ids=[e['id'] for e in graph['experiments']]
    if len(ids)<=3:orders=list(itertools.permutations(ids))
    else:
        rng=random.Random(20261019);orders=[tuple(ids),tuple(reversed(ids))]
        durations={eid:sum(t['process_s'] for t in graph['tasks'] if t['experiment']==eid) for eid in ids}
        orders += [tuple(sorted(ids,key=lambda e:durations[e])),tuple(sorted(ids,key=lambda e:-durations[e]))]
        for _ in range(60):
            shuffled=ids.copy();rng.shuffle(shuffled);orders.append(tuple(shuffled))
        orders=list(dict.fromkeys(orders))
    # Interleave policies so a tight cap cannot suppress all later policies.
    for order in orders:
        for policy in ['experiment','urgency','finish']:
            if time.perf_counter()>=stop:break
            delays={};p=None
            for retry in range(12):
                p=one(graph,cat,layout,objective,order,policy,blocks,stop,delays);attempts+=1
                if not p or 'retry_shift' not in p:break
                delta,eid=p['retry_shift'];delays[eid]=delays.get(eid,0)+delta
            if p and 'retry_shift' in p:p=None
            key=lambda x:(x['makespan_s'],x['cost_cny']) if objective=='fastest' else (x['cost_cny'],x['makespan_s'])
            if p and (best is None or key(p)<key(best)):best=p
    return {**(best or {'ok':False,'status':'NO_GREEDY_PLAN'}),'solve_seconds':time.perf_counter()-start,'heuristic_starts':attempts}
