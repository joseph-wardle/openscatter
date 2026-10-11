"""Tests that run inside Blender. Use run_tests.py rather than running this directly.

    blender -b --python blender_tests.py -- <add-on module> <smoke|effects|custom|shared|free_assets> <output.json>

Writes the results as JSON; run_tests.py decides whether they pass.
"""

import importlib
import json
import os
import random
import sys
import threading
import time
import traceback

import bpy


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    for group in list(bpy.data.node_groups):
        bpy.data.node_groups.remove(group)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)


def scatter(clear=True):
    """Scatter a small cube over a 10x10 plane, or over the plane already there
    if clear is False. Returns the scatter system object."""
    # The add-on picks the system's seed with the random module.
    random.seed(1)
    if clear:
        clear_scene()
        bpy.ops.mesh.primitive_plane_add(size=10)
    plane = bpy.data.objects["Plane"]
    systems = {o for o in bpy.data.objects if o.gscatter.is_gscatter_system}
    bpy.ops.mesh.primitive_cube_add(size=0.1, location=(20, 0, 0))
    cube = bpy.context.active_object
    plane.select_set(True)
    cube.select_set(True)
    bpy.context.view_layer.objects.active = plane
    with bpy.context.temp_override(
        active_object=plane, selected_objects=[plane, cube], object=plane
    ):
        bpy.ops.gscatter.scatter_selected_to_active()
    system = next(
        o for o in bpy.data.objects if o.gscatter.is_gscatter_system and o not in systems
    )
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


def system_fingerprints() -> dict:
    """fingerprint() for each scatter system, by name."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    result = {}
    for instance in depsgraph.object_instances:
        if instance.is_instance:
            r = result.setdefault(instance.parent.original.name, {"instances": 0, "checksum": 0.0})
            r["instances"] += 1
            r["checksum"] += sum(abs(v) for row in instance.matrix_world for v in row)
    for r in result.values():
        r["checksum"] = round(r["checksum"], 3)
    return result


def add_effect(effect):
    bpy.context.scene.gscatter.active_category = effect.categories[0]
    bpy.ops.gscatter.add_effect(type=effect.id)


def user_effects(module: str) -> list:
    store = importlib.import_module(module + ".effects.store").effectstore
    effects = [e for e in store.get_all() if e.namespace != "internal"]
    return sorted(effects, key=lambda e: (e.id, e.effect_version))


def error_message(e: Exception) -> str:
    return str(e).strip().splitlines()[-1]


def handlers(module: str) -> list:
    """Names of the add-on's functions in bpy.app.handlers."""
    result = []
    for name in dir(bpy.app.handlers):
        functions = getattr(bpy.app.handlers, name)
        if isinstance(functions, list):
            result += [
                f"{name}: {f.__name__}"
                for f in functions
                if getattr(f, "__module__", "").startswith(module + ".")
            ]
    return result


def smoke(module: str) -> dict:
    """Scatter, then stack every effect on one system, then disable the add-on."""
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
    result["icons"] = icons(module)
    bpy.ops.preferences.addon_disable(module=module)
    result["handlers_left"] = handlers(module)
    return result


def icons(module: str) -> dict:
    """Load every bundled icon, and an asset preview from a path with no file."""
    icons = importlib.import_module(module + ".icons")
    previews = importlib.import_module(module + ".asset_manager.previews")
    result = {}
    for name in sorted(icons.get_all()):
        try:
            icons.get(name)
            preview = icons.collection.get(icons.get_icon_path(name))
            result[name] = {
                "icon_size": list(preview.icon_size),
                "image_size": list(preview.image_size),
                "visible": any(preview.icon_pixels[:]),
            }
        except Exception as e:
            result[name] = {"error": error_message(e)}
    try:
        previews.get("")
        result[""] = {}
    except Exception as e:
        result[""] = {"error": error_message(e)}
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


