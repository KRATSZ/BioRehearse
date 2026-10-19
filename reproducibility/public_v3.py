#!/usr/bin/env python3
"""Append v3 evidence to a sanitized v2 release, or relocate public manifests.

Original scientific code, configuration and results are never rewritten.
Only public dependency hashes affected by v2 administrative path adaptation
are remapped. Original design/protocol bytes remain in provenance/.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

DESIGN = Path('benchmarks/v3/design.json')
FROZEN = 'benchmarks/v2/frozen.json'
TREES = ('benchmarks/v3', 'source-data/v3', 'reproducibility/v3', 'reproducibility/source-v3', 'figures/v3/source')
ALLOWED_SUFFIXES={'.py','.ts','.json','.jsonl','.csv','.tsv','.md','.txt','.mjs','.js','.yaml','.yml','.toml','.lock','.cff','.sha256'}
SKIP = {'.git', '__pycache__', '.agent-runs', '.aris', '.venv', 'node_modules'}

def sha(path):
 return hashlib.sha256(path.read_bytes()).hexdigest()
def safe_target(root,relative):
 relative=Path(relative)
 if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe destination path')
 target=root/relative
 for part in [target,*target.parents]:
  if part==root:break
  if part.is_symlink():raise ValueError('Destination symlink: '+str(relative))
  if part.is_file() and part.stat().st_nlink>1:raise ValueError('Hardlinked destination: '+str(relative))
 if not target.resolve().is_relative_to(root.resolve()):raise ValueError('Destination escapes release')
 return target

def read(path):
 return json.loads(path.read_text())
def write(path, value):
 path.parent.mkdir(parents=True, exist_ok=True)
 path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')
def manifest_hash(design):
 items=[]
 for section in ('code_hashes','dependency_hashes','inputs'):
  items.extend((section, name, value) for name,value in sorted(design[section].items()))
 return hashlib.sha256(json.dumps(items,separators=(',',':')).encode()).hexdigest()
def verify_design(root, design, allow_public_frozen=False):
 for section in ('code_hashes','dependency_hashes','inputs'):
  for name,expected in design[section].items():
   if name==FROZEN and allow_public_frozen:
    if not (root/name).is_file():raise FileNotFoundError(root/name)
    continue
   if sha(root/name)!=expected:raise RuntimeError('Unexpected scientific-source/input change: '+name)
 if manifest_hash(design)!=design['manifest_sha256']:raise RuntimeError('Original design manifest mismatch')
def sensitive_name(p):
 name=p.name.lower()
 return any(x.lower() in {'account','accounts','account_snapshots','billing','fulltext','fulltexts','full-text','full-texts'} for x in p.parts) or any(word in name for word in ('manuscript','preprint','private-account','account-snapshot','account_snapshot','account-state','api-account','credential','secret','id_rsa','id_ed25519','access_token','api_token','token.json')) or p.suffix.lower() in {'.pem','.key','.p12','.pfx'}
def safe_file(p, root):
 rel=p.relative_to(root)
 return p.suffix.lower() in ALLOWED_SUFFIXES and not any((root/Path(*rel.parts[:i])).is_symlink() for i in range(1,len(rel.parts)+1)) and not sensitive_name(p) and p.suffix.lower() not in {'.png','.jpg','.jpeg','.svg','.pdf','.blend','.blend1','.glb','.gltf','.mp4','.mov','.mp3','.wav','.tex','.bib','.doc','.docx','.pages','.pptx'} and p.is_file() and p.resolve().is_relative_to(root.resolve()) and not any(part in SKIP for part in rel.parts) and p.suffix!='.pyc' and p.name!='.DS_Store' and not p.name.startswith('.env') and not any(word in p.name.lower() for word in ('account-balance','balance-before','balance-after','spend-origin'))
def selection(paper):
 found=set()
 for name in TREES:
  base=paper/name
  if base.exists():found.update(p.relative_to(paper) for p in base.rglob('*') if safe_file(p,paper))
 for p in (paper/'figures/v3').rglob('*'):
  if p.suffix in ('.json','.csv') and safe_file(p,paper):found.add(p.relative_to(paper))
 for name in ('benchmarks/common.py','reproducibility/README-v3.md','reproducibility/public_v3.py','audit/v3/SCHEDULING_V33.md','audit/v3/SCHEDULING_OUTAGE_BASELINE_R2.md','audit/v3/PORTABLE_VALIDATION_REPLAY.md','audit/v3/VALIDATION_CONSTRUCTION_AUDIT.md'):
  if (paper/name).is_file():
   if not safe_file(paper/name,paper):raise ValueError('Unsafe explicit source: '+name)
   found.add(Path(name))
 return sorted(found,key=str)
def adapt(root):
 original_path=root/'provenance/v3-design-original.json'
 if not safe_file(original_path,root):raise ValueError('Unsafe original design source')
 original=read(original_path)
 verify_design(root,original,allow_public_frozen=True)
 public=copy.deepcopy(original)
 public['dependency_hashes'][FROZEN]=sha(root/FROZEN)
 public['manifest_sha256']=manifest_hash(public)
 write(safe_target(root,DESIGN),public)
 design_sha=sha(root/DESIGN)
 changes=[{'path':FROZEN,'original_sha256':original['dependency_hashes'][FROZEN],'public_sha256':sha(root/FROZEN),'reason':'Existing public v2 privacy/path adaptation; scientific source unchanged'}]
 for source in sorted((root/'provenance/v3-protocols-original').glob('protocol-*.json')):
  if not safe_file(source,root):raise ValueError('Unsafe protocol provenance source')
  protocol=read(source); adapted=copy.deepcopy(protocol)
  mapping=adapted.get('input_hashes',{})
  if str(DESIGN) in mapping:
   if mapping[str(DESIGN)]!=sha(original_path):raise RuntimeError('Unexpected original protocol design hash: '+source.name)
   mapping[str(DESIGN)]=design_sha
  target=safe_target(root,Path('benchmarks/v3')/source.name)
  write(target,adapted)
  changes.append({'path':str(target.relative_to(root)),'original_sha256':sha(source),'public_sha256':sha(target),'reason':'Only dependency hash of public-adapted design; configuration and source hashes unchanged'})
 write(safe_target(root,'provenance/v3-public-adaptations.json'),{'schema':'biorehearse.public-path-adaptation.v3','original_design_sha256':sha(original_path),'public_design_sha256':design_sha,'changes':changes,'not_a_new_prospective_freeze':True,'unchanged':['scientific source bytes','configuration and case membership','raw results','scorers']})
 verify_design(root,public)
 return changes

def build(paper,dest,dry_run):
 if dest==paper or (dest.is_relative_to(paper) and not dest.is_relative_to(paper/'release')) or paper.is_relative_to(dest):raise ValueError('Destination overlaps source inputs')
 if not (dest/'provenance/public-adaptations.json').is_file():raise RuntimeError('Destination must be the existing sanitized v2 release')
 if not safe_file(paper/DESIGN,paper):raise ValueError('Unsafe design source')
 for protocol in (paper/'benchmarks/v3').glob('protocol-*.json'):
  if not safe_file(protocol,paper):raise ValueError('Unsafe protocol source')
 original=read(paper/DESIGN);verify_design(paper,original)
 # Verify existing public v2 scientific dependencies before any copy.
 verify_design(dest,original,allow_public_frozen=True) if (dest/'benchmarks/v3/design.py').exists() else None
 files=selection(paper)
 for section in ('dependency_hashes','inputs'):
  for name,expected in original[section].items():
   if name==FROZEN:continue
   if not (dest/name).is_file() or sha(dest/name)!=expected:raise RuntimeError('Public v2 scientific dependency changed: '+name)
 if dry_run:return {'dry_run':True,'files':len(files),'bytes':sum((paper/p).stat().st_size for p in files),'destination':str(dest)}
 extra=[DESIGN,Path('provenance/v3-design-original.json'),Path('provenance/v3-public-adaptations.json')]
 extra.extend(Path('provenance/v3-protocols-original')/p.name for p in (paper/'benchmarks/v3').glob('protocol-*.json'))
 for rel in [*files,*extra]:safe_target(dest,rel)
 for rel in files:
  if not safe_file(paper/rel,paper):raise ValueError('Unsafe selected source: '+str(rel))
  target=safe_target(dest,rel);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(paper/rel,target)
 target=safe_target(dest,'provenance/v3-design-original.json');target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(paper/DESIGN,target)
 for p in sorted((paper/'benchmarks/v3').glob('protocol-*.json')):
  target=safe_target(dest,Path('provenance/v3-protocols-original')/p.name);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
 changes=adapt(dest)
 return {'files':len(files),'destination':str(dest),'adaptations':len(changes),'public_design_sha256':sha(dest/DESIGN)}

def main():
 ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='mode',required=True)
 a=sub.add_parser('build');a.add_argument('--paper',type=Path,required=True);a.add_argument('--destination',type=Path,required=True);a.add_argument('--dry-run',action='store_true')
 a=sub.add_parser('relocate');a.add_argument('--destination',type=Path,default=Path(__file__).resolve().parents[1])
 args=ap.parse_args();dest=args.destination.resolve()
 if args.mode=='build':result=build(args.paper.resolve(),dest,args.dry_run)
 else:
  original=read(dest/'provenance/v3-design-original.json');verify_design(dest,original,True)
  safe_target(dest,FROZEN)
  subprocess.run([sys.executable,str(dest/'reproducibility/relocate_v2.py')],check=True)
  result={'destination':str(dest),'adaptations':len(adapt(dest))}
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
