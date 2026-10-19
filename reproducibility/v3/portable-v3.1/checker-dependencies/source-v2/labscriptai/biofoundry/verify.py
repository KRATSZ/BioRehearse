"""Executable acceptance cases. Reports retain actual errors and state artifacts."""
import copy
from .workflow import Run, Blocked, baseline, complete, confirmation, totals, write_json


def acceptance(directory):
    results = []

    def success(name, fn):
        try:
            detail = fn()
            results.append({"case": name, "passed": True, "actual": detail})
        except Exception as exc:
            results.append({"case": name, "passed": False, "error": repr(exc)})

    def rejected(name, run, action, codes):
        before = copy.deepcopy(run.state)
        try:
            action()
            raise AssertionError("Action unexpectedly accepted")
        except Blocked as exc:
            assert exc.code in codes, (exc.code, codes)
            assert run.state == before, "Rejected transaction changed the authoritative state"
            run.save(directory / name)
            write_json(directory / name / "rejection.json", {"code": exc.code, "detail": str(exc), "state_unchanged": True})
            return {"blocked_code": exc.code, "detail": str(exc), "state_unchanged": True}

    def normal():
        run = complete(Run())
        s = run.state
        assert s["status"] == "complete" and len(s["events"]) == 9
        assert s["experiment_elapsed_s"] == 10800
        assert s["result"]["values"] is None and s["result"]["source"] is None
        assert s["containers"]["P01"]["location"] == "id5.tray:1"
        assert [s["containers"][c]["volume_ul"] for c in ["MIX", "DNA", "WATER"]] == [130, 85, 505]
        for i in range(1, 7):
            assert s["containers"][f"T{i}"]["volume_ul"] == 30
            well = s["containers"][f"P01:A{i}"]
            assert well["volume_ul"] == 100 and well["sample_ids"] == [f"sample:T{i}"]
            assert abs(well["components_ul"].get("DNA", 0) - (2 if i <= 3 else 0)) < 1e-7
        assert totals(s["containers"]) == {"MIX": 400, "DNA": 100, "WATER": 1000}
        run.save(directory / "normal")
        assert Run.load(directory / "normal").state == s
        return {"steps": 9, "events": 9, "tips_used": s["tips_used"], "total_ul": 1500,
                "stocks_remaining_ul": {c: s["containers"][c]["volume_ul"] for c in ["MIX", "DNA", "WATER"]},
                "tube_residual_ul": 30, "plate_well_ul": 100,
                "result": s["result"], "confirmation_mode": "explicitly simulated acceptance confirmations"}

    success("normal", normal)
    r = Run()
    success("missing_manual_confirmation", lambda: rejected("missing_manual_confirmation", r,
            lambda: r.act(expected_step="mix_ready"), {"MANUAL_CONFIRMATION_REQUIRED"}))
    r = Run()
    r.act(expected_step="mix_ready", confirmation=confirmation(r))
    r.plan["steps"][1]["moves"][0][2] = "prep.rack:1"
    success("position_conflict", lambda: rejected("position_conflict", r,
            lambda: r.act(expected_step="load_fluent", confirmation=confirmation(r)), {"LOCATION_CONFLICT"}))
    p = baseline()
    p["initial_containers"]["MIX"]["volume_ul"] = 260
    p["initial_containers"]["MIX"]["components_ul"] = {"MIX": 260}
    r = Run(p)
    for _ in range(2):
        r.act(expected_step=r.current()["id"], confirmation=confirmation(r))
    success("insufficient_volume", lambda: rejected("insufficient_volume", r,
            lambda: r.act(expected_step="fluent_dispense"), {"INSUFFICIENT_VOLUME", "PLANIR_CHECK_FAILED"}))
    r = Run()
    wrong = {**confirmation(r), "container_ids": ["wrong-tube"]}
    success("wrong_container_confirmation", lambda: rejected("wrong_container_confirmation", r,
            lambda: r.act(expected_step="mix_ready", confirmation=wrong), {"WRONG_CONFIRMATION"}))
    r = Run()
    old = confirmation(r)
    r.act(expected_step="mix_ready", confirmation=old)
    success("duplicate_confirmation", lambda: rejected("duplicate_confirmation", r,
            lambda: r.act(expected_step="mix_ready", confirmation=old), {"STALE_STEP"}))
    mutations = [
        ('no_template_DNA', lambda p: [t.__setitem__(0,'DNA') for t in p['steps'][2]['transfers'] if t[0]=='WATER'], 'CONTROL_RECIPE'),
        ('reader_2600nm',lambda p:p['demo_configuration']['reader'].__setitem__('excitation_nm',2600),'SOP_CONDITION'),
        ('reader_incompatible',lambda p:p['devices'].__setitem__('reader','absorbance_only'),'DEVICE_CAPABILITY'),
        ('plate_incompatible',lambda p:p['devices'].__setitem__('plate','384_qPCR'),'DEVICE_CAPABILITY'),
        ('tips_exhausted',lambda p:p.__setitem__('tips_available',0),'INSUFFICIENT_TIPS'),
        ('DNA_concentration_missing',lambda p:p['demo_configuration'].pop('DNA_stock_ng_per_ul'),'MISSING_PARAMETER'),
        ('unregistered_action',lambda p:p['steps'][4].__setitem__('kind','teleport_quantum'),'UNKNOWN_ACTION'),
        ('temperature_37C',lambda p:p['steps'][4].__setitem__('temperature_c',37),'SOP_CONDITION'),
        ('plate_sample_swapped',lambda p:p['plate_map'][0].__setitem__('sample_id','sample:T6'),'CONTAINER_MAPPING'),
        ('pipetting_below_range',lambda p:p['steps'][2]['transfers'][1].__setitem__(2,1),'PIPETTING_RANGE'),
        ('prefilled_reaction',lambda p:p['initial_containers']['T1'].update(volume_ul=50,components_ul={'WATER':50}),'INITIAL_CONTENTS'),
        ('stock_label_mismatch',lambda p:p['initial_containers']['WATER'].__setitem__('components_ul',{'DNA':1000}),'REAGENT_IDENTITY'),
        ('unsupported_validation_claim',lambda p:p['validation_scope'].__setitem__('biological_validation',True),'UNVERIFIED_CLAIM'),
        ('closed_assembly_tube',lambda p:p['initial_containers']['T1'].__setitem__('closure','closed'),'SOP_CONDITION'),
        ('model_capacity_mismatch',lambda p:p['initial_containers']['T1'].__setitem__('capacity_ul',15000),'CAPACITY'),
        ('dependency_cycle',lambda p:p['steps'][0].__setitem__('depends_on',['read_plate']),'DEPENDENCY'),
    ]
    for name,mutate,code in mutations:
        p=baseline();mutate(p);r=Run(p)
        success(name,lambda name=name,r=r,code=code:rejected(name,r,lambda:r.act(expected_step='mix_ready',confirmation=confirmation(r)),{code}))
    def overflow():
        p=baseline();r=Run(p)
        for _ in range(2):r.act(expected_step=r.current()['id'],confirmation=confirmation(r))
        r.state['containers']['T1']['capacity_ul']=40
        return rejected('destination_overflow',r,lambda:r.act(expected_step='fluent_dispense'),{'OVERFLOW','PLANIR_CHECK_FAILED','CAPACITY'})
    success('destination_overflow',overflow)
    report = {"ok": all(c["passed"] for c in results), "cases": results,
              "scope": "D1-D7 deterministic software ledger, frozen SOP/capability and PlanIR checks; simulated confirmations; no real measurements",
              "validation_scope": baseline()["validation_scope"],
              "required_cases": ["normal", "missing_manual_confirmation", "position_conflict", "insufficient_volume"]}
    write_json(directory / "checks.json", report)
    return report


