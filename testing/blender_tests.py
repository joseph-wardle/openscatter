"""Tests that run inside Blender. Use run_tests.py rather than running this directly.

    blender -b --python blender_tests.py -- <add-on module> <smoke|effects> <output.json>

Writes the results as JSON; run_tests.py decides whether they pass.
"""

import importlib
import json
import os
import random
import sys
import threading
import traceback

import bpy


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    for group in list(bpy.data.node_groups):
        bpy.data.node_groups.remove(group)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)


def scatter():
    """Scatter a small cube over a 10x10 plane. Returns the scatter system object."""
    # The add-on picks the system's seed with the random module.
    random.seed(1)
    clear_scene()
    bpy.ops.mesh.primitive_plane_add(size=10)
    plane = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(size=0.1, location=(20, 0, 0))
    cube = bpy.context.active_object
    plane.select_set(True)
    cube.select_set(True)
    bpy.context.view_layer.objects.active = plane
    with bpy.context.temp_override(
        active_object=plane, selected_objects=[plane, cube], object=plane
    ):
        bpy.ops.gscatter.scatter_selected_to_active()
    system = next(o for o in bpy.data.objects if o.gscatter.is_gscatter_system)
    bpy.context.view_layer.objects.active = system
    return system


def fingerprint() -> dict:
    """Number of scattered instances and a checksum of their transforms."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    count = 0
    checksum = 0.0
    for instance in depsgraph.object_instances:
        if instance.is_instance:
            count += 1
            checksum += sum(abs(v) for row in instance.matrix_world for v in row)
    return {"instances": count, "checksum": round(checksum, 3)}


def add_effect(effect):
    bpy.context.scene.gscatter.active_category = effect.categories[0]
    bpy.ops.gscatter.add_effect(type=effect.id)


def user_effects(module: str) -> list:
    store = importlib.import_module(module + ".effects.store").effectstore
    effects = [e for e in store.get_all() if e.namespace != "internal"]
    return sorted(effects, key=lambda e: (e.id, e.effect_version))


def error_message(e: Exception) -> str:
    return str(e).strip().splitlines()[-1]


def smoke(module: str) -> dict:
    """Scatter, then stack every effect on one system."""
    result = {}
    scatter()
    result["scatter"] = fingerprint()
    failed = {}
    added = 0
    for effect in user_effects(module):
        try:
            add_effect(effect)
            added += 1
        except Exception as e:
            failed[f"{effect.id}@{effect.version_str}"] = error_message(e)
    result["effects_added"] = added
    result["effects_failed"] = failed
    return result


def add_effect_version(module: str, effect, category: str):
    """Add this exact effect version to a category, as the add_effect operator
    does for the newest version. Returns the effect layer."""
    utils = importlib.import_module(module + ".effects.utils")
    getters = importlib.import_module(module + ".utils.getters")
    bpy.context.scene.gscatter.active_category = category
    category_tree = getters.get_node_tree(bpy.context).nodes[category].node_tree
    return utils.add_effect(
        effect.nodetree, category_tree, category, effect.id, effect.effect_version
    )


def settings(effect, layer) -> list:
    """(label, layer property, value) for each non-default mix setting."""
    result = [("influence 50", "influence", 50), ("invert", "invert", True)]
    for blend_type in effect.blend_types:
        if blend_type != layer.blend_type:
            result.append((f"blend {blend_type}", "blend_type", blend_type))
    return result


def effects(module: str) -> dict:
    """Fingerprint each effect version in each of its categories, alone on a
    fresh scatter, first with default settings and then with each mix setting
    changed in turn."""
    scatter()
    result = {"base": fingerprint(), "effects": {}, "saved_with": {}}
    for effect in user_effects(module):
        result["saved_with"][f"{effect.id}@{effect.version_str}"] = list(
            effect.blender_version[:2]
        )
        for category in effect.categories:
            prefix = f"{effect.id}@{effect.version_str} {category}"
            key = prefix + " default"
            try:
                scatter()
                layer = add_effect_version(module, effect, category)
                result["effects"][key] = {"name": effect.name, **fingerprint()}
                for label, prop, value in settings(effect, layer):
                    key = f"{prefix} {label}"
                    old = getattr(layer, prop)
                    setattr(layer, prop, value)
                    result["effects"][key] = {"name": effect.name, **fingerprint()}
                    setattr(layer, prop, old)
            except Exception as e:
                result["effects"][key] = {"name": effect.name, "error": error_message(e)}
    return result


def main():
    module, test, output = sys.argv[sys.argv.index("--") + 1 :]
    result = {"blender": bpy.app.version_string}
    try:
        bpy.ops.preferences.addon_enable(module=module)
        result["enabled"] = module in bpy.context.preferences.addons
        if result["enabled"]:
            result.update({"smoke": smoke, "effects": effects}[test](module))
    except Exception:
        result["error"] = traceback.format_exc()
    # Non-daemon threads keep background Blender from exiting.
    result["blocking_threads"] = [
        t.name
        for t in threading.enumerate()
        if t is not threading.main_thread() and not t.daemon and t.is_alive()
    ]
    with open(output, "w") as f:
        json.dump(result, f, indent=1)
    sys.stdout.flush()
    # Exit even if threads are left, so the original GScatter can be tested.
    os._exit(0)


main()
