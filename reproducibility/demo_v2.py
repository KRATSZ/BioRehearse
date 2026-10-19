"""A new offline run in a separate output, using the frozen method snapshot."""
import argparse,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'benchmarks/v2'))
from common import PAPER,read
from labscriptai.biofoundry.methods import compile_graph
from labscriptai.biofoundry.scheduling import solve
from labscriptai.biofoundry.portfolio import prepare_plan
from scorer import score,states
ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
if a.out.exists():raise RuntimeError('Choose a new output file')
case=read(PAPER/'benchmarks/v2/repair.json')[1];cap=read(PAPER/'source-data/v2/catalog.json');g=compile_graph(case['intent'],cap)['graph'];p=solve(g,cap,case['layout'],bookings=case['bookings'],time_limit_s=2)
check=score(p,g,cap,case['bookings'])
if p.get('ok'):prepare_plan(p,cap);audit=states(p);p['independent_checks']={**check,'material_valid':audit['material_valid'],'mass_valid':audit['mass_valid']}
a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(p,indent=2)+'\n');print(json.dumps({'path':str(a.out),'returned':p.get('ok'),'checks':p.get('independent_checks',check)}))
