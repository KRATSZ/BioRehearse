"""One CP-SAT model for all experiments, operator, transport and instance occupancy."""
import copy
import hashlib
import json
import math
from collections import defaultdict
from .workflow import require, Blocked
from .methods import validate_graph


def transport(catalog,layout,a,b):
    points=catalog['layouts'][layout]['positions'];cfg=catalog['transport']
    distance=sum(abs(x-y) for x,y in zip(points[a],points[b]))
    return math.ceil(distance/cfg['speed_m_s'])+(cfg['handoff_s'] if a!=b else cfg['same_station_s']),distance


def options(task,catalog):
    result=[]
    for key in task['candidates']:
        d=catalog['devices'][key];caps=d.get('capabilities',{})
        if not (d.get('selectable') and caps.get(task['capability']) is True and all(c in d.get('containers',[]) for c in task.get('required_labware',[task['container']])) and
                type(d.get('capacity')) is int and d['capacity']>=task['demand'] and d.get('available_s') and d.get('cost_cny_per_hour') is not None):continue
        temp=task.get('temperature_c')
        if temp is not None and temp not in caps.get('temperature_c',[]):continue
        if any(not isinstance(caps.get(field),list) or not caps[field][0]<=value<=caps[field][1] for field,value in task.get('optics',{}).items()):continue
        if task['name']=='dark_incubation' and not d.get('conditions',{}).get('dark_cover'):continue
        factor=d.get('duration_factor',1) if task['capability']=='liquid' else 1
        process=math.ceil(task['process_s']*factor);duration=task['load_s']+process+task['clean_s']
        manual=duration if task['manual'] or key=='bench' and task['capability']=='liquid' else task['load_s']+task['clean_s']
        machine=math.ceil(duration*d['cost_cny_per_hour']/36);labor=math.ceil(manual*catalog['costs']['operator_per_hour']/36)
        fixed=process if task['name'] in ('incubate','dark_incubation') else 0
        result.append({'resource':key,'duration_s':duration,'process_s':process,'operator_s':manual,'cost_cents':machine+labor,'machine_cents':machine,'labor_cents':labor,
            'duration_assumed_range_s':[fixed+math.floor((duration-fixed)*.7),fixed+math.ceil((duration-fixed)*1.5)]})
    return result


