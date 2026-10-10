import bpy

from ..utils.previews import Previews

collection: Previews = None


def get(path: str) -> bpy.types.ImagePreview:
    return collection.get(path)


def register():
    global collection
    collection = Previews(lazy=True)


def unregister():
    collection.close()
