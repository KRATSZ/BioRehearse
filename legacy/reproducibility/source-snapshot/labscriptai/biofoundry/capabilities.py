"""Instance identity and deliberately bounded simulation capabilities, not hardware claims."""
import copy
import json
from pathlib import Path

RATE_BASIS = 'Planning assumption in CNY, not a vendor quote or measured facility tariff; low/high = 0.7/1.5 × estimate'
SOURCES = {
 'fluent': 'https://lifesciences.tecan.com/fluent-laboratory-automation-workstation',
 'reader': 'https://www.moleculardevices.com/sites/default/files/en/assets/brochures/br/spectramax-id5-multi-mode-microplate-reader.pdf',
 'shaker': 'https://www.ika.com/en/Products-LabEq/Shakers-pg179/KS-4000-i-control-3510000/Technical-Data-cptd.html',
}
# A device needs only its capability record and these explicit digital actions.
# A future hardware driver must implement the same actions separately.
ACTION_FOR = {'liquid':'dispense','incubate':'incubate','FI':'read_fluorescence',
              'ABS':'read_absorbance','manual':'manual_step'}


def actions_for(device):
    return [{'id':action,'capability':cap,'mode':'digital','hardware_driver':None,
             'arguments':'checked task_id, container_ids and registered method parameters',
             'lifecycle':['load','run','unload_clean']}
            for cap,action in ACTION_FOR.items()
            if device.get('selectable') and device.get('capabilities',{}).get(cap) is True]
LAYOUTS = {
 'compact': {'name':'紧凑工作岛（假设）','positions':{'bench':[0,0], 'device:19':[3,0], 'device:18':[3,3], 'device:67':[0,3], 'device:68':[0,5], 'demo:ks4000:1':[5,3]}},
 'linear': {'name':'直线工作区（假设）','positions':{'bench':[0,0], 'device:19':[4,0], 'device:18':[8,0], 'device:67':[12,0], 'device:68':[16,0], 'demo:ks4000:1':[20,0]}},
 'separated': {'name':'跨房间工作区（假设）','positions':{'bench':[0,0], 'device:19':[5,0], 'device:18':[5,6], 'device:67':[0,28], 'device:68':[6,28], 'demo:ks4000:1':[14,8]}},
}


def catalog(output):
    output = Path(output)
    inventory = json.loads((output/'facility-inventory.json').read_text())
    assets = {a['asset_id']: a for a in json.loads((output/'asset-library.json').read_text())['assets']}
    motion = {a['asset_id']:a.get('passed',False) for a in json.loads((output/'library-protocol-checks.json').read_text())['assets']}
    devices = {}
    for item in inventory['devices']:
        aid=item.get('asset_id')
        devices[f"device:{item['id']}"] = {'id':f"device:{item['id']}", 'facility_id':item['id'], 'model':item.get('model_raw'),
            'name':item['name'], 'asset_id':aid, 'glb':assets.get(aid,{}).get('normalized_glb'),
            'identity_basis':'published facility instance; installed options unverified', 'capabilities':{}, 'containers':[],
            'capacity':None, 'available_s':None, 'cost_cny_per_hour':None, 'method_adapter_validated':False,
            'digital_motion_tested':motion.get(aid,False), 'hardware_validated':False, 'selectable':False}
    # The library has this model, but the facility list does not establish its presence.
    devices['demo:ks4000:1'] = {'id':'demo:ks4000:1','facility_id':None,'model':'IKA KS 4000 i control','name':'KS4000 数字工位',
        'asset_id':'ika_ks4000','glb':assets['ika_ks4000']['normalized_glb'],
        'identity_basis':'one explicitly configured prototype instance of an existing library asset; not an installed facility assertion',
        'digital_motion_tested':motion.get('ika_ks4000',False),'method_adapter_validated':False,'hardware_validated':False}
    configs = {
      'device:19': ({'liquid':True}, ['tube_1p5ml','reservoir_50ml','black96','clear96'],96,180,1.0,'fluent'),
      'device:18': ({'liquid':True}, ['tube_1p5ml','reservoir_50ml','black96','clear96'],96,100,1.65,'fluent'),
      'device:67': ({'FI':True,'ABS':True,'excitation_nm':[250,830],'emission_nm':[270,850],'absorbance_nm':[230,1000]},['black96','clear96'],96,90,1.0,'reader'),
      # i3x optics/options remain unknown and are deliberately NOT made selectable.
      'demo:ks4000:1': ({'incubate':True,'temperature_c':[30,37],'shaking':'vigorous; rpm unverified'},['tube_1p5ml','clear96'],96,25,1.0,'shaker'),
    }
    for key,(caps,containers,capacity,rate,speed,source) in configs.items():
        devices[key].update(capabilities=caps,containers=containers,capacity=capacity,available_s=[[0,28800]],
            capacity_unit='wells per single batch, or tube positions for the explicitly assumed digital carrier',
            cost_cny_per_hour=rate,duration_factor=speed,selectable=True,conditions={'ambient_c':22,'dark_cover':True,
            'temperature_changeover_s':180,'carrier_fit':'explicit digital assumption; physical carrier not qualified'},
            source=SOURCES[source], capability_basis='public model family + explicit prototype configuration; requires accept_demo_assumptions',
            cost_basis=RATE_BASIS,consumables=['tips200ul','labelled vessels'],manual_requirement='operator load/unload/clean',
            duration_basis='simulation estimate; setup/process/cleanup durations have range 0.7–1.5× except manufacturer incubation')
    devices['bench'] = {'id':'bench','name':'人工工作台 / 冰上与避光容器','model':'manual station','asset_id':None,'glb':None,
        'capabilities':{'manual':True,'liquid':True,'dark':True,'ice':True}, 'containers':['tube_1p5ml','reservoir_50ml','black96','clear96'],
        'capacity':96,'available_s':[[0,28800]],'cost_cny_per_hour':0,'duration_factor':3.0,'selectable':True,
        'digital_motion_tested':False,'method_adapter_validated':False,'hardware_validated':False,'cost_basis':RATE_BASIS,
        'conditions':{'ambient_c':22,'dark_cover':True},'manual_requirement':'operator for full operation',
        'consumables':['manual pipette','ice','foil'],'identity_basis':'explicit human station retained from GFP baseline'}
    for d in devices.values():d['actions']=actions_for(d)
    return {'schema':'biofoundry.capabilities.v2','devices':devices,'layouts':copy.deepcopy(LAYOUTS),
        'consumables_inventory':{'tips200ul':288,'black96':4,'clear96':4,'tube_1p5ml':32,'reservoir_50ml':4},
        'inventory_basis':'explicit demo staging inventory, not measured facility stock; prepared reagent stocks live in the sample ledger',
        'costs':{'currency':'CNY','operator_per_hour':60,'tip':0.35,'black96':15,'clear96':8,'reservoir_50ml':5,
                 'gfp_reaction':12,'bca_well':0.6,'picogreen_well':1.8,'basis':RATE_BASIS},
        'transport':{'speed_m_s':0.8,'handoff_s':20,'same_station_s':5,'distance':'Manhattan walk, assumed obstacle-free orthogonal aisles',
                     'basis':'all layouts hypothetical; not a surveyed floor plan, clearance or robot reach certification'},
        'scope':{'digital_planning':True,'model_motion_demo':True,'method_adaptation':False,'hardware_validation':False},
        'unknown_policy':'unknown capability, container, capacity or availability excludes that instance; no automatic fallback'}
