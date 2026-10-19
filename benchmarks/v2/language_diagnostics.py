"""Post-study diagnostic annotation; primary frozen scores are never overwritten."""
import json,re
from pathlib import Path
from collections import Counter
PAPER=Path(__file__).resolve().parents[2];DATA=PAPER/'source-data/v2'
def main():
 spec={c['id']:c for c in json.loads((PAPER/'benchmarks/v2/language.json').read_text())['heldout']};diagnostics=[];fees={}
 for model in ['deepseek-flash','deepseek-v4-pro']:
  rr=[json.loads(s) for s in (DATA/'heldout/language'/model/'scores.jsonl').read_text().splitlines()]
  for r in rr:
   if r['repeat'] or r['success']:continue
   d=json.loads((PAPER/r['raw_file']).read_text())['result'];case=spec[r['case']]
   if r['decision']=='clarify':
    fields=d.get('clarification',{}).get('missing_fields',[]);expected=case['missing_field'];ok=all(expected in f for f in fields) and bool(d.get('clarification',{}).get('question'))
    diagnostics.append({'model':model,'case':r['case'],'primary_success':False,'diagnostic':'matching nested/free-text field identifier outside frozen aliases','fields':fields,'expected_field':expected,'secondary_field_equivalence':ok,'question':d.get('clarification',{}).get('question')})
   elif r['decision']=='compile':
    actual=d['generated']['graph']['intent'];expected=case['expected'];diagnostics.append({'model':model,'case':r['case'],'primary_success':False,'diagnostic':'deadline mismatch','expected_deadline_s':expected['deadline_s'],'actual_deadline_s':actual['deadline_s']})
  # Usage.input excludes separately recorded cacheRead; reasoning is already within output.
  u={k:sum(r[k] for r in rr) for k in ['input_tokens','cache_read_tokens','output_tokens','reasoning_tokens','total_tokens']}
  hit,miss,out=(.003,.15,.6) if model=='deepseek-flash' else (.022,.66,1.98)
  base=(u['input_tokens']*miss+u['cache_read_tokens']*hit+u['output_tokens']*out)/1e6
  fees[model]={'usage':u,'estimated_usd_offpeak':base,'estimated_usd_peak':2*base,'source':'https://api-docs.deepseek.com/quick_start/pricing/','accessed':'2026-10-19','scope':'Usage-based provider tariff estimate for120 model runs; not an invoice; no account-balance attribution.'}
 result={'timing':'Post-study diagnostic, not a replacement primary score','annotations':diagnostics,'fees':fees};(DATA/'language-diagnostics.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
