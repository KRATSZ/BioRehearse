"""Add explicit input/image/script hashes after native renders; changes no pixels."""
from pathlib import Path
import json,hashlib,os
PAPER=Path(__file__).resolve().parents[3];ROOT=Path(os.environ['BIOFOUNDRY_VLAB']) if os.environ.get('BIOFOUNDRY_VLAB') else next(p for p in PAPER.parents if (p/'sim').is_dir());OUT=PAPER/'figures/v2/renders'
def rec(p,label=None):return {'path':label or str(p.relative_to(PAPER)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def main():
 for kind in ['hero','gallery','anatomy','rehearsal']:
  path=OUT/(kind+'-provenance.json');d=json.loads(path.read_text());d['renderer_script']=rec(Path(__file__).with_name('render_rehearsal.py' if kind=='rehearsal' else 'render_assets.py'))
  if kind=='hero':d['input_scene']=rec(ROOT/'exports/biofoundry/island/latest.json','virtual-lab:exports/biofoundry/island/latest.json');d['portable_scene_reference']=rec(PAPER/'source-data/v2/island-example.json')
  if kind=='rehearsal':
   for key,name in [('frame_source','example.json'),('layout_source','catalog.json'),('material_state_source','material-example.json')]:d[key]=rec(PAPER/'source-data/v2'/name)
   d['generated_geometry']='Human bench, station pedestals and carrier glyphs are generated visual proxies; source station meshes are recorded separately.'
  for image in d['images']:image['sha256']=hashlib.sha256((OUT/image['image']).read_bytes()).hexdigest()
  d['status']='Native digital geometry render; no hardware execution';path.write_text(json.dumps(d,indent=2)+'\n')
 print('Four render manifests enriched; image pixels unchanged')
if __name__=='__main__':main()
