"""Export Agri-Edge airframe meshes for mechanic handoff.

Prefer regenerating from airframe_spec via blender_airframe.py (keeps STLs
aligned with the numeric source of truth). Falls back to an existing .blend
if --blend is given and --no-regen is set.

Usage (headless):
  blender -b -P mechanical/handoff/scripts/export_airframe.py -- \\
      --out mechanical/handoff/exports

  blender -b runs/airframe/agri_edge_airframe.blend \\
      -P mechanical/handoff/scripts/export_airframe.py -- \\
      --out mechanical/handoff/exports --no-regen
"""
from __future__ import annotations

import os
import sys

import bpy

# Resolve repo mechanical/ so airframe_spec + blender_airframe import cleanly.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_MECH_DIR = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
_REPO_ROOT = os.path.abspath(os.path.join(_MECH_DIR, ".."))
if _MECH_DIR not in sys.path:
    sys.path.insert(0, _MECH_DIR)

COLLECTION = "AgriEdge_Airframe"

# Major printable / structural groups. Keys become STL filenames.
# role: structural = build/print reference; visual = clearance / layout only.
PART_GROUPS = {
    "01_plates_structural": {
        "role": "structural",
        "match": lambda n: n.startswith("Plate.") or n.startswith("Standoff."),
        "note": "Top/bottom sandwich plates + corner standoffs",
    },
    "02_arms_structural": {
        "role": "structural",
        "match": lambda n: n.startswith("Arm."),
        "note": "Four carbon-tube arms (X layout)",
    },
    "03_landing_gear_structural": {
        "role": "structural",
        "match": lambda n: n.startswith("Leg.") or n.startswith("Foot."),
        "note": "Landing gear legs + feet — MUST stay outside camera FOV",
    },
    "04_camera_mount_structural": {
        "role": "structural",
        "match": lambda n: (
            n.startswith("Isolator.")
            or n in ("Enclosure", "Camera.IMX708")
        ),
        "note": "Vibration isolators, payload enclosure, camera body",
    },
    "05_motors_visual": {
        "role": "visual",
        "match": lambda n: n.startswith("Motor."),
        "note": "Motor envelopes for packaging — not structural FEA solids",
    },
    "06_props_visual": {
        "role": "visual",
        "match": lambda n: n.startswith("Blade.") or n.startswith("Disc."),
        "note": "Prop blades + swept discs for tip-gap / clearance ONLY",
    },
    "07_avionics_payload_visual": {
        "role": "visual",
        "match": lambda n: n in (
            "Battery.6S10Ah",
            "Pi5+HailoHAT",
            "Regulator.5V6A",
            "Rangefinder",
            "Boom.Environment",
            "RadiationShield",
            "CG.target",
        ),
        "note": "Battery, Pi/Hailo, regulator, rangefinder, env boom — layout",
    },
}

# Exclude from mesh exports (guidance geometry / scene).
SKIP_NAMES = {"FOV.pyramid", "Ground", "RenderCam", "Sun", "Light"}


def _parse_argv(argv: list[str]) -> dict:
    out = {
        "out": os.path.join(_REPO_ROOT, "mechanical", "handoff", "exports"),
        "no_regen": False,
        "blend": None,
        "also_render": False,
    }
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--out" and i + 1 < len(argv):
            out["out"] = argv[i + 1]
            i += 2
        elif a == "--blend" and i + 1 < len(argv):
            out["blend"] = argv[i + 1]
            i += 2
        elif a == "--no-regen":
            out["no_regen"] = True
            i += 1
        elif a == "--also-render":
            out["also_render"] = True
            i += 1
        else:
            i += 1
    return out


def _ensure_collection() -> bpy.types.Collection:
    col = bpy.data.collections.get(COLLECTION)
    if col is None:
        raise RuntimeError(
            f"Collection '{COLLECTION}' not found. Regenerate with "
            "blender_airframe.py or open agri_edge_airframe.blend."
        )
    return col


def _mesh_objects(col: bpy.types.Collection) -> list[bpy.types.Object]:
    objs = []
    for obj in col.objects:
        if obj.type != "MESH":
            continue
        if obj.name in SKIP_NAMES or obj.name.startswith("RenderCam"):
            continue
        objs.append(obj)
    return objs


def _apply_transforms(obj: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    # Apply scale/rotation so STL dimensions match metres in Blender (1 BU = 1 m).
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def _duplicate_joined(objs: list[bpy.types.Object], name: str) -> bpy.types.Object | None:
    if not objs:
        return None
    bpy.ops.object.select_all(action="DESELECT")
    copies = []
    for src in objs:
        dup = src.copy()
        dup.data = src.data.copy()
        bpy.context.scene.collection.objects.link(dup)
        copies.append(dup)
        dup.select_set(True)
    bpy.context.view_layer.objects.active = copies[0]
    if len(copies) > 1:
        bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = name
    _apply_transforms(joined)
    return joined


def _export_stl(obj: bpy.types.Object, path: str) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    path = os.path.abspath(path)
    # Blender 4.x uses export_mesh.stl; older used export_scene.stl.
    if hasattr(bpy.ops.wm, "stl_export"):
        bpy.ops.wm.stl_export(
            filepath=path,
            export_selected_objects=True,
            ascii_format=False,
            apply_modifiers=True,
        )
    elif hasattr(bpy.ops.export_mesh, "stl"):
        bpy.ops.export_mesh.stl(
            filepath=path,
            use_selection=True,
            ascii=False,
            use_mesh_modifiers=True,
        )
    else:
        raise RuntimeError("No STL export operator found in this Blender build")


def _export_glb(objs: list[bpy.types.Object], path: str) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    if not objs:
        return
    bpy.context.view_layer.objects.active = objs[0]
    path = os.path.abspath(path)
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
    )