def custom(module: str, folder: str) -> dict:
    """Save each effect version as a custom effect, export and import it, store
    and reload the user effects, and fingerprint the reloaded effect alongside
    the original."""
    store = importlib.import_module(module + ".effects.store").effectstore
    Effect = importlib.import_module(module + ".effects.store.effect_item").Effect
    schema_version = importlib.import_module(module + ".effects.default").EFFECT_SCHEMA_VERSION
    EffectNamespace = importlib.import_module(
        module + ".effects.store.effect_namespace"
    ).EffectNamespace
    if "user" not in store.namespace:
        store._load_user_namespace()
    user = store.namespace["user"]
    if not os.path.abspath(user.filepath).startswith(os.path.abspath(folder)):
        raise RuntimeError(f"not saving to the user's own effect store, {user.filepath}")

    originals = {}
    saved = []
    result = {"effects": {}}
    for effect in user_effects(module):
        category = effect.categories[0]
        key = f"{effect.id}@{effect.version_str} {category}"
        try:
            scatter()
            add_effect_version(module, effect, category)
            originals[key] = {"name": effect.name, **fingerprint()}
            # As the Create and Update operators do, on this Blender.
            copy = Effect(
                "custom." + effect.id, effect.name, effect.author, effect.description,
                effect.icon, effect.categories, effect.subcategory,
                effect.effect_version, schema_version, list(bpy.app.version),
                effect.nodetree, effect.blend_types, effect.default_blend_type,
            )
            path = os.path.join(folder, f"{copy.id}@{copy.version_str}.json")
            copy.export(path)
            # As the Import operator does.
            store.add_from_filepath(path)
            if store.get_by_id_and_version(copy.id, copy.effect_version) is None:
                raise RuntimeError("importing the exported effect failed")
            saved.append((key, copy))
        except Exception as e:
            result["effects"][key] = {"name": effect.name, "error": error_message(e)}

    user.changes = True
    user.store()
    reloaded = EffectNamespace(user.filepath, "user")
    for key, copy in saved:
        try:
            effect = reloaded._item_index.get(f"{copy.id}:{copy.version_str}")
            if effect is None:
                raise RuntimeError("the effect was missing after reloading the user store")
            scatter()
            add_effect_version(module, effect, key.split(" ")[1])
            result["effects"][key] = {**originals[key], "saved": fingerprint()}
        except Exception as e:
            result["effects"][key] = {"name": copy.name, "error": error_message(e)}
    return result


SHARED_EFFECTS = ("system.musgrave", "system.randomize", "system.randomize_rotation")


def shared(module: str, folder: str) -> dict:
    """Add the same effects to two systems, then delete, duplicate, reload and
    edit, recording what happens to the node groups the effects share."""
    effect_item = importlib.import_module(module + ".effects.store.effect_item")
    store = importlib.import_module(module + ".effects.store").effectstore

    def shared_groups() -> set:
        return {g.name for g in bpy.data.node_groups if effect_item.is_shared(g)}

    def empty_group_nodes() -> int:
        return sum(
            1
            for g in bpy.data.node_groups
            for n in g.nodes
            if isinstance(n, bpy.types.GeometryNodeGroup) and n.node_tree is None
        )

    def add_effects():
        for effect_id in SHARED_EFFECTS:
            add_effect(store.get_newest_by_id(effect_id))

    def select(system):
        items = bpy.context.scene.gscatter.scatter_surface.gscatter.scatter_items
        index = next(i for i, item in enumerate(items) if item.obj == system)
        bpy.context.scene.gscatter.scatter_surface.gscatter.scatter_index = index
        bpy.context.view_layer.objects.active = system

    result = {}
    first = scatter()
    add_effects()
    groups = shared_groups()
    result["shared"] = len(groups)
    second = scatter(clear=False)
    add_effects()
    result["second_system_new_shared"] = sorted(shared_groups() - groups)
    first_name = first.name
    before = system_fingerprints().get(first_name)
    result["second_system"] = system_fingerprints().get(second.name)

    select(second)
    bpy.ops.gscatter.delete_scatter_item()
    result["delete"] = {
        "before": before,
        "after": system_fingerprints().get(first_name),
        "empty_group_nodes": empty_group_nodes(),
    }

    select(first)
    bpy.ops.gscatter.duplicate_scatter_item()
    copy = next(
        o for o in bpy.data.objects if o.gscatter.is_gscatter_system and o != first
    )
    copy_name = copy.name
    duplicated = system_fingerprints().get(copy_name)
    select(first)
    bpy.ops.gscatter.delete_scatter_item()
    result["duplicate"] = {
        "original": before,
        "copy": duplicated,
        "after_deleting_original": system_fingerprints().get(copy_name),
        "empty_group_nodes": empty_group_nodes(),
    }

    path = os.path.join(folder, "shared.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    groups = shared_groups()
    select(bpy.data.objects[copy_name])
    add_effects()
    result["reload_new_shared"] = sorted(shared_groups() - groups)

    edited = next(
        (g for g in bpy.data.node_groups if effect_item.is_shared(g) and g.name.startswith("mixer")),
        None,
    )
    if edited is None:
        result["edit"] = None
        return result
    edited.nodes.new("NodeReroute")
    users = edited.users
    groups = shared_groups()
    add_effects()
    source = edited[effect_item.SHARED_KEY]["source"]
    result["edit"] = {
        "users_before": users,
        "users_after": edited.users,
        "rebuilt": any(
            bpy.data.node_groups[name][effect_item.SHARED_KEY]["source"] == source
            for name in shared_groups() - groups
        ),
    }
    return result


class FakeServer:
    """A local stand-in for Graswald's server, which records what's requested.

    /list           the list of free assets, with one asset
    /icon.bip       the asset's icon
    /asset.zip      the asset
    /trickle.zip    a zip sent slowly, to cancel
    /slow           replies after 3 s
    /broken         an error
    """

    def __init__(self, icon: bytes):
        import http.server
        import io
        import signal
        import zipfile

        # Blender 4.2 doesn't ignore SIGPIPE, so writing to a download that
        # was cancelled would kill it.
        if hasattr(signal, "SIGPIPE"):
            signal.signal(signal.SIGPIPE, signal.SIG_IGN)

        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("Test Plant/product.json", json.dumps({"name": "Test Plant"}))
        self.files = {"/icon.bip": icon, "/asset.zip": archive.getvalue()}
        self.requests = []
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                server.requests.append(self.path)
                if self.path == "/list":
                    body = json.dumps({"assets": [{
                        "asset_id": "test_plant", "name": "Test Plant",
                        "description": "A test", "asset_type": "3D_PLANT",
                        "icon": server.url("/icon.bip"), "url": server.url("/asset.zip"),
                    }]}).encode()
                    self.reply(body, "application/json")
                elif self.path in server.files:
                    self.reply(server.files[self.path], "application/octet-stream")
                elif self.path == "/trickle.zip":
                    self.send_response(200)
                    self.send_header("Content-Length", str(1024 * 200))
                    self.end_headers()
                    for _ in range(200):
                        self.wfile.write(bytes(1024))
                        self.wfile.flush()
                        time.sleep(0.05)
                elif self.path == "/slow":
                    time.sleep(3)
                    self.reply(b"{}", "application/json")
                else:
                    self.send_error(500)

            def reply(self, body, content_type):
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}{path}"


