import bpy
from queue import Queue, Empty
from traceback import print_exc

_queue = None


def put(callback):
    """Add a callback function to the queue."""
    global _queue
    if _queue:
        _queue.put(callback)
        # Only run the timer while there is work, instead of polling forever.
        if not bpy.app.timers.is_registered(_timer):
            bpy.app.timers.register(_timer, persistent=True)


def _timer():
    """Run queued callback functions, one per tick, until the queue is empty."""
    global _queue
    if _queue is None:
        return None
    try:
        callback = _queue.get(block=False)
    except Empty:
        return None
    try:
        callback()
    except Exception:
        print_exc()
    return 0.0


def register():
    """Register queue."""
    global _queue
    _queue = Queue()


def unregister():
    """Unregister queue and timer."""
    global _queue
    if bpy.app.timers.is_registered(_timer):
        bpy.app.timers.unregister(_timer)
    _queue = None
