"""Build the airframe in Blender, at full scale, from `airframe_spec.py`.

    # headless -- writes four PNG views and a .blend
    blender -b -P mechanical/blender_airframe.py -- --out runs/airframe

    # or paste into Blender's Text Editor and press Run Script

WHY GENERATE IT RATHER THAN MODEL IT
------------------------------------
The point of this model is to answer mechanical questions that have numeric
answers: does a leg appear in the corner of the frame, do the propeller discs
clear each other, where does the camera actually look. A hand-modelled drone
looks the part and answers none of them, because nothing connects the shape to
the constraint. Here every dimension comes from `airframe_spec.py`, so changing
the wheelbase moves the motors, re-checks the tip gap, and redraws the view
pyramid together.

The view pyramid is the object worth having. It is the real
`IMX708 / Camera Module 3` field of view, drawn as geometry, so "is this in
frame" stops being a judgement call and becomes something you look at.

WHAT IT DOES NOT TOUCH
----------------------
Everything is created inside a collection named `AgriEdge_Airframe`, and only
that collection is cleared on a re-run. Nothing else in an open scene is
modified. Re-running it is safe.
"""

from __future__ import annotations

import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import airframe_spec as spec  # noqa: E402

COLLECTION = "AgriEdge_Airframe"

# Colour is load-bearing here: each subsystem reads as one thing, and the
# pyramid has to be visible through the aircraft, so it is transparent.
PALETTE = {
    "frame":    (0.09, 0.09, 0.11, 1.0),
    "arm":      (0.14, 0.14, 0.17, 1.0),
    "motor":    (0.72, 0.45, 0.13, 1.0),
    "prop":     (0.55, 0.58, 0.63, 1.0),
    "disc":     (0.62, 0.66, 0.72, 0.10),
    "battery":  (0.16, 0.42, 0.62, 1.0),
    "payload":  (0.85, 0.85, 0.82, 1.0),
    "compute":  (0.18, 0.55, 0.36, 1.0),
    "camera":   (0.78, 0.18, 0.22, 1.0),
    "leg":      (0.30, 0.31, 0.34, 1.0),
    "fov":      (0.98, 0.66, 0.08, 0.30),
    "ground":   (0.33, 0.29, 0.22, 1.0),
    "cg":       (0.90, 0.25, 0.55, 1.0),
    "sensor":   (0.45, 0.70, 0.90, 1.0),
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def material(name: str, rgba) -> bpy.types.Material:
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = rgba
        # Roughness by eye: carbon and plastic are matte, motors are not.
        bsdf.inputs["Roughness"].default_value = 0.45
        if len(rgba) == 4 and rgba[3] < 1.0:
            bsdf.inputs["Alpha"].default_value = rgba[3]
            mat.blend_method = "BLEND"
            if hasattr(mat, "show_transparent_back"):
                mat.show_transparent_back = False
    return mat


def collection() -> bpy.types.Collection:
    col = bpy.data.collections.get(COLLECTION)
    if col is None:
        col = bpy.data.collections.new(COLLECTION)
        bpy.context.scene.collection.children.link(col)
    else:
        # Only ours. An open scene keeps everything else it had.
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
    return col


def place(obj, name, mat_key, col):
    obj.name = name
    obj.data.name = name
    obj.data.materials.clear()
    obj.data.materials.append(material(mat_key, PALETTE[mat_key]))
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)
    return obj


def box(col, name, mat_key, size, loc, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    obj = bpy.context.active_object
    obj.scale = Vector(size)
    return place(obj, name, mat_key, col)


def cyl(col, name, mat_key, radius, depth, loc, rot=(0, 0, 0), verts=32):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts, radius=radius, depth=depth, location=loc, rotation=rot
    )
    return place(bpy.context.active_object, name, mat_key, col)


# ---------------------------------------------------------------------------
# the aircraft
# ---------------------------------------------------------------------------


