"""Image previews that can also show BIP files.

GScatter's icons and Graswald's asset previews are BIP files: zlib-compressed
RGBA pixels, which Blender can't read. They are decoded here and their pixels
set on the preview directly; any other file is loaded by Blender itself.
"""

import time
import zlib
from array import array

import bpy
import bpy.utils.previews

BIP_MAGIC = b"BIP2"

# Seconds spent loading queued previews each time the timer runs, so the
# interface stays responsive while a gallery of large previews loads.
BUDGET = 0.05


def read_bip(path: str) -> list:
    """Return the (size, pixels) of each image in a BIP file, smallest first."""
    with open(path, "rb") as file:
        data = file.read()
    if data[:4] != BIP_MAGIC or not data[4]:
        raise ValueError("not a BIP file")

    count = data[4]
    images = []
    offset = 5 + 8 * count
    for index in range(count):
        header = data[5 + 8 * index : 13 + 8 * index]
        size = (int.from_bytes(header[0:2], "big"), int.from_bytes(header[2:4], "big"))
        length = int.from_bytes(header[4:8], "big")
        pixels = array("i", zlib.decompress(data[offset : offset + length]))
        if len(pixels) != size[0] * size[1]:
            raise ValueError("wrong number of pixels")
        images.append((size, pixels))
        offset += length
    return images


def is_bip(path: str) -> bool:
    try:
        with open(path, "rb") as file:
            return file.read(4) == BIP_MAGIC
    except OSError:
        return False


class Previews:
    """A preview collection keyed by file path.

    With lazy loading, BIP files are read by a timer in small batches instead of
    when they're first drawn. Background Blender loads them straight away, as it
    doesn't run timers while scripts are working.
    """

    def __init__(self, lazy: bool):
        self._collection = bpy.utils.previews.new()
        self._lazy = lazy and not bpy.app.background
        self._queue = {}
        # Kept so the timer can be found again; each attribute access makes a
        # new bound method, which bpy.app.timers wouldn't recognise.
        self._timer = self._load_queued

    def get(self, path: str) -> bpy.types.ImagePreview:
        preview = self._collection.get(path)
        if preview is not None:
            return preview

        if not is_bip(path):
            return self._collection.load(path, path, "IMAGE")

        preview = self._collection.new(path)
        if self._lazy:
            self._queue[path] = None
            if not bpy.app.timers.is_registered(self._timer):
                bpy.app.timers.register(self._timer, persistent=True)
        else:
            self._load(preview, path)
        return preview

    def close(self):
        if bpy.app.timers.is_registered(self._timer):
            bpy.app.timers.unregister(self._timer)
        self._queue.clear()
        bpy.utils.previews.remove(self._collection)

    def _load(self, preview: bpy.types.ImagePreview, path: str):
        try:
            images = read_bip(path)
        except (OSError, ValueError, zlib.error) as e:
            print(f"OpenScatter: can't load preview {path}: {e}")
            return

        # foreach_set is far faster than assigning the pixels for large images.
        (icon_size, icon_pixels), (image_size, image_pixels) = images[0], images[-1]
        preview.icon_size = icon_size
        preview.icon_pixels.foreach_set(icon_pixels)
        preview.image_size = image_size
        preview.image_pixels.foreach_set(image_pixels)

    def _load_queued(self):
        start = time.perf_counter()
        while self._queue and time.perf_counter() - start < BUDGET:
            path = next(iter(self._queue))
            del self._queue[path]
            preview = self._collection.get(path)
            if preview is not None:
                self._load(preview, path)

        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()

        return 0.01 if self._queue else None