def orchestration_acceptance(output):
    """Persist scenario evidence in the existing export tree without touching live reservations."""
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    from .capabilities import catalog
    from .methods import compile_graph
    from .portfolio import EXAMPLE, build, prepare_plan, replay
    from .scheduling import solve, replan, validate_schedule
    from .reservations import Reservations
    import uuid
    directory=Path(output)/'orchestration'/'acceptance'/str(uuid.uuid4());directory.mkdir(parents=True)
    caps=catalog(output);cases=[]
    def graph(intent=EXAMPLE,c=caps):
        compiled=compile_graph(intent,c);assert compiled['ok'],compiled;return compiled['graph']
    def record(name,fn):
        try:
            result=fn();cases.append({'case':name,'passed':True,'actual':result})
        except Exception as e:cases.append({'case':name,'passed':False,'error':repr(e)})
    for exp in EXAMPLE['experiments']:
        def single(exp=exp):
            p=prepare_plan(solve(graph({**EXAMPLE,'experiments':[exp]}),caps));assert p['ok'];write_json(directory/(exp['method']+'.json'),p)
            return {'status':p['status'],'makespan_s':p['makespan_s'],'cost_cny':p['cost_cny'],'ledger':p['validation'],'events':len(p['events'])}
        record('single_'+exp['method'],single)
    g=graph({**EXAMPLE,'enabled_devices':['device:19','device:67','demo:ks4000:1','bench']});p=prepare_plan(solve(g,caps));write_json(directory/'shared-plan.json',p)
    def normal():
        assert p['ok'] and validate_schedule(p,caps)['passed'];fifo=solve(g,caps,fifo=True);assert fifo['ok'] and p['makespan_s']<fifo['makespan_s']
        return {'status':p['status'],'makespan_s':p['makespan_s'],'fifo_s':fifo['makespan_s'],'saved_seconds':fifo['makespan_s']-p['makespan_s'],'proof_scope':'each fixed-layout objective only'}
    record('shared_parallel_vs_fifo',normal)
    def infeasible(intent=EXAMPLE,c=caps,layout='compact'):
        r=solve(graph(intent,c),c,layout);assert not r['ok'] and r['status']=='INFEASIBLE',r;return {k:r.get(k) for k in ('status','code','detail')}
    record('over_budget',lambda:infeasible({**EXAMPLE,'budget_cny':1}))
    record('deadline_missed',lambda:infeasible({**EXAMPLE,'deadline_s':100}))
    small=copy.deepcopy(caps)
    for d in ('device:19','device:18'):small['devices'][d]['capacity']=2
    record('insufficient_capacity',lambda:infeasible(c=small))
    far=copy.deepcopy(caps);far['layouts']['separated']['positions']['device:67']=[0,1000]
    record('sample_window_missed',lambda:infeasible({**EXAMPLE,'experiments':[EXAMPLE['experiments'][2]]},far,'separated'))
    def contention():
        store=Reservations(directory/'concurrent.sqlite')
        def commit():
            try:return store.commit(p,0)
            except Blocked as e:return {'rejected':e.code}
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:commit(),range(2)))
        assert len([r for r in results if r.get('rejected')=='STALE_REVISION'])==1
        snapshot=store.snapshot();second=solve(g,caps,bookings=snapshot['bookings'])
        # The second long GFP run may exceed this day's deadline; no double booking is permitted either way.
        return {'simultaneous_commits':results,'booked_intervals':len(snapshot['bookings']),'second_request_status':second['status']}
    record('concurrent_shared_reservations',contention)
    def failure():
        q=replan(p,caps,1,'device:19',1800);assert q['ok'];prepare_plan(q);write_json(directory/'replanned.json',q)
        return {'status':q['status'],'frozen':q['replanning']['frozen_steps'],'only_unstarted_modified':q['replanning']['only_unstarted_modified'],'makespan_s':q['makespan_s']}
    record('failure_replan',failure)
    def every_event():
        for at in sorted({e['time_s'] for e in p['events']}):replay(p,at)
        return {'timestamps_checked':len({e['time_s'] for e in p['events']}),'events':len(p['events']),'measurement':None}
    record('replay_ledger_conservation',every_event)
    def enumeration():
        import itertools,math
        from .scheduling import options,transport
        tiny=graph({**EXAMPLE,'experiments':[{'id':'tiny','method':'bca','samples':1,'replicates':1}]});candidates=[]
        for choice in itertools.product(*(options(t,caps) for t in tiny['tasks'])):
            duration=sum(o['duration_s'] for o in choice);cents=round(tiny['consumables_cny']*100)+sum(o['cost_cents'] for o in choice)
            for a,b in zip(choice,choice[1:]):
                seconds,_=transport(caps,'compact',a['resource'],b['resource']);duration+=seconds;cents+=math.ceil(seconds*caps['costs']['operator_per_hour']/36)
            candidates.append((duration,cents))
        proofs=[]
        for objective in ('fastest','cheapest','balanced'):
            q=solve(tiny,caps,objective=objective);best=min(d if objective=='fastest' else c if objective=='cheapest' else d+2*c for d,c in candidates)
            assert q['proven_optimal'] and q['objective_value']==best
            proofs.append({'objective':objective,'enumerated_value':best,'solver_value':q['objective_value'],'status':q['status']})
        return {'candidate_assignments':len(candidates),'proofs':proofs,'scope':'one complete source-bound assay, plus separate multi-job machine-order enumeration in pytest'}
    record('exhaustive_crosscheck',enumeration)
    report={'ok':all(c['passed'] for c in cases),'cases':cases,'directory':str(directory),'scope':'Digital planning and ledger only; no hardware or assay measurement'}
    write_json(directory/'report.json',report);write_json(Path(output)/'orchestration/acceptance.json',report);return report