def build(af: spec.Airframe, mass: spec.MassBudget) -> dict:
    col = collection()
    r = af.rotors
    plate_t = 0.003
    top_z = 0.0
    bot_z = -af.plate_gap_m

    # --- body: two plates with a gap, the usual sandwich -------------------
    box(col, "Plate.Top", "frame",
        (af.body_length_m, af.body_width_m, plate_t), (0, 0, top_z))
    box(col, "Plate.Bottom", "frame",
        (af.body_length_m, af.body_width_m, plate_t), (0, 0, bot_z))
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl(col, f"Standoff.{sx}{sy}", "frame", 0.005, af.plate_gap_m,
                (sx * af.body_length_m * 0.36, sy * af.body_width_m * 0.36,
                 (top_z + bot_z) / 2))

    # --- arms and motors ---------------------------------------------------
    motors = spec.motor_positions(af)
    for i, (mx, my, _) in enumerate(motors, start=1):
        ang = math.atan2(my, mx)
        length = r.arm_radius_m
        cyl(col, f"Arm.{i}", "arm", af.arm_diameter_m / 2, length,
            (mx / 2, my / 2, bot_z + af.plate_gap_m / 2),
            rot=(0, math.pi / 2, ang))
        cyl(col, f"Motor.{i}", "motor", 0.021, af.motor_height_m,
            (mx, my, top_z + af.motor_height_m / 2))
        # Blades, drawn thin and flat -- shape is irrelevant, the swept disc
        # is what the clearance question is about.
        for b in range(r.blades):
            blade_ang = ang + b * math.pi
            box(col, f"Blade.{i}.{b}", "prop",
                (r.prop_diameter_m / 2, 0.026, 0.004),
                (mx + math.cos(blade_ang) * r.prop_diameter_m / 4,
                 my + math.sin(blade_ang) * r.prop_diameter_m / 4,
                 top_z + af.motor_height_m + 0.006),
                rot=(0, 0, blade_ang))
        # The swept disc. This is the object that answers "do they overlap".
        cyl(col, f"Disc.{i}", "disc", r.prop_diameter_m / 2, 0.001,
            (mx, my, top_z + af.motor_height_m + 0.006), verts=64)

    # --- energy ------------------------------------------------------------
    box(col, "Battery.6S10Ah", "battery", (0.165, 0.075, 0.060),
        (0.0, 0.0, top_z + 0.033))

    # --- compute payload, on isolators, under the body ---------------------
    pz = bot_z - af.payload_drop_m
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl(col, f"Isolator.{sx}{sy}", "camera", 0.008, af.payload_drop_m,
                (sx * 0.062, sy * 0.055, bot_z - af.payload_drop_m / 2), verts=16)
    box(col, "Enclosure", "payload", (0.155, 0.130, 0.055), (0, 0, pz - 0.0275))
    box(col, "Pi5+HailoHAT", "compute", (0.085, 0.056, 0.030), (0, 0, pz - 0.022))
    box(col, "Regulator.5V6A", "compute", (0.050, 0.030, 0.015), (-0.052, 0.0, pz - 0.018))

    # --- the camera, and what it can see -----------------------------------
    lens_z = pz - af.lens_drop_from_payload_m
    cyl(col, "Camera.IMX708", "camera", 0.013, af.lens_drop_from_payload_m,
        (0, 0, pz - af.lens_drop_from_payload_m / 2), verts=24)
    cyl(col, "Rangefinder", "sensor", 0.010, 0.022, (0.055, 0.0, pz - 0.011), verts=16)
    build_fov(col, af, lens_z)

    # --- landing gear, on the azimuth the camera cares about ---------------
    for i, (lx, ly, lz) in enumerate(spec.leg_positions(af), start=1):
        top = Vector((lx * 0.30, ly * 0.30, bot_z))
        foot = Vector((lx, ly, lz))
        mid = (top + foot) / 2
        d = foot - top
        cyl(col, f"Leg.{i}", "leg", 0.009, d.length, mid,
            rot=(0, math.acos(d.z / d.length), math.atan2(d.y, d.x)), verts=12)
        cyl(col, f"Foot.{i}", "leg", 0.018, 0.010, (lx, ly, lz - 0.005), verts=16)

    # --- the environment sensor: out in clean air, brief item 07 -----------
    boom_r, boom_z = 0.190, top_z + 0.075
    cyl(col, "Boom.Environment", "sensor", 0.005, boom_r,
        (-boom_r / 2, 0.0, boom_z), rot=(0, math.pi / 2, math.pi))
    cyl(col, "RadiationShield", "sensor", 0.024, 0.030, (-boom_r, 0.0, boom_z), verts=20)

    # --- centre of gravity, marked ----------------------------------------
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.016, location=(0, 0, bot_z + 0.010))
    place(bpy.context.active_object, "CG.target", "cg", col)

    return {"collection": col, "lens_z": lens_z}


