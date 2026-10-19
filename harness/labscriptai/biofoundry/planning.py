"""Frozen SOP compiler and checks used by both the authoring and runtime loops."""
import copy
import math
from .workflow import baseline, require, Blocked, Run, complete


def validate_plan(plan):
    cfg = plan['demo_configuration']
    r = cfg.get('replicates_per_group')
    reference = baseline(r)
    require(all(plan.get(k)==reference[k] for k in ('validation_scope','unknowns','sources','verified_public_facts')), 'UNVERIFIED_CLAIM', 'Source facts, unknowns and validation boundaries must come from the registered method')
    require(plan.get('mode') == 'simulation', 'SIMULATION_ONLY', 'Digital backend only')
    require(plan.get('devices') == reference['devices'], 'DEVICE_CAPABILITY', 'Only the registered Fluent1080 / fluorescence iD5 / black96 / 200uL demo is supported')
    dna = cfg.get('DNA_stock_ng_per_ul')
    require(type(dna) in (int, float) and math.isfinite(dna) and dna > 0, 'MISSING_PARAMETER', 'Positive DNA stock concentration required; explicitly accept demo defaults to use 100 ng/uL')
    require(cfg.get('positive_final_DNA_ng_per_ul') == dna/10, 'DNA_CONCENTRATION', 'Final DNA concentration must follow the 45+5 dilution')
    for field in ('groups','reaction_ul','premixed_MIX_ul','DNA_or_water_ul','pipetting_assumed_range_ul','incubation_seconds','read_aliquot_ul','read_diluent_ul','dilution_factor','reader'):
        require(cfg.get(field) == reference['demo_configuration'][field], 'SOP_CONDITION', f'Frozen method mismatch: {field}')
    steps = plan.get('steps', [])
    require(len(steps) == 9 and [s.get('id') for s in steps] == [s['id'] for s in reference['steps']], 'DEPENDENCY', 'Nine ordered registered steps required')
    for step, expected in zip(steps, reference['steps']):
        require(step.get('kind') == expected['kind'], 'UNKNOWN_ACTION', step['id'])
        require(step.get('depends_on') == expected['depends_on'], 'DEPENDENCY', step['id'])
        require(step.get('closures',{}) == expected.get('closures',{}), 'SOP_CONDITION', 'Tube closure/reopening required')
        require(step.get('containers') == expected['containers'], 'CONTAINER_MAPPING', step['id'])
        require(step.get('duration_s') == expected['duration_s'] and step.get('temperature_c') == expected.get('temperature_c') and step.get('shaking') == expected.get('shaking'), 'SOP_CONDITION', step['id'])
        # Report spatial conflicts at the runtime move, where both occupants are known.
        require(len(step.get('moves', [])) == len(expected['moves']), 'CONTAINER_MAPPING', step['id'])
        for a,b in zip(step.get('transfers', []), expected['transfers']):
            require(len(a) == 3 and type(a[2]) in (int,float) and math.isfinite(a[2]) and 5 <= a[2] <= 200, 'PIPETTING_RANGE', str(a))
        require(step.get('transfers') == expected['transfers'], 'CONTROL_RECIPE', f'{step["id"]}: preserve positive and no-template identities and frozen 45+5 / 20+80 recipe')
    require(plan.get('plate_map') == reference['plate_map'], 'CONTAINER_MAPPING', 'Well/sample/group mapping differs from compiled plan')
    require(set(plan['initial_containers']) == set(reference['initial_containers']), 'CONTAINER_MAPPING', 'Unexpected/missing container')
    for cid,c in plan['initial_containers'].items():
        ref=reference['initial_containers'][cid]
        require(all(c.get(k)==ref.get(k) for k in ('id','kind','location','parent','sample_ids','group')), 'CONTAINER_MAPPING', cid)
        require(c.get('capacity_ul')==ref['capacity_ul'], 'CAPACITY', f'{cid}: container capacity must match the registered model')
        require(c.get('closure')==ref.get('closure'), 'SOP_CONDITION', f'{cid}: initial closure must match liquid assembly')
        if c['kind']=='stock_tube':
            require(c['components_ul']=={cid:c['volume_ul']}, 'REAGENT_IDENTITY', f'{cid}: stock contents differ from label')
            require(c['dead_volume_ul']==ref['dead_volume_ul'], 'SOP_CONDITION', f'{cid}: declared reserve changed')
        else:
            require(c['volume_ul']==0 and c['components_ul']=={}, 'INITIAL_CONTENTS', f'{cid}: an empty reaction vessel/well is required')
    needed=sum(len(s['transfers']) for s in steps)
    require(type(plan.get('tips_available')) is int and needed <= plan['tips_available'] <= 96, 'INSUFFICIENT_TIPS', f'{needed} fresh tips required')
    return {'passed': True, 'checks': ['registered actions/devices/plate/tips', 'dependency order/manual gates', 'frozen SOP conditions', 'positive/no-template recipes', 'DNA concentration', 'container/sample/plate mapping'], 'tips_required': needed}


def check_plan(plan):
    try:
        contract=validate_plan(plan)
        run=complete(Run(plan))
        return {'ok': True, 'contract': contract, 'steps_simulated': len(run.state['events']), 'component_totals_ul': run.expected,
                'tips_required': run.state['tips_used'], 'result': run.state['result'], 'scope': plan['validation_scope']}
    except (Blocked, KeyError, TypeError, ValueError) as exc:
        return {'ok': False, 'code': getattr(exc,'code','INVALID_PLAN'), 'detail': str(exc)}


def compile_intent(intent):
    """Model selects typed intent; arithmetic and layout have one deterministic owner."""
    try:
        require(not intent.get('unsupported_requests'), 'UNSUPPORTED_REQUEST', str(intent.get('unsupported_requests')))
        require(intent.get('accept_demo_defaults') is True, 'MISSING_PARAMETER', 'Accept labelled demo settings or provide a separately validated SOP; onsite guidance remains blocked')
        require(intent.get('temperature_c') == 30 and intent.get('duration_s') == 10800 and intent.get('excitation_nm') == 488 and intent.get('emission_nm') == 525, 'SOP_CONDITION', 'Supported demo: 30C/3h, Ex488/Em525')
        plan=baseline(intent.get('replicates'))
        dna=intent.get('DNA_stock_ng_per_ul')
        plan['demo_configuration']['DNA_stock_ng_per_ul']=dna
        plan['demo_configuration']['positive_final_DNA_ng_per_ul']=dna/10 if type(dna) in (int,float) else None
        checks=check_plan(plan)
        return {'ok': checks['ok'], 'intent': copy.deepcopy(intent), 'plan': plan if checks['ok'] else None, 'checks': checks}
    except (Blocked, KeyError, TypeError, ValueError) as exc:
        return {'ok':False, 'code':getattr(exc,'code','INVALID_INTENT'), 'detail':str(exc)}
