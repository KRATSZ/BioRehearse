"""Main figures from complete raw records; editable vectors and native scene renders."""
import sys,json,csv,re,collections,statistics as st
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
PAPER=Path(__file__).resolve().parents[3];OUT=PAPER/'figures/v2';DATA=PAPER/'source-data/v2';REND=OUT/'renders'
SKILL=PAPER/'reproducibility/figure-qa';sys.path.insert(0,str(SKILL));from audit_panel_alignment import require_matplotlib_panel_alignment
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Arial','Helvetica','DejaVu Sans'],'font.size':6.5,'axes.labelsize':6.5,'axes.titlesize':7,'xtick.labelsize':6,'ytick.labelsize':6,'legend.fontsize':6,'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False,'lines.linewidth':1.1,'axes.linewidth':.5,'savefig.dpi':400})
COL={'gfp':'#2A7F9E','bca':'#D88A40','picogreen':'#8A78B0'};METH={'cp_sat':'#17242E','parallel_greedy':'#7A858D','serial_fifo':'#C2C8CD'};LABEL={'cp_sat':'CP-SAT','parallel_greedy':'Parallel greedy','serial_fifo':'Serial FIFO'}
def read(p):return json.loads(p.read_text())
def lines(p):return [json.loads(s) for s in p.read_text().splitlines() if s]
def label(ax,letter,title):
 ax.text(-.065,1.025,letter,transform=ax.transAxes,fontsize=8,fontweight='bold',va='bottom');ax.set_title(title,loc='left',pad=8)
def save(fig,name,axes,rows=None,cols=None):
 fig.canvas.draw();require_matplotlib_panel_alignment(fig,axes=axes,panel_ids=[str(i) for i in range(len(axes))],row_groups=rows or [],column_groups=cols or [],json_out=OUT/(name+'.alignment.json'))
 for ext in ['pdf','svg','png']:fig.savefig(OUT/(name+'.'+ext),dpi=400,facecolor='white')
 plt.close(fig)
def gantt(ax,p,markers=()):
 resources=['device:19','device:18','demo:ks4000:1','device:67','bench','operator'];names=['Fluent 1080','Fluent 780','KS4000','iD5','Human bench','Shared operator'];mp={e['id']:e['method'] for e in p['graph']['experiments']}
 for row in p['rows']:
  if row['kind']=='operation':
   y=resources.index(row['resource']);ax.broken_barh([(row['start_s']/3600,(row['end_s']-row['start_s'])/3600)],(y-.29,.58),facecolor=COL[mp[row['experiment']]],edgecolor='white',linewidth=.25)
 for r in p['reservations']:
  if r['resource']=='operator' and r['task_id'] in {row['id'] for row in p['rows']}:
   row=next(row for row in p['rows'] if row['id']==r['task_id']);color=COL[mp[row['experiment']]];ax.broken_barh([(r['start_s']/3600,(r['end_s']-r['start_s'])/3600)],(4.72,.56),facecolor=color,edgecolor='white',linewidth=.15)
 for i,t in enumerate(markers):ax.axvline(t/3600,ymin=.15,color='#586069',lw=.6,ls=(0,(2,2)));ax.text(t/3600,5.65,str(i+1),ha='center',fontsize=6)
 ax.set_yticks(range(6),names);ax.set_ylim(5.95,-.65);ax.set_xlim(0,p['makespan_s']/3600+.05);ax.set_xlabel('Time after 09:00 (h)');ax.grid(axis='x',color='#E8EAEC',lw=.5);ax.set_axisbelow(True)