def build_fov(col, af: spec.Airframe, lens_z: float, to_z: float | None = None):
    """The viewing pyramid as real geometry, from the lens down to the ground.

    Drawn as a rectangle, not a cone, and oriented to the image axes -- which is
    the whole reason `leg_azimuth_deg` exists. The short axis of the sensor is
    rotated onto the legs, so the pyramid is at its narrowest exactly where the
    aircraft has something sticking down.
    """
    fov = spec.field_of_view()
    to_z = to_z if to_z is not None else -af.leg_height_m - af.plate_gap_m - 0.040
    depth = lens_z - to_z
    a = depth * math.tan(math.radians(fov.half_width_deg))
    b = depth * math.tan(math.radians(fov.half_height_deg))
    # Image long axis perpendicular to the legs.
    yaw = math.radians(af.leg_azimuth_deg + 90.0)

    verts = [(0.0, 0.0, lens_z)]
    for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
        x, y = sx * a, sy * b
        verts.append((x * math.cos(yaw) - y * math.sin(yaw),
                      x * math.sin(yaw) + y * math.cos(yaw), to_z))
    faces = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1), (1, 2, 3, 4)]
    mesh = bpy.data.meshes.new("FOV.pyramid")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("FOV.pyramid", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return place(obj, "FOV.pyramid", "fov", col)


# ---------------------------------------------------------------------------
# presentation
# ---------------------------------------------------------------------------


def stage(af: spec.Airframe):
    """Ground, light and render settings. Only touched in headless runs."""
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "METERS"
    col = bpy.data.collections[COLLECTION]

    ground_z = -af.leg_height_m - af.plate_gap_m - 0.010
    bpy.ops.mesh.primitive_plane_add(size=12.0, location=(0, 0, ground_z))
    place(bpy.context.active_object, "Ground", "ground", col)

    bpy.ops.object.light_add(type="SUN", location=(2.5, -3.0, 4.0))
    sun = bpy.context.active_object
    sun.data.energy = 4.0
    sun.data.angle = math.radians(2.0)
    sun.rotation_euler = (math.radians(48), 0, math.radians(35))
    for c in list(sun.users_collection):
        c.objects.unlink(sun)
    col.objects.link(sun)

    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [
        e.identifier for e in
        bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
    ] else "BLENDER_EEVEE"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1100
    scene.render.film_transparent = False
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.82, 0.84, 0.87, 1.0)
        bg.inputs[1].default_value = 1.0


# Direction the camera sits in, its rotation, and whether the view is
# orthographic. The three square-on views are ortho deliberately: a drawing that
# a part gets measured off must not have perspective in it.
#
# The rotations are written out rather than aimed with a Track To constraint or
# `to_track_quat`. Both were tried; in background mode the constraint is not
# evaluated before `render.render` and every frame came back empty -- a failure
# that looks identical to "the model did not build".
_R90 = math.radians(90.0)
VIEWS = {
    "iso":   ((1.0, -1.0, 0.62), None, False),               # aimed, below
    "front": ((0.0, -1.0, 0.0), (_R90, 0.0, 0.0), True),     # looking +Y
    "side":  ((1.0, 0.0, 0.0), (_R90, 0.0, _R90), True),     # looking -X
    "top":   ((0.0, 0.0, 1.0), (0.0, 0.0, -_R90), True),     # looking -Z, nose up
}


