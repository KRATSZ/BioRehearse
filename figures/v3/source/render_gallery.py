#!/usr/bin/env python3
"""Render a consistent native-asset gallery for the BioRehearse v3 figures.

Every asset is imported at its delivered metre scale.  The camera scale is
changed only to frame each asset; no source mesh is resized.  The transparent
PNGs are kept as the source renders and can be composited on white with
``compose_white.py``.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


parser = argparse.ArgumentParser()
parser.add_argument("--root", required=True)
parser.add_argument("--out", required=True)
parser.add_argument("--width", type=int, default=1400)
parser.add_argument("--height", type=int, default=1050)
opts = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])

ROOT = Path(opts.root).resolve()
ASSETS = ROOT / "exports/biofoundry"
OUT = Path(opts.out).resolve()
TRANSPARENT = OUT / "transparent"
TRANSPARENT.mkdir(parents=True, exist_ok=True)

lib = {a["asset_id"]: a for a in json.loads((ASSETS / "asset-library.json").read_text())["assets"]}

GROUPS = [
    ("Liquid handling", ["fluent1080", "tecan-fluent780", "agilent_bravo_assaymap", "opentrons_flex_project"]),
    ("Optical detection", ["spectramax-id5", "spectramax-i3x", "bmg_clariostarplus", "thermo_ibrightfl1500"]),
    ("Incubation and culture", ["ika_ks4000", "biotek-logphase-600", "eppendorf_cellxpertc170i", "sartorius_ambr15"]),
    ("Chromatography and mass spectrometry", ["cytiva_akta_pure_25m1", "agilent-1290-infinity-ii-analytical", "agilent-rapidfire400-6470", "sciex_zenotof_7600"]),
    ("Cytometry and sequencing", ["bd_lsrfortessa", "beckman_cytoflex_lx", "mgi_dnbseq_g99rs", "fluidigm_helios"]),
    ("Centrifugation", ["beckman_optima_xe100", "beckman_optima_xpn100", "thermo_sorvall_lynx6000", "eppendorf_5910ri"]),
]


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


def mat(name, rgba, roughness=0.78):
    material = bpy.data.materials.new(name)
    material.diffuse_color = tuple(rgba)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = tuple(rgba)
    bsdf.inputs["Roughness"].default_value = roughness
    return material


def load_path(path: Path, name: str):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = list(set(bpy.data.objects) - before)
    meshes = [o for o in imported if o.type == "MESH"]
    bpy.context.view_layer.update()
    lo, hi = bounds(meshes)

    wrapper = bpy.data.objects.new(f"v3 gallery source binding {name}", None)
    bpy.context.scene.collection.objects.link(wrapper)
    for obj in imported:
        if obj.parent not in imported:
            world = obj.matrix_world.copy()
            obj.parent = wrapper
            obj.matrix_world = world
    # Normalise only the local origin, preserving the delivered model scale.
    wrapper.location = (-(lo.x + hi.x) / 2.0, -(lo.y + hi.y) / 2.0, -lo.z)
    bpy.context.view_layer.update()
    return wrapper, imported, hi - lo


def aim(camera, target, scale, angle=(1.0, -1.25, 0.82)):
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
    camera.name = "v3 asset gallery orthographic camera"
    camera.data.type = "ORTHO"
    scene.camera = camera
    return scene, camera


def add_plinth(dimensions):
    # A neutral, very thin plinth gives small objects a stable visual datum.
    side = max(float(dimensions.x), float(dimensions.y), float(dimensions.z))
    width = max(float(dimensions.x) * 1.22, side * 0.74)
    depth = max(float(dimensions.y) * 1.22, side * 0.62)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, -0.025))
    plinth = bpy.context.object
    plinth.name = "v3 gallery neutral plinth"
    plinth.dimensions = (width, depth, 0.05)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    plinth.data.materials.append(mat("v3 gallery plinth", (0.78, 0.81, 0.84, 1.0)))
    bevel = plinth.modifiers.new("soft gallery plinth edge", "BEVEL")
    bevel.width = min(0.03, side * 0.025)
    bevel.segments = 3
    return plinth


def remove_objects(objects):
    for obj in objects:
        if obj and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)


def main():
    scene, camera = setup_scene()
    manifest = {
        "schema": "biorehearse.v3.asset-gallery-provenance/1",
        "renderer": "Blender " + bpy.app.version_string,
        "engine": scene.render.engine,
        "studio": "Workbench paint.sl; Standard; Medium High Contrast; cavity and outline; long projections disabled",
        "images": [],
        "sources": [],
        "geometry_policy": "native GLB metre scale; local-origin normalisation and rigid framing only; no source mesh rescaling",
        "display_scale": "each tile is independently framed and therefore not-to-scale across assets; native dimensions are recorded per image",
        "transparent_film": True,
        "groups": [{"name": name, "asset_ids": ids} for name, ids in GROUPS],
    }
    for group_name, asset_ids in GROUPS:
        for asset_id in asset_ids:
            entry = lib[asset_id]
            source_path = ASSETS / entry["normalized_glb"]
            wrapper, imported, dimensions = load_path(source_path, asset_id)
            plinth = add_plinth(dimensions)
            target = (0.0, 0.0, max(0.08, float(dimensions.z) * 0.44))
            scale = max(float(dimensions.x), float(dimensions.y), float(dimensions.z)) * 1.62
            aim(camera, target, scale)
            scene.render.resolution_x = opts.width
            scene.render.resolution_y = opts.height
            filename = f"asset-{asset_id}"
            scene.render.filepath = str(TRANSPARENT / f"{filename}.png")
            bpy.ops.render.render(write_still=True)
            manifest["images"].append(
                {
                    "image": f"transparent/{filename}.png",
                    "asset_id": asset_id,
                    "group": group_name,
                    "display_name": entry.get("model") or entry.get("name") or asset_id,
                    "width_px": opts.width,
                    "height_px": opts.height,
                    "native_dimensions_m": [round(float(v), 6) for v in dimensions],
                    "display_scale": "not-to-scale; camera framing only",
                }
            )
            contract = ASSETS / entry.get("source_contract", "")
            manifest["sources"].append(
                {
                    "asset_id": asset_id,
                    "normalized_glb": entry["normalized_glb"],
                    "glb_sha256": sha256(source_path),
                    "contract": entry.get("source_contract"),
                    "contract_sha256": sha256(contract) if contract.exists() else None,
                    "license": entry.get("license"),
                    "source": entry.get("source"),
                }
            )
            remove_objects(imported + [wrapper, plinth])
            bpy.context.view_layer.update()
    (OUT / "asset-gallery-provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    # Save an editable scene containing the camera and the final tile setup;
    # source assets remain external and are never overwritten.
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "asset-gallery.blend"))


if __name__ == "__main__":
    main()
