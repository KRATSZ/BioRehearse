"""Render the delivered meshes with one Cycles studio; no browser UI or retouch."""
import argparse,json,math,sys,hashlib
from pathlib import Path
import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
args=argparse.ArgumentParser();args.add_argument('--root',required=True);args.add_argument('--out',required=True);args.add_argument('--mode',choices=['hero','gallery','anatomy'],required=True);opt=args.parse_args(sys.argv[sys.argv.index('--')+1:])
ROOT=Path(opt.root);OUT=Path(opt.out);OUT.mkdir(parents=True,exist_ok=True);ASSETS=ROOT/'exports/biofoundry';lib={a['asset_id']:a for a in json.loads((ASSETS/'asset-library.json').read_text())['assets']}
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=32;scene.cycles.use_denoising=True
try:
 prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='METAL';prefs.get_devices()
 for d in prefs.devices:d.use=True
 if any(d.type=='METAL' for d in prefs.devices):scene.cycles.device='GPU'
except Exception:pass
scene.render.image_settings.file_format='PNG';scene.render.resolution_percentage=100;scene.world.color=(.8,.8,.8);scene.view_settings.view_transform='AgX'
scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.8,.83,.88,1);scene.world.node_tree.nodes['Background'].inputs[1].default_value=.45

def mat(name,rgb,rough=.6):
 m=bpy.data.materials.new(name);m.diffuse_color=(*rgb,1);m.use_nodes=True;m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(*rgb,1);m.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=rough;return m
floor_mat=mat('Paper studio floor',(.86,.87,.88));bpy.ops.mesh.primitive_plane_add(size=200);floor=bpy.context.object;floor.name='Paper studio floor';floor.data.materials.append(floor_mat)
lights=[]
for name,pos,power,size in [('Key',(-4,-7,9),1700,7),('Fill',(6,-2,7),1300,6),('Rim',(2,6,10),1900,5)]:
 bpy.ops.object.light_add(type='AREA',location=pos);o=bpy.context.object;o.name='Studio '+name;o.data.energy=power;o.data.shape='DISK';o.data.size=size;lights.append(o)
bpy.ops.object.camera_add();camera=bpy.context.object;camera.data.type='ORTHO';scene.camera=camera

def aim(target,scale,angle=(1.25,-1.7,1.15)):
 target=Vector(target);camera.location=target+Vector(angle).normalized()*scale*2;camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.ortho_scale=scale

def bounds(objects):
 v=[o.matrix_world@Vector(c) for o in objects if o.type=='MESH' for c in o.bound_box]
 return Vector([min(x[i] for x in v) for i in range(3)]),Vector([max(x[i] for x in v) for i in range(3)])

def load_path(path,name,position=(0,0,0),yaw=0):
 before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(path));objects=list(set(bpy.data.objects)-before);meshes=[o for o in objects if o.type=='MESH'];bpy.context.view_layer.update();lo,hi=bounds(meshes)
 wrap=bpy.data.objects.new('Paper binding '+name,None);scene.collection.objects.link(wrap)
 for o in objects:
  if o.parent not in objects:
   world=o.matrix_world.copy();o.parent=wrap;o.matrix_world=world
 wrap.location=(-(lo.x+hi.x)/2,-(lo.y+hi.y)/2,-lo.z);bpy.context.view_layer.update()
 # Separate translation and rotation preserves the delivered metre-scale geometry.
 anchor=bpy.data.objects.new('Paper placement '+name,None);scene.collection.objects.link(anchor);wrap.parent=anchor;anchor.location=position;anchor.rotation_euler.z=yaw;bpy.context.view_layer.update()
 return anchor,objects

def load(aid,position=(0,0,0),yaw=0):return load_path(ASSETS/lib[aid]['normalized_glb'],aid,position,yaw)
def render(name,width,height):
 scene.render.resolution_x=width;scene.render.resolution_y=height;scene.render.filepath=str(OUT/(name+'.png'));bpy.ops.render.render(write_still=True)
 return {'image':name+'.png','width':width,'height':height,'engine':'Cycles','samples':scene.cycles.samples,'device':scene.cycles.device}
def proj(point):
 p=world_to_camera_view(scene,camera,Vector(point));return [p.x,1-p.y]