def _model_extent(col) -> tuple[Vector, float, float]:
    """Centre, span and bounding radius, so framing is not hand-tuned.

    The radius matters more than the span: the views look at the model from
    several directions, and a box that is 0.84 m across is 1.26 m across its
    own diagonal. Framing on the span crops the corners off the top view.

    Excludes the ground plane, which is large and would push every view out
    until the aircraft was a speck.
    """
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    points = []
    for obj in col.objects:
        if obj.type != "MESH" or obj.name == "Ground":
            continue
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            points.append(world)
            for i in range(3):
                lo[i] = min(lo[i], world[i])
                hi[i] = max(hi[i], world[i])
    if not points:
        raise RuntimeError("Nothing was built -- no mesh to frame.")
    centre = (lo + hi) / 2.0
    radius = max((p - centre).length for p in points)
    return centre, max(hi[i] - lo[i] for i in range(3)), radius


def render_views(af: spec.Airframe, out_dir: str):
    col = bpy.data.collections[COLLECTION]
    scene = bpy.context.scene
    # Absolute, because Blender resolves a relative render path against the blend
    # file, not the working directory -- a relative path here silently lands the
    # renders at the drive root.
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    centre, span, radius = _model_extent(col)

    cam_data = bpy.data.cameras.new("RenderCam")
    cam_data.lens = 35.0
    cam = bpy.data.objects.new("RenderCam", cam_data)
    col.objects.link(cam)
    scene.camera = cam

    written = []
    for name, (direction, euler, ortho) in VIEWS.items():
        cam.location = centre + Vector(direction).normalized() * radius * 3.4
        if euler is None:
            cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
        else:
            cam.rotation_euler = euler
        cam_data.type = "ORTHO" if ortho else "PERSP"
        cam_data.ortho_scale = radius * 2.25
        bpy.context.view_layer.update()

        path = os.path.join(out_dir, f"airframe_{name}.png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        _refuse_blank(path, name)
        written.append(path)
    return written


def _refuse_blank(path: str, name: str) -> None:
    """A render with one colour in it is a failure, and it looks like a success.

    The same shape as every other guard in this project: the expensive mistake
    is not the error, it is the confident empty output that gets filed as a
    result.
    """
    img = bpy.data.images.load(path)
    try:
        distinct = len({round(v, 2) for v in img.pixels})
    finally:
        bpy.data.images.remove(img)
    if distinct <= 8:
        raise RuntimeError(
            f"View '{name}' rendered as a single flat colour -- the model was "
            "not in frame, or the renderer produced nothing. Not writing this "
            "out as if it were a drawing."
        )


def main(argv):
    out_dir = "runs/airframe"
    if "--out" in argv:
        out_dir = argv[argv.index("--out") + 1]

    headless = bpy.app.background
    if headless:
        # Blender's startup file ships a 2 m Cube at the origin, which encloses
        # a 0.8 m aircraft. From inside it the model renders; from outside, the
        # cube's inner face fills the frame with flat grey and every view comes
        # back blank -- which reads exactly like "the model failed to build" and
        # cost an hour of looking in the wrong place. An empty scene, and only
        # in background mode, so an open project is never cleared.
        bpy.ops.wm.read_factory_settings(use_empty=True)

    af = spec.Airframe()
    mass = spec.MassBudget()
    build(af, mass)

    if headless:
        stage(af)
        written = render_views(af, out_dir)
        blend = os.path.join(out_dir, "agri_edge_airframe.blend")
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(blend))
        print("\n".join(["wrote " + p for p in written + [blend]]))

    # The verdict, printed next to the model it describes.
    for label, ok, detail in af.checks(mass):
        print(f"[{'PASS' if ok else 'FAIL'}] {label:<44} {detail}")


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    main(args)
