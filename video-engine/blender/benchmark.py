"""Banc d'essai de rendu : scène représentative d'une vidéo éducative 3D (personnage stylisé, décor, 2 lumières).

Usage (lancé par le backend) : blender -b -Y --factory-startup --python benchmark.py -- '{"out": "...", "engines": [...]}'
"""
import math
import os
import sys
import time

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import args, emit, engine_ids  # noqa: E402

A = args()
OUT = A.get("out", "/tmp/profia_bench")
os.makedirs(OUT, exist_ok=True)


def mat(name, rgb, rough=0.6):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    return m


def add(obj_op, name, material, **kw):
    obj_op(**kw)
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return o


bpy.ops.wm.read_factory_settings(use_empty=True)
skin, shirt, pants, eye, floor_m, wall_m = (mat("peau", (0.95, 0.75, 0.6)), mat("tshirt", (0.35, 0.3, 0.9)),
                                             mat("pantalon", (0.15, 0.17, 0.25)), mat("oeil", (0.05, 0.05, 0.05), 0.2),
                                             mat("sol", (0.85, 0.8, 0.7)), mat("mur", (0.55, 0.75, 0.9)))
# personnage stylisé (~ budget d'un personnage « low poly » : quelques dizaines de milliers de triangles)
add(bpy.ops.mesh.primitive_uv_sphere_add, "tete", skin, radius=0.32, location=(0, 0, 1.62), segments=64, ring_count=32)
add(bpy.ops.mesh.primitive_uv_sphere_add, "oeil_g", eye, radius=0.045, location=(-0.11, -0.28, 1.68))
add(bpy.ops.mesh.primitive_uv_sphere_add, "oeil_d", eye, radius=0.045, location=(0.11, -0.28, 1.68))
add(bpy.ops.mesh.primitive_cylinder_add, "corps", shirt, radius=0.28, depth=0.7, location=(0, 0, 1.05), vertices=64)
for side in (-1, 1):
    add(bpy.ops.mesh.primitive_cylinder_add, f"bras{side}", shirt, radius=0.07, depth=0.65, location=(side * 0.38, 0, 1.05),
        rotation=(0, side * 0.25, 0), vertices=32)
    add(bpy.ops.mesh.primitive_cylinder_add, f"jambe{side}", pants, radius=0.09, depth=0.75, location=(side * 0.13, 0, 0.37), vertices=32)
for o in list(bpy.data.objects):
    mod = o.modifiers.new("lisse", "SUBSURF")
    mod.levels = mod.render_levels = 1
# décor : sol, mur, tableau, bureau
add(bpy.ops.mesh.primitive_plane_add, "sol", floor_m, size=12)
add(bpy.ops.mesh.primitive_plane_add, "mur", wall_m, size=12, location=(0, 2.5, 3), rotation=(math.pi / 2, 0, 0))
add(bpy.ops.mesh.primitive_cube_add, "tableau", mat("tableau", (0.1, 0.3, 0.2)), size=1, location=(0, 2.45, 2.0), scale=(1.6, 0.03, 0.9))
add(bpy.ops.mesh.primitive_cube_add, "bureau", mat("bois", (0.5, 0.33, 0.2)), size=1, location=(1.3, 0.4, 0.4), scale=(0.9, 0.5, 0.4))
# lumières et caméra (plan moyen vertical)
bpy.ops.object.light_add(type="AREA", location=(-2, -3, 4))
bpy.context.active_object.data.energy = 600
bpy.context.active_object.data.size = 3
bpy.ops.object.light_add(type="SUN", location=(3, -2, 5))
bpy.context.active_object.data.energy = 2.5
bpy.ops.object.camera_add(location=(0, -4.2, 1.45), rotation=(math.radians(88), 0, 0))
cam = bpy.context.active_object
cam.data.lens = 35
scene = bpy.context.scene
scene.camera = cam
world = bpy.data.worlds.new("monde")
world.color = (0.7, 0.8, 0.95)
scene.world = world
# petite animation de tête (pour que les images diffèrent)
head = bpy.data.objects["tete"]
head.rotation_euler = (0, 0, -0.3)
head.keyframe_insert("rotation_euler", frame=1)
head.rotation_euler = (0, 0, 0.3)
head.keyframe_insert("rotation_euler", frame=48)

tris = sum(len(o.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh().loop_triangles) for o in scene.objects if o.type == "MESH")
gpu_info = None
try:
    import gpu
    gpu_info = {"vendor": gpu.platform.vendor_get(), "renderer": gpu.platform.renderer_get(), "version": gpu.platform.version_get()}
except Exception as e:  # noqa: BLE001
    gpu_info = {"error": str(e)}
emit("info", blender=bpy.app.version_string, triangles=tris, gpu=gpu_info, threads=os.cpu_count())

ids = engine_ids()
for spec in A.get("runs", []):
    engine, w, h, frames = spec["engine"], spec["width"], spec["height"], spec.get("frames", 3)
    scene.render.engine = ids[engine]
    scene.render.resolution_x, scene.render.resolution_y = w, h
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    if engine == "cycles":
        scene.cycles.device = "CPU"
        scene.cycles.samples = spec.get("samples", 16)
        scene.cycles.use_denoising = True
    elif engine == "eevee":
        try:
            scene.eevee.taa_render_samples = spec.get("samples", 16)
        except AttributeError:
            pass
    times = []
    try:
        for f in range(1, frames + 1):
            scene.frame_set(1 + (f - 1) * 15)
            scene.render.filepath = os.path.join(OUT, f"{engine}_{w}x{h}_{f}.png")
            t = time.time()
            bpy.ops.render.render(write_still=True)
            times.append(time.time() - t)
        emit("result", engine=engine, width=w, height=h, times=[round(x, 3) for x in times],
             first=round(times[0], 2), steady=round(sum(times[1:]) / max(1, len(times) - 1), 2) if len(times) > 1 else round(times[0], 2))
    except Exception as e:  # noqa: BLE001
        emit("result", engine=engine, width=w, height=h, error=str(e)[:300])
emit("done")
