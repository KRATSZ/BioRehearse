"""Reproducible digital protocols bound to delivered asset nodes, never hardware.

Run: python -m sim.library_protocols --output exports/biofoundry
Integration: run_validation(output); per_asset_status(output, asset_id).
The access positions are *existing checked demonstration frames*, not measured
loading clearances. Liquid bookkeeping is explicit simulation, not pipette IK.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

SCHEMA = 'biofoundry.digital-protocols/1'
REPORT = 'library-protocol-checks.json'
# Exact node names, not fuzzy equipment-name matching. Additional authored assets
# may declare this dictionary in their contract's digital_protocol_profile.
PROFILES = {
    'ika_ks4000': {'access_joint_names': ['ika_ks4000__urdf__hood_joint'], 'operation_joint_names': ['ika_ks4000__urdf__orbit_x_joint', 'ika_ks4000__urdf__platform_joint']},
    'eppendorf_5910ri': {'access_joint_names': ['eppendorf_5910ri__urdf__lid_joint'], 'operation_joint_names': ['eppendorf_5910ri__urdf__rotor_joint']},
    'biorad_miniprotean': {'access_joint_names': ['biorad_miniprotean__urdf__lid_joint']},
    'eppendorf_cellxpertc170i': {'access_joint_names': ['eppendorf_cellxpertc170i__urdf__outer_door_joint', 'eppendorf_cellxpertc170i__urdf__inner_door_joint']},
    'bmg_clariostarplus': {'access_joint_names': ['bmg_clariostarplus__urdf__plate_carrier_joint']},
    'thermo_ibrightfl1500': {'access_joint_names': ['thermo_ibrightfl1500__urdf__sample_drawer_joint']},
    'biotek_405ts': {'access_joint_names': ['biotek_405ts__urdf__plate_carrier_joint']},
    'sartorius_octet_r8': {'access_joint_names': ['front_top_hood_hinge']},
    'roche_lightcycler_480_ii': {'access_joint_names': ['LC480 multiwell plate loader']},
    'beckman_optima_xe100': {'access_joint_names': ['beckman_optima_xe100_chamber_door_slide'], 'operation_joint_names': ['beckman_optima_xe100_rotor_Z']},
    'beckman_optima_xpn100': {'access_joint_names': ['beckman_optima_xpn100_chamber_door_slide'], 'operation_joint_names': ['beckman_optima_xpn100_rotor_Z']},
    'thermo_sorvall_lynx6000': {'access_joint_names': ['thermo_sorvall_lynx6000_lid_hinge'], 'operation_joint_names': ['thermo_sorvall_lynx6000_rotor_Z']},
    'spectramax-i3x': {'access_joint_names': ['i3x_plate_drawer_slide']},
    'biotek-logphase-600': {'access_joint_names': ['logphase_chamber_lid_hinge'], 'operation_joint_names': ['logphase_orbital_shaker_x', 'logphase_orbital_shaker_y']},
    'tecan-fluent780': {'access_joint_names': ['f780_front_guard_hinge_0', 'f780_front_guard_hinge_1'], 'liquid_accounting': True},
    'agilent_bravo_assaymap': {'liquid_accounting': True},
    # New authored assets: exact sample hatches/ports confirmed by each recipe
    # owner. Source/service covers and open microscope XY stages are excluded.
    'beckman_cytoflex_lx': {'access_joint_names': ['beckman_cytoflex_lx_plate_loader_Y']},
    'quantum_design_ppms_dynacool': {'access_joint_names': ['quantum_design_ppms_dynacool_sample_port_cap_Z', 'quantum_design_ppms_dynacool_sample_transfer_rod_Z']},
    'perkinelmer_tga8000': {'access_joint_names': ['perkinelmer_tga8000_furnace_elevator_Z']},
    'wyatt_dynapro_nanostar': {'access_joint_names': ['wyatt_dynapro_nanostar_sample_hatch_slide_Y', 'wyatt_dynapro_nanostar_chamber_cap_Z']},
    'rigaku_xtalab_synergy_dw': {
        'access_joint_names': ['rigaku_dw_cabinet_door'],
        'mutually_exclusive_joint_groups': [
            ['rigaku_dw_detector_two_theta', 'rigaku_dw_detector_distance'],
            ['rigaku_dw_omega'], ['rigaku_dw_kappa'], ['rigaku_dw_phi']],
    },
    'nanoscribe_gt2': {'access_joint_names': ['GT2 hinged top print-chamber lid']},
    'agilent-1260-infinity-ii-analytical': {'access_joint_names': ['agilent-1260-infinity-ii-analytical_sampler_door_L', 'agilent-1260-infinity-ii-analytical_sampler_door_R', 'agilent-1260-infinity-ii-analytical_sampler_sample_tray']},
    'agilent-1260-infinity-ii-semiprep': {'access_joint_names': ['agilent-1260-infinity-ii-semiprep_sampler_door_L', 'agilent-1260-infinity-ii-semiprep_sampler_door_R', 'agilent-1260-infinity-ii-semiprep_sampler_sample_tray']},
    'agilent-1290-infinity-ii-analytical-elsd': {'access_joint_names': ['agilent-1290-infinity-ii-analytical-elsd_multisampler_door_L', 'agilent-1290-infinity-ii-analytical-elsd_multisampler_door_R', 'agilent-1290-infinity-ii-analytical-elsd_multisampler_sample_tray']},
    'agilent-1290-infinity-ii-analytical': {'access_joint_names': ['agilent-1290-infinity-ii-analytical_multisampler_door_L', 'agilent-1290-infinity-ii-analytical_multisampler_door_R', 'agilent-1290-infinity-ii-analytical_multisampler_sample_tray']},
    'agilent-rapidfire400-6470': {'access_joint_names': ['agilent-rapidfire400-6470_front_guard']},

}


class Blocked(ValueError):
    def __init__(self, code, detail):
        self.code = code
        super().__init__(detail)


def require(ok, code, detail):
    if not ok:
        raise Blocked(code, detail)


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class Library:
    """One asset configuration may back many separately identified devices."""
    def __init__(self, output):
        self.output = Path(output)
        self.assets = {a['asset_id']: a for a in read(self.output / 'asset-library.json')['assets']}
        inventory = self.output / 'facility-inventory.json'
        self.devices = {d['id']: d for d in read(inventory)['devices']} if inventory.exists() else {}

    def select(self, *, asset_id=None, device_id=None):
        require((asset_id is None) != (device_id is None), 'IDENTITY', 'Select exactly one asset_id or device_id')
        if device_id is not None:
            require(type(device_id) is int and device_id in self.devices, 'UNKNOWN_DEVICE', str(device_id))
            asset_id = self.devices[device_id].get('asset_id')
            require(asset_id is not None, 'UNMAPPED_DEVICE', str(device_id))
        require(asset_id in self.assets, 'UNKNOWN_ASSET', str(asset_id))
        return Binding(self, asset_id, device_id)


class Binding:
    def __init__(self, library, asset_id, device_id):
        self.library, self.asset_id, self.device_id = library, asset_id, device_id
        self.asset = library.assets[asset_id]
        self.contract_path = library.output / 'library' / asset_id / 'asset.contract.json'
        self.contract = read(self.contract_path)
        self.reference_path = library.output / self.asset['assembly_reference']
        self.reference = read(self.reference_path)
        require(self.contract['asset_id'] == self.reference['asset_id'] == asset_id, 'IDENTITY', asset_id)
        sampled_ids = {p['joint'] for p in self.reference['poses'] if p.get('joint')}
        self.joints = {n['id']: n for n in self.reference['nodes'] if n['id'] in sampled_ids and n.get('joint', {}).get('joint_type') in ('prismatic', 'revolute', 'continuous')}
        require(self.joints.keys() == sampled_ids, 'UNBOUND_CHECKED_JOINT', asset_id)
        self.unsampled_joint_nodes = [n['id'] for n in self.reference['nodes'] if n.get('joint') and n['id'] not in sampled_ids]
        self.profile = copy.deepcopy(self.contract.get('digital_protocol_profile', self.asset.get('digital_protocol_profile', PROFILES.get(asset_id, {}))))
        names = {n['name']: n['id'] for n in self.joints.values()}
        groups = self.profile.get('mutually_exclusive_joint_groups', [])
        require(isinstance(groups, list), 'PROFILE_JOINT_GROUPS', 'Exclusive groups must be a list of nonempty name lists')
        self.exclusive_groups = []
        grouped_names = set()
        for group in groups:
            require(isinstance(group, list) and bool(group) and all(isinstance(name, str) for name in group),
                    'PROFILE_JOINT_GROUPS', 'Each exclusive group must contain exact joint names')
            bound = []
            for name in group:
                require(name in names, 'PROFILE_JOINT_MISSING', name)
                require(name not in grouped_names, 'PROFILE_JOINT_GROUP_DUPLICATE', name)
                grouped_names.add(name);bound.append(names[name])
            self.exclusive_groups.append(bound)
        self.access = []
        for name in self.profile.get('access_joint_names', []):
            require(name in names, 'PROFILE_JOINT_MISSING', name)
            self.access.append(names[name])
        self.operations = []
        for name in self.profile.get('operation_joint_names', []):
            require(name in names, 'PROFILE_JOINT_MISSING', name)
            self.operations.append(names[name])
        self.samples = {}
        for p in self.reference['poses']:
            if p.get('joint') in self.joints and abs(p['position']) > 1e-12:
                self.samples.setdefault(p['joint'], p)
        for jid, node in self.joints.items():
            j = node['joint']; axis = j.get('joint_axis', [])
            require(len(axis) == 3 and all(finite(v) for v in axis) and sum(v*v for v in axis) > 1e-12, 'JOINT_AXIS', jid)
            unit = 'm' if j['joint_type'] == 'prismatic' else 'rad'
            require(j.get('joint_units') == unit, 'JOINT_UNIT', jid)
            limits = j.get('joint_limits', [])
            require(len(limits) == 2 and all(finite(v) for v in limits) and limits[0] <= 0 <= limits[1], 'JOINT_LIMITS', jid)
            require(jid in self.samples, 'NO_CHECKED_POSE', jid)
            self.validate_position(jid, self.samples[jid]['position'], unit)
        self.fingerprint = binding_fingerprint(self)

    def validate_position(self, jid, value, unit):
        require(jid in self.joints, 'UNKNOWN_JOINT', str(jid))
        j = self.joints[jid]['joint']
        require(unit == j['joint_units'], 'JOINT_UNIT', f'{jid}: use {j["joint_units"]}')
        require(finite(value), 'JOINT_POSITION', str(value))
        # Continuous joints also stay inside the digital preview range; this is
        # deliberately not claimed as their physical rotation limit.
        require(j['joint_limits'][0] <= value <= j['joint_limits'][1], 'JOINT_LIMIT', f'{jid}: {value}')

    def validate_combination(self, positions):
        # Unlisted joints (for example an access door) retain their existing
        # per-axis limits. This rule restricts explicitly listed joints only.
        active = [index for index,group in enumerate(self.exclusive_groups)
                  if any(positions.get(jid, 0.0) != 0.0 for jid in group)]
        require(len(active) <= 1, 'MUTUALLY_EXCLUSIVE_JOINTS',
                'Digital demonstration permits nonzero positions in only one listed group: '+str(active))

    def combination_policy(self):
        return {'groups': [{'joint_names': [self.joints[jid]['name'] for jid in group], 'node_ids': list(group)}
                           for group in self.exclusive_groups],
                'active_position_rule': 'position != 0.0', 'unlisted_joint_policy': 'unrestricted_by_this_combination_rule',
                'scope': 'Digital demonstration whitelist only; not manufacturer or calibrated hardware limits, or collision certification'}

    def frame_for(self, jid, value):
        if abs(value) < 1e-12:
            return 0
        p = self.samples[jid]
        return p['frame'] if abs(value-p['position']) < 1e-12 else None

    def motion_trace(self, jid, value):
        node = self.joints[jid]
        return {'asset_id': self.asset_id, 'device_id': self.device_id, 'node_id': jid, 'node_name': node['name'],
                **copy.deepcopy(node['joint']), 'position': value, 'position_semantics': 'delta_from_rest_URDF_q0', 'units': node['joint']['joint_units'], 'joint_node_id': jid, 'reference_frame': self.frame_for(jid, value),
                'axis_frame': 'Blender Z-up node-local', 'reference': str(self.reference_path.relative_to(self.library.output))}


def binding_fingerprint(binding):
    profile_json = json.dumps(binding.profile, sort_keys=True, allow_nan=False).encode()
    return {'runner_source_sha256': digest(__file__), 'model_glb_sha256': digest(binding.library.output/binding.asset['normalized_glb']),
            'reference_sha256': digest(binding.reference_path), 'profile_sha256': hashlib.sha256(profile_json).hexdigest()}


def component_totals(samples):
    result = {}
    for c in samples.values():
        for name, amount in c['components_ul'].items():
            result[name] = result.get(name, 0.0) + amount
    return result


class Run:
    """Transactional digital lifecycle and conservative sample bookkeeping."""
    def __init__(self, binding, samples=None):
        self.binding = binding
        self.state = {'mode': 'digital_simulation_only', 'asset_id': binding.asset_id, 'device_id': binding.device_id,
                      'running': False, 'loaded': [], 'positions': {j: 0.0 for j in binding.joints},
                      'samples': copy.deepcopy(samples or {}), 'events': [], 'pose_trace': [],
                      'readout': {'status': 'unavailable', 'values': None, 'unit': None, 'reason': 'No connected readout source'}}
        self.expected = component_totals(self.state['samples'])
        self._validate(self.state)

    def _validate(self, state):
        occupied = set()
        for cid, c in state['samples'].items():
            require(isinstance(c['location'], str) and c['location'] not in occupied, 'LOCATION_CONFLICT', cid)
            occupied.add(c['location'])
            require(all(finite(c[k]) for k in ('volume_ul', 'capacity_ul')) and 0 <= c['volume_ul'] <= c['capacity_ul'], 'INVALID_VOLUME', cid)
            require(all(finite(v) and v >= 0 for v in c['components_ul'].values()), 'COMPONENT_BALANCE', cid)
            require(abs(sum(c['components_ul'].values())-c['volume_ul']) < 1e-8, 'COMPONENT_BALANCE', cid)
        actual = component_totals(state['samples'])
        require(actual.keys() == self.expected.keys() and all(abs(actual[k]-v) < 1e-8 for k,v in self.expected.items()), 'VOLUME_CONSERVATION', str(actual))
        for jid, value in state['positions'].items():
            self.binding.validate_position(jid, value, self.binding.joints[jid]['joint']['joint_units'])
        self.binding.validate_combination(state['positions'])

    def act(self, command, **args):
        require(self.state['mode'] == 'digital_simulation_only', 'SIMULATION_ONLY', 'No hardware mode or vendor adapter')
        fields = {'open': set(), 'close': set(), 'start': set(), 'finish': set(), 'read': set(),
                  'pose': {'node_id','position','unit'}, 'load': {'sample_id','origin'},
                  'unload': {'sample_id','origin','destination'}, 'replay': {'frame'},
                  'transfer': {'source','destination','volume_ul','source_location','destination_location'}}
        require(command in fields, 'UNKNOWN_COMMAND', command)
        require(not (fields[command]-args.keys()), 'MISSING_ARGUMENT', str(sorted(fields[command]-args.keys())))
        require(not (args.keys()-fields[command]), 'UNKNOWN_ARGUMENT', str(sorted(args.keys()-fields[command])))
        candidate = copy.deepcopy(self.state)
        trace_start = len(candidate['pose_trace'])
        self._apply(candidate, command, args)
        for trace in candidate['pose_trace'][trace_start:]:
            trace.update(action=command, phase=command, event_sequence=len(candidate['events']))
        self._validate(candidate)
        candidate['events'].append({'sequence': len(candidate['events']), 'command': command, 'arguments': copy.deepcopy(args)})
        self.state = candidate
        return copy.deepcopy(self.state)

    def _pose(self, state, jid, value, unit):
        self.binding.validate_position(jid, value, unit)
        state['positions'][jid] = value
        trace = self.binding.motion_trace(jid, value)
        trace['positions_after'] = copy.deepcopy(state['positions'])
        trace['reference_frame_scope'] = 'single_command_joint_from_rest; positions_after may combine joints'
        state['pose_trace'].append(trace)

    def _apply(self, s, command, args):
        b = self.binding
        if command in ('open', 'close', 'pose', 'load', 'unload', 'transfer', 'replay'):
            require(not s['running'], 'BUSY', command)
        if command in ('open', 'close'):
            require(bool(b.access), 'CAPABILITY_UNAVAILABLE', 'No explicitly mapped loading access')
            for jid in (b.access if command == 'open' else reversed(b.access)):
                value = b.samples[jid]['position'] if command == 'open' else 0.0
                self._pose(s, jid, value, b.joints[jid]['joint']['joint_units'])
        elif command == 'pose':
            self._pose(s, args['node_id'], args['position'], args['unit'])
        elif command in ('load', 'unload'):
            require(bool(b.access), 'CAPABILITY_UNAVAILABLE', 'No explicitly mapped loading access')
            require(all(abs(s['positions'][jid]-b.samples[jid]['position']) < 1e-12 for jid in b.access), 'ACCESS_CLOSED', command)
            cid = args['sample_id']; require(cid in s['samples'], 'UNKNOWN_SAMPLE', cid)
            c = s['samples'][cid]
            destination = f'device:{b.device_id if b.device_id is not None else b.asset_id}:sample' if command == 'load' else args['destination']
            require(c['location'] == args['origin'], 'WRONG_LOCATION', cid)
            require(not any(v['location'] == destination for v in s['samples'].values()), 'LOCATION_CONFLICT', destination)
            if command == 'load':
                require(not s['loaded'], 'CAPACITY', 'Digital demonstration has one loading slot')
                require(cid not in s['loaded'], 'ALREADY_LOADED', cid)
                s['loaded'].append(cid)
            else:
                require(isinstance(destination, str) and destination.startswith('prep:') and len(destination)>5, 'WRONG_LOCATION', 'Unload into an explicit preparation location')
                require(cid in s['loaded'], 'NOT_LOADED', cid)
                s['loaded'].remove(cid)
            c['location'] = destination
        elif command == 'start':
            require(not s['running'], 'BUSY', command)
            require(bool(b.access), 'CAPABILITY_UNAVAILABLE', 'No explicitly mapped operating lifecycle')
            require(bool(s['loaded']), 'NO_SAMPLE', 'Load a sample before running')
            require(all(abs(s['positions'][jid]) < 1e-12 for jid in b.access), 'ACCESS_OPEN', 'Close every loading access before start')
            s['running'] = True
            for jid in b.operations:
                self._pose(s, jid, b.samples[jid]['position'], b.joints[jid]['joint']['joint_units'])
        elif command == 'finish':
            require(s['running'], 'NOT_RUNNING', command)
            for jid in reversed(b.operations):
                self._pose(s, jid, 0.0, b.joints[jid]['joint']['joint_units'])
            s['running'] = False
        elif command == 'read':
            require(not s['running'], 'BUSY', command)
            s['readout'] = {'status': 'unavailable', 'values': None, 'unit': None, 'reason': 'No connected readout source'}
        elif command == 'transfer':
            require(b.profile.get('liquid_accounting') is True, 'CAPABILITY_UNAVAILABLE', 'No liquid accounting profile')
            src, dst, volume = args['source'], args['destination'], args['volume_ul']
            require(src != dst and src in s['samples'] and dst in s['samples'], 'UNKNOWN_SAMPLE', str((src,dst)))
            require(finite(volume) and volume > 0, 'INVALID_VOLUME', str(volume))
            a,c = s['samples'][src], s['samples'][dst]
            require(a['location'] == args['source_location'] and c['location'] == args['destination_location'], 'WRONG_LOCATION', 'Transfer location mismatch')
            require(a['volume_ul'] >= volume, 'INSUFFICIENT_VOLUME', src)
            require(c['volume_ul']+volume <= c['capacity_ul'], 'OVERFLOW', dst)
            for component, amount in list(a['components_ul'].items()):
                part = amount*volume/a['volume_ul']
                a['components_ul'][component] -= part
                c['components_ul'][component] = c['components_ul'].get(component,0)+part
            a['volume_ul'] -= volume; c['volume_ul'] += volume
        elif command == 'replay':
            require(not b.joints, 'USE_JOINT_POSE', 'Articulated assets use explicit joint poses')
            frames = {p['frame'] for p in b.reference['poses']}
            require(args['frame'] in frames, 'UNKNOWN_FRAME', str(args['frame']))
            s['pose_trace'].append({'asset_id': b.asset_id, 'device_id': b.device_id, 'mode': 'existing_animation_frame_replay',
                                    'reference_frame': args['frame'], 'reference': str(b.reference_path.relative_to(b.library.output))})
        else:
            raise Blocked('UNKNOWN_COMMAND', command)


def demo_samples():
    return {'sample': {'location': 'prep:sample', 'capacity_ul': 200.0, 'volume_ul': 100.0, 'components_ul': {'sample': 100.0}},
            'destination': {'location': 'prep:destination', 'capacity_ul': 200.0, 'volume_ul': 0.0, 'components_ul': {}}}



class Workflow:
    """A shared sample ledger and distinct device instances, committed atomically."""
    def __init__(self, bindings, samples, routes=None):
        identities = [(b.asset_id,b.device_id) for b in bindings.values()]
        require(len(identities) == len(set(identities)), 'IDENTITY', 'Device instance may occupy only one workflow station')
        self.bindings = bindings
        self.routes = copy.deepcopy(routes or {})
        for route_id,route in self.routes.items():
            require(route['source'] in bindings and route['destination'] in bindings and route['source'] != route['destination'], 'IDENTITY', route_id)
            require(route['sample_id'] in samples, 'UNKNOWN_SAMPLE', route_id)
            require(all(dep in self.routes for dep in route.get('depends_on',[])), 'UNKNOWN_ROUTE', route_id)
        self.expected = component_totals(samples)
        self.state = {'samples': copy.deepcopy(samples), 'stations': {}, 'events': [], 'completed_handoffs': [], 'revision': 0}
        for station, binding in bindings.items():
            self.state['stations'][station] = Run(binding, samples).state
        self._initial = copy.deepcopy(self.state)

    def act(self, station, command, **args):
        require(station in self.bindings, 'UNKNOWN_DEVICE', station)
        candidate = copy.deepcopy(self.state)
        run = Run(self.bindings[station], candidate['samples'])
        run.state = candidate['stations'][station]
        run.state['samples'] = copy.deepcopy(candidate['samples'])
        # Custody in any other station cannot be bypassed by spelling its port.
        touched = [args[k] for k in ('sample_id','source','destination') if k in args]
        held_elsewhere = {cid for name,s in candidate['stations'].items() if name != station for cid in s['loaded']}
        require(not held_elsewhere.intersection(touched), 'SAMPLE_CUSTODY', str(touched))
        run.act(command, **args)
        candidate['stations'][station] = run.state
        candidate['samples'] = copy.deepcopy(run.state['samples'])
        for device_state in candidate['stations'].values():
            device_state['samples'] = copy.deepcopy(candidate['samples'])
        actual = component_totals(candidate['samples'])
        require(actual.keys() == self.expected.keys() and all(abs(actual[k]-v)<1e-8 for k,v in self.expected.items()), 'VOLUME_CONSERVATION', station)
        candidate['events'].append({'station': station, 'command': command, 'arguments': copy.deepcopy(args)})
        candidate['revision'] = self.state['revision']+1
        self._validate_snapshot_state(candidate)
        self.state = candidate
        return copy.deepcopy(self.state)


    def _manifest(self):
        return {name: {'asset_id': b.asset_id, 'device_id': b.device_id, 'fingerprint': binding_fingerprint(b)}
                for name,b in self.bindings.items()}

    @staticmethod
    def _state_digest(state):
        return hashlib.sha256(json.dumps(state,sort_keys=True,allow_nan=False,separators=(',',':')).encode()).hexdigest()

    def _validate_snapshot_state(self, state):
        require(set(state['stations']) == set(self.bindings), 'IDENTITY', 'Station set changed')
        require(set(state['samples']) == set(self._initial['samples']), 'IDENTITY', 'Sample set changed')
        require(set(state['completed_handoffs']).issubset(self.routes) and len(state['completed_handoffs']) == len(set(state['completed_handoffs'])),
                'FLOW_ORDER', 'Invalid completed route history')
        for index,route_id in enumerate(state['completed_handoffs']):
            require(all(dep in state['completed_handoffs'][:index] for dep in self.routes[route_id].get('depends_on',[])), 'FLOW_ORDER', route_id)
        claimed = set()
        for cid,c in state['samples'].items():
            require(c['capacity_ul'] == self._initial['samples'][cid]['capacity_ul'], 'IDENTITY', 'Container capacity changed: '+cid)
        for name,binding in self.bindings.items():
            device = state['stations'][name]
            require(device['mode'] == 'digital_simulation_only', 'SIMULATION_ONLY', name)
            require(device['asset_id'] == binding.asset_id and device['device_id'] == binding.device_id, 'IDENTITY', name)
            require(device['samples'] == state['samples'], 'SAMPLE_CUSTODY', 'Station ledger differs: '+name)
            require(set(device['positions']) == set(binding.joints), 'UNKNOWN_JOINT', name)
            run = Run(binding,self._initial['samples']);run.state = device;run._validate(device)
            require(len(device['loaded']) <= 1 and len(set(device['loaded'])) == len(device['loaded']), 'CAPACITY', name)
            port = f'device:{binding.device_id if binding.device_id is not None else binding.asset_id}:sample'
            for cid in device['loaded']:
                require(cid in state['samples'] and cid not in claimed and state['samples'][cid]['location'] == port, 'SAMPLE_CUSTODY', name)
                claimed.add(cid)
            occupants = {cid for cid,c in state['samples'].items() if c['location'] == port}
            require(occupants == set(device['loaded']), 'SAMPLE_CUSTODY', name)
            if device['running']:
                require(device['loaded'] and binding.access and all(abs(device['positions'][jid])<1e-12 for jid in binding.access), 'ACCESS_OPEN', name)
            require(device['readout']['status'] == 'unavailable' and device['readout']['values'] is None and device['readout']['unit'] is None,
                    'FABRICATED_READOUT', name)
        for cid,c in state['samples'].items():
            require(not c['location'].startswith('device:') or cid in claimed, 'SAMPLE_CUSTODY', 'Unclaimed device location: '+cid)
        actual = component_totals(state['samples'])
        require(actual.keys() == self.expected.keys() and all(abs(actual[k]-v)<1e-8 for k,v in self.expected.items()), 'VOLUME_CONSERVATION', 'Snapshot')

    def handoff(self, route_id, *, sample_id, expected_revision=None):
        """Commit unload+load together against a declared, single-use sample route.

        Both devices must already be stopped and their actual loading access open.
        This models a manual custody change, without a robot path or hardware I/O.
        """
        if expected_revision is not None:
            require(type(expected_revision) is int and expected_revision == self.state['revision'], 'STALE_REVISION', route_id)
        require(route_id in self.routes, 'UNKNOWN_ROUTE', route_id)
        route = self.routes[route_id]
        require(sample_id == route['sample_id'], 'WRONG_SAMPLE', route_id)
        require(route_id not in self.state['completed_handoffs'], 'DUPLICATE_HANDOFF', route_id)
        require(all(dep in self.state['completed_handoffs'] for dep in route.get('depends_on',[])), 'FLOW_ORDER', route_id)
        source,destination = route['source'],route['destination']
        require(sample_id in self.state['stations'][source]['loaded'], 'NOT_LOADED', route_id)
        candidate = copy.copy(self);candidate.state = copy.deepcopy(self.state)
        origin = candidate.state['samples'][sample_id]['location']
        staging = 'prep:handoff:'+route_id
        candidate.act(source,'unload',sample_id=sample_id,origin=origin,destination=staging)
        candidate.act(destination,'load',sample_id=sample_id,origin=staging)
        candidate.state['completed_handoffs'].append(route_id)
        candidate.state['events'].append({'command': 'handoff', 'route_id': route_id, 'sample_id': sample_id,
                                          'source': source, 'destination': destination, 'manual_simulation': True})
        candidate.state['revision'] = self.state['revision']+1
        candidate._validate_snapshot_state(candidate.state)
        self.state = candidate.state
        return copy.deepcopy(self.state)

    def checkpoint(self):
        self._validate_snapshot_state(self.state)
        return {'schema': 'biofoundry.workflow-checkpoint/1', 'mode': 'digital_simulation_only',
                'manifest': self._manifest(), 'routes': copy.deepcopy(self.routes),
                'state': copy.deepcopy(self.state), 'state_sha256': self._state_digest(self.state)}

    def restore(self, checkpoint, *, expected_revision):
        """Restore an explicitly selected simulation checkpoint, atomically."""
        require(type(expected_revision) is int and expected_revision == self.state['revision'], 'STALE_REVISION', 'restore')
        require(checkpoint.get('schema') == 'biofoundry.workflow-checkpoint/1' and checkpoint.get('mode') == 'digital_simulation_only',
                'SIMULATION_ONLY', 'Checkpoint schema or mode')
        require(checkpoint['manifest'] == self._manifest() and checkpoint['routes'] == self.routes, 'CHECKPOINT_BINDING', 'Assets, instances or routes changed')
        state = copy.deepcopy(checkpoint['state'])
        require(checkpoint['state_sha256'] == self._state_digest(state), 'CHECKPOINT_CORRUPT', 'Checkpoint digest mismatch')
        self._validate_snapshot_state(state)
        state['revision'] = self.state['revision']+1
        state['events'].append({'command': 'restore', 'checkpoint_state_sha256': checkpoint['state_sha256'],
                                 'previous_revision': self.state['revision'], 'simulation_only': True})
        self.state = state
        return copy.deepcopy(self.state)

    def reset(self, *, expected_revision):
        """Reset only an unloaded, stopped digital run; never implies hardware reset."""
        require(type(expected_revision) is int and expected_revision == self.state['revision'], 'STALE_REVISION', 'reset')
        require(not any(s['running'] for s in self.state['stations'].values()), 'BUSY', 'reset')
        require(not any(s['loaded'] for s in self.state['stations'].values()), 'SAMPLES_LOADED', 'Unload samples before reset')
        state = copy.deepcopy(self._initial)
        state['revision'] = self.state['revision']+1
        state['events'].append({'command': 'reset', 'previous_revision': self.state['revision'], 'simulation_only': True})
        self._validate_snapshot_state(state)
        self.state = state
        return copy.deepcopy(self.state)


def validate_workflow(library):
    """20 uL abstract transfer -> thermocycler lifecycle -> reader lifecycle.

    There is no thermochemistry, pipette path/IK, or simulated optical signal.
    Every loading action targets exact delivered LC480/i3x access nodes.
    """
    required = ('agilent_bravo_assaymap', 'roche_lightcycler_480_ii', 'spectramax-i3x')
    if not all(ident in library.assets for ident in required):
        return {'passed': False, 'status': 'unavailable', 'reason': 'Required reference assets missing'}
    flow = Workflow({ident: library.select(asset_id=ident) for ident in required}, demo_samples())
    arguments = {'source': 'sample', 'destination': 'destination', 'source_location': 'prep:sample', 'destination_location': 'prep:destination'}
    before = copy.deepcopy(flow.state)
    try:
        flow.act(required[0], 'transfer', volume_ul=101, **arguments)
    except Blocked as exc:
        require(exc.code == 'INSUFFICIENT_VOLUME' and flow.state == before, 'NONATOMIC_REJECTION', 'workflow transfer')
    else:
        raise Blocked('EXPECTED_REJECTION_MISSING', 'workflow transfer')
    flow.act(required[0], 'transfer', volume_ul=20, **arguments)
    origin = 'prep:destination'
    for station in required[1:]:
        flow.act(station, 'open')
        flow.act(station, 'load', sample_id='destination', origin=origin)
        flow.act(station, 'close'); flow.act(station, 'start'); flow.act(station, 'finish')
        flow.act(station, 'read'); flow.act(station, 'open')
        device_origin = flow.state['samples']['destination']['location']
        origin = 'prep:after:'+station
        flow.act(station, 'unload', sample_id='destination', origin=device_origin, destination=origin)
        flow.act(station, 'close')
    require(flow.state['samples']['sample']['volume_ul'] == 80 and flow.state['samples']['destination']['volume_ul'] == 20,
            'TRANSFER_RESULT', 'workflow')
    traces = [{'asset_id': name, 'steps': state['pose_trace']} for name,state in flow.state['stations'].items()]
    return {'passed': True, 'status': 'digital_simulation_passed', 'mode': 'shared_ledger_cross_device_simulation',
            'workflow_adapter_validated': False, 'hardware_adapter_validated': False,
            'events': flow.state['events'], 'sample_final': flow.state['samples'], 'traces': traces,
            'readouts': {name: s['readout'] for name,s in flow.state['stations'].items()},
            'limitations': ['No pipetting IK, collision/clearance validation, thermochemistry, or connected reader data']}


def _reject(run, command, code, **args):
    before = copy.deepcopy(run.state)
    try:
        run.act(command, **args)
    except Blocked as exc:
        require(exc.code == code, 'WRONG_REJECTION', f'{command}: {exc.code} != {code}')
        require(run.state == before, 'NONATOMIC_REJECTION', command)
        return {'command': command, 'expected_code': code, 'observed_code': exc.code, 'state_unchanged': True}
    raise Blocked('EXPECTED_REJECTION_MISSING', command)


def validate_asset(binding):
    run = Run(binding, demo_samples()); negative = []
    for jid, node in binding.joints.items():
        j = node['joint']; unit = j['joint_units']; value = binding.samples[jid]['position']
        negative.append(_reject(run, 'pose', 'JOINT_UNIT', node_id=jid, position=value, unit='mm' if unit == 'm' else 'degree'))
        negative.append(_reject(run, 'pose', 'JOINT_LIMIT', node_id=jid, position=j['joint_limits'][1]+1, unit=unit))
        run.act('pose', node_id=jid, position=value, unit=unit)
        run.act('pose', node_id=jid, position=0, unit=unit)
    if binding.exclusive_groups:
        # Exercise the actual declared combinations, not merely profile parsing.
        first = binding.exclusive_groups[0]
        for jid in first:
            run.act('pose', node_id=jid, position=binding.samples[jid]['position'], unit=binding.joints[jid]['joint']['joint_units'])
        for group in binding.exclusive_groups[1:]:
            jid = group[0]
            negative.append(_reject(run, 'pose', 'MUTUALLY_EXCLUSIVE_JOINTS', node_id=jid,
                                    position=binding.samples[jid]['position'], unit=binding.joints[jid]['joint']['joint_units']))
        for jid in reversed(first):
            run.act('pose', node_id=jid, position=0.0, unit=binding.joints[jid]['joint']['joint_units'])
    lifecycle = False
    if binding.access:
        negative.append(_reject(run, 'load', 'ACCESS_CLOSED', sample_id='sample', origin='prep:sample'))
        run.act('open'); run.act('load', sample_id='sample', origin='prep:sample')
        negative.append(_reject(run, 'start', 'ACCESS_OPEN'))
        run.act('close'); run.act('start')
        negative.append(_reject(run, 'open', 'BUSY'))
        negative.append(_reject(run, 'unload', 'BUSY', sample_id='sample', origin='wrong', destination='prep:sample'))
        run.act('finish'); run.act('open')
        origin = run.state['samples']['sample']['location']
        negative.append(_reject(run, 'unload', 'LOCATION_CONFLICT', sample_id='sample', origin=origin, destination='prep:destination'))
        run.act('unload', sample_id='sample', origin=origin, destination='prep:sample'); run.act('close')
        lifecycle = True
    elif not binding.joints:
        for p in binding.reference['poses']:
            run.act('replay', frame=p['frame'])
        negative.append(_reject(run, 'pose', 'UNKNOWN_JOINT', node_id='invented-joint', position=0, unit='m'))
    liquid = binding.profile.get('liquid_accounting') is True
    if liquid:
        arguments = {'source': 'sample', 'destination': 'destination', 'source_location': 'prep:sample', 'destination_location': 'prep:destination'}
        negative.append(_reject(run, 'transfer', 'INSUFFICIENT_VOLUME', volume_ul=101, **arguments))
        run.act('transfer', volume_ul=20, **arguments)
        require(run.state['samples']['sample']['volume_ul'] == 80 and run.state['samples']['destination']['volume_ul'] == 20, 'TRANSFER_RESULT', binding.asset_id)
    run.act('read')
    require(run.state['readout']['values'] is None and run.state['readout']['status'] == 'unavailable', 'FABRICATED_READOUT', binding.asset_id)
    require(all(t.get('reference_frame') is not None for t in run.state['pose_trace']), 'UNREPLAYABLE_POSE', binding.asset_id)
    mode = 'joint_bound_digital_simulation' if binding.joints else ('existing_animation_frame_replay' if binding.reference['poses'] else 'static_no_protocol_capability')
    return {'asset_id': binding.asset_id, 'passed': True, 'status': 'digital_simulation_passed' if binding.joints or binding.reference['poses'] else 'static_only',
            'mode': mode, 'protocol_scope': 'loading_lifecycle' if lifecycle else ('liquid_accounting_only' if liquid else ('joint_contract_only' if binding.joints else mode)), 'workflow_adapter_validated': False, 'hardware_adapter_validated': False,
            'fingerprint': binding.fingerprint, 'joint_combination_policy': binding.combination_policy(), 'joint_count': len(binding.joints), 'unsampled_joint_nodes': binding.unsampled_joint_nodes, 'access_lifecycle_tested': lifecycle,
            'liquid_accounting_tested': liquid, 'operation_joints_tested': binding.operations if lifecycle else [], 'negative_cases': negative, 'pose_trace': run.state['pose_trace'],
            'events': run.state['events'], 'final_running': run.state['running'], 'final_loaded': run.state['loaded'],
            'sample_final': run.state['samples'], 'readout': run.state['readout'],
            'limitations': ['Access open positions are checked visual demonstration poses; loading clearances uncalibrated',
                            'Operating-joint excursions show digital demonstration displacement only; no speed, duration, process or analytical model',
                            'Explicit mutually exclusive joint groups are a digital demonstration whitelist; unlisted joints are unrestricted by that rule; not manufacturer motion limits or collision certification',
                            'No vendor commands, hardware calibration, collision certification, or experimental measurements']}


def run_validation(output):
    """Write evidence without changing contracts; finalize can consume statuses."""
    library = Library(output); results = []
    for ident in sorted(library.assets):
        try:
            results.append(validate_asset(library.select(asset_id=ident)))
        except (Blocked, KeyError, ValueError, OSError) as exc:
            results.append({'asset_id': ident, 'passed': False, 'status': 'failed', 'error_code': getattr(exc, 'code', type(exc).__name__), 'error': str(exc), 'workflow_adapter_validated': False})
    bindings = []
    for device_id, d in sorted(library.devices.items()):
        if not d.get('asset_id'):
            continue
        try:
            b = library.select(device_id=device_id)
            bindings.append({'device_id': device_id, 'asset_id': b.asset_id, 'passed': b.device_id == device_id and b.asset_id == d['asset_id']})
        except (Blocked, KeyError, OSError, ValueError) as exc:
            bindings.append({'device_id': device_id, 'asset_id': d.get('asset_id'), 'passed': False, 'error': str(exc)})
    try:
        workflow = validate_workflow(library)
    except (Blocked, KeyError, ValueError, OSError) as exc:
        workflow = {'passed': False, 'status': 'failed', 'error': str(exc), 'error_code': getattr(exc, 'code', type(exc).__name__)}
    report = {'schema': SCHEMA, 'mode': 'digital_simulation_only', 'passed': all(r['passed'] for r in results+bindings) and workflow['passed'],
              'workflow_adapter_validated': False, 'hardware_adapter_validated': False,
              'input_catalog_sha256': digest(library.output / 'asset-library.json'),
              'input_catalog_hash_scope': 'Exact input before protocol status fields are merged by finalize; freshness is enforced with per-asset GLB/reference/profile/runner fingerprints, not the later catalog formatting or status fields.',
              'assets': results, 'device_bindings': bindings, 'cross_device_workflow': workflow,
              'traces': [{'asset_id': row['asset_id'], 'steps': row.get('pose_trace',[])} for row in results],
              'counts': {'assets': len(results), 'assets_passed': sum(r['passed'] for r in results), 'device_bindings': len(bindings),
                         'lifecycle': sum(r.get('access_lifecycle_tested',False) for r in results),
                         'negative_cases': sum(len(r.get('negative_cases',[])) for r in results)}}
    report['ok'] = report['passed']
    path = library.output / REPORT
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    return report


def per_asset_status(output, asset_id):
    """Fail closed for missing/stale evidence; never promote a vendor adapter."""
    output = Path(output); path = output / REPORT
    default = {'status': 'unvalidated', 'workflow_adapter_validated': False, 'hardware_adapter_validated': False}
    if not path.exists():
        return default
    try:
        report = read(path)
    except (ValueError, OSError):
        return default
    if report.get('schema') != SCHEMA or report.get('mode') != 'digital_simulation_only':
        return default
    row = next((r for r in report.get('assets',[]) if r['asset_id'] == asset_id), None)
    if not row or not row.get('passed'):
        return default
    try:
        catalog = read(output/'asset-library.json')
        asset = next(a for a in catalog['assets'] if a['asset_id'] == asset_id)
        current = binding_fingerprint(Library(output).select(asset_id=asset_id))
        if row.get('fingerprint') != current:
            return {**default, 'status': 'stale_evidence'}
    except (OSError, KeyError, StopIteration, ValueError, TypeError):
        return default
    return {**default, 'status': row['status'], 'report': REPORT, 'mode': row['mode'], 'protocol_scope': row['protocol_scope'],
            'access_lifecycle_tested': row['access_lifecycle_tested'], 'liquid_accounting_tested': row['liquid_accounting_tested']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('exports/biofoundry'))
    args = parser.parse_args()
    report = run_validation(args.output)
    print(json.dumps({'report': str(args.output/REPORT), 'passed': report['passed'], **report['counts']}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
