"""Study-v2 paths and source resolution, independent of the original workspace."""
import os,sys,json,hashlib
from pathlib import Path
PAPER=Path(__file__).resolve().parents[2]
VLAB=Path(os.environ.get('BIOFOUNDRY_VLAB',str(next((p for p in PAPER.parents if (p/'sim').is_dir()),PAPER))))
PROJECT=Path(os.environ.get('BIOFOUNDRY_PROJECT',str(VLAB.parent/'Flexagent/Opentrons-Lab-Agent')))
SNAP=PAPER/'reproducibility/source-v2'
sys.path.insert(0,str(SNAP if (SNAP/'labscriptai').exists() else PROJECT))
def read(p):return json.loads(Path(p).read_text())
def write(p,d):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(d,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def emit(p,d):
 with Path(p).open('a') as f:f.write(json.dumps(d,ensure_ascii=False,allow_nan=False)+'\n')
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def frozen(live=False):
 for r in read(PAPER/'benchmarks/v2/frozen.json')['files']:
  if digest(PAPER/r['path'])!=r['sha256']:raise RuntimeError('Frozen v2 file changed: '+r['path'])
 if live:
  for r in read(PAPER/'benchmarks/v2/frozen.json')['live_files']:
   if digest(r['path'])!=r['sha256']:raise RuntimeError('Live v2 dependency changed: '+r['path'])
