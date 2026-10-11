"""Tests that run inside Blender. Use run_tests.py rather than running this directly.

    blender -b --python blender_tests.py -- <add-on module> <test> <output.json>

Writes the results as JSON; run_tests.py decides whether they pass.
"""

import gc
import hashlib
import importlib
import json
import os
import pathlib
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
    result["enums"] = enum_names(module)
    bpy.ops.preferences.addon_disable(module=module)
    result["handlers_left"] = handlers(module)
    return result


def enum_owners(module: str) -> list:
    """(owner, property) for the dropdowns whose items a callback makes, on the
    smoke test's system."""
    wm = bpy.context.window_manager
    layers = [layer for group in bpy.data.node_groups for layer in group.gscatter.effects]
    owners = [
        (bpy.context.preferences.addons[module].preferences, "default_scatter_preset"),
        (wm.gscatter.library, "presets"),
        (wm.gscatter.effect_properties, "default_blend_type"),
        (layers[0], "blend_type"),
    ]
    owners += [
        (dropdown, "dropdown_items")
        for layer in layers
        for dropdown in layer.dropdowns
    ][:1]
    for op, prop in (
        ("add_effect", "type"),
        ("duplicate_effect", "target"),
        ("add_existing_effect", "type"),
        ("set_effect", "type"),
        ("set_system", "type"),
        ("create_linked_system", "type"),
        ("add_environment_property", "inputs"),
    ):
        owners.append((wm.operator_properties_last(f"gscatter.{op}"), prop))
    return owners


def enum_names(module: str) -> dict:
    """Read each dropdown's names through Blender many times, freeing memory in
    between, and check they don't change. Blender doesn't copy the strings the
    items callback returns, so freed ones would come back garbled."""
    wm = bpy.context.window_manager
    wm.gscatter.effect_properties.blend_types.set(["ADD", "MIX"])
    result = {}
    for owner, prop in enum_owners(module):
        name = f"{type(owner).__name__}.{prop}"
        # Operator properties are OperatorProperties; their class is in bpy.types.
        cls = getattr(bpy.types, owner.bl_rna.identifier, type(owner))
        callback = next(
            c.__annotations__[prop]
            for c in cls.__mro__
            if prop in getattr(c, "__annotations__", {})
        ).keywords["items"]
        first = callback(owner, bpy.context)
        expected = {item[0]: item[1] for item in first if item[0]}
        wrong = set()
        for _ in range(20):
            gc.collect()
            junk = [str(n) * 50 for n in range(2000)]  # reuse freed memory
            for identifier, label in expected.items():
                got = bpy.types.UILayout.enum_item_name(owner, prop, identifier)
                if got != label:
                    wrong.add(f"{label!r} read as {got!r}")
            del junk
        result[name] = {
            "items": len(expected),
            "kept": callback(owner, bpy.context) is first,
            "wrong": sorted(wrong)[:3],
        }
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