manifest={'mode':opt.mode,'Blender':bpy.app.version_string,'sources':[],'images':[],'transforms':'native GLB importer; rigid placement only; source meshes unchanged','studio':'three area lights; AgX; fixed orthographic viewing direction; neutral floor'}
if opt.mode=='gallery':
 groups=[('Liquid handling',['fluent1080','tecan-fluent780','agilent_bravo_assaymap','opentrons_flex_project']),('Optical detection',['spectramax-id5','spectramax-i3x','bmg_clariostarplus','thermo_ibrightfl1500']),('Incubation and culture',['ika_ks4000','biotek-logphase-600','eppendorf_cellxpertc170i','sartorius_ambr15']),('Chromatography and mass spectrometry',['cytiva_akta_pure_25m1','agilent-1290-infinity-ii-analytical','agilent-rapidfire400-6470','sciex_zenotof_7600']),('Cytometry and sequencing',['bd_lsrfortessa','beckman_cytoflex_lx','mgi_dnbseq_g99rs','fluidigm_helios']),('Centrifugation',['beckman_optima_xe100','beckman_optima_xpn100','thermo_sorvall_lynx6000','eppendorf_5910ri'])]
 for group,ids in groups:
  for aid in ids:
   anchor,objects=load(aid);lo,hi=bounds(objects);dim=hi-lo;scale=max(dim.x,dim.y,dim.z)*1.65;target=(0,0,dim.z*.43);aim(target,scale)
   for l in lights:
    l.location*=max(.5,scale/3);l.data.energy*=max(.35,(scale/3)**2);l.data.size=max(1,scale*1.2)
   manifest['images'].append({**render('asset-'+aid,840,640),'asset_id':aid,'group':group,'display_name':lib[aid].get('model') or lib[aid].get('name'),'dimensions_m':list(dim)})
   manifest['sources'].append({'asset_id':aid,'path':lib[aid]['normalized_glb'],'sha256':hashlib.sha256((ASSETS/lib[aid]['normalized_glb']).read_bytes()).hexdigest(),'license':lib[aid].get('license'),'source':lib[aid].get('source')})
   for o in objects+[anchor]:
    if o.name in bpy.data.objects:bpy.data.objects.remove(o,do_unlink=True)
   # Restore absolute studio positions after each object, rather than compounding.
   for l,pos,power,size in zip(lights,[(-4,-7,9),(6,-2,7),(2,6,10)],[1700,1300,1900],[7,6,5]):l.location=pos;l.data.energy=power;l.data.size=size
elif opt.mode=='hero':
 table,objects=load_path(ASSETS/'demo-blank/model.glb','island');manifest['sources'].append({'asset_id':'robot-island-base','path':'demo-blank/model.glb','sha256':hashlib.sha256((ASSETS/'demo-blank/model.glb').read_bytes()).hexdigest()})
 for o in objects:
  if 'enclosure' in o.name.lower():o.hide_render=True
 plan=json.loads((ASSETS/'island/latest.json').read_text());stations=plan['scene']['stations'];centres={}
 for key,s in stations.items():
  if s.get('asset_id'):
   _,obs=load(s['asset_id'],s['position'],s.get('yaw',0));lo,hi=bounds(obs);centres[key]=(lo+hi)/2;manifest['sources'].append({'asset_id':s['asset_id'],'position_m':s['position'],'binding':'existing island station','path':lib[s['asset_id']]['normalized_glb'],'sha256':hashlib.sha256((ASSETS/lib[s['asset_id']]['normalized_glb']).read_bytes()).hexdigest()})
 load('tecan-fluent780',(-4,-.1,0),.08);load('spectramax-id5',(3.45,.35,.74),-.15)
 for aid in ['tecan-fluent780','spectramax-id5']:manifest['sources'].append({'asset_id':aid,'path':lib[aid]['normalized_glb'],'sha256':hashlib.sha256((ASSETS/lib[aid]['normalized_glb']).read_bytes()).hexdigest(),'binding':'additional digital module for conceptual illustration'})
 bpy.ops.mesh.primitive_cube_add(size=1,location=(3.45,.35,.37));o=bpy.context.object;o.scale=(.8,.75,.74);o.data.materials.append(mat('Pedestal',(.72,.75,.77)))
 aim((-.35,0,.95),10.2,(1.05,-1.65,1.15));scene.cycles.samples=64
 manifest['images'].append(render('hero-island',3000,1500));manifest['port_projection']={k:proj(s.get('dock',s['position'])) for k,s in stations.items()};manifest['projection']={k:proj(centres.get(k,s['position'])) for k,s in stations.items()};manifest['projection'].update({'fluent780':proj((-4,-.1,1.2)),'id5':proj((3.45,.35,1.1)),'robot':proj((0,.4,1.45))})
 # Project the recorded robot route for a vector overlay in the assembled figure.
 manifest['route_projection']=[proj(p) for r in plan.get('routes',[]) for p in r.get('tcp_path',[]) if isinstance(p,list) and len(p)==3]
 bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'hero-island.blend'))
elif opt.mode=='anatomy':
 anchor,objects=load('fluent1080')
 # A documented cutaway removes only the door/glazing to expose existing mechanics.
 hidden=[]
 for o in objects:
  if o.type=='MESH' and any(x in o.name.lower() for x in ['door_glass','window_glass','front_glass','fluent_glass_door']):o.hide_render=True;hidden.append(o.name)
 lo,hi=bounds(objects);aim((0,0,.95),3.25,(.8,-1.6,.9));scene.cycles.samples=64
 manifest['images'].append(render('fluent-anatomy',2200,1800));manifest['hidden_for_cutaway']=hidden
 manifest['sources'].append({'asset_id':'fluent1080','path':lib['fluent1080']['normalized_glb'],'sha256':hashlib.sha256((ASSETS/lib['fluent1080']['normalized_glb']).read_bytes()).hexdigest()})
 manifest['landmarks']={}
 for name,keywords in [('FCA',['fca_nozzle_0']),('MCA96',['mca96_adapter_F6']),('Deck',['deck_index_rail_122']),('Plate sites',['fluent_spare_plate_nest_1050_220'])]:
  match=next((o for o in objects if any(k in o.name for k in keywords)),None)
  if match:manifest['landmarks'][name]={'node':match.name,'xy':proj(sum((match.matrix_world@Vector(c) for c in match.bound_box),Vector())/8 if match.type=='MESH' else match.matrix_world.translation)}
 bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'fluent-anatomy.blend'))
(OUT/(opt.mode+'-provenance.json')).write_text(json.dumps(manifest,indent=2)+'\n')
