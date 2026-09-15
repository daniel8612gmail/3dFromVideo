import bpy
import sys
import math

input_file =  r"D:\GIT\3dFromVideo\users\user_000001\devices\S25_x06\videos\DJI_20260909_104710_FHD\GLB\frame_0001_totest.glb"
output_file = r"D:\GIT\3dFromVideo\users\user_000001\devices\S25_x06\videos\DJI_20260909_104710_FHD\GLB\frame_0001_totest_reduced_mesh.glb"

# Maksymalny kąt między normalnymi powierzchni,
# które traktujemy jako tę samą płaszczyznę.
ANGLE = math.radians(1.0)

# Wyczyść scenę
bpy.ops.wm.read_factory_settings(use_empty=True)

# Import GLB
bpy.ops.import_scene.gltf(filepath=input_file)

# Scalanie koplanarnych ścian
for obj in bpy.context.scene.objects:

    if obj.type != "MESH":
        continue

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")

    bpy.ops.mesh.dissolve_limited(
        angle_limit=ANGLE,
        delimit={'NORMAL', 'MATERIAL'}
    )

    bpy.ops.object.mode_set(mode="OBJECT")

    obj.select_set(False)

# Eksport GLB
bpy.ops.export_scene.gltf(
    filepath=output_file,
    export_format='GLB',
    export_materials='EXPORT'
)

print("Saved:", output_file)