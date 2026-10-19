"""Render the delivered meshes with one Cycles studio; no browser UI or retouch."""
import argparse,json,math,sys,hashlib
from pathlib import Path
import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
args=argparse.ArgumentParser();args.add_argument('--root',required=True);args.add_argument('--out',required=True);args.add_argument('--mode',choices=['rehearsal'],required=True);opt=args.parse_args(sys.argv[sys.argv.index('--')+1:])
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

# State-linked scenes use the scheduling catalog and its explicit illustrative layout.
PAPER=Path(__file__).resolve().parents[3]
example=json.loads((PAPER/'source-data/v2/example.json').read_text());plan=example['plan']
positions=json.loads((PAPER/'source-data/v2/catalog.json').read_text())['layouts'][plan['layout']]['positions']
bindings={'device:19':'fluent1080','device:18':'tecan-fluent780','device:67':'spectramax-id5','demo:ks4000:1':'ika_ks4000'}
manifest['mode']='rehearsal'
manifest['input_plan']={'path':'source-data/v2/repair/plans/repair-001.json','sha256':hashlib.sha256((PAPER/'source-data/v2/repair/plans/repair-001.json').read_bytes()).hexdigest()}
for key,aid in bindings.items():
 manifest['sources'].append({'station':key,'asset_id':aid,'path':lib[aid]['normalized_glb'],'sha256':hashlib.sha256((ASSETS/lib[aid]['normalized_glb']).read_bytes()).hexdigest()})
 xy=positions[key];load(aid,(xy[0],xy[1],.75 if key in ['device:67','demo:ks4000:1'] else 0))
 if key in ['device:67','demo:ks4000:1']:
  bpy.ops.mesh.primitive_cube_add(size=1,location=(*xy,.37));o=bpy.context.object;o.scale=(1.0,.8,.74);o.data.materials.append(mat('Station pedestal '+key,(.72,.75,.77)))
xy=positions['bench'];bpy.ops.mesh.primitive_cube_add(size=1,location=(*xy,.4));o=bpy.context.object;o.scale=(1.9,.9,.8);o.data.materials.append(mat('Human bench',(.78,.81,.83)))
aim((2.2,1.6,.7),9.8,(1.15,-1.7,1.6));scene.cycles.samples=32
colors={'E1':(.85,.54,.25),'E2':(.54,.47,.69),'E3':(.16,.50,.62)}
materials={key:mat(key+' carrier',color) for key,color in colors.items()};red=mat('Location error',(.78,.08,.1));glyphs=[]
def glyph_state(state,redwater=False):
 global glyphs
 for o in glyphs:bpy.data.objects.remove(o,do_unlink=True)
 glyphs=[];counts={};projections={}
 for cid,c in state['containers'].items():
  if c.get('parent'):continue
  location=state['locations'].get(cid,c['location']);key=next((k for k in positions if location==k or location.startswith(k+'/') or location.startswith(k+':')),None)
  if key is None:continue
  j=counts.get(key,0);counts[key]=j+1;x,y=positions[key];x+=(j%5-2)*.16;y-=.36+(j//5)*.15;z=1.0 if key=='bench' else 1.25
  if c['kind']=='read_plate':
   bpy.ops.mesh.primitive_cube_add(size=1,location=(x,y,z));o=bpy.context.object;o.scale=(.128,.086,.018)
  else:
   bpy.ops.mesh.primitive_cylinder_add(vertices=20,radius=.045,depth=.16,location=(x,y,z+.08));o=bpy.context.object
  o.name='State glyph '+cid;o.data.materials.append(red if redwater and cid=='E3:WATER' else materials[cid.split(':')[0]]);glyphs.append(o);projections[cid]=proj(o.location)
 return projections
manifest['layout']=plan['layout'];manifest['positions_m']=positions;manifest['plan_id']=plan['id'];manifest['note']='Actual recorded station states; carrier glyph dimensions are illustrative. Layout is a configured scenario, not a surveyed facility floorplan.'
manifest['station_projection']={k:proj((*xy,1.0)) for k,xy in positions.items() if k in bindings or k=='bench'}
for i,frame in enumerate(example['frames']):
 points=glyph_state(frame['state']);manifest['images'].append({**render('rehearsal-'+str(i+1),1800,1200),'time_s':frame['time_s'],'task':frame['task'],'container_projection':points})
error=json.loads((PAPER/'source-data/v2/material-example.json').read_text())
for key in ['injected','correct']:
 points=glyph_state(error[key],key=='injected');manifest['images'].append({**render('water-'+key,1800,1200),'time_s':error['time_s'],'container_projection':points})
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'rehearsal.blend'))
(OUT/'rehearsal-provenance.json').write_text(json.dumps(manifest,indent=2)+'\n')