def fig3():
 e=read(DATA/'example.json');p=e['plan'];frames=e['frames'];fig=plt.figure(figsize=(180/25.4,155/25.4));ax=fig.add_axes([.12,.72,.85,.21]);label(ax,'a','One task graph coordinates three assays');gantt(ax,p,[f['time_s'] for f in frames])
 for i,(name,color) in enumerate(COL.items()):fig.text(.52+i*.14,.965,{'gfp':'GFP','bca':'BCA','picogreen':'PicoGreen'}[name],color=color,fontsize=7,weight='bold')
 films=[]
 for i,f in enumerate(frames):
  a=fig.add_axes([.035+i*.244,.41,.232,.185]);a.imshow(plt.imread(REND/f'rehearsal-{i+1}.png'));a.set_axis_off();a.set_title(f"{i+1}   {f['time_s']/60:.1f} min",loc='left',fontsize=6.5,pad=2);films.append(a)
 fig.text(.035,.655,'b',weight='bold',fontsize=8);fig.text(.065,.655,'State-linked replay at the marked times',fontsize=7)
 final=frames[-1]['state'];heat=[]
 for i,ex in enumerate(p['graph']['experiments']):
  a=fig.add_axes([.065+i*.182,.15,.16,.16]);matrix=np.full((8,12),np.nan)
  for w in p['graph']['plate_map']:
   if w['experiment']!=ex['id']:continue
   well=w['well'];matrix[ord(well[0])-65,int(well[1:])-1]=final['containers'][w['container']]['volume_ul']
  a.imshow(np.ma.masked_invalid(matrix),vmin=0,vmax=225,cmap='Greys',aspect='equal');a.set_xticks([0,5,11],['1','6','12']);a.set_yticks([0,3,7],['A','D','H']);a.set_title({'gfp':'GFP · 100 µl','bca':'BCA · 225 µl','picogreen':'PG · 200 µl'}[ex['method']],color=COL[ex['method']],fontsize=6.3);heat.append(a)
 fig.text(.035,.365,'c',weight='bold',fontsize=8);fig.text(.065,.365,'Plate occupancy and volume at the final milestone',fontsize=7);fig.text(.065,.085,'Grey = occupied wells; white = unallocated',fontsize=6)
 path=fig.add_axes([.72,.125,.245,.22]);pos=read(DATA/'catalog.json')['layouts'][p['layout']]['positions'];keys=['bench','device:19','device:18','device:67','demo:ks4000:1'];short=['Bench','1080','780','iD5','KS4000']
 for key,name in zip(keys,short):x,y=pos[key];path.scatter(x,y,c='#E0E4E7',s=100,edgecolor='#667078',linewidth=.5,zorder=4);path.annotate(name,(x,y),xytext=(0,-13 if name in ['Bench','1080'] else 8),textcoords='offset points',ha='center',fontsize=6)
 for ex in p['graph']['experiments']:
  rows_=sorted([r for r in p['rows'] if r['kind']=='transfer' and r['experiment']==ex['id']],key=lambda r:r['start_s'])
  for r in rows_:
   a,b=pos[r['source']],pos[r['destination']]
   if a!=b:path.add_patch(FancyArrowPatch(a,b,arrowstyle='->',mutation_scale=5,color=COL[ex['method']],alpha=.7,lw=.6,connectionstyle='arc3,rad='+str(.07*(list(COL).index(ex['method'])+1))))
 path.set_xlim(-.8,6);path.set_ylim(-.8,4);path.set_aspect('equal');path.set_xticks([0,3,5]);path.set_yticks([0,3]);path.set_xlabel('Configured x (m)');path.set_ylabel('y (m)');label(path,'d','Recorded transfers')
 save(fig,'fig3_rehearsal',[ax,*films,*heat,path],rows=[['1','2','3','4'],['5','6','7']])

def fig6():
 ii=lines(DATA/'repair/injections.jsonl');labels=['Intent mismatch','Resource overlap','Liquid overdraw','Missing water move','Unchanged control'];types=['intent_mismatch','resource_overlap','liquid_overdraw','missing_water_movement','unchanged'];layers=['intent','schedule','mass','material'];matrix=np.array([[sum(r[k+'_detected'] for r in ii if r['error_type']==t) for k in layers] for t in types]);fig=plt.figure(figsize=(180/25.4,153/25.4));a=fig.add_axes([.23,.61,.70,.29]);a.imshow(matrix,vmin=0,vmax=24,cmap='Greys',aspect='auto')
 a.set_yticks(range(5),labels);a.set_xticks(range(4),['Intent','Schedule','Liquid balance','Material location']);a.tick_params(length=0,pad=4);label(a,'a','Different checks expose different inconsistencies')
 for i in range(5):
  for j in range(4):a.text(j,i,f'{matrix[i,j]}/24',ha='center',va='center',color='white' if matrix[i,j]>12 else '#444',fontsize=6.5)
 axes=[a];prov=read(REND/'rehearsal-provenance.json');error=read(DATA/'material-example.json')
 for i,key in enumerate(['injected','correct']):
  b=fig.add_axes([.025+i*.49,.19,.47,.32]);b.imshow(plt.imread(REND/('water-'+key+'.png')));b.set_axis_off();label(b,chr(98+i),'Omitted water transfer' if i==0 else 'Explicit stock staging')
  im=next(x for x in prov['images'] if x['image']=='water-'+key+'.png');xy=im['container_projection']['E3:WATER'];b.annotate('E3:WATER',xy=(xy[0],1-xy[1]),xytext=(.15,.87),xycoords='axes fraction',textcoords='axes fraction',arrowprops={'arrowstyle':'->','lw':.7,'color':'#B82932' if i==0 else '#30383E'},color='#B82932' if i==0 else '#30383E',fontsize=6.5,bbox={'facecolor':'white','edgecolor':'none','pad':1})
  axes.append(b)
 fig.text(.04,.12,'Water at Fluent 1080; dilution requires the bench',color='#B82932',fontsize=6.5);fig.text(.535,.12,'Water staged at the bench before dilution',fontsize=6.5)
 fig.text(.04,.055,'Schedule: pass   Liquid balance: pass   Location: fail',fontsize=6.3);fig.text(.535,.055,'24/24 new plans pass all three execution checks',fontsize=6.3)
 save(fig,'fig6_layers',axes,rows=[['1','2']])

