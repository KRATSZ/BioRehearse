"""Reference requests authored from typed constraints, before any model output."""
import copy
from common import PAPER,write
from design import BASE
WORDS={1:'one',2:'two',3:'three',4:'four',5:'five',6:'six',7:'seven',8:'eight'}
CONTEXT=' These are digital planning requests. I explicitly accept estimated costs, handling durations, digital carriers and layout assumptions. A person prepares cellfreeMIX, standards and working reagents; manual transport is allowed, but liquid-workstation assembly must remain automated. Use only device:19, device:18, device:67, demo:ks4000:1 and bench. Keep every registered assay condition and its controls.'
COMBOS=[['gfp'],['bca'],['picogreen'],['gfp','bca'],['gfp','picogreen'],['bca','picogreen'],['gfp','bca','picogreen'],['bca','picogreen']]

def supported(i,style,split='heldout'):
 it=copy.deepcopy(BASE);it['deadline_s']=[21600,25200,28800][i%3];it['budget_cny']=450+20*i;it['experiments']=[];pieces=[];release=3600 if i%4==0 else 0
 for j,m in enumerate(COMBOS[i%8]):
  n=1 if m=='gfp' else 2+(i+j)%7;rep=1+(i+j)%2
  e={'id':f'J{j+1}','method':m,'samples':n,'replicates':rep,'release_s':release};it['experiments'].append(e)
  if style==0:pieces.append(f'CFXpress GFP with one positive template and NTC, {rep} replicates per group' if m=='gfp' else f'{"Pierce BCA" if m=="bca" else "Quant-iT PicoGreen"} with {n} unknown samples, {rep} replicates')
  elif style==1:
   pieces.append(f'Use CFXpress to express a positive GFP template alongside a no-DNA control; prepare each group in {"duplicate" if rep==2 else "a single reaction"}' if m=='gfp' else f'For {"protein" if m=="bca" else "DNA"} quantification, I have {WORDS[n]} unknowns for {"Pierce BCA" if m=="bca" else "Quant-iT PicoGreen"}; measure every unknown and standard in {"duplicate" if rep==2 else "a single well"}')
  else:pieces.append(f'CFXpress GFP：一个阳性模板加无模板对照，每组{rep}次反应' if m=='gfp' else f'{"Pierce BCA蛋白定量" if m=="bca" else "Quant-iT PicoGreen DNA定量"}：{n}个未知样品，各{rep}个技术重复，保留注册标准曲线')
 h=it['deadline_s']//3600
 time=f'Start the workday at 09:00 and finish within {h} hours.' if style==0 else f'The day starts at 09:00 Shanghai time, with everything finished by {9+h}:00.' if style==1 else f'工作日09:00开始，{9+h}:00前完成。'
 request=('Plan ' if style==0 else 'Please coordinate the following work: ' if style==1 else '请编排：')+'; '.join(pieces)+f'. {time} Operating budget CNY {it["budget_cny"]}.'
 if release:request+=' No experiment may start before 10:00.'
 return {'id':f'{split}-language-{i:02}-s{style}','cluster':f'{split}-semantic-{i:02}','style':['controlled','open','mixed'][style],'decision':'compile','request':request+CONTEXT,'expected':it}

def main():
 target=PAPER/'benchmarks/v2/language.json'
 if target.exists():raise RuntimeError('Do not overwrite prospective requests')
 held=[supported(i,s) for i in range(24) for s in range(3)]
 missing=[('budget_cny',3),('deadline_s',3),('samples',2),('replicates',2),('conflicting_constraints',1),('accept_demo_assumptions',1)]
 for field,count in missing:
  for j in range(count):
   c=supported(2+j,0);c.update(id=f'clarify-{len(held)-72:02}',cluster=f'clarify-{len(held)-72:02}',decision='clarify',missing_field=field,expected=None)
   if field=='budget_cny':
    import re;c['request']=re.sub(r'Operating budget CNY \d+\.','Please ask me for the operating budget.',c['request'])
   elif field=='deadline_s':
    import re;c['request']=re.sub(r'and finish within \d+ hours\.','; I have not decided the deadline.',c['request'])
   elif field=='samples':
    import re;c['request']=re.sub(r'with \d+ unknown samples','with an unspecified number of unknown samples',c['request'])
   elif field=='replicates':
    import re;c['request']=re.sub(r', \d+ replicates',', an unspecified number of replicates',c['request'])
   elif field=='conflicting_constraints':c['request']+=' The hard completion deadline is both 12:00 and 16:00; neither is preferred. Ask which one to use.'
   else:c['request']=c['request'].replace('I explicitly accept estimated costs, handling durations, digital carriers and layout assumptions.','I have not yet agreed to any estimated costs, durations, carriers or layout assumptions.')
   held.append(c)
 unsupported=[('bca_temperature','Use BCA incubation at 25 C instead of 37 C.'),('gfp_temperature','Run CFXpress at 45 C, replacing the registered incubation temperature.'),('pcr','Replace the registered assays with PCR amplification.'),('manual_assembly','Replace all robot liquid assembly by hand pipetting; no liquid workstation may be used.'),('unknown_device','Use an unregistered reader device:99 instead of device:67.'),('raman','The final read must be a Raman spectrum on iD5.'),('elisa','Replace all assays by an ELISA assay not in the registry.'),('light','Expose the PicoGreen reaction to bright light throughout incubation instead of protecting it.'),('no_control','Remove the GFP no-template control entirely.'),('mix_recipe','Reverse engineer and change the composition of the opaque cellfreeMIX.'),('no_standards','Discard all BCA and PicoGreen standards; measure unknowns only.'),('volume','Change every PicoGreen reaction to 500 uL per well without altering the method name.')]
 for i,(label,extra) in enumerate(unsupported):
  c=supported(6,1);c.update(id=f'unsupported-{i:02}',cluster=f'unsupported-{i:02}',decision='reject',expected=None,unsupported_reason=label,request=c['request']+' '+extra);held.append(c)
 dev=[supported(i,s,'development') for i in range(24,28) for s in range(3)]
 repeats=[c['id'] for c in held if c['decision']=='compile'][::9]+[c['id'] for c in held if c['decision']!='compile'][::6]
 write(target,{'development':dev,'heldout':held,'extra_repeat_ids':repeats,'models':['deepseek-flash','deepseek-v4-pro'],'repetitions':'one for every request; two additional executions for 12 prespecified requests','note':'No model-generated references or explicit negative-case signature marker.'})
 print('language',len(held),'repeat subset',len(repeats),'development',len(dev))
if __name__=='__main__':main()
