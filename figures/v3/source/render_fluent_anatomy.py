#!/usr/bin/env python3
"""Render a clean Fluent 1080 anatomy view from the delivered native GLB."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


parser = argparse.ArgumentParser()
parser.add_argument("--root", required=True)
parser.add_argument("--out", required=True)
parser.add_argument("--width", type=int, default=2400)
parser.add_argument("--height", type=int, default=1800)
opts = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])

ROOT = Path(opts.root).resolve()
ASSETS = ROOT / "exports/biofoundry"
OUT = Path(opts.out).resolve()
TRANSPARENT = OUT / "transparent"
TRANSPARENT.mkdir(parents=True, exist_ok=True)
source_path = ASSETS / "assets/fluent1080.glb"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def bounds(objects):
    vertices = [o.matrix_world @ Vector(c) for o in objects if o.type == "MESH" for c in o.bound_box]
    return Vector((min(v[i] for v in vertices) for i in range(3))), Vector((max(v[i] for v in vertices) for i in range(3)))


def load_source(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = list(set(bpy.data.objects) - before)
    meshes = [o for o in imported if o.type == "MESH"]
    bpy.context.view_layer.update()
    lo, hi = bounds(meshes)
    wrapper = bpy.data.objects.new("v3 Fluent 1080 source binding", None)
    bpy.context.scene.collection.objects.link(wrapper)
    for obj in imported:
        if obj.parent not in imported:
            world = obj.matrix_world.copy()
            obj.parent = wrapper
            obj.matrix_world = world
    wrapper.location = (-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)
    bpy.context.view_layer.update()
    return wrapper, imported, hi - lo


def aim(camera, target, scale, angle=(0.88, -1.42, 0.86)):
    target = Vector(target)
    camera.location = target + Vector(angle).normalized() * scale * 2.0
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.ortho_scale = scale


def setup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    try:
        scene.view_settings.look = "Medium High Contrast"
    except Exception:
        pass
    scene.view_settings.exposure = 0.35
    scene.display.shading.light = "STUDIO"
    scene.display.shading.studio_light = "paint.sl"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = False
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "BOTH"
    scene.display.shading.curvature_ridge_factor = 1.35
    scene.display.shading.curvature_valley_factor = 1.05
    scene.display.shading.show_specular_highlight = True
    if hasattr(scene.display.shading, "show_outline"):
        scene.display.shading.show_outline = True
    if hasattr(scene.display.shading, "outline_color"):
        scene.display.shading.outline_color = (0.055, 0.07, 0.09)
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.name = "v3 Fluent 1080 anatomy camera"
    camera.data.type = "ORTHO"
    scene.camera = camera
    return scene, camera


def projection(scene, camera, obj):
    if obj.type == "MESH":
        point = sum((obj.matrix_world @ Vector(c) for c in obj.bound_box), Vector()) / 8
    else:
        point = obj.matrix_world.translation
    p = world_to_camera_view(scene, camera, point)
    return [round(float(p.x), 6), round(float(1 - p.y), 6)]


def main():
    scene, camera = setup()
    wrapper, imported, dimensions = load_source(source_path)
    hidden = []
    for obj in imported:
        if obj.type == "MESH" and any(token in obj.name.lower() for token in ["fluent_glass_door", "door_glass", "front_glass", "window_glass"]):
            obj.hide_render = True
            hidden.append(obj.name)
    aim(camera, (0.0, 0.0, max(0.8, float(dimensions.z) * 0.46)), max(float(dimensions.x), float(dimensions.y), float(dimensions.z)) * 1.62)
    scene.render.resolution_x = opts.width
    scene.render.resolution_y = opts.height
    scene.render.filepath = str(TRANSPARENT / "fluent-anatomy.png")
    bpy.ops.render.render(write_still=True)
    landmarks = {}
    for label, needles in {
        "FCA": ["fca_nozzle_0"],
        "MCA96": ["mca96_adapter_F6", "mca96_adapter"],
        "Deck": ["deck_index_rail_122"],
        "Plate sites": ["fluent_spare_plate_nest_1050_220"],
    }.items():
        match = next((obj for obj in imported if any(needle.lower() in obj.name.lower() for needle in needles)), None)
        if match:
            landmarks[label] = {"node": match.name, "xy": projection(scene, camera, match)}
    manifest = {
        "schema": "biorehearse.v3.anatomy-render-provenance/1",
        "renderer": "Blender " + bpy.app.version_string,
        "engine": scene.render.engine,
        "studio": "Workbench paint.sl; Standard; Medium High Contrast; cavity and outline; glass doors hidden for anatomy view",
        "image": "transparent/fluent-anatomy.png",
        "width_px": opts.width,
        "height_px": opts.height,
        "source": {"asset_id": "fluent1080", "path": "assets/fluent1080.glb", "sha256": sha256(source_path), "native_dimensions_m": [round(float(v), 6) for v in dimensions]},
        "hidden_nodes": hidden,
        "landmarks": landmarks,
        "geometry_policy": "native GLB metre scale; rigid framing only; source mesh unchanged",
    }
    (OUT / "anatomy-provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "fluent-anatomy.blend"))


if __name__ == "__main__":
    main()
