"""Concept and asset-resource figures from native geometry and source records."""
import sys,json,math,re
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,Rectangle,FancyArrowPatch
PAPER=Path(__file__).resolve().parents[3];sys.path.insert(0,str(Path(__file__).parent));from figure3456 import save,COL
OUT=PAPER/'figures/v2';REND=OUT/'renders';DATA=PAPER/'source-data/v2'
def read(p):return json.loads(p.read_text())
def panel(ax,letter,title):ax.text(-.06,1.025,letter,transform=ax.transAxes,fontsize=8,weight='bold');ax.set_title(title,loc='left',fontsize=7,pad=8)
def box(ax,x,y,w,h,title,text):
 ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.006,rounding_size=.015',lw=.6,edgecolor='#9AA4AC',facecolor='#F8F9FA'))
 ax.text(x+.012,y+h-.06,title,fontsize=6.5,weight='bold',va='top');ax.text(x+.012,y+h-.26,text,fontsize=6,va='top',linespacing=1.5)
def fig1():
 e=read(DATA/'example.json');p=e['plan'];hero=read(REND/'hero-provenance.json');fig=plt.figure(figsize=(180/25.4,145/25.4));a=fig.add_axes([.035,.78,.93,.185]);a.set_axis_off();a.set_xlim(0,1);a.set_ylim(0,1)
 titles=['Language goal','Typed intent','Method task graph','Shared schedule','State rehearsal'];body=['GFP + BCA + PicoGreen\n8-hour horizon\nOperating budget','mode: simulation\nreplicates: 1–2\ndeadline_s: 28800','','','Location + liquid\nJoint / site state\n3D replay']
 for i,(title,text) in enumerate(zip(titles,body)):
  x=i*.204;box(a,x,.08,.176,.84,title,text)
  if i<4:a.annotate('',xy=(x+.197,.5),xytext=(x+.181,.5),arrowprops={'arrowstyle':'->','lw':.8,'color':'#555'})
 tasks=p['graph']['tasks'];points={};exps=[ex['id'] for ex in p['graph']['experiments']]
 for j,ex in enumerate(exps):
  ts=[t for t in tasks if t['experiment']==ex];color=COL[p['graph']['experiments'][j]['method']]
  for k,t in enumerate(ts):points[t['id']]=(.424+k*.018,.58-j*.17);a.plot(*points[t['id']],'o',color=color,ms=2.7)
 for t in tasks:
  for d in t['depends_on']:
   x,y=points[d];u,v=points[t['id']];a.plot([x,u],[y,v],color='#AAB2B8',lw=.4,zorder=0)
 for r in p['rows']:
  if r['kind']=='operation':
   j=exps.index(r['experiment']);color=COL[p['graph']['experiments'][j]['method']];a.add_patch(Rectangle((.63+.15*r['start_s']/p['makespan_s'],.58-j*.17),max(.002,.15*(r['end_s']-r['start_s'])/p['makespan_s']),.065,facecolor=color,edgecolor='none'))
 b=fig.add_axes([.015,.245,.97,.53]);b.imshow(plt.imread(REND/'hero-island.png'));b.set_axis_off();b.set_xlim(0,3000);b.set_ylim(1500,0)
 # Native image pixel geometry is preserved. Annotation endpoints use Blender projection.
 positions={'fluent780':(.04,.08),'incubator':(.33,.08),'washer':(.56,.08),'reader':(.81,.08),'bravo':(.31,.94),'pcr':(.58,.94),'id5':(.91,.94)}
 names={'fluent780':'Fluent 780','incubator':'KS4000','washer':'405 TS','reader':'i3x','bravo':'AssayMAP Bravo','pcr':'LightCycler 480','id5':'iD5'}
 for key,xy in positions.items():
  px,py=hero['projection'][key];b.annotate(names[key],xy=(px*3000,py*1500),xytext=xy,xycoords='data',textcoords='axes fraction',fontsize=6.5,ha='center',va='center',bbox={'facecolor':'white','edgecolor':'none','pad':1.4},arrowprops={'arrowstyle':'-','lw':.5,'color':'#606A73'})
 px,py=hero['projection']['robot'];b.annotate('Rizon4 + rail',xy=(px*3000,py*1500),xytext=(.76,.94),xycoords='data',textcoords='axes fraction',fontsize=6.5,bbox={'facecolor':'white','edgecolor':'none','pad':1.2},arrowprops={'arrowstyle':'-','lw':.5,'color':'#606A73'})
 fig.text(.035,.225,'Native asset modules and robot-island demonstration; three-assay replay is shown in Fig. 3.',fontsize=6,color='#555')
 c=fig.add_axes([.035,.035,.93,.15]);c.set_axis_off();c.set_xlim(0,1);c.set_ylim(0,1)
 checks=[('Intent','Assay, counts, limits'),('Schedule','Devices, operator, windows'),('Liquid balance','Volumes and components'),('Material location','Stock at the required site')]
 for i,(title,text) in enumerate(checks):box(c,i*.206,.12,.188,.78,title,text)
 c.add_patch(Rectangle((.834,.12),.165,.78,facecolor='#ECEEEF',edgecolor='#BEC5CB',lw=.6));c.text(.85,.68,'Collision',fontsize=6.5,color='#777');c.text(.85,.4,'Outside this study',fontsize=6,color='#777')
 save(fig,'fig1_concept',[a,b,c],cols=[['0','2']])

