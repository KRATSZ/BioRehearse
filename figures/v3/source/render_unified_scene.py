#!/usr/bin/env python3
"""Render the v3 BioRehearse rehearsal scene from the recorded state traces.

The scene uses the compact scheduling anchors without changing the source meshes:
bench=(0, 0), Fluent 1080=(3, 0), Fluent 780=(3, 3), iD5=(0, 3), and
KS4000=(5, 3).  The rendered carriers are deliberately enlarged visual glyphs;
their dimensions and the exact source-state mapping are recorded in the
provenance manifest.  This file does not modify any source GLB.
"""

import argparse
import copy
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


parser = argparse.ArgumentParser()
parser.add_argument("--root", required=True)
parser.add_argument("--out", required=True)
parser.add_argument("--mode", choices=["preview", "rehearsal", "water", "all"], default="preview")
parser.add_argument("--engine", choices=["cycles", "workbench"], default="cycles")
parser.add_argument("--samples", type=int, default=128)
parser.add_argument("--width", type=int, default=1200)
parser.add_argument("--height", type=int, default=750)
opts = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])

ROOT = Path(opts.root).resolve()
PAPER = ROOT / "docs/paper/biofoundry-preprint"
OUT = Path(opts.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)
TRANSPARENT = OUT / "transparent"
TRANSPARENT.mkdir(parents=True, exist_ok=True)

ASSETS = ROOT / "exports/biofoundry"
lib = {a["asset_id"]: a for a in json.loads((ASSETS / "asset-library.json").read_text())["assets"]}

STATIONS = {
    "bench": (0.0, 0.0),
    "device:19": (3.0, 0.0),
    "device:18": (3.0, 3.0),
    "device:67": (0.0, 3.0),
    "demo:ks4000:1": (5.0, 3.0),
}
ASSET_FOR_STATION = {
    "device:19": "fluent1080",
    "device:18": "tecan-fluent780",
    "device:67": "spectramax-id5",
    "demo:ks4000:1": "ika_ks4000",
}
# These are measured from the delivered asset contracts/source geometry.  The
# liquid glyphs sit at the configured deck/tray/bench surface, not at the mesh
# bounding-box roof.  The small deck offset is retained as an explicit datum.
SURFACE_Z = {
    "bench": 0.93,
    "device:19": 0.98,  # Fluent 1080 deck datum in the source geometry
    "device:18": 0.98,  # Fluent 780 deck datum represented by the source mesh
    "device:67": 0.96,  # iD5 tray datum used for the digital plate glyph
    "demo:ks4000:1": 0.98,  # KS4000 platform datum
}