def solve(graph,catalog,layout='compact',objective='fastest',bookings=None,*,fixed=None,now_s=0,time_limit_s=3,fifo=False):
    from ortools.sat.python import cp_model
    validate_graph(graph,catalog)
    require(layout in catalog['layouts'],'UNKNOWN_LAYOUT',layout)
    require(objective in ('fastest','cheapest','balanced'),'OBJECTIVE',objective)
    model=cp_model.CpModel();horizon=graph['deadline_s'];tasks=graph['tasks'];byid={t['id']:t for t in tasks}
    variables={};choices={};intervals=defaultdict(list);costs=[];transfers=[];fixed=fixed or {}
    def interval(s,d,e,name,presence=None):
        return model.new_optional_interval_var(s,d,e,presence,name) if presence is not None else model.new_interval_var(s,d,e,name)
    for t in tasks:
        tid=t['id'];opts=options(t,catalog)
        if not opts:return {'ok':False,'status':'INFEASIBLE','code':'CAPABILITY_OR_CAPACITY','detail':f'{tid}: no explicitly configured compatible instance'}
        start=model.new_int_var(0,horizon,tid+':s');end=model.new_int_var(0,horizon,tid+':e');variables[tid]=(start,end)
        choices[tid]=[];pres=[]
        for i,opt in enumerate(opts):
            key=opt['resource'];p=model.new_bool_var(tid+':'+key);pres.append(p);choices[tid].append((p,opt))
            intervals[key].append(interval(start,opt['duration_s'],end,tid+':device:'+str(i),p));costs.append(opt['cost_cents']*p)
            if opt['operator_s']==opt['duration_s']:
                intervals['operator'].append(interval(start,opt['duration_s'],end,tid+':operator',p))
            else:
                if t['load_s']:intervals['operator'].append(interval(start,t['load_s'],start+t['load_s'],tid+':load',p))
                if t['clean_s']:intervals['operator'].append(interval(end-t['clean_s'],t['clean_s'],end,tid+':unload-clean',p))
            available=[]
            for j,(a,b) in enumerate(catalog['devices'][key]['available_s']):
                q=model.new_bool_var(tid+':available:'+str(i)+':'+str(j));available.append(q)
                model.add(start>=a).only_enforce_if(q);model.add(end<=b).only_enforce_if(q)
            model.add(sum(available)==p)
            if tid in fixed:
                old=fixed[tid];model.add(p==(1 if old['resource']==key else 0));model.add(start==old['start_s']);model.add(end==old['end_s'])
        model.add_exactly_one(pres)
        model.add(start>=t['release_s']);model.add(end<=t['deadline_s'])
        if tid not in fixed:model.add(start>=now_s)
    # Explicit transport nodes reserve the same operator pool across every experiment.
    for t in tasks:
        for dep in t['depends_on']:
            name=dep+'→'+t['id'];start=model.new_int_var(0,horizon,name+':s');end=model.new_int_var(0,horizon,name+':e')
            duration=model.new_int_var(1,horizon,name+':duration');terms=[];pairs=[]
            for p,a in choices[dep]:
                for q,b in choices[t['id']]:
                    active=model.new_bool_var(name+':'+a['resource']+':'+b['resource']);model.add(active<=p);model.add(active<=q);model.add(active>=p+q-1)
                    seconds,distance=transport(catalog,layout,a['resource'],b['resource']);terms.append(seconds*active)
                    pairs.append((active,a['resource'],b['resource'],seconds,distance))
                    if name in fixed and (a['resource']!=fixed[name]['source'] or b['resource']!=fixed[name]['destination']):model.add(active==0)
            model.add(duration==sum(terms));intervals['operator'].append(interval(start,duration,end,name))
            model.add(start>=variables[dep][1]);model.add(variables[t['id']][0]>=end)
            if name in fixed:
                old=fixed[name];model.add(start==old['start_s']);model.add(end==old['end_s'])
            else:model.add(start>=now_s)
            fee=model.new_int_var(0,10000,name+':cost');model.add(fee*36>=duration*catalog['costs']['operator_per_hour']);model.add(fee*36<duration*catalog['costs']['operator_per_hour']+36);costs.append(fee)
            transfers.append((name,dep,t['id'],start,end,pairs,fee))
        if t.get('window'):
            w=t['window'];src=byid[w['from']]
            # Chemical wait is measured from process completion (before unloading/cleaning).
            reference=variables[src['id']][1]-src['clean_s']
            model.add(variables[t['id']][0]+t['load_s']-reference<=w['max_s'])
            if w.get('min_s'):model.add(variables[t['id']][0]+t['load_s']-reference>=w['min_s'])
    if fifo:
        # Reproducible FCFS baseline: whole experiments dispatched in input order.
        exps=graph['experiments']
        for a,b in zip(exps,exps[1:]):
            first=next(t for t in tasks if t['experiment']==b['id']);last=next(t for t in reversed(tasks) if t['experiment']==a['id'])
            model.add(variables[first['id']][0]>=variables[last['id']][1])
    for b in bookings or []:
        if b['end_s']<=now_s:continue
        intervals[b['resource']].append(model.new_interval_var(b['start_s'],b['end_s']-b['start_s'],b['end_s'],'existing:'+str(b)))
    for resource,items in intervals.items():model.add_no_overlap(items)
    makespan=model.new_int_var(0,horizon,'makespan');model.add_max_equality(makespan,[v[1] for v in variables.values()])
    total=model.new_int_var(0,100000000,'cost_cents');model.add(total==sum(costs)+round(graph['consumables_cny']*100))
    model.add(total<=math.floor(graph['budget_cny']*100))
    if objective=='fastest':target=makespan
    elif objective=='cheapest':target=total
    else:target=makespan+2*total # Explicit value-of-time: 1 CNY corresponds to 200 seconds.
    model.minimize(target)
    solver=cp_model.CpSolver();solver.parameters.max_time_in_seconds=time_limit_s;solver.parameters.num_search_workers=1;solver.parameters.random_seed=7
    status=solver.solve(model);state=solver.status_name(status)
    if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        return {'ok':False,'status':state,'code':'NO_FEASIBLE_SCHEDULE' if state=='INFEASIBLE' else 'SOLVER_UNRESOLVED',
                'detail':'Joint capacity, availability, deadline, sample window or budget constraints; no relaxation applied','layout':layout,'objective':objective}
    rows=[];reservations=[]
    for t in tasks:
        p,opt=next((p,o) for p,o in choices[t['id']] if solver.value(p));s,e=(solver.value(v) for v in variables[t['id']]);key=opt['resource']
        row={**copy.deepcopy(t),**opt,'start_s':s,'end_s':e,'process_start_s':s+t['load_s'],'process_end_s':e-t['clean_s'],'kind':'operation'}
        rows.append(row);reservations.append({'task_id':t['id'],'resource':key,'start_s':s,'end_s':e})
        if opt['operator_s']==opt['duration_s']:reservations.append({'task_id':t['id'],'resource':'operator','start_s':s,'end_s':e})
        else:
            if t['load_s']:reservations.append({'task_id':t['id'],'resource':'operator','start_s':s,'end_s':s+t['load_s']})
            if t['clean_s']:reservations.append({'task_id':t['id'],'resource':'operator','start_s':e-t['clean_s'],'end_s':e})
    for name,a,b,s,e,pairs,fee in transfers:
        active,src,dst,seconds,distance=next(p for p in pairs if solver.value(p[0]));start=solver.value(s);end=solver.value(e)
        rows.append({'id':name,'name':'manual_transfer','kind':'transfer','experiment':byid[b]['experiment'],'resource':'operator','source':src,'destination':dst,
                     'depends_on':[a],'to_task':b,'start_s':start,'end_s':end,'duration_s':seconds,'distance_m':distance,'cost_cents':solver.value(fee),
                     'plate_id':byid[b]['plate_id'],'transfers':[],'manual':True})
        reservations.append({'task_id':name,'resource':'operator','start_s':start,'end_s':end})
    duration=solver.value(makespan);cost=solver.value(total)/100
    usage={r:round(sum(b['end_s']-b['start_s'] for b in reservations if b['resource']==r)/duration,4) for r in {b['resource'] for b in reservations}}
    bottleneck=max(usage,key=usage.get)
    signature=hashlib.sha256(json.dumps([layout,objective,sorted((r['id'],r['resource'],r['start_s'],r['end_s']) for r in rows)]).encode()).hexdigest()[:16]
    plan={'schema':'biofoundry.schedule.v2','id':signature,'mode':'simulation','ok':True,'status':state,'proven_optimal':status==cp_model.OPTIMAL,
        'objective':objective,'objective_value':solver.objective_value,'best_bound':solver.best_objective_bound,'solver':'OR-Tools CP-SAT',
        'solve_seconds':round(solver.wall_time,4),'layout':layout,'layout_name':catalog['layouts'][layout]['name'],'rows':sorted(rows,key=lambda r:(r['start_s'],r['id'])),
        'reservations':reservations,'makespan_s':duration,'cost_cny':cost,'cost_range_cny':[round(cost*.7,2),round(cost*1.5,2)],
        'budget_basis':'nominal planning estimate; high end is sensitivity, not a guaranteed budget',
        'cost_breakdown_cny':{'consumables':graph['consumables_cny'],'machine_and_operator':round(cost-graph['consumables_cny'],2),'model_api':None},
        'samples_per_hour':round(graph['input_samples']*3600/duration,2),'wells_per_hour':round(len(graph['plate_map'])*3600/duration,2),
        'utilization':usage,'bottleneck':bottleneck,'transport_distance_m':round(sum(r.get('distance_m',0) for r in rows),2),
        'transport_seconds':sum(r['duration_s'] for r in rows if r['kind']=='transfer'),
        'explanation':[f'{bottleneck} occupies {usage[bottleneck]:.1%} of elapsed time; one job per physical instance',
            'KS4000 30°C / 37°C batches serialize; 180s setup includes assumed temperature changeover',
            'Every transfer, load, unload and cleaning reserves the shared operator',
            'PicoGreen read begins 120–300s after reagent completion; unknown reader i3x options excluded',
            f'{layout}: transport {sum(r["duration_s"] for r in rows if r["kind"]=="transfer")}s included',
            'Balanced objective = makespan_seconds + 200 × cost_CNY'], 'graph':graph}
    plan['cost_breakdown_cny']={'consumables':graph['consumables_cny'],'machine':sum(r.get('machine_cents',0) for r in rows)/100,
        'operator':sum(r.get('labor_cents',r['cost_cents'] if r['kind']=='transfer' else 0) for r in rows)/100,'model_api':None}
    plan['equipment']=[{'resource':key,'name':catalog['devices'][key].get('model') or catalog['devices'][key]['name'],
        'busy_s':sum(b['end_s']-b['start_s'] for b in reservations if b['resource']==key)} for key in sorted(usage) if key!='operator']
    plan['validation']=validate_schedule(plan,catalog)
    return plan


