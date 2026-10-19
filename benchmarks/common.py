"""Portable project resolution; never loads credentials."""
import os, sys, json
from pathlib import Path

PAPER = Path(__file__).resolve().parents[1]
VLAB = Path(os.environ.get('BIOFOUNDRY_VLAB', str(PAPER.parents[1])))
PROJECT = Path(os.environ.get('BIOFOUNDRY_PROJECT', str(VLAB.parent/'Flexagent/Opentrons-Lab-Agent')))
SNAPSHOT = PAPER/'reproducibility/source-snapshot'
sys.path.insert(0, str(SNAPSHOT if SNAPSHOT.exists() else PROJECT))

def read(path):
    return json.loads(Path(path).read_text())

def write(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False)+'\n')

def catalog():
    return read(PAPER/'source-data/catalog.json')