def free_assets(module: str) -> dict:
    """Load the list of free assets and download one from a fake server, with
    online access on and off, and when the server fails, is slow, or the
    download is cancelled."""
    free = importlib.import_module(module + ".asset_manager.props.free_assets")
    library_module = importlib.import_module(module + ".asset_manager.props.library")
    asset_utils = importlib.import_module(module + ".asset_manager.utils")
    background = importlib.import_module(module + ".utils.background")
    icons = importlib.import_module(module + ".icons")
    library = bpy.context.window_manager.gscatter.library
    server = FakeServer(open(icons.get_icon_path("custom_brick"), "rb").read())
    result = {"online_access": bpy.app.online_access}

    def load(path: str, allow_networking=True) -> dict:
        free.FREE_ASSETS_JSON_LIST_URL = server.url(path)
        for m in (free, library_module):
            m.get_allow_networking = lambda: allow_networking
        server.requests.clear()
        start = time.monotonic()
        asset_utils.load_library(True)
        loading = library.loading_free_assets
        background.wait()
        return {
            "requests": list(server.requests),
            "loading_while_waiting": loading,
            "loading_after": library.loading_free_assets,
            "assets": [(a.asset_id, bool(a.icon)) for a in library.free_assets],
            "seconds": round(time.monotonic() - start, 1),
        }

    def download(path: str, cancel=False) -> dict:
        if not library.free_assets:
            return {"error": "there was no free asset to download"}
        library.free_assets[0].url = server.url(path)
        server.requests.clear()
        start = time.monotonic()
        bpy.ops.gscatter.download_free_asset(asset_id="test_plant")
        asset = library.free_assets[0]
        downloading = asset.downloading
        asset.cancel_download = cancel
        background.wait()
        asset = library.free_assets[0]
        return {
            "requests": list(server.requests),
            "downloading_while_waiting": downloading,
            "downloading_after": asset.downloading,
            "seconds": round(time.monotonic() - start, 1),
        }

    result["offline_first"] = load("/list", allow_networking=False)
    result["online"] = load("/list")
    result["list_saved"] = (
        free.get_asset_browser_dir().joinpath("free_assets.json").exists()
    )
    result["offline"] = load("/list", allow_networking=False)
    result["broken"] = load("/broken")
    free.TIMEOUT = (2, 1)
    result["slow"] = load("/slow")

    assets_dir = asset_utils.user_library().joinpath("Assets")
    result["download"] = download("/asset.zip")
    result["installed"] = assets_dir.joinpath("Test Plant", "product.json").exists()
    result["download_broken"] = download("/broken")
    result["cancel"] = download("/trickle.zip", cancel=True)
    result["leftovers"] = sorted(
        p.name for p in assets_dir.glob("*") if p.name != "Test Plant"
    )

    for m in (free, library_module):
        m.get_allow_networking = lambda: False
    result["offline_operator"] = bpy.ops.gscatter.download_free_asset.poll()
    return result


def main():
    module, test, output = sys.argv[sys.argv.index("--") + 1 :]
    result = {"blender": bpy.app.version_string}
    try:
        bpy.ops.preferences.addon_enable(module=module)
        result["enabled"] = module in bpy.context.preferences.addons
        if result["enabled"] and test in ("custom", "shared"):
            test = {"custom": custom, "shared": shared}[test]
            result.update(test(module, os.path.dirname(output)))
        elif result["enabled"]:
            tests = {"smoke": smoke, "effects": effects, "free_assets": free_assets}
            result.update(tests[test](module))
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