def validate_schedule(plan,catalog):
    """Independent arithmetic/interval audit; never trusts the solver status alone."""
    graph=plan['graph'];validate_graph(graph,catalog);rows={r['id']:r for r in plan['rows']};busy=defaultdict(list)
    expected_ids={t['id'] for t in graph['tasks']}|{dep+'→'+t['id'] for t in graph['tasks'] for dep in t['depends_on']}
    require(len(rows)==len(plan['rows']) and set(rows)==expected_ids,'SCHEDULE_TAMPERED','Missing, duplicate or extra tasks')
    for b in plan['reservations']+plan.get('calendar_blocks',[]):
        require(b['start_s']<b['end_s'],'RESERVATION',str(b));busy[b['resource']].append(b)
    for resource,bookings in busy.items():
        bookings.sort(key=lambda b:b['start_s'])
        require(all(a['end_s']<=b['start_s'] for a,b in zip(bookings,bookings[1:])),'DOUBLE_BOOKING',resource)
    derived=[];cost=round(graph['consumables_cny']*100)
    for t in graph['tasks']:
        r=rows[t['id']];opt=next((o for o in options(t,catalog) if o['resource']==r['resource']),None)
        require(opt is not None,'CAPABILITY_OR_CAPACITY',t['id'])
        require(all(r.get(k)==v for k,v in {**t,**opt}.items()) and r.get('kind')=='operation' and
                r.get('process_start_s')==r['start_s']+t['load_s'] and r.get('process_end_s')==r['end_s']-t['clean_s'],
                'SCHEDULE_TAMPERED',t['id']+': scheduled action differs from its registered task')
        require(r['end_s']-r['start_s']==opt['duration_s'],'DURATION',t['id'])
        require(t['release_s']<=r['start_s']<r['end_s']<=t['deadline_s'],'DEADLINE',t['id'])
        require(any(a<=r['start_s'] and r['end_s']<=b for a,b in catalog['devices'][r['resource']]['available_s']),'AVAILABILITY',t['id'])
        derived.append({'task_id':t['id'],'resource':r['resource'],'start_s':r['start_s'],'end_s':r['end_s']});cost+=opt['cost_cents']
        if opt['operator_s']==opt['duration_s']:derived.append({'task_id':t['id'],'resource':'operator','start_s':r['start_s'],'end_s':r['end_s']})
        else:
            if t['load_s']:derived.append({'task_id':t['id'],'resource':'operator','start_s':r['start_s'],'end_s':r['start_s']+t['load_s']})
            if t['clean_s']:derived.append({'task_id':t['id'],'resource':'operator','start_s':r['end_s']-t['clean_s'],'end_s':r['end_s']})
        for dep in t['depends_on']:
            transit=rows[dep+'→'+t['id']];seconds,distance=transport(catalog,plan['layout'],rows[dep]['resource'],r['resource'])
            require(transit.get('kind')=='transfer' and transit.get('source')==rows[dep]['resource'] and
                    transit.get('destination')==r['resource'] and transit.get('experiment')==t['experiment'] and
                    transit.get('to_task')==t['id'] and transit.get('resource')=='operator' and not transit.get('transfers'),
                    'SCHEDULE_TAMPERED',transit['id'])
            require(rows[dep]['end_s']<=transit['start_s'] and transit['end_s']<=r['start_s'],'DEPENDENCY',t['id'])
            require(transit['end_s']-transit['start_s']==seconds and transit['distance_m']==distance,'TRANSPORT',transit['id'])
            derived.append({'task_id':transit['id'],'resource':'operator','start_s':transit['start_s'],'end_s':transit['end_s']});cost+=math.ceil(seconds*catalog['costs']['operator_per_hour']/36)
        if t.get('window'):
            w=t['window'];src=next(x for x in graph['tasks'] if x['id']==w['from']);lag=r['start_s']+t['load_s']-(rows[w['from']]['end_s']-src['clean_s'])
            require(w.get('min_s',0)<=lag<=w['max_s'],'SAMPLE_WINDOW',t['id'])
    key=lambda b:(b['task_id'],b['resource'],b['start_s'],b['end_s'])
    require(sorted(map(key,derived))==sorted(map(key,plan['reservations'])),'RESERVATION','Missing or extra device/operator reservation')
    require(cost==round(plan['cost_cny']*100) and cost<=math.floor(graph['budget_cny']*100),'BUDGET','Exact cents and nominal budget')
    require(plan['makespan_s']==max(r['end_s'] for r in rows.values()),'SCHEDULE_TAMPERED','Completion time differs from the schedule')
    return {'passed':True,'checks':['method DAG and ledger','capability/container/temperature/capacity','precedence and all transport','device and human exclusivity','load/unload/clean','sample windows','availability/deadline','itemized nominal budget'],'measurement':None}