def fig2():
 assets=read(REND/'gallery-provenance.json');summary=read(DATA/'asset-summary.json');fig=plt.figure(figsize=(180/25.4,215/25.4));gallery=[];short={'Liquid handling':'Liquid handling','Optical detection':'Optical detection','Incubation and culture':'Incubation / culture','Chromatography and mass spectrometry':'Chromatography / MS','Cytometry and sequencing':'Cytometry / sequencing','Centrifugation':'Centrifugation'}
 groups=list(dict.fromkeys(x['group'] for x in assets['images']));display_labels={}
 fig.text(.025,.985,'a',fontsize=8,weight='bold');fig.text(.055,.985,'A reusable library of digital laboratory instruments',fontsize=7)
 for i,record in enumerate(assets['images']):
  row,col=divmod(i,4);x=.025+col*.244;y=.95-row*.095
  if col==0:fig.text(.026,y,short[record['group']],fontsize=6.5,color='#55616B',weight='bold')
  ax=fig.add_axes([x,y-.073,.232,.066]);ax.imshow(plt.imread(REND/record['image']));ax.set_axis_off();name=['Fluent 1080','Fluent 780','AssayMAP Bravo','Opentrons Flex','SpectraMax iD5','SpectraMax i3x','CLARIOstar Plus','iBright FL1500','KS4000','LogPhase 600','CellXpert C170i','ambr 15','AKTA pure 25M1','1290 Infinity II','RapidFire 400 / 6470','ZenoTOF 7600','LSRFortessa','CytoFLEX LX','DNBSEQ G99RS','Helios','Optima XE100','Optima XPN100','Sorvall LYNX6000','Eppendorf 5910Ri'][i]
  display_labels[record['asset_id']]={'label':name,'original_display_name':record['display_name']};name=re.sub(r'[^\x00-\x7F]+',' ',name).strip();ax.text(.5,-.035,name,transform=ax.transAxes,ha='center',va='top',fontsize=5.5);gallery.append(ax)
 (DATA/'asset-display-labels.json').write_text(json.dumps(display_labels,indent=2)+'\n')
 # Middle: real asset anatomy and explicit feature coverage, not a maturity ladder.
 b=fig.add_axes([.04,.18,.43,.17]);b.imshow(plt.imread(REND/'fluent-anatomy.png'));b.set_axis_off();panel(b,'b','Fluent 1080 mechanism references')
 landmarks=read(REND/'anatomy-provenance.json')['landmarks']
 for text,key,tx in [('FCA nozzle','FCA',(.06,.80)),('MCA96 head','MCA96',(.68,.84)),('Deck reference','Deck',(.08,.14)),('Plate nest','Plate sites',(.78,.16))]:
  px,py=landmarks[key]['xy'];xy=(px,1-py);b.annotate(text,xy=xy,xytext=tx,xycoords='axes fraction',textcoords='axes fraction',fontsize=6,arrowprops={'arrowstyle':'-','lw':.6,'color':'#555'},bbox={'facecolor':'white','edgecolor':'none','pad':1.2})
 c=fig.add_axes([.64,.18,.31,.17]);features=['Joint contracts','Animation poses','Access lifecycle','Liquid profiles','Hardware adapters'];values=[summary[k] for k in ['assets_with_joint_contract','assets_with_animation_poses','access_lifecycle_assets','liquid_accounting_assets','hardware_adapters']];c.barh(range(5),values,color='#7A8791',height=.55);c.invert_yaxis();c.set_yticks(range(5),features);c.set_xlim(0,78);c.set_xlabel('Assets (of 71)');c.set_xticks([0,35,71]);panel(c,'c','Digital feature coverage')
 for i,v in enumerate(values):c.text(v+1.3,i,str(v),va='center',fontsize=6)
 # Bottom: inventory-to-asset relationship and robot island ports.
 d=fig.add_axes([.04,.035,.57,.095]);d.set_axis_off();d.set_xlim(0,1);d.set_ylim(0,1);panel(d,'d','Instance-to-asset binding')
 d.text(0,.7,'73 instances · 52 raw model strings',fontsize=6.5,weight='bold');d.text(0,.34,'54 assigned instances → 43 asset IDs',fontsize=6.5);d.text(0,.02,'19 unassigned instances; 71 assets in the full library',fontsize=6.3)
 e=fig.add_axes([.705,.015,.26,.095]);e.set_axis_off();panel(e,'e','Handoff sites');island=read(DATA/'island-example.json');stations=island['scene']['stations']
 for key,s in stations.items():
  x,y=s['position'][:2];e.scatter(x,y,c='#D1D7DC',s=30,edgecolors='#66737D',linewidths=.3);e.annotate({'input':'In','output':'Out','bravo':'Bravo','washer':'405TS','pcr':'LC480','reader':'i3x','incubator':'KS4000'}.get(key,key),(x,y),xytext=(0,6 if y>0 else -10),textcoords='offset points',ha='center',fontsize=5.5)
 e.plot([-3,3],[0,0],color='#778892',lw=2);e.set_xlim(-3.4,3.4);e.set_ylim(-1.2,1.2)
 save(fig,'fig2_assets',[*gallery,b,c,d,e],rows=[[str(i) for i in range(r*4,r*4+4)] for r in range(6)])
if __name__=='__main__':
 for n in sys.argv[1:] or ['1','2']:globals()['fig'+n]()
