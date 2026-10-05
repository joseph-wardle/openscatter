from typing import List

import bpy
from bpy.app.handlers import persistent

from ..common.props import ScatterItemProps
from .props import EffectLayerProps
from ..utils.getters import get_scatter_props, get_node_tree, get_scene_props
from . import default
from .store import effectstore
from .utils import trees


@persistent
def check_and_set_effect_category_and_database(self, context: bpy.types.Context):
    """Checks if effect category is defined and sets the effect category if not"""
    scatter_props = get_scatter_props(context)
    get_scene_props(context)
    if scatter_props is not None:
        scatter_items: List[ScatterItemProps] = scatter_props.scatter_items
        for item in scatter_items:
            for category in default.EFFECT_CATEGORIES:
                node_tree = get_node_tree(item.obj)
                node: bpy.types.GeometryNodeGroup = node_tree.nodes[category]
                effects: list[EffectLayerProps] = node.node_tree.gscatter.effects
                for effect in effects:
                    if effect.group_node.node_tree.gscatter.category == ["NONE"]:
                        effect_item = effectstore.get_by_id_and_version(
                            effect.effect_id, effect.version
                        )
                        if effect_item is None:
                            effect_item = effectstore.get_newest_by_id(effect.effect_id)
                        if effect_item:
                            effect.group_node.node_tree.gscatter.category = (
                                effect_item.categories
                            )
                            effect.group_node.node_tree.gscatter.icon = effect_item.icon

                        effect.set_effect_id(effect.effect_id)
                        effect.set_effect_version(effect.version)

                    trees.set_channel_input(effect.group_node, category)
                    trees.create_mix_inputs(effect)


@persistent
def node_deleted_handler(self, context: bpy.types.Context):
    scene_props = get_scene_props(bpy.context)
    category: str = scene_props.active_category
    node_tree = get_node_tree(context)
    if node_tree is None:
        return
    if category not in node_tree.nodes:
        return
    node: bpy.types.GeometryNodeGroup = node_tree.nodes[category]
    selected = node.node_tree.gscatter.get_selected()
    if selected and selected.group_node is None:
        index = node.node_tree.gscatter.effects.find(selected.name)
        node.node_tree.gscatter.effects.remove(index)


# Name of the camera last set on effects' Active Camera inputs, so that
# updates that don't change it or any node tree can skip the search.
_applied_camera = None


@persistent
def active_camera_handler(scene, depsgraph):
    global _applied_camera
    camera = bpy.context.scene.camera
    camera_name = camera.name if camera else None
    if camera_name == _applied_camera and not depsgraph.id_type_updated("NODETREE"):
        return
    _applied_camera = camera_name

    for obj in bpy.data.objects:
        node_tree = get_node_tree(obj)
        if node_tree is None:
            continue
        for category in default.EFFECT_CATEGORIES:
            node: bpy.types.GeometryNodeGroup = node_tree.nodes[category]
            effects: list[EffectLayerProps] = node.node_tree.gscatter.effects
            for effect in effects:
                for inp in effect.effect_node.inputs:
                    if (
                        inp.type == "OBJECT"
                        and inp.name.endswith("Active Camera")
                        and inp.default_value != camera
                    ):
                        inp.default_value = camera


@persistent
def reset_active_camera(*args):
    global _applied_camera
    _applied_camera = None


def register():
    bpy.app.handlers.depsgraph_update_post.append(node_deleted_handler)
    bpy.app.handlers.depsgraph_update_post.append(active_camera_handler)
    bpy.app.handlers.frame_change_post.append(active_camera_handler)
    bpy.app.handlers.load_post.append(reset_active_camera)
    bpy.app.handlers.load_post.append(check_and_set_effect_category_and_database)


def unregister():
    bpy.app.handlers.depsgraph_update_post.remove(node_deleted_handler)
    bpy.app.handlers.depsgraph_update_post.remove(active_camera_handler)
    bpy.app.handlers.frame_change_post.remove(active_camera_handler)
    bpy.app.handlers.load_post.remove(reset_active_camera)
    bpy.app.handlers.load_post.remove(check_and_set_effect_category_and_database)