ASSAY_COLORS = {
    "E1": (0.88, 0.47, 0.12, 1.0),  # BCA
    "E2": (0.47, 0.34, 0.72, 1.0),  # PicoGreen
    "E3": (0.04, 0.47, 0.66, 1.0),  # GFP
}
ASSAY_NAMES = {"E1": "BCA", "E2": "PicoGreen", "E3": "GFP"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def mat(name, rgba, roughness=0.54, metallic=0.0, emission=None):
    material = bpy.data.materials.new(name)
    material.diffuse_color = tuple(rgba)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = tuple(rgba)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = tuple(emission)
        bsdf.inputs["Emission Strength"].default_value = 1.5
    return material


def add_box(name, location, dimensions, material, bevel=0.025):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    if bevel:
        modifier = obj.modifiers.new("soft manufactured edges", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    return obj


def add_torus(name, location, radius, material, z=0.02):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=radius,
        minor_radius=0.024,
        major_segments=64,
        minor_segments=12,
        location=(location[0], location[1], z),
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    return obj


def bounds(objects):
    vertices = [o.matrix_world @ Vector(c) for o in objects if o.type == "MESH" for c in o.bound_box]
    if not vertices:
        return Vector((0.0, 0.0, 0.0)), Vector((0.0, 0.0, 0.0))
    return (
        Vector((min(v[i] for v in vertices) for i in range(3))),
        Vector((max(v[i] for v in vertices) for i in range(3))),
    )


def load_path(path: Path, name: str, position=(0.0, 0.0, 0.0), yaw=0.0):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = list(set(bpy.data.objects) - before)
    meshes = [o for o in imported if o.type == "MESH"]
    bpy.context.view_layer.update()
    lo, hi = bounds(meshes)

    wrapper = bpy.data.objects.new(f"v3 source binding {name}", None)
    bpy.context.scene.collection.objects.link(wrapper)
    for obj in imported:
        if obj.parent not in imported:
            world = obj.matrix_world.copy()
            obj.parent = wrapper
            obj.matrix_world = world
    # Canonicalize only the local origin.  No source mesh is rescaled or edited.
    wrapper.location = (-(lo.x + hi.x) / 2.0, -(lo.y + hi.y) / 2.0, -lo.z)
    bpy.context.view_layer.update()
    anchor = bpy.data.objects.new(f"v3 station anchor {name}", None)
    bpy.context.scene.collection.objects.link(anchor)
    wrapper.parent = anchor
    anchor.location = position
    anchor.rotation_euler.z = yaw
    bpy.context.view_layer.update()
    return anchor, imported, (hi - lo)


def load_asset(asset_id, position, yaw=0.0):
    entry = lib[asset_id]
    path = ASSETS / entry["normalized_glb"]
    return load_path(path, asset_id, position, yaw)


def setup_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    try:
        scene.view_settings.look = "Medium High Contrast"
    except Exception:
        pass
    scene.view_settings.exposure = 0.45
    scene.view_settings.gamma = 1.0
    if scene.world is None:
        scene.world = bpy.data.worlds.new("v3 white studio world")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.8

    if opts.engine == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = max(32, opts.samples)
        scene.cycles.use_denoising = True
        try:
            preferences = bpy.context.preferences.addons["cycles"].preferences
            preferences.compute_device_type = "METAL"
            preferences.get_devices()
            for device in preferences.devices:
                device.use = True
            if any(device.type == "METAL" for device in preferences.devices):
                scene.cycles.device = "GPU"
        except Exception:
            scene.cycles.device = "CPU"
    else:
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.studio_light = "paint.sl"
        scene.display.shading.color_type = "MATERIAL"
        # Keep the workbench outline/cavity pass, but suppress long studio
        # projections.  The latter read as geometry artefacts at full-scene
        # scale and are not evidence for a physical lighting measurement.
        scene.display.shading.show_shadows = False
        scene.display.shading.show_cavity = True
        scene.display.shading.cavity_type = "BOTH"
        scene.display.shading.curvature_ridge_factor = 1.3
        scene.display.shading.curvature_valley_factor = 1.0
        scene.display.shading.show_specular_highlight = True
        # Blender 5.2 keeps the outline controls build-dependent; retain the
        # cavity pass when the optional outline properties are unavailable.
        if hasattr(scene.display.shading, "show_outline"):
            scene.display.shading.show_outline = True
        if hasattr(scene.display.shading, "outline_color"):
            scene.display.shading.outline_color = (0.055, 0.07, 0.09)

    # Transparent film plus a white shadow-catching plane gives both a clean
    # compositing layer and a white-background preview without baking a panel.
    floor_mat = mat("v3 white shadow catcher", (0.96, 0.97, 0.98, 1.0), roughness=0.9)
    bpy.ops.mesh.primitive_plane_add(size=200, location=(2.5, 2.0, -0.004))
    floor = bpy.context.object
    floor.name = "v3 white shadow catcher"
    floor.data.materials.append(floor_mat)
    if opts.engine == "cycles":
        floor.is_shadow_catcher = True

    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.name = "v3 fixed orthographic camera"
    camera.data.type = "ORTHO"
    bpy.context.scene.camera = camera
    return scene, camera


def aim(camera, target, scale, angle=(1.18, -1.72, 1.38)):
    target = Vector(target)
    camera.location = target + Vector(angle).normalized() * scale * 2.0
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.ortho_scale = scale


def station_for_location(location):
    if not isinstance(location, str):
        return None
    value = location
    if value.startswith("staging:"):
        value = value[len("staging:") :]
    # Preserve transit as a special state so the transfer path can be shown.
    if value.startswith("transit:"):
        return None
    for key in sorted(STATIONS, key=len, reverse=True):
        if value == key or value.startswith(key + ":") or value.startswith(key + "/"):
            return key
    if value.startswith(("bench", "prep", "cold")):
        return "bench"
    return None


def transfer_midpoint(state):
    for event in state.get("active", []):
        if event.get("kind") == "transfer" and event.get("source") and event.get("destination"):
            src = station_for_location(event["source"])
            dst = station_for_location(event["destination"])
            if src in STATIONS and dst in STATIONS:
                sx, sy = STATIONS[src]
                dx, dy = STATIONS[dst]
                return (0.5 * (sx + dx), 0.5 * (sy + dy), 1.06), src, dst
    return None, None, None


def material_for_container(container_id):
    prefix = str(container_id).split(":", 1)[0]
    rgba = ASSAY_COLORS.get(prefix, (0.38, 0.45, 0.50, 1.0))
    return mat(f"v3 {ASSAY_NAMES.get(prefix, prefix)} carrier", rgba, roughness=0.35)


def clear_overlay(objects):
    for obj in objects:
        if obj and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    objects.clear()


def add_cylinder_between(name, a, b, radius, material):
    a = Vector(a)
    b = Vector(b)
    delta = b - a
    length = delta.length
    if length <= 1e-6:
        return None
    mid = (a + b) / 2.0
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=radius, depth=length, location=mid)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = delta.to_track_quat("Z", "Y").to_euler()
    obj.data.materials.append(material)
    return obj


def active_rows(state):
    rows = list(state.get("active", []))
    rows.extend(
        {
            "resource": row.get("resource"),
            "task_id": row.get("task_id"),
            "kind": "operation",
            "container_ids": row.get("container_ids", []),
            "source": None,
            "destination": None,
        }
        for row in state.get("device_states", [])
    )
    return rows


def selected_container_ids(state, frame_task):
    containers = state.get("containers", {})
    ids = []
    for row in active_rows(state):
        for cid in row.get("container_ids", []):
            if cid in containers and not containers[cid].get("parent") and cid not in ids:
                ids.append(cid)
    if "prepare_plate" in frame_task:
        for cid in ["E3:WATER", "E3:P01"]:
            if cid in containers and cid not in ids:
                ids.append(cid)
    return ids


def add_carrier_glyph(container_id, container, state, index, overlay, error_stock=None):
    locations = state.get("locations", {})
    location = locations.get(container_id, container.get("location"))
    station = station_for_location(location)
    transfer, src, dst = transfer_midpoint(state)
    if station is None and transfer is None:
        return None
    if station is None:
        position = transfer
        station_for_glyph = "transit"
    else:
        x, y = STATIONS[station]
        # Keep the glyphs on the configured station surface and separated enough
        # to remain readable at the full-scene scale.
        offset = ((index % 3) - 1) * 0.23
        offset_y = ((index // 3) % 2) * 0.20 - 0.10
        position = (x + offset, y + offset_y, SURFACE_Z[station])
        station_for_glyph = station
    prefix = str(container_id).split(":", 1)[0]
    material = material_for_container(container_id)
    is_plate = container.get("kind") == "read_plate" or str(container_id).endswith(":P01")
    is_error = error_stock == container_id
    if is_plate:
        bpy.ops.mesh.primitive_cube_add(size=1, location=position)
        obj = bpy.context.object
        obj.name = f"v3 plate glyph {container_id}"
        obj.dimensions = (0.38, 0.28, 0.035)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.data.materials.append(material)
        # Plate edges remain native-looking; assay/error outlines are added by
        # the vector figure layer using the recorded projection coordinate.
        overlay.append(obj)
    else:
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.095, depth=0.25, location=(position[0], position[1], position[2] + 0.125))
        obj = bpy.context.object
        obj.name = f"v3 tube glyph {container_id}"
        obj.data.materials.append(material)
        overlay.append(obj)
        # A cap/halo keeps stock tubes visible without claiming physical tube
        # dimensions; exact glyph exaggeration is recorded in the manifest.
        bpy.ops.mesh.primitive_torus_add(major_radius=0.11, minor_radius=0.018, major_segments=32, location=(position[0], position[1], position[2] + 0.255))
        cap = bpy.context.object
        cap.name = f"v3 tube cap {container_id}"
        cap.data.materials.append(material)
        overlay.append(cap)
    record = {
        "container_id": container_id,
        "experiment": prefix,
        "assay": ASSAY_NAMES.get(prefix, "unknown"),
        "recorded_location": location,
        "resolved_station": station_for_glyph,
        "world_position_m": [round(float(v), 6) for v in position],
        "glyph_geometry": "plate 0.38 x 0.28 m; tube radius 0.095 m, height 0.25 m; visual glyphs exaggerated",
        "state_annotation": "custody mismatch" if is_error else None,
    }
    if station_for_glyph == "transit":
        record["transfer_source"] = src
        record["transfer_destination"] = dst
    p = world_to_camera_view(bpy.context.scene, bpy.context.scene.camera, Vector(position))
    record["projection_normalized_xy"] = [round(float(p.x), 6), round(float(1.0 - p.y), 6)]
    return record


def add_active_halos(state, overlay):
    # Active resources are retained in the provenance records and are marked
    # by the vector figure assembly layer.  Rendering coloured torus/point
    # lights into the native scene obscures the asset geometry and produces
    # floor rings that can be mistaken for physical evidence.
    return None


def render_one(scene, filename, width, height):
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.filepath = str(TRANSPARENT / f"{filename}.png")
    bpy.ops.render.render(write_still=True)
    return {
        "image": f"transparent/{filename}.png",
        "width_px": width,
        "height_px": height,
        "engine": scene.render.engine,
        "samples": getattr(scene.cycles, "samples", None) if scene.render.engine == "CYCLES" else None,
        "film_transparent": True,
    }


def layout_manifest():
    return {
        "layout_id": "compact-v3-unified-scene",
        "station_xy_m": {k: list(v) for k, v in STATIONS.items()},
        "counter_top_z_m": 0.9,
        "counter_segments": [
            {"id": "u-left-run", "center_m": [0.0, 1.5], "width_m": 1.7, "depth_m": 3.6},
            {"id": "u-back-left", "center_m": [1.4, 3.0], "width_m": 1.2, "depth_m": 1.3},
            {"id": "u-back-right", "center_m": [4.9, 3.0], "width_m": 1.8, "depth_m": 1.3},
            {"id": "u-back-bridge", "center_m": [3.0, 3.65], "width_m": 4.0, "depth_m": 0.35},
            {"id": "u-right-run", "center_m": [5.0, 1.5], "width_m": 1.6, "depth_m": 3.6},
        ],
        "surface_z_m": SURFACE_Z,
        "geometry_policy": "source GLBs imported at native metres; rigid translation/yaw only; Fluent cabinets floor-standing; iD5 and KS4000 placed on 0.9-m counters",
        "not_a_surveyed_floorplan": True,
    }


def build_scene():
    scene, camera = setup_scene()
    mats = {
        "counter": mat("v3 counter white", (0.80, 0.83, 0.85, 1.0), roughness=0.70),
        "front": mat("v3 counter front", (0.60, 0.64, 0.68, 1.0), roughness=0.72),
        "ice": mat("v3 manual ice tray", (0.39, 0.72, 0.86, 1.0), roughness=0.25),
    }
    # The exact compact XY anchors are shared by the scheduler and all v3
    # rehearsal renders.  The equipment sits in one open U-shaped counter
    # system: the left and right runs join the back run, while a rear bridge
    # passes behind the floor-standing Fluent 780.  The top is thin and the
    # supports remain open, so the scene reads as one work island rather than
    # three independent solid blocks.
    top_z = 0.84  # 0.12-m top slab, giving a 0.90-m work surface
    top_thickness = 0.12
    top_segments = [
        ("v3 u-counter left run", (0.0, 1.5, top_z), (1.7, 3.6, top_thickness)),
        ("v3 u-counter back left", (1.4, 3.0, top_z), (1.2, 1.3, top_thickness)),
        ("v3 u-counter back right", (4.9, 3.0, top_z), (1.8, 1.3, top_thickness)),
        ("v3 u-counter rear bridge", (3.0, 3.65, top_z), (4.0, 0.35, top_thickness)),
        ("v3 u-counter right run", (5.0, 1.5, top_z), (1.6, 3.6, top_thickness)),
    ]
    for name, location, dimensions in top_segments:
        add_box(name, location, dimensions, mats["counter"], bevel=0.035)

    support_positions = [
        (-0.72, -0.12), (-0.72, 3.12), (0.72, -0.12), (0.72, 3.12),
        (4.28, -0.12), (5.72, -0.12), (4.28, 3.12), (5.72, 3.12),
    ]
    for idx, (x, y) in enumerate(support_positions, 1):
        add_box(f"v3 u-counter support {idx:02d}", (x, y, 0.43), (0.12, 0.12, 0.74), mats["front"], bevel=0.012)
    # Low front fascias make the shared counter legible in the perspective
    # view without closing the open centre of the U.
    add_box("v3 u-counter left fascia", (0.0, -0.28, 0.62), (1.7, 0.07, 0.42), mats["front"], bevel=0.012)
    add_box("v3 u-counter right fascia", (5.0, -0.28, 0.62), (1.6, 0.07, 0.42), mats["front"], bevel=0.012)

    anchors = {}
    groups = {}
    placements = {
        "fluent1080": ("device:19", (3.0, 0.0, 0.0), 0.0),
        "tecan-fluent780": ("device:18", (3.0, 3.0, 0.0), 0.0),
        "spectramax-id5": ("device:67", (0.0, 3.0, 0.9), 0.0),
        "ika_ks4000": ("demo:ks4000:1", (5.0, 3.0, 0.9), 0.0),
        "manual-pipette": ("bench", (-0.36, -0.14, 0.9), -0.35),
        "nih-3dpx-023347": ("bench", (0.30, 0.16, 0.9), 0.0),
        "tiprack-96": ("bench", (0.64, -0.18, 0.9), 0.0),
    }
    sources = []
    for asset_id, (station, position, yaw) in placements.items():
        anchor, objects, dimensions = load_asset(asset_id, position, yaw)
        anchors[station] = anchor if station in ASSET_FOR_STATION else anchors.get(station)
        groups[asset_id] = (anchor, objects, dimensions)
        entry = lib[asset_id]
        source_path = ASSETS / entry["normalized_glb"]
        contract_path = ASSETS / entry.get("source_contract", "")
        sources.append(
            {
                "asset_id": asset_id,
                "station": station,
                "normalized_glb": entry["normalized_glb"],
                "glb_sha256": sha256(source_path),
                "contract": entry.get("source_contract"),
                "contract_sha256": sha256(contract_path) if contract_path.exists() else None,
                "license": entry.get("license"),
                "source": entry.get("source"),
                "native_dimensions_m": [round(float(v), 6) for v in dimensions],
                "placement_m": list(position),
                "yaw_rad": yaw,
            }
        )

    # A simple authored ice tray is included only as a manual-bench prop.  It
    # is not counted as a facility asset and is explicitly separated in the
    # provenance manifest.
    ice = add_box("v3 authored manual ice tray", (-0.10, 0.28, 0.955), (0.60, 0.36, 0.11), mats["ice"], bevel=0.05)
    groups["authored-manual-ice-tray"] = (ice, [ice], Vector((0.60, 0.36, 0.11)))

    # Place the camera before glyph projections are computed.
    aim(camera, (2.55, 1.85, 0.92), 8.5)
    scene = bpy.context.scene
    return scene, camera, groups, sources


def read_state_inputs():
    example_path = PAPER / "source-data/v2/example.json"
    material_path = PAPER / "source-data/v2/material-example.json"
    example = json.loads(example_path.read_text())
    material = json.loads(material_path.read_text())
    return example, material, {
        "example": {"path": "source-data/v2/example.json", "sha256": sha256(example_path)},
        "material_example": {"path": "source-data/v2/material-example.json", "sha256": sha256(material_path)},
        "catalog": {"path": "source-data/v2/catalog.json", "sha256": sha256(PAPER / "source-data/v2/catalog.json")},
        "asset_library": {"path": "exports/biofoundry/asset-library.json", "sha256": sha256(ASSETS / "asset-library.json")},
    }


def render_states(scene, camera, example, material, width, height):
    overlay = []
    images = []
    frame_records = []
    base_target = (2.55, 1.85, 0.92)
    base_scale = 8.5
    frames = example["frames"]
    if opts.mode in {"preview", "rehearsal", "all"}:
        for idx, frame in enumerate(frames, 1):
            clear_overlay(overlay)
            state = frame["state"]
            # Projections in the provenance manifest correspond to the same
            # fixed full-scene camera used by the authoritative frame render,
            # rather than the preceding frame's inset camera.
            aim(camera, base_target, base_scale)
            add_active_halos(state, overlay)
            selected = selected_container_ids(state, frame["task"])
            glyph_records = []
            for j, cid in enumerate(selected):
                if cid in state.get("containers", {}):
                    record = add_carrier_glyph(cid, state["containers"][cid], state, j, overlay)
                    if record:
                        glyph_records.append(record)
            transfer, source, destination = transfer_midpoint(state)
            if transfer and source and destination:
                path_mat = mat("v3 transfer path", (0.18, 0.18, 0.22, 1.0), roughness=0.30)
                a = (STATIONS[source][0], STATIONS[source][1], SURFACE_Z.get(source, 0.93) + 0.12)
                b = (STATIONS[destination][0], STATIONS[destination][1], SURFACE_Z.get(destination, 0.93) + 0.12)
                shaft = add_cylinder_between("v3 active transfer path", a, b, 0.018, path_mat)
                overlay.append(shaft)
            aim(camera, base_target, base_scale)
            images.append({"frame": idx, "task": frame["task"], "time_s": frame["time_s"], **render_one(scene, f"rehearsal-{idx}", width, height)})
            # A close-up uses one fixed angle per frame and is designed for an
            # inset panel; the full-scene render remains the authoritative view.
            active_station = next((r.get("resource") for r in active_rows(state) if r.get("resource") in STATIONS), None)
            if active_station:
                target = (*STATIONS[active_station], SURFACE_Z.get(active_station, 0.93) + 0.25)
            elif transfer:
                target = transfer
            else:
                target = base_target
            aim(camera, target, 3.0, (1.0, -1.35, 0.95))
            images.append({"frame": idx, "task": frame["task"], "time_s": frame["time_s"], "inset": True, **render_one(scene, f"rehearsal-{idx}-closeup", max(900, width // 2), max(600, height // 2))})
            frame_records.append({"frame": idx, "task": frame["task"], "time_s": frame["time_s"], "selected_containers": selected, "glyphs": glyph_records, "active_resources": sorted({r.get("resource") for r in active_rows(state) if r.get("resource")}), "transfer": {"source": source, "destination": destination} if source else None})

    if opts.mode in {"preview", "water", "all"}:
        for label, state_key in [("injected", "injected"), ("correct", "correct")]:
            clear_overlay(overlay)
            state = material[state_key]
            aim(camera, (1.55, 0.42, 0.95), 4.5, (1.05, -1.55, 1.0))
            # Keep the mismatch tube visible even though the state may not be
            # part of the active operation list; this is the controlled custody
            # contrast used by Fig. 6.
            add_active_halos(state, overlay)
            selected = [material["stock"]]
            for j, cid in enumerate(selected):
                if cid in state.get("containers", {}):
                    record = add_carrier_glyph(cid, state["containers"][cid], state, j, overlay, error_stock=material["stock"] if label == "injected" else None)
                    if record:
                        frame_records.append({"water_case": label, "stock": material["stock"], "glyph": record})
            aim(camera, (1.55, 0.42, 0.95), 4.5, (1.05, -1.55, 1.0))
            images.append({"water_case": label, "time_s": material["time_s"], **render_one(scene, f"water-{label}", width, height)})
            aim(camera, (1.55, 0.42, 0.95), 2.25, (1.05, -1.55, 1.0))
            images.append({"water_case": label, "time_s": material["time_s"], "inset": True, **render_one(scene, f"water-{label}-closeup", max(900, width // 2), max(600, height // 2))})
    clear_overlay(overlay)
    aim(camera, base_target, base_scale)
    return images, frame_records


def main():
    scene, camera, groups, sources = build_scene()
    example, material, input_records = read_state_inputs()
    width = opts.width
    height = opts.height
    if opts.mode == "rehearsal":
        width, height = max(width, 2400), max(height, 1500)
    images, state_records = render_states(scene, camera, example, material, width, height)
    layout = layout_manifest()
    layout_path = OUT / "unified-layout.json"
    layout_path.write_text(json.dumps(layout, indent=2) + "\n")
    manifest = {
        "schema": "biorehearse.v3.render-provenance/1",
        "renderer": "Blender " + bpy.app.version_string,
        "engine": scene.render.engine,
        "samples": getattr(scene.cycles, "samples", None) if scene.render.engine == "CYCLES" else None,
        "color_management": {"view_transform": scene.view_settings.view_transform, "look": scene.view_settings.look, "exposure": scene.view_settings.exposure},
        "transparent_film": True,
        "shadow_catcher": opts.engine == "cycles",
        "sources": sources,
        "inputs": input_records,
        "layout": layout,
        "layout_sha256": sha256(layout_path),
        "images": images,
        "state_records": state_records,
        "camera": {"type": camera.data.type, "final_target_m": [2.55, 1.85, 0.92], "final_ortho_scale_m": 8.5, "projection": "orthographic"},
        "scope": {"scene": "native digital asset rehearsal; no hardware connection", "geometry": "source GLBs rigidly translated/yawed; no source rescaling", "glyphs": "visual carriers enlarged for readability; not dimensional measurements", "layout": "shared compact scheduler anchors; illustrative U/L counter, not a surveyed facility floorplan"},
        "state_parser": {"staging_prefix": "removed before station matching", "transit": "represented at source/destination midpoint with transfer path", "missing_station": "not rendered as a carrier"},
    }
    (OUT / "unified-scene-provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "unified-scene.blend"))


if __name__ == "__main__":
    main()