def make_bip(width: int, height: int) -> bytes:
    """A BIP image of a gradient, with colour multiplied by alpha as in
    Graswald's, which is different upside down and in each channel."""
    import zlib

    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            alpha = 255 if x < width // 2 else 128
            for value in (x * 255 // width, y * 255 // height, 200):
                pixels.append(value * alpha // 255)
            pixels.append(alpha)
    data = zlib.compress(bytes(pixels))
    header = width.to_bytes(2, "big") + height.to_bytes(2, "big") + len(data).to_bytes(4, "big")
    return b"BIP2" + bytes([1]) + header + data


def plant_files() -> dict:
    """The files of an asset with one variant, Spring, as Graswald makes them."""
    import tempfile

    collection = bpy.data.collections.new("Spring")
    lod = bpy.data.collections.new("Spring_Plant_lod0")
    collection.children.link(lod)
    mesh = bpy.data.meshes.new("Spring_Plant_lod0")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new("Test_Spring_Plant_lod0", mesh)
    lod.objects.link(obj)
    obj.active_material = bpy.data.materials.new("Spring")
    if not obj.active_material.node_tree:  # Blender 5 always has one
        obj.active_material.use_nodes = True
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "data.blend")
        bpy.data.libraries.write(path, {collection}, fake_user=True)
        data = open(path, "rb").read()
    for block, items in ((bpy.data.objects, [obj]), (bpy.data.meshes, [mesh]),
                         (bpy.data.collections, [lod, collection])):
        for item in items:
            block.remove(item)
    bpy.data.materials.remove(bpy.data.materials["Spring"])

    variant = {
        "name": "Test Plant Spring",
        "description": "A test",
        "tags": ["Spring"],
        "url": "",
        "author": "openscatter",
        "previews": {"gallery": "spring.bip", "details": ["spring.bip"]},
        "blends": ["data/data.blend"],
        "configurator": {
            "name": "graswald_two",
            "attributes": {"Variant": "Spring"},
            "properties": {"Level Of Detail": ["0"]},
        },
    }
    product = {
        "name": "Test Plant",
        "assets": ["spring.json"],
        "description": "A test",
        "authors": {"openscatter": {"name": "OpenScatter", "icon": "spring.bip", "url": ""}},
    }
    return {
        "product.json": json.dumps(product),
        "spring.json": json.dumps(variant),
        "spring.bip": make_bip(16, 8),
        "data/data.blend": data,
    }


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
            for name, data in plant_files().items():
                z.writestr("Test Plant/" + name, data)
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

    # Operators find assets from strings that refer to them, without eval().
    paths = importlib.import_module(module + ".utils.paths")
    asset_utils.load_library()
    library.browse_type = "ASSETS"
    library.update_search(bpy.context)
    asset = library.assets[0] if library.assets else None
    result["references"] = {
        "loaded": asset is not None,
        "resolve": asset is not None and paths.resolve(paths.ref(asset)) == asset,
        "parent": asset is not None and asset.parent == library,
        "parent_collection": asset is not None and asset.parent_collection == library.assets,
        "filtered": library.filtered_assets() == list(library.assets),
    }
    result["download_broken"] = download("/broken")
    result["cancel"] = download("/trickle.zip", cancel=True)
    result["leftovers"] = sorted(
        p.name for p in assets_dir.glob("*") if p.name != "Test Plant"
    )

    # With experimental features, the asset is also added to the asset browser,
    # by a script run in another Blender.
    import shutil

    free.FREE_ASSETS_JSON_LIST_URL = server.url("/list")
    bpy.context.preferences.addons[module].preferences.enable_experimental_features = True
    background.wait()
    shutil.rmtree(assets_dir.joinpath("Test Plant"))
    result["browser_download"] = download("/asset.zip")
    blend = free.get_asset_browser_dir().joinpath("Test Plant.blend")
    result["browser_blend"] = blend.exists()
    if blend.exists():
        with bpy.data.libraries.load(str(blend), assets_only=True) as (data_from, _):
            result["browser_assets"] = list(data_from.collections)
    png = assets_dir.joinpath("Test Plant", "spring.png")
    if png.exists():
        image = bpy.data.images.load(str(png))
        size, pixels = importlib.import_module(module + ".utils.previews").read_bip(
            str(assets_dir.joinpath("Test Plant", "spring.bip"))
        )[-1]
        # BIP pixels are bottom-up RGBA bytes with colour multiplied by alpha.
        expected = pixels.tobytes()
        png = image.pixels[:]
        premultiplied = [
            round(png[i] * (png[i - i % 4 + 3] if i % 4 != 3 else 1) * 255)
            for i in range(len(png))
        ]
        result["preview_png"] = {
            "size_matches": tuple(image.size) == size,
            "visible": max(png[3::4]) > 0,
            "pixels_match": len(premultiplied) == len(expected)
            and max(abs(a - b) for a, b in zip(premultiplied, expected)) <= 2,
        }

    for m in (free, library_module):
        m.get_allow_networking = lambda: False
    result["offline_operator"] = bpy.ops.gscatter.download_free_asset.poll()
    return result


def folder_hashes(folder: pathlib.Path) -> dict:
    return {
        str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def files(module: str) -> dict:
    """Where the extension keeps its files, that it doesn't save the user's
    preferences or change its own folder, and that disabling it removes the
    asset library it added."""
    result = {}
    prefs = bpy.context.preferences.addons[module].preferences
    home = pathlib.Path.home()
    package = pathlib.Path(importlib.import_module(module).__file__).parent
    before = folder_hashes(package)
    result["online_access"] = bpy.app.online_access
    import logging

    root = logging.getLogger()
    result["root_logger"] = {"handlers": len(root.handlers), "level": root.level}
    result["level_25_name"] = logging.getLevelName(25)

    # Messages reach handlers on the root logger, and developer mode prints
    # them all with a handler of its own, which it removes again.
    log = importlib.import_module(module + ".utils.logger")
    received = []
    catcher = logging.Handler(logging.DEBUG)
    catcher.emit = received.append
    root.addHandler(catcher)
    root.setLevel(logging.DEBUG)
    log.warn("warning")
    log.debug("debug")
    plain = {"received": [r.getMessage() for r in received], "handlers": len(log.logger.handlers)}
    prefs.enable_developer_mode = True
    developer = {"handlers": len(log.logger.handlers), "level": log.logger.level}
    prefs.enable_developer_mode = False
    plain["handlers_after"] = len(log.logger.handlers)
    root.removeHandler(catcher)
    root.setLevel(logging.WARNING)
    result["logging"] = {"plain": plain, "developer": developer}

    getters = importlib.import_module(module + ".utils.getters")
    default = bpy.utils.extension_path_user(module, path="library")
    result["library"] = str(getters.get_library_dir()) == default
    scatter()
    add_effect(user_effects(module)[0])
    result["documents_used"] = (home / "Documents").exists()
    result["library_used"] = pathlib.Path(default).is_dir()

    # GScatter's library is used if there is one, unless another is chosen.
    gscatter = home / "Documents" / "GScatter"
    gscatter.mkdir(parents=True, exist_ok=True)
    result["gscatter_library"] = getters.get_library_dir() == gscatter
    chosen = home / "Chosen"
    prefs.t3dn_library = str(chosen)
    result["chosen_library"] = getters.get_library_dir() == chosen
    prefs.t3dn_library = ""
    result["cleared_library"] = getters.get_library_dir() == gscatter

    # The popups' "don't show again" doesn't save every preference.
    userpref = pathlib.Path(bpy.utils.user_resource("CONFIG"), "userpref.blend")
    saved = userpref.stat().st_mtime_ns if userpref.exists() else None
    bpy.context.preferences.is_dirty = False
    bpy.ops.gscatter.show_tutorial_popup("EXEC_DEFAULT")
    bpy.ops.gscatter.close_compatibility_warning("EXEC_DEFAULT")
    result["userpref_saved"] = (
        userpref.stat().st_mtime_ns if userpref.exists() else None
    ) != saved
    result["preferences_dirty"] = bpy.context.preferences.is_dirty

    # Changes to the stores bundled with the extension are only saved in
    # developer mode; at disable, they'd otherwise be written to its folder.
    stores = [
        importlib.import_module(module + ".effects.store").effectstore,
        importlib.import_module(module + ".effects.store").effectpresetstore,
        importlib.import_module(module + ".scatter.store").scattersystempresetstore,
    ]
    bundled = [
        namespace
        for store in stores
        for name, namespace in store.namespace.items()
        if name in ("system", "internal")
    ]
    for namespace in bundled:
        namespace.changes = True
    prefs.enable_developer_mode = True
    result["developer_can_store"] = all(n.can_store() for n in bundled)
    prefs.enable_developer_mode = False
    result["bundled_count"] = len(bundled)

    libraries = bpy.context.preferences.filepaths.asset_libraries
    prefs.enable_experimental_features = True
    result["asset_library_added"] = "Graswald" in libraries
    bpy.ops.preferences.addon_disable(module=module)
    result["asset_library_left"] = "Graswald" in libraries
    after = folder_hashes(package)
    result["package_changed"] = sorted(
        name for name in set(before) | set(after) if before.get(name) != after.get(name)
    )
    return result


def scene_state() -> dict:
    """What the operators in undo() can change: objects, collections, node
    trees with their effects, and a few settings."""
    scene = bpy.context.scene
    groups = {}
    for g in bpy.data.node_groups:
        groups[g.name] = {
            "nodes": sorted(
                (n.name, n.label, n.node_tree.name if getattr(n, "node_tree", None) else "",
                 tuple(i.default_value for i in n.inputs if i.type == "STRING"))
                for n in g.nodes
            ),
            "links": sorted(
                (l.from_node.name, l.from_socket.identifier, l.to_node.name, l.to_socket.identifier)
                for l in g.links
            ),
            "effects": [(e.name, e.selected) for e in g.gscatter.effects],
        }
    return {
        "marker": scene.get("undo_marker"),
        "mode": bpy.context.mode,
        "objects": sorted(
            (o.name, o.type, tuple(vg.name for vg in o.vertex_groups),
             tuple((i.name, tuple(i.ntree_version)) for i in o.gscatter.scatter_items))
            for o in bpy.data.objects
        ),
        "collections": sorted(
            (c.name, tuple(sorted(ch.name for ch in c.children)), tuple(sorted(o.name for o in c.objects)))
            for c in bpy.data.collections
        ),
        "node_groups": groups,
        "environment_preview": scene.gscatter.environment_creator.preview,
    }


def view3d_override() -> dict:
    window = bpy.context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    return {"window": window, "area": area, "region": region}


def node_editor_override() -> dict:
    """Show the active object's node tree in the largest non-3D area."""
    window = bpy.context.window_manager.windows[0]
    area = max(
        (a for a in window.screen.areas if a.type != "VIEW_3D"),
        key=lambda a: a.width * a.height,
    )
    area.ui_type = "GeometryNodeTree"
    # Blender 4.2 only shows the active object's tree once the editor redraws.
    space = area.spaces.active
    space.node_tree = bpy.context.active_object.modifiers.active.node_group
    region = next(r for r in area.regions if r.type == "WINDOW")
    return {"window": window, "area": area, "region": region, "space_data": space}


def check_undo(op: str, override: dict = None, invoke=False, **properties) -> dict:
    """Run an operator as a button would, then undo once. A marker set between
    two undo steps before running it shows whether undo went back too far,
    which it does if the operator didn't add an undo step of its own."""
    print(f"undo: {op}", flush=True)
    override = override or view3d_override()
    # Operators called from scripts only add undo steps when passed undo=True.
    context = "INVOKE_DEFAULT" if invoke else "EXEC_DEFAULT"
    run = lambda: getattr(bpy.ops.gscatter, op)(context, True, **properties)
    scene = bpy.context.scene
    with bpy.context.temp_override(**override):
        bpy.ops.ed.undo_push(message="before marker")
        scene["undo_marker"] = scene.get("undo_marker", 0) + 1
        bpy.ops.ed.undo_push(message="marker")
        before = scene_state()
        try:
            run()
        except Exception as e:
            return {"error": error_message(e)}
        after = scene_state()
        bpy.ops.ed.undo()
        undone = scene_state()
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
    return {
        "changed": sorted(k for k in before if before[k] != after[k]),
        "not_undone": sorted(k for k in before if before[k] != undone[k]),
    }


def undo(module: str) -> dict:
    """Run each operator that changes the scene, then undo it, from the
    interface (background Blender can't undo)."""
    getters = importlib.import_module(module + ".utils.getters")
    presets = importlib.import_module(module + ".scatter.store").scattersystempresetstore
    misc = importlib.import_module(module + ".asset_manager.ops.misc")
    result = {}

    def category_tree():
        return getters.get_node_tree(bpy.context).nodes["DISTRIBUTION"].node_tree

    def setup(effect_count=2):
        """A fresh scatter with effect_count effects in Distribution, the
        last one selected."""
        with bpy.context.temp_override(**view3d_override()):
            if bpy.context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            system = scatter()
            for effect in [e for e in user_effects(module) if "DISTRIBUTION" in e.categories][:effect_count]:
                add_effect(effect)
            bpy.ops.ed.undo_push(message="setup")
        return system

    setup()
    first = category_tree().gscatter.effects[0]
    result["select_effect"] = check_undo("select_effect", invoke=True, effect_name=first.name)

    setup()
    name = category_tree().gscatter.effects[0].name
    result["move_effect"] = check_undo("move_effect", effect_name=name, up=True)

    setup()
    effects = category_tree().gscatter.effects
    node_name, other = effects[0].group_node.name, effects[1].group_node.node_tree.name
    result["set_effect"] = check_undo("set_effect", node_name=node_name, type=other)

    setup(0)
    weight_map = None
    for effect in user_effects(module):
        if "DISTRIBUTION" not in effect.categories:
            continue
        add_effect(effect)
        layer = category_tree().gscatter.get_selected()
        inputs = [i.name for i in layer.effect_node.inputs if i.name.endswith("Weight Map")]
        if inputs:
            weight_map = (layer.name, inputs[0])
            break
        bpy.ops.gscatter.delete_effect()
    if weight_map:
        bpy.ops.ed.undo_push(message="weight map effect")
        result["paint_weight_map"] = check_undo(
            "paint_weight_map", effect_name=weight_map[0], input_name=weight_map[1]
        )
    else:
        result["paint_weight_map"] = {"error": "no effect has a weight map"}

    setup()
    item = bpy.data.objects["Plane"].gscatter.scatter_items[0]
    item.ntree_version = (2, 1, 0)
    bpy.ops.ed.undo_push(message="old version")
    result["update_scatter_system_tree"] = check_undo(
        "update_scatter_system_tree", mode="SINGLE", system_index=0
    )

    setup()
    preset = next(iter(presets._item_index))
    result["change_scatter_system_preset"] = check_undo(
        "change_scatter_system_preset", type=preset
    )

    system = setup()
    first_system = system.name
    with bpy.context.temp_override(**view3d_override()):
        bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 30, 0))
        second = bpy.context.active_object
        bpy.ops.mesh.primitive_cube_add(size=0.1, location=(20, 30, 0))
        cube = bpy.context.active_object
        second.select_set(True)
        bpy.context.view_layer.objects.active = second
        with bpy.context.temp_override(active_object=second, selected_objects=[second, cube], object=second):
            bpy.ops.gscatter.scatter_selected_to_active()
        bpy.ops.ed.undo_push(message="second surface")
    result["set_system"] = check_undo("set_system", type=first_system, index=0)

    for op in ("realize_scatter_system", "apply_scatter_system"):
        system = setup()
        with bpy.context.temp_override(**view3d_override()):
            bpy.ops.object.select_all(action="DESELECT")
            system.select_set(True)
            bpy.context.view_layer.objects.active = system
            bpy.ops.ed.undo_push(message="select system")
        result[op] = check_undo(op)

    setup()
    result["set_environment_preview"] = check_undo(
        "set_environment_preview", filepath="/nowhere/preview.png"
    )

    # The effect manager's operators act on the node editor.
    setup()
    override = node_editor_override()
    wm_props = bpy.context.window_manager.gscatter
    wm_props.effect_manager_props.effect_type_toggle = "USER"
    result["create_effect_manager"] = check_undo("create_effect_manager", override)

    store = importlib.import_module(module + ".effects.store").effectstore
    wm_props.effect_items.clear()
    for effect in sorted(store.get_all(), key=lambda e: e.name):
        if effect.namespace == "user":
            item = wm_props.effect_items.add()
            item.name, item.id, item.version = effect.name, effect.id, effect.effect_version
    wm_props.effect_index = 0
    result["edit_effect_tree"] = check_undo("edit_effect_tree", override)

    with bpy.context.temp_override(**override):
        bpy.ops.gscatter.edit_effect_tree()
        bpy.ops.ed.undo_push(message="edit effect")
    wm_props.effect_properties.name = "Renamed Effect"
    result["update_effect_manager"] = check_undo("update_effect_manager", override)

    # Using an item needs an installed asset, so only check it adds an undo step.
    result["use_item"] = {"has_undo": "UNDO" in misc.UseItemOperator.bl_options}
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
            tests = {
                "smoke": smoke,
                "effects": effects,
                "files": files,
                "free_assets": free_assets,
                "undo": undo,
            }
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


if bpy.app.background:
    main()
else:
    # With the interface, wait for the window to open first.
    bpy.app.timers.register(main, first_interval=1)
