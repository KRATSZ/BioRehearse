"""Freeze study-v2 files and the actual live harness dependency chain."""
import shutil
from datetime import datetime,timezone
from common import PAPER,PROJECT,read,write,digest

def main():
 target=PAPER/'benchmarks/v2/frozen.json'
 if target.exists():raise RuntimeError('Already frozen; do not silently replace a test')
 for folder in ['biofoundry','planir']:
  shutil.copytree(PROJECT/'labscriptai'/folder,PAPER/'reproducibility/source-v2/labscriptai'/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'),dirs_exist_ok=True)
 paths=list((PAPER/'benchmarks/v2').glob('*.py'))+[PAPER/'benchmarks/v2/workloads.json',PAPER/'benchmarks/v2/language.json',PAPER/'benchmarks/v2/repair.json',PAPER/'source-data/v2/catalog.json',PAPER/'source-data/catalog.json',PAPER/'benchmarks/scorer.py']+list((PAPER/'reproducibility/source-v2').rglob('*.py'))
 old=read(PAPER/'benchmarks/frozen.json');live=[r['path'] for r in old['live_files'] if __import__('pathlib').Path(r['path']).exists()]
 for path in ['labscriptai/biofoundry/methods.py','labscriptai/biofoundry/portfolio.py','labscriptai/biofoundry/scheduling.py','labscriptai/webdemo/server/src/biofoundry-author.ts','scripts/biofoundry.py']:
  if str(PROJECT/path) not in live:live.append(str(PROJECT/path))
 write(target,{'protocol':'v2.1','frozen_at':datetime.now(timezone.utc).isoformat(),'public_preregistration':False,'files':[{'path':str(p.relative_to(PAPER)),'sha256':digest(p)} for p in paths],
  'live_files':[{'path':p,'sha256':digest(p)} for p in sorted(live)],'note':'Two-model execution uses the actual live TS and Python CLI chain, verified before every invocation. Snapshot is the offline scheduling source.'})
 print('frozen',len(paths),'packaged and',len(live),'live files')
if __name__=='__main__':main()
