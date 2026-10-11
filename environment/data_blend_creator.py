import ast
import bpy
import sys

# read command line arguments
args = sys.argv[sys.argv.index("--") + 1 :]
src_blend_path = args[0]
dest_blend_path = args[1]
material_names = ast.literal_eval(args[2])

dependency_objs = ast.literal_eval(args[3])
dependency_cols = ast.literal_eval(args[4])
dependency_images = ast.literal_eval(args[5])
dependency_mats = ast.literal_eval(args[6])


def create_safe_deps(data_set):
    safe_data_set = set()
    for obj_name in data_set:
        safe_data_set.add(obj_name)

    safe_data_set = list(safe_data_set)

    return safe_data_set


dependency_objs_safe = create_safe_deps(dependency_objs)
dependency_cols_safe = create_safe_deps(dependency_cols)
dependency_images_safe = create_safe_deps(dependency_images)
dependency_mats_safe = create_safe_deps(material_names + dependency_mats)


for ob in bpy.data.objects:
    bpy.data.objects.remove(ob)

bpy.ops.outliner.orphans_purge(
    do_local_ids=True, do_linked_ids=True, do_recursive=False
)

with bpy.data.libraries.load(src_blend_path) as (data_from, data_to):
    data_to.materials = dependency_mats_safe
    data_to.objects = dependency_objs_safe
    data_to.images = dependency_images_safe
    data_to.collections = dependency_cols_safe

for ob in bpy.data.objects:
    ob.use_fake_user = True

for image in bpy.data.images:
    image.use_fake_user = True

for col in bpy.data.collections:
    col.use_fake_user = True

for mat in bpy.data.materials:
    mat.use_fake_user = True

try:
    bpy.ops.file.pack_all()
except Exception:
    pass

bpy.ops.wm.save_as_mainfile(filepath=dest_blend_path)
bpy.ops.wm.quit_blender()
sys.exit(0)