def compare(graph,catalog,bookings=None,time_limit_s=2):
    results=[];attempts=[]
    for layout in catalog['layouts']:
        for objective in ('fastest','cheapest','balanced'):
            plan=solve(graph,catalog,layout,objective,bookings,time_limit_s=time_limit_s)
            attempts.append({k:plan.get(k) for k in ('ok','status','layout','objective','makespan_s','cost_cny','proven_optimal','best_bound','objective_value','transport_seconds')})
            if plan['ok']:results.append(plan)
    if not results:return {'ok':False,'attempts':attempts,'plans':[],'detail':'No feasible plan found; see solver states (UNKNOWN is not proof of infeasibility)'}
    best=[min(results,key=lambda p:(p['makespan_s'],p['cost_cny'])),min(results,key=lambda p:(p['cost_cny'],p['makespan_s'])),min(results,key=lambda p:p['makespan_s']+200*p['cost_cny'])]
    plans=[]
    for label,p in zip(('最快','最低运行成本','折中'),best):
        p=copy.deepcopy(p);p['label']=label;plans.append(p)
    fifo=solve(graph,catalog,'compact','fastest',bookings,time_limit_s=time_limit_s,fifo=True)
    return {'ok':True,'plans':plans,'attempts':attempts,'fifo':{k:fifo.get(k) for k in ('ok','status','makespan_s','cost_cny','proven_optimal')},
        'selection_scope':'best incumbent among three hypothetical layouts and registered existing device alternatives; OPTIMAL applies to each displayed objective/layout only'}


