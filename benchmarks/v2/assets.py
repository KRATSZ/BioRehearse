"""Recount bindings and exercise delivered digital asset contracts afresh."""
import csv,json,sys
from collections import Counter
from common import PAPER,VLAB,read,write,digest
sys.path.insert(0,str(VLAB))
from sim.library_protocols import Library,validate_asset

def main():
 root=VLAB/'exports/biofoundry';lib=Library(root);inventory=read(root/'facility-inventory.json');rows=[];checks=[]
 for aid,a in sorted(lib.assets.items()):
  try:
   binding=lib.select(asset_id=aid);result=validate_asset(binding);error=None
  except Exception as exc:result={'asset_id':aid,'passed':False};binding=None;error=repr(exc)
  contract=read(root/'library'/aid/'asset.contract.json');ref=read(root/a['assembly_reference']);mesh=root/a['normalized_glb']
  row={'asset_id':aid,'model':a.get('model',a.get('name')),'facility_instances':sum(d.get('asset_id')==aid for d in inventory['devices']),'mesh_present':mesh.is_file(),'joint_count':len(binding.joints) if binding else 0,'joint_contract':bool(binding and binding.joints),'animation_poses':len(ref.get('poses',[])),'access_lifecycle':result.get('access_lifecycle_tested',False),'liquid_accounting':result.get('liquid_accounting_tested',False),'contract_check_pass':result['passed'],'hardware_adapter':bool(contract.get('protocol',{}).get('hardware_adapter_validated',False)),'mode':result.get('mode'),'license':a.get('license'),'source':a.get('source'),'error':error,'mesh_sha256':digest(mesh) if mesh.exists() else None}
  rows.append(row);checks.append(result)
 devices=inventory['devices'];summary={'facility_instances':len(devices),'raw_model_strings':len({d['model_raw'] for d in devices}),'library_assets':len(rows),'assigned_instances':sum(bool(d.get('asset_id')) for d in devices),'assigned_asset_ids':len({d['asset_id'] for d in devices if d.get('asset_id')}),'unassigned_instances':sum(not d.get('asset_id') for d in devices),'assets_with_joint_contract':sum(r['joint_contract'] for r in rows),'checked_joints':sum(r['joint_count'] for r in rows),'assets_with_animation_poses':sum(r['animation_poses']>0 for r in rows),'access_lifecycle_assets':sum(r['access_lifecycle'] for r in rows),'liquid_accounting_assets':sum(r['liquid_accounting'] for r in rows),'contract_checks_passed':sum(r['contract_check_pass'] for r in rows),'hardware_adapters':sum(r['hardware_adapter'] for r in rows),'mode_counts':dict(Counter(r['mode'] for r in rows)),'scope':'Fresh execution of digital contract scenarios; counts are assets, not biological replicates or hardware demonstrations.'}
 write(PAPER/'source-data/v2/asset-summary.json',summary);write(PAPER/'source-data/v2/asset-contract-runs.json',checks)
 with (PAPER/'source-data/v2/asset-coverage.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 write(PAPER/'source-data/v2/instance-asset-links.json',[{'instance':d['id'],'raw_model':d['model_raw'],'room':d.get('location'),'asset_id':d.get('asset_id'),'official_url':d.get('official_url')} for d in devices]);print(json.dumps(summary,indent=2))
 # Analyze official Opentrons files as a separate command-stream demonstration.
 records=[]
 for p in sorted((VLAB/'exports').rglob('*.analysis.json')):
  if '/asset-before/' in str(p) or '/test-tmp/' in str(p):continue
  try:d=read(p)
  except Exception:continue
  commands=d.get('commands',[])
  if not commands and isinstance(d.get('data'),dict):commands=d['data'].get('commands',[])
  if not commands:continue
  types=Counter(c.get('commandType') for c in commands)
  records.append({'file':str(p.relative_to(VLAB)),'sha256':digest(p),'commands':len(commands),'errors':len(d.get('errors',[])),'command_types':dict(types),'successful_commands':sum(c.get('status')=='succeeded' for c in commands),'protocol_binding':'existing command-stream example; not an automatic export of the three-assay portfolio'})
 write(PAPER/'source-data/v2/opentrons-command-audit.json',records)
if __name__=='__main__':main()