def _write_manifest(out_dir: str, rows: list[dict]) -> str:
    path = os.path.join(out_dir, "EXPORT_MANIFEST.txt")
    lines = [
        "Agri-Edge airframe mesh export",
        "Units: metres in Blender / STL (scale 1.0 = 1 m). Convert to mm in slicer if needed.",
        "structural = intended build geometry reference",
        "visual = packaging / clearance ONLY — do not treat as structural solids",
        "",
        f"{'file':<45} {'role':<12} {'bytes':>10}  note",
        "-" * 100,
    ]
    for r in rows:
        lines.append(
            f"{r['file']:<45} {r['role']:<12} {r['bytes']:>10}  {r['note']}"
        )
    path = os.path.abspath(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def regenerate() -> None:
    import blender_airframe as gen
    import airframe_spec as spec

    if bpy.app.background:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    af = spec.Airframe()
    mass = spec.MassBudget()
    gen.build(af, mass)
    # Do not stage ground/sun for mesh export — keeps STLs clean.
    print("Regenerated AgriEdge_Airframe from airframe_spec")


def main(argv: list[str]) -> None:
    opts = _parse_argv(argv)
    out_dir = os.path.abspath(opts["out"])
    os.makedirs(out_dir, exist_ok=True)

    if opts["no_regen"]:
        if opts["blend"]:
            bpy.ops.wm.open_mainfile(filepath=os.path.abspath(opts["blend"]))
        # else: assume blend already loaded via blender -b file.blend
    else:
        regenerate()

    col = _ensure_collection()
    meshes = _mesh_objects(col)
    if not meshes:
        raise RuntimeError("No mesh objects to export")

    # Apply transforms on originals so individual and combined match.
    for obj in meshes:
        _apply_transforms(obj)

    rows: list[dict] = []
    written: list[str] = []

    # Per-group STLs
    for key, meta in PART_GROUPS.items():
        group_objs = [o for o in meshes if meta["match"](o.name)]
        if not group_objs:
            print(f"SKIP {key}: no matching objects")
            continue
        joined = _duplicate_joined(group_objs, f"Export.{key}")
        if joined is None:
            continue
        fname = f"{key}.stl"
        path = os.path.join(out_dir, fname)
        _export_stl(joined, path)
        size = os.path.getsize(path)
        rows.append(
            {
                "file": fname,
                "role": meta["role"],
                "bytes": size,
                "note": meta["note"],
            }
        )
        written.append(path)
        # Clean temp join
        bpy.data.objects.remove(joined, do_unlink=True)

    # Combined structural-only STL
    structural_objs = []
    for _key, meta in PART_GROUPS.items():
        if meta["role"] != "structural":
            continue
        structural_objs.extend([o for o in meshes if meta["match"](o.name)])
    if structural_objs:
        joined = _duplicate_joined(structural_objs, "Export.combined_structural")
        fname = "00_combined_structural.stl"
        path = os.path.join(out_dir, fname)
        _export_stl(joined, path)
        rows.insert(
            0,
            {
                "file": fname,
                "role": "structural",
                "bytes": os.path.getsize(path),
                "note": "All structural groups joined (plates, arms, gear, mount)",
            },
        )
        written.append(path)
        bpy.data.objects.remove(joined, do_unlink=True)

    # Combined everything (minus FOV/ground) for overview
    joined = _duplicate_joined(meshes, "Export.combined_all")
    fname = "00_combined_all_reference.stl"
    path = os.path.join(out_dir, fname)
    _export_stl(joined, path)
    rows.insert(
        1 if rows and rows[0]["file"].startswith("00_combined_structural") else 0,
        {
            "file": fname,
            "role": "mixed",
            "bytes": os.path.getsize(path),
            "note": "Full airframe reference including visual props/avionics",
        },
    )
    written.append(path)
    bpy.data.objects.remove(joined, do_unlink=True)

    # GLB for web viewing
    glb_name = "agri_edge_airframe.glb"
    glb_path = os.path.join(out_dir, glb_name)
    _export_glb(meshes, glb_path)
    rows.append(
        {
            "file": glb_name,
            "role": "web",
            "bytes": os.path.getsize(glb_path),
            "note": "glTF binary for browser / CAD viewers",
        }
    )
    written.append(glb_path)

    # Save a blend next to exports for the mechanic who has Blender
    blend_path = os.path.join(out_dir, "agri_edge_airframe.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    rows.append(
        {
            "file": "agri_edge_airframe.blend",
            "role": "source",
            "bytes": os.path.getsize(blend_path),
            "note": "Blender source regenerated from airframe_spec",
        }
    )
    written.append(blend_path)

    man = _write_manifest(out_dir, rows)
    written.append(man)

    print("EXPORT OK")
    for p in written:
        print(f"wrote {p} ({os.path.getsize(p)} bytes)")


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    main(args)