def replan(plan,catalog,now_s,failed_resource,repair_s,bookings=None):
    require(type(now_s) is int and type(repair_s) is int and 0<=now_s<repair_s<=plan['graph']['deadline_s'],'REPLAN','valid failure and repair times required')
    require(failed_resource in catalog['devices'],'UNKNOWN_DEVICE',failed_resource)
    # No in-flight experiment is silently healed. An active failed device needs an explicit recovery decision.
    require(not any(r['kind']=='operation' and r['resource']==failed_resource and r['start_s']<=now_s<r['end_s'] for r in plan['rows']),
            'IN_FLIGHT_FAILURE','Failed device has an active step; operator recovery required, no automatic modification')
    fixed={r['id']:r for r in plan['rows'] if r['start_s']<=now_s}
    downtime={'task_id':'failure','resource':failed_resource,'start_s':now_s,'end_s':repair_s}
    blocks=[]
    for b in sorted(copy.deepcopy(plan.get('calendar_blocks',[]))+[downtime],key=lambda b:(b['resource'],b['start_s'])):
        if blocks and b['resource']==blocks[-1]['resource'] and b['start_s']<=blocks[-1]['end_s']:
            blocks[-1]['end_s']=max(blocks[-1]['end_s'],b['end_s'])
        else:blocks.append(b)
    result=solve(plan['graph'],catalog,plan['layout'],plan['objective'],(bookings or [])+blocks,fixed=fixed,now_s=now_s,time_limit_s=5)
    if result['ok']:
        result['calendar_blocks']=blocks
        validate_schedule(result,catalog)
        for row in result['rows']:
            if row['id'] in fixed:require(all(row[k]==fixed[row['id']][k] for k in ('start_s','end_s','resource')),'REPLAN','Started step changed')
        result['replanning']={'now_s':now_s,'failed_resource':failed_resource,'repair_s':repair_s,'frozen_steps':list(fixed),'parent_plan_id':plan['id'],'only_unstarted_modified':True}
    return result
