#!/usr/bin/env python3
"""Render the recorded Rizon4 island as a separate Fig. 2 asset view.

The island scene is kept separate from the unified assay rehearsal scene.  All
facility meshes are imported from their delivered GLBs and positioned using
``exports/biofoundry/island/latest.json``; no source geometry is changed.
"""

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
parser.add_argument("--width", type=int, default=3000)
parser.add_argument("--height", type=int, default=1500)
opts = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])

ROOT = Path(opts.root).resolve()
ASSETS = ROOT / "exports/biofoundry"
OUT = Path(opts.out).resolve()
TRANSPARENT = OUT / "transparent"
TRANSPARENT.mkdir(parents=True, exist_ok=True)
lib = {a["asset_id"]: a for a in json.loads((ASSETS / "asset-library.json").read_text())["assets"]}
plan_path = ASSETS / "island/latest.json"
plan = json.loads(plan_path.read_text())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def bounds(objects):
    vertices = [o.matrix_world @ Vector(c) for o in objects if o.type == "MESH" for c in o.bound_box]
    if not vertices:
        return Vector((0, 0, 0)), Vector((0, 0, 0))
    return (
        Vector((min(v[i] for v in vertices) for i in range(3))),
        Vector((max(v[i] for v in vertices) for i in range(3))),
    )


def load_path(path: Path, name: str, position=(0, 0, 0), yaw=0.0):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = list(set(bpy.data.objects) - before)
    meshes = [o for o in imported if o.type == "MESH"]
    bpy.context.view_layer.update()
    lo, hi = bounds(meshes)
    wrapper = bpy.data.objects.new(f"v3 Rizon source binding {name}", None)
    bpy.context.scene.collection.objects.link(wrapper)
    for obj in imported:
        if obj.parent not in imported:
            world = obj.matrix_world.copy()
            obj.parent = wrapper
            obj.matrix_world = world
    wrapper.location = (-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)
    bpy.context.view_layer.update()
    anchor = bpy.data.objects.new(f"v3 Rizon station anchor {name}", None)
    bpy.context.scene.collection.objects.link(anchor)
    wrapper.parent = anchor
    anchor.location = position
    anchor.rotation_euler.z = yaw
    bpy.context.view_layer.update()
    return anchor, imported, hi - lo


def aim(camera, target, scale, angle=(1.08, -1.62, 1.08)):
    target = Vector(target)
    camera.location = target + Vector(angle).normalized() * scale * 2.0
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.ortho_scale = scale


def setup_scene():
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
    camera.name = "v3 fixed Rizon island camera"
    camera.data.type = "ORTHO"
    scene.camera = camera
    return scene, camera


def main():
    scene, camera = setup_scene()
    manifest = {
        "schema": "biorehearse.v3.rizon-render-provenance/1",
        "renderer": "Blender " + bpy.app.version_string,
        "engine": scene.render.engine,
        "studio": "Workbench paint.sl; Standard; Medium High Contrast; cavity and outline; long projections disabled",
        "source_plan": {"path": "exports/biofoundry/island/latest.json", "sha256": sha256(plan_path), "generator_sha256": plan.get("generator_sha256")},
        "scene_role": "separate Rizon4/robot-island asset view for Fig. 2; not the assay rehearsal scene",
        "geometry_policy": "native GLB metre scale; rigid translation/yaw only; source meshes unchanged",
        "images": [],
        "sources": [],
    }
    base_path = ASSETS / "demo-blank/model.glb"
    base_anchor, base_objects, base_dimensions = load_path(base_path, "Rizon4-island-base")
    hidden = []
    for obj in base_objects:
        if "enclosure" in obj.name.lower():
            obj.hide_render = True
            hidden.append(obj.name)
    manifest["sources"].append({"asset_id": "Rizon4-island-base", "path": "demo-blank/model.glb", "sha256": sha256(base_path), "hidden_nodes": hidden})

    station_centres = {}
    for key, station in plan["scene"]["stations"].items():
        asset_id = station.get("asset_id")
        if not asset_id:
            continue
        path = ASSETS / lib[asset_id]["normalized_glb"]
        position = station.get("position", [0, 0, 0])
        anchor, objects, dimensions = load_path(path, asset_id, position, station.get("yaw", 0.0))
        lo, hi = bounds(objects)
        station_centres[key] = (lo + hi) / 2
        contract = ASSETS / lib[asset_id].get("source_contract", "")
        manifest["sources"].append(
            {
                "station": key,
                "asset_id": asset_id,
                "path": lib[asset_id]["normalized_glb"],
                "sha256": sha256(path),
                "contract": lib[asset_id].get("source_contract"),
                "contract_sha256": sha256(contract) if contract.exists() else None,
                "license": lib[asset_id].get("license"),
                "placement_m": position,
                "yaw_rad": station.get("yaw", 0.0),
                "native_dimensions_m": [round(float(v), 6) for v in dimensions],
            }
        )

    aim(camera, (-0.35, 0.0, 0.95), 10.2)
    scene.render.resolution_x = opts.width
    scene.render.resolution_y = opts.height
    scene.render.filepath = str(TRANSPARENT / "rizon-island.png")
    bpy.ops.render.render(write_still=True)
    manifest["images"].append({"image": "transparent/rizon-island.png", "width_px": opts.width, "height_px": opts.height, "camera": {"projection": "orthographic", "target_m": [-0.35, 0.0, 0.95], "ortho_scale_m": 10.2}})

    def projection(point):
        p = world_to_camera_view(scene, camera, Vector(point))
        return [round(float(p.x), 6), round(float(1 - p.y), 6)]

    manifest["projection"] = {key: projection(value) for key, value in station_centres.items()}
    manifest["dock_projection"] = {key: projection(station.get("dock", station.get("position"))) for key, station in plan["scene"]["stations"].items() if station.get("asset_id")}
    manifest["route_projection"] = [projection(point) for route in plan.get("routes", []) for point in route.get("tcp_path", []) if isinstance(point, list) and len(point) == 3]
    (OUT / "rizon-island-provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "rizon-island.blend"))


if __name__ == "__main__":
    main()
