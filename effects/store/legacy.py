"""Upgrade stored effect node trees to the current Blender version.

The effect store keeps node trees as JSON written by older Blender versions,
so node types and socket identifiers in it can be out of date. Blender's own
versioning only runs on .blend files, so the equivalent changes are made here.
"""

import bpy

# Old identifier suffixes of data-type variants, keyed by data_type.
_TYPE_SUFFIX = {
    "FLOAT": "_Float",
    "INT": "_Int",
    "INT8": "_Int",
    "BOOLEAN": "_Bool",
    "FLOAT_VECTOR": "_Vector",
    "FLOAT2": "_Vector",
    "FLOAT_COLOR": "_Color",
    "BYTE_COLOR": "_Color",
    "QUATERNION": "_Rotation",
}
# Older nodes numbered their variants instead.
_INDEX_SUFFIX = {
    "FLOAT_VECTOR": "",
    "FLOAT": "_001",
    "FLOAT_COLOR": "_002",
    "BOOLEAN": "_003",
    "INT": "_004",
}
# Node properties whose default changed: (node type, property) -> (Blender
# version that changed it, previous default). The store only saves properties
# that differ from the default, so older effects rely on the old default.
_CHANGED_DEFAULTS = {
    ("GeometryNodeSwitch", "input_type"): ((5, 1, 0), "GEOMETRY"),
}
_COMPARE_SUFFIX = {"INT": "_INT", "VECTOR": "_VEC3", "RGBA": "_COL", "STRING": "_STR"}
_RANDOM_SUFFIX = {"FLOAT": "_001", "INT": "_002", "BOOLEAN": "_003"}


def _data_type(node: bpy.types.Node):
    if isinstance(node, bpy.types.GeometryNodeCaptureAttribute):
        items = getattr(node, "capture_items", None)
        return items[0].data_type if items else None
    return getattr(node, "data_type", None)


def _renamed_sockets(node: bpy.types.Node, is_output: bool) -> dict[str, str]:
    """Old identifiers of the node's active data-type variant, mapped to the
    identifiers used since Blender 5.0 (which only exposes the active variant)."""
    data_type = _data_type(node)
    kind = node.bl_idname

    if kind == "FunctionNodeCompare" and not is_output:
        suffix = _COMPARE_SUFFIX.get(data_type)
        return {f"A{suffix}": "A", f"B{suffix}": "B"} if suffix else {}
    if kind == "FunctionNodeRandomValue":
        suffix = _RANDOM_SUFFIX.get(data_type)
        if not suffix:
            return {}
        if is_output:
            return {f"Value{suffix}": "Value"}
        return {f"Min{suffix}": "Min", f"Max{suffix}": "Max"}

    if kind in {"GeometryNodeStoreNamedAttribute", "GeometryNodeSampleNearestSurface"}:
        base, suffixes = "Value", _TYPE_SUFFIX
    elif kind == "GeometryNodeInputNamedAttribute":
        base, suffixes = "Attribute", _TYPE_SUFFIX
    elif kind == "GeometryNodeRaycast":
        base, suffixes = "Attribute", _INDEX_SUFFIX
    elif kind == "GeometryNodeCaptureAttribute":
        base, suffixes = ("Attribute" if is_output else "Value"), _INDEX_SUFFIX
    else:
        return {}
    suffix = suffixes.get(data_type)
    return {base + suffix: base} if suffix else {}


def find_socket(
    node: bpy.types.Node,
    identifier: str,
    is_output: bool,
    old_identifiers: list[str] = None,
):
    """Find a node socket by an identifier that may be from an older Blender.

    old_identifiers lists the stored identifiers of a group interface in order,
    for group sockets whose identifiers changed (e.g. "Input_2" to "Socket_2").
    """
    sockets = node.outputs if is_output else node.inputs
    is_group = node.type in {"GROUP_INPUT", "GROUP_OUTPUT", "GROUP"}

    if is_group and identifier in sockets:
        return sockets[identifier]
    for socket in sockets:
        if socket.identifier == identifier:
            return socket
    if is_group and old_identifiers and identifier in old_identifiers:
        index = old_identifiers.index(identifier)
        if index < len(sockets):
            return sockets[index]

    new_identifier = _renamed_sockets(node, is_output).get(identifier)
    if new_identifier:
        for socket in sockets:
            if socket.identifier == new_identifier:
                return socket
    return None


def upgrade_node_data(node_data: dict, blender_version: list[int]) -> dict:
    """Return node_data converted for node types and properties that changed.

    blender_version is the version the effect was saved with.
    """
    node_type = node_data["type"]

    for (changed_type, prop), (version, old_default) in _CHANGED_DEFAULTS.items():
        props = node_data.get("props", {})
        if (
            node_type == changed_type
            and prop not in props
            and tuple(blender_version) < version <= bpy.app.version
        ):
            node_data = {**node_data, "props": {**props, prop: old_default}}

    # Musgrave Texture was merged into Noise Texture in Blender 4.1. This
    # follows Blender's own versioning for unlinked Detail/Dimension inputs.
    if node_type == "ShaderNodeTexMusgrave" and not hasattr(bpy.types, node_type):
        props = dict(node_data.get("props", {}))
        props["noise_dimensions"] = props.pop("musgrave_dimensions", "3D")
        props["noise_type"] = props.pop("musgrave_type", "FBM")
        props["normalize"] = False
        inputs = []
        values = {inp[0]: inp[1] for inp in node_data.get("inputs", []) if len(inp) == 2}
        for inp in node_data.get("inputs", []):
            if inp[0] == "Detail" and len(inp) == 2:
                inp = ["Detail", max(inp[1] - 1.0, 0.0)]
            elif inp[0] == "Dimension":
                if len(inp) != 2:
                    continue
                lacunarity = values.get("Lacunarity", 2.0)
                inp = ["Roughness", lacunarity ** -inp[1] if lacunarity > 0 else 0.0]
            inputs.append(inp)
        return {**node_data, "type": "ShaderNodeTexNoise", "props": props, "inputs": inputs}

    # Rotate Euler's "type" property was renamed in Blender 4.x.
    if node_type == "FunctionNodeRotateEuler" and "type" in node_data.get("props", {}):
        props = dict(node_data["props"])
        props["rotation_type"] = props.pop("type")
        return {**node_data, "props": props}

    return node_data


def upgrade_node(node: bpy.types.Node, node_data: dict):
    """Fix up a node created from stored data, after its properties are set."""
    # Capture Attribute has a list of capture items since Blender 4.2, instead
    # of a single value with a data_type.
    data_type = node_data.get("props", {}).get("data_type")
    if (
        isinstance(node, bpy.types.GeometryNodeCaptureAttribute)
        and data_type
        and hasattr(node, "capture_items")
        and not node.capture_items
    ):
        socket_type = {"FLOAT_VECTOR": "VECTOR", "FLOAT_COLOR": "RGBA"}.get(data_type, data_type)
        node.capture_items.new(socket_type, "Attribute")
