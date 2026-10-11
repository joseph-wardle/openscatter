"""Run slow work, like downloads, without freezing Blender.

Threads mustn't touch Blender's data, so the work runs on a thread and only
returns its result. A timer on the main thread waits for it and passes the
result on, and can show progress while it waits.
"""

import threading
import time

import bpy

from .logger import error

INTERVAL = 0.1  # seconds between checks on a running task

_tasks = []  # (thread, check) for each running task


def run(work, on_done, on_tick=None):
    """Run work() on a thread, then on_done(result, exception) on the main thread.

    on_tick() is called on the main thread every INTERVAL while the work runs.
    """
    outcome = {}

    def target():
        try:
            outcome["result"] = work()
        except Exception as e:
            outcome["exception"] = e

    thread = threading.Thread(target=target, daemon=True)

    def check():
        running = thread.is_alive()
        if not running:
            _tasks.remove((thread, check))
        try:
            if running and on_tick is not None:
                on_tick()
            elif not running:
                on_done(outcome.get("result"), outcome.get("exception"))
        except Exception as e:
            error(e, "in a background task")
        redraw()
        return INTERVAL if running else None

    _tasks.append((thread, check))
    thread.start()
    bpy.app.timers.register(check, first_interval=INTERVAL, persistent=True)


def wait():
    """Run every task to the end now, doing the timers' work here, as background
    Blender doesn't run timers while a script runs."""
    while _tasks:
        _thread, check = _tasks[0]
        if bpy.app.timers.is_registered(check):
            bpy.app.timers.unregister(check)
        while check() is not None:
            time.sleep(INTERVAL)


def redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def unregister():
    # Running threads are left to finish; nothing will use their results.
    for _thread, check in _tasks:
        if bpy.app.timers.is_registered(check):
            bpy.app.timers.unregister(check)
    _tasks.clear()