def fig4():
 summary=read(DATA/'summary.json');models=['deepseek-flash','deepseek-v4-pro'];fig=plt.figure(figsize=(180/25.4,132/25.4));a=fig.add_axes([.10,.62,.60,.27]);x=np.arange(5);cats=['Controlled','Open English','Mixed zh–en','Clarify','Reject'];colors=['#111D26','#77838C'];rates=[]
 for m,path in [('rules',DATA/'heldout/language/rules.jsonl')]+[(m,DATA/'heldout/language'/m/'scores.jsonl') for m in models]:
  rr=lines(path);rr=[r for r in rr if r.get('repeat',0)==0];values=[]
  for style in ['controlled','open','mixed','clarify','reject']:
   ss=[r for r in rr if (r['decision']==style if style in ['clarify','reject'] else r['decision']=='compile' and r['style']==style)];values.append(sum(r['success'] for r in ss)/len(ss));rates.append({'model':m,'category':style,'n':len(ss),'success':sum(r['success'] for r in ss)})
  i=['rules',*models].index(m);a.bar(x+(i-1)*.24,values,width=.22,color=['#CDD2D6',*colors][i],label=['Rule parser','Flash','Pro'][i])
 a.set_ylim(0,1.08);a.set_yticks([0,.5,1],['0','50','100']);a.set_ylabel('Frozen-score success (%)');a.set_xticks(x,cats);a.legend(frameon=False,ncol=3,loc='upper center',bbox_to_anchor=(.5,-.20));label(a,'a','Natural language beyond the controlled grammar')
 b=fig.add_axes([.80,.62,.17,.27]);lat=[summary['language'][m]['latency_s_median'] for m in models];b.bar(range(2),lat,color=colors);b.set_xticks(range(2),['Flash','Pro']);b.set_ylabel('Median latency (s)');label(b,'b','Inference time')
 c=fig.add_axes([.18,.16,.79,.29]);matrix=np.zeros((6,24))
 for mi,model in enumerate(models):
  rr=lines(DATA/'heldout/language'/model/'scores.jsonl')
  for r in rr:
   if r['repeat']==0 and r['decision']=='compile':
    col=int(re.search(r'language-(\d+)-s',r['case']).group(1));row=mi*3+['controlled','open','mixed'].index(r['style']);matrix[row,col]=not r['success']
 from matplotlib.colors import ListedColormap
 c.imshow(matrix,cmap=ListedColormap(['#DFE3E6','#B82932']),vmin=0,vmax=1,aspect='auto');c.set_yticks(range(6),['Flash · controlled','Flash · open','Flash · mixed','Pro · controlled','Pro · open','Pro · mixed']);c.set_xticks([0,5,11,17,23],['1','6','12','18','24']);c.set_xlabel('Underlying semantic design');c.tick_params(length=0);label(c,'c','Paired paraphrases localize the remaining deadline errors')
 fig.text(.18,.07,'Grey: exact intent   Red: incorrect deadline',fontsize=6.3);fig.text(.18,.025,'Time contract: 09:00 = 0 s; 16:00 = 25,200 s; 10:00 release = 3,600 s.',fontsize=6.3)
 with (DATA/'figure4-source.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=rates[0]);w.writeheader();w.writerows(rates)
 save(fig,'fig4_language',[a,b,c],rows=[['0','1']])

def fig5():
 rr=lines(DATA/'heldout/scheduling.jsonl');rates=list(csv.DictReader((DATA/'scheduling-rate.csv').open()));pairs=list(csv.DictReader((DATA/'paired-effects.csv').open()));fig=plt.figure(figsize=(180/25.4,159/25.4));a=fig.add_axes([.10,.60,.37,.30]);b=fig.add_axes([.59,.60,.37,.30]);label(a,'a','Constraint-valid plans under increasing load');label(b,'b','Time gain among jointly valid plans')
 for method in METH:
  ss=[r for r in rates if r['objective']=='fastest' and r['method']==method];a.plot([float(r['load']) for r in ss],[100*float(r['rate']) for r in ss],'o-',color=METH[method],ms=3,label=LABEL[method]);a.fill_between([float(r['load']) for r in ss],[100*float(r['low']) for r in ss],[100*float(r['high']) for r in ss],color=METH[method],alpha=.13,lw=0)
 for i,baseline in enumerate(['parallel_greedy','serial_fifo']):
  ss=[r for r in pairs if r['objective']=='fastest' and r['baseline']==baseline];xx=[];yy=[]
  for load in [1,3,6,9,12]:
   v=[float(r['makespan_gain_percent']) for r in ss if int(r['load'])==load]
   if v:xx.append(load);yy.append(st.mean(v))
  b.plot(xx,yy,'o-',ms=3,color=METH[baseline],label='vs '+LABEL[baseline])
 a.set_ylim(-3,105);a.set_ylabel('Valid plan rate (%)');a.set_xlabel('Experiments per portfolio');a.set_xticks([1,3,6,9,12]);a.legend(frameon=False,fontsize=6,loc='lower left');b.set_xlabel('Experiments per portfolio');b.set_ylabel('CP-SAT makespan reduction (%)');b.set_xticks([1,3,6,9,12]);b.axhline(0,color='#BBBBBB',lw=.5);b.legend(frameon=False,loc='upper left',fontsize=6)
 c=fig.add_axes([.10,.10,.37,.32]);d=fig.add_axes([.59,.10,.37,.32]);label(c,'c','Time and nominal operating cost');label(d,'d','Reader outage shifts only unstarted work')
 for method in METH:
  sub=[r for r in rr if r['method']==method and r['valid'] and r['case']=='heldout-012' and r['repeat']==0];c.scatter([r['makespan_s']/3600 for r in sub],[r['cost_cny'] for r in sub],s=22,c=METH[method],label=LABEL[method],edgecolors='white',linewidths=.3)
 c.set_xlabel('Makespan (h)');c.set_ylabel('Nominal operating cost (CNY)');c.legend(frameon=False,fontsize=6,loc='best');c.text(0,-.22,'Illustrative 3-assay case; both objectives',transform=c.transAxes,fontsize=6)
 p=read(DATA/'repair/plans/repair-001.json');q=read(DATA/'repair/replans/repair-001.json')
 for i,plan in enumerate([p,q]):
  for r in plan['rows']:
   if r['kind']=='operation' and r['resource']=='device:67':
    ex=next(e for e in plan['graph']['experiments'] if e['id']==r['experiment']);d.broken_barh([(r['start_s']/3600,(r['end_s']-r['start_s'])/3600)],(i-.25,.5),facecolor=COL[ex['method']])
 d.broken_barh([(1/3600,3599/3600)],(.7,.6),facecolor='#F5DDDF',edgecolor='#B82932',linewidth=.5);d.text(.5,1,'Outage',ha='center',va='center',fontsize=6,color='#9B232B');d.set_yticks([0,1],['Original','Replanned']);d.set_ylim(1.6,-.6);d.set_xlabel('Time after 09:00 (h)');d.set_xlim(0,max(p['makespan_s'],q['makespan_s'])/3600+.05);d.text(0,-.22,'Reader operations; assay colours as in Fig. 3',transform=d.transAxes,fontsize=6)
 save(fig,'fig5_scheduling',[a,b,c,d],rows=[['0','1'],['2','3']],cols=[['0','2'],['1','3']])
if __name__=='__main__':
 for index in sys.argv[1:] or ['3','4','5','6']:globals()['fig'+index]()
