"""Refer to Blender data from a string, such as an operator's target, and find
it again without eval()."""

import json

import bpy

# The bpy.data collection of each type of ID the add-on refers into.
_COLLECTIONS = {
    "WINDOWMANAGER": "window_managers",
    "NODETREE": "node_groups",
    "SCENE": "scenes",
    "OBJECT": "objects",
}


def ref(struct: bpy.types.bpy_struct) -> str:
    """A string for resolve() to find struct with."""
    owner = struct.id_data
    return json.dumps([_COLLECTIONS[owner.id_type], owner.name, struct.path_from_id()])


def resolve(reference: str) -> bpy.types.bpy_struct:
    collection, name, path = json.loads(reference)
    return getattr(bpy.data, collection)[name].path_resolve(path)
