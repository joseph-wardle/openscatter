#!/usr/bin/env python3
"""Build the extension, install it into a throwaway Blender profile and home
folder, and test it.

    python testing/run_tests.py                      # all tests, with `blender` on PATH
    python testing/run_tests.py --blender ~/blender-5.2/blender smoke

Tests:
  smoke    The extension enables, scatters, every effect can be added,
           dropdowns built from the scene keep their option names, and
           disabling it removes all its handlers.
  effects  Each effect version, added alone to a fresh scatter in each of its
           categories, gives the same instance count and transforms as in
           reference/effects.json, with default settings and with influence,
           invert and each blend type changed in turn.
  custom   Each effect version, saved as a custom effect on this Blender,
           exported, imported and reloaded from the user store, gives the
           same result as the original.
  shared   Effects share the node groups that show no settings, and deleting
           or duplicating a system, reloading the file and editing a shared
           group all keep the scatter working.
  files    The library is in the extension's user folder, or GScatter's if
           there is one, unless another is chosen; nothing is made in
           Documents; the popups don't save the preferences; the extension's
           own folder isn't changed; Python's shared logging is left alone;
           and disabling it removes the asset library it added.
  free_assets
           The free assets list and a download, from a fake local server,
           work, and nothing is requested with online access off; a broken
           or slow server and a cancelled download leave things as they were.
           With experimental features on, the downloaded asset is added to
           the asset browser, with its preview converted to PNG.
  undo     Each operator that changes the scene can be undone in one step.
           This needs Blender's interface, so it runs on a virtual display
           and is skipped if Xvfb isn't installed (or set XVFB to its path).

reference/effects.json is from the original GScatter 0.12.0, run on the Blender
major version each effect was saved with: 3.6 for effects saved in Blender 3.x
(GScatter on 4.x drops some of their links) and 4.2 for those saved in 4.x.
To record it again, run both; each run replaces only its own effects:

    python testing/run_tests.py --blender <blender 3.6> \\
        --extension-zip gscatter-0.12.0.zip --update-reference effects
    python testing/run_tests.py --blender <blender 4.2> \\
        --extension-zip gscatter-0.12.0.zip --update-reference effects

Blender before 4.2 has no extensions, so there the zip is installed as a
legacy add-on, with its pure-Python wheels unpacked next to it.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

TESTING = Path(__file__).resolve().parent
REPO = TESTING.parent
REFERENCE = TESTING / "reference" / "effects.json"
TESTS = ("smoke", "effects", "custom", "shared", "files", "free_assets", "undo")
INTERFACE_TESTS = ("undo",)

# Effects whose output Blender itself changed, so they can't match the
# reference: {effect id: (first Blender version (major, minor) affected, reason)}.
KNOWN_DIFFERENCES = {
    "0d2a8eb9922d4515b758a8c343588d67": (
        (5, 0),
        "Voronoi Texture: Blender 5.x changed the 4D Voronoi node's output",
    ),
}
CHECKSUM_TOLERANCE = 0.01


def run(cmd: list, env: dict, timeout: int):
    proc = subprocess.run(
        cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout
    )
    return proc.returncode, proc.stdout


def start_display():
    """Start a virtual X display for tests that need Blender's interface.
    Returns (Xvfb process, display), or None if Xvfb isn't installed."""
    xvfb = os.environ.get("XVFB") or shutil.which("Xvfb")
    if not xvfb:
        return None
    read, write = os.pipe()
    proc = subprocess.Popen(
        [xvfb, "-displayfd", str(write), "-screen", "0", "1280x1024x24", "-nolisten", "tcp"],
        pass_fds=(write,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    os.close(write)
    with os.fdopen(read) as f:
        display = f.readline().strip()
    if not display:
        proc.kill()
        sys.exit("Xvfb didn't start")
    return proc, ":" + display


def extension_id(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if n.endswith("blender_manifest.toml"))
        manifest = z.read(name).decode()
    return re.search(r'^id\s*=\s*"([^"]+)"', manifest, re.M).group(1)


def install(blender: str, zip_path: Path, version: tuple, env: dict, timeout: int) -> str:
    """Install the zip into the profile in env. Returns the add-on's module."""
    if version >= (4, 2):
        code, out = run(
            [blender, "-b", "--command", "extension", "install-file",
             "-r", "user_default", "-e", str(zip_path)],
            env, timeout,
        )
        if code != 0:
            sys.exit("Install failed:\n" + out)
        return "bl_ext.user_default." + extension_id(zip_path)

    addons = Path(env["BLENDER_USER_RESOURCES"]) / "scripts" / "addons"
    with zipfile.ZipFile(zip_path) as z:
        top = {n.split("/")[0] for n in z.namelist()}
        if len(top) != 1:
            sys.exit(f"{zip_path.name} has no top-level folder to install as a legacy add-on")
        module = top.pop()
        z.extractall(addons)
    for wheel in (addons / module / "wheels").glob("*-none-any.whl"):
        with zipfile.ZipFile(wheel) as z:
            z.extractall(addons / "modules")
    return module


def blender_version(blender: str) -> tuple:
    _, out = run([blender, "--version"], dict(os.environ), 60)
    match = re.search(r"Blender (\d+)\.(\d+)", out)
    return (int(match.group(1)), int(match.group(2)))


def check_smoke(result: dict) -> list[str]:
    errors = []
    if result["blocking_threads"]:
        errors.append(
            "threads would stop background Blender from exiting: "
            + ", ".join(result["blocking_threads"])
        )
    if result["scatter"]["instances"] == 0:
        errors.append("scatter produced no instances")
    for effect, message in result["effects_failed"].items():
        errors.append(f"adding {effect} failed: {message}")
    if result["effects_added"] == 0:
        errors.append("no effects were added")
    if not result["icons"]:
        errors.append("no icons were loaded")
    for name, icon in result["icons"].items():
        if "error" in icon:
            errors.append(f"loading icon {name!r} failed: {icon['error']}")
        elif name and (
            icon["icon_size"] != [32, 32]
            or 0 in icon["image_size"]
            or not icon["visible"]
        ):
            errors.append(f"icon {name} didn't load: {icon}")
    if result.get("handlers_left"):
        errors.append(
            "handlers left after disabling: " + ", ".join(result["handlers_left"])
        )
    for name, enum in result["enums"].items():
        if not enum["items"]:
            errors.append(f"dropdown {name} has no items")
        if not enum["kept"]:
            errors.append(f"dropdown {name}'s items aren't kept between calls")
        if enum["wrong"]:
            errors.append(f"dropdown {name} shows wrong names: " + ", ".join(enum["wrong"]))
    return errors


def same_major(saved_with: list, version: tuple) -> bool:
    return saved_with[0] == version[0]


def update_reference(result: dict, version: tuple, zip_path: Path):
    """Replace the reference's results for effects saved with this Blender
    major version, keeping the others."""
    reference = json.loads(REFERENCE.read_text()) if REFERENCE.exists() else {}
    saved_with = {**reference.get("saved_with", {}), **result["saved_with"]}
    effects = {
        key: value
        for key, value in reference.get("effects", {}).items()
        if not same_major(saved_with[key.split(" ")[0]], version)
    }
    recorded = 0
    for key, value in result["effects"].items():
        if same_major(saved_with[key.split(" ")[0]], version):
            effects[key] = value
            recorded += 1
    if reference.get("base") not in (None, result["base"]):
        print(f"  note: plain scatter differs from the existing reference: {reference['base']}")
    recorded_with = reference.get("recorded_with", {})
    recorded_with[f"saved with Blender {version[0]}.x"] = (
        f"{zip_path.name} on Blender {result['blender']}"
    )
    REFERENCE.parent.mkdir(exist_ok=True)
    REFERENCE.write_text(json.dumps(
        {"base": result["base"], "effects": effects, "recorded_with": recorded_with,
         "saved_with": saved_with},
        indent=1, sort_keys=True,
    ) + "\n")
    print(f"Saved {recorded} results to {REFERENCE.relative_to(REPO)}")


def check_effects(result: dict, version: tuple) -> tuple[list[str], list[str]]:
    reference = json.loads(REFERENCE.read_text())
    errors = []
    # Notes are grouped per effect version, as most apply to all its results.
    notes = {}

    def same(a: dict, b: dict) -> bool:
        return (
            a.get("error") is None
            and a["instances"] == b["instances"]
            and abs(a["checksum"] - b["checksum"]) <= CHECKSUM_TOLERANCE
        )

    def show(r: dict) -> str:
        if r.get("error"):
            return "error: " + r["error"]
        return f"{r['instances']} instances, checksum {r['checksum']}"

    if not same(result["base"], reference["base"]):
        errors.append(f"plain scatter: expected {show(reference['base'])}, got {show(result['base'])}")

    for key, expected in reference["effects"].items():
        got = result["effects"].get(key)
        label = f"{expected['name']} ({key})"
        effect = f"{expected['name']} ({key.split(' ')[0]})"
        if got is None:
            errors.append(f"{label}: missing")
        elif expected.get("error"):
            # GScatter itself failed here, so there's nothing to compare with.
            if got.get("error"):
                notes.setdefault(effect, set()).add("fails, as it did in GScatter")
            else:
                notes.setdefault(effect, set()).add("works, but failed in GScatter")
        elif not same(got, expected):
            known = KNOWN_DIFFERENCES.get(key.split("@")[0])
            if known and version >= known[0]:
                notes.setdefault(effect, set()).add(f"differs as expected: {known[1]}")
            else:
                errors.append(f"{label}: expected {show(expected)}, got {show(got)}")
    for key in result["effects"].keys() - reference["effects"].keys():
        notes.setdefault(key.split(" ")[0], set()).add("not in the reference, not checked")
    notes = [f"{effect}: {message}" for effect, messages in sorted(notes.items())
             for message in sorted(messages)]
    return errors, notes


def check_custom(result: dict) -> list[str]:
    errors = []
    for key, r in result["effects"].items():
        label = f"{r['name']} ({key})"
        if r.get("error"):
            errors.append(f"{label}: error: {r['error']}")
        elif r["instances"] != r["saved"]["instances"] or (
            abs(r["checksum"] - r["saved"]["checksum"]) > CHECKSUM_TOLERANCE
        ):
            errors.append(
                f"{label}: {r['instances']} instances, checksum {r['checksum']}"
                f" before saving, {r['saved']['instances']} instances, checksum"
                f" {r['saved']['checksum']} after"
            )
    if not result["effects"]:
        errors.append("no effects were saved")
    return errors


def check_shared(result: dict) -> list[str]:
    errors = []
    if result["shared"] == 0:
        errors.append("no node groups were shared")
    if not result["delete"]["before"]:
        errors.append("the first system scattered nothing")
    if result["second_system_new_shared"]:
        errors.append(
            "a second system with the same effects built its own groups: "
            + ", ".join(result["second_system_new_shared"])
        )
    if not result["second_system"]:
        errors.append("the second system scattered nothing")
    delete = result["delete"]
    if delete["after"] != delete["before"]:
        errors.append(
            f"deleting the second system changed the first: {delete['before']} before, {delete['after']} after"
        )
    duplicate = result["duplicate"]
    if not (duplicate["original"] == duplicate["copy"] == duplicate["after_deleting_original"]):
        errors.append(
            f"duplicating: original {duplicate['original']}, copy {duplicate['copy']},"
            f" copy after deleting the original {duplicate['after_deleting_original']}"
        )
    for label, r in (("deleting", delete), ("duplicating", duplicate)):
        if r["empty_group_nodes"]:
            errors.append(f"{label} left {r['empty_group_nodes']} group nodes with no node group")
    if result["reload_new_shared"]:
        errors.append(
            "after reloading, effects built their own groups: "
            + ", ".join(result["reload_new_shared"])
        )
    edit = result["edit"]
    if edit is None:
        errors.append("there was no shared mixer group to edit")
    elif edit["users_after"] != edit["users_before"] or not edit["rebuilt"]:
        errors.append(f"new effects reused an edited shared group: {edit}")
    return errors


def check_files(result: dict) -> list[str]:
    checks = {
        "library": "the library isn't in the extension's user folder by default",
        "library_used": "the library folder wasn't made in the extension's user folder",
        "gscatter_library": "GScatter's library in Documents isn't used when it exists",
        "chosen_library": "the chosen library folder isn't used",
        "cleared_library": "clearing the library folder doesn't go back to the default",
        "preferences_dirty": "the popups don't mark the preferences as changed",
        "developer_can_store": "developer mode can't save the bundled stores",
        "asset_library_added": "enabling experimental features doesn't add the asset library",
    }
    errors = [message for key, message in checks.items() if not result[key]]
    if result["online_access"]:
        errors.append("online access is on in the test profile")
    if result["root_logger"] != {"handlers": 0, "level": 30}:
        errors.append(f"the root logger was changed: {result['root_logger']}")
    if result["level_25_name"] != "Level 25":
        errors.append(f"logging level 25 was renamed {result['level_25_name']!r}")
    if result["documents_used"]:
        errors.append("a folder was made in Documents")
    if result["userpref_saved"]:
        errors.append("the popups saved the preferences")
    if not result["bundled_count"]:
        errors.append("no bundled stores were found")
    if result["asset_library_left"]:
        errors.append("disabling didn't remove the asset library")
    if result["package_changed"]:
        errors.append(
            "the extension's folder was changed: " + ", ".join(result["package_changed"])
        )
    return errors


def check_free_assets(result: dict) -> list[str]:
    errors = []
    listed = [["test_plant", True]]

    def check_load(label: str, r: dict, assets: list, requested: bool):
        if r["loading_after"]:
            errors.append(f"{label}: still loading after the download finished")
        if r["assets"] != assets:
            errors.append(f"{label}: expected free assets {assets}, got {r['assets']}")
        if requested and not r["requests"]:
            errors.append(f"{label}: nothing was requested")
        if not requested and r["requests"]:
            errors.append(f"{label}: requested {r['requests']} with online access off")

    check_load("offline before any download", result["offline_first"], [], False)
    check_load("loading the list", result["online"], listed, True)
    if not result["online"]["loading_while_waiting"]:
        errors.append("loading the list: didn't show that it was loading")
    if not result["list_saved"]:
        errors.append("the list wasn't saved")
    check_load("offline", result["offline"], listed, False)
    check_load("broken server", result["broken"], listed, True)
    check_load("slow server", result["slow"], listed, True)
    if result["slow"]["seconds"] > 2.5:
        errors.append(f"slow server: took {result['slow']['seconds']} s despite the timeout")

    for label in ("download", "download_broken", "cancel", "browser_download"):
        r = result[label]
        if "error" in r:
            errors.append(f"{label}: {r['error']}")
        elif not r["downloading_while_waiting"] or r["downloading_after"]:
            errors.append(f"{label}: downloading was {r['downloading_while_waiting']}"
                          f" while waiting and {r['downloading_after']} after")
        elif not r["requests"]:
            errors.append(f"{label}: nothing was requested")
    if not result["installed"]:
        errors.append("the downloaded asset wasn't installed")
    if result["cancel"].get("seconds", 0) > 5:
        errors.append(f"cancelling took {result['cancel']['seconds']} s")
    if result["leftovers"]:
        errors.append(f"failed downloads left files in the library: {result['leftovers']}")
    if result["offline_operator"]:
        errors.append("the Download button works with online access off")
    if not all(result["references"].values()):
        errors.append(f"finding assets from references failed: {result['references']}")
    if not result["browser_blend"]:
        errors.append("with experimental features, the asset browser file wasn't made")
    elif result.get("browser_assets") != ["Test Plant Spring"]:
        errors.append(
            f"the asset browser file has assets {result.get('browser_assets')}, "
            "not ['Test Plant Spring']"
        )
    preview = result.get("preview_png")
    if not preview:
        errors.append("the variant's BIP preview wasn't saved as a PNG")
    elif not all(preview.values()):
        errors.append(f"the variant's preview PNG is wrong: {preview}")
    return errors


def check_undo(result: dict) -> list[str]:
    errors = []
    for op, r in sorted(result.items()):
        if not isinstance(r, dict):
            continue
        if "error" in r:
            errors.append(f"{op}: {r['error']}")
        elif "has_undo" in r:
            if not r["has_undo"]:
                errors.append(f"{op}: has no UNDO option")
        elif not r["changed"]:
            errors.append(f"{op}: changed nothing, so its undo wasn't tested")
        elif r["not_undone"]:
            errors.append(f"{op}: undo didn't restore {', '.join(r['not_undone'])}")
    return errors


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("tests", nargs="*", metavar="test", help=", ".join(TESTS) + " (default: all)")
    parser.add_argument("--blender", default="blender", help="Blender executable")
    parser.add_argument("--extension-zip", type=Path, help="test this zip instead of building the repo")
    parser.add_argument("--update-reference", action="store_true", help="save the effects results as the reference")
    parser.add_argument("--timeout", type=int, default=900, help="seconds per Blender run")
    args = parser.parse_args()
    tests = args.tests or list(TESTS)
    for test in tests:
        if test not in TESTS:
            parser.error(f"unknown test {test!r}, choose from {', '.join(TESTS)}")

    with tempfile.TemporaryDirectory(prefix="openscatter-tests-") as tmp:
        tmp = Path(tmp)
        # The add-on keeps its library in the home folder, so use a fresh one.
        home = tmp / "home"
        home.mkdir()
        env = dict(
            os.environ,
            BLENDER_USER_RESOURCES=str(tmp / "profile"),
            HOME=str(home),
            USERPROFILE=str(home),
        )

        version = blender_version(args.blender)
        zip_path = args.extension_zip
        if zip_path is None:
            if version < (4, 2):
                sys.exit("Blender before 4.2 can't build extensions; pass --extension-zip")
            code, out = run(
                [args.blender, "--command", "extension", "build",
                 "--source-dir", str(REPO), "--output-dir", str(tmp)],
                env, args.timeout,
            )
            zips = list(tmp.glob("*.zip"))
            if code != 0 or not zips:
                sys.exit("Build failed:\n" + out)
            zip_path = zips[0]
        module = install(args.blender, zip_path, version, env, args.timeout)
        print(f"Testing {zip_path.name} ({module}) on Blender {version[0]}.{version[1]}")
        failed = False
        display = None
        for test in tests:
            output = tmp / f"{test}.json"
            test_env, background = env, ["-b"]
            if test in INTERFACE_TESTS:
                display = display or start_display()
                if display is None:
                    print(f"skip {test}: needs Xvfb")
                    continue
                # Never the desktop's own display: without WAYLAND_DISPLAY,
                # Blender still finds the desktop's Wayland socket in
                # XDG_RUNTIME_DIR, so give it an empty one.
                runtime = tmp / "runtime"
                runtime.mkdir(mode=0o700, exist_ok=True)
                test_env = {k: v for k, v in env.items() if k != "WAYLAND_DISPLAY"}
                test_env.update(DISPLAY=display[1], XDG_RUNTIME_DIR=str(runtime))
                background = []
            try:
                code, log = run(
                    [args.blender, *background, "--python-exit-code", "1",
                     "--python", str(TESTING / "blender_tests.py"),
                     "--", module, test, str(output)],
                    test_env, args.timeout,
                )
            except subprocess.TimeoutExpired:
                print(f"FAIL {test}: Blender didn't exit within {args.timeout} s")
                failed = True
                continue
            if not output.exists():
                print(f"FAIL {test}: no results (exit code {code})\n{log}")
                failed = True
                continue
            result = json.loads(output.read_text())
            notes = []
            if result.get("error"):
                errors = [result["error"]]
            elif not result.get("enabled"):
                errors = ["the extension could not be enabled\n" + log]
            elif test == "smoke":
                errors = check_smoke(result)
            elif test == "custom":
                errors = check_custom(result)
            elif test == "shared":
                errors = check_shared(result)
            elif test == "files":
                errors = check_files(result)
            elif test == "free_assets":
                errors = check_free_assets(result)
            elif test == "undo":
                errors = check_undo(result)
            elif args.update_reference:
                update_reference(result, version, zip_path)
                continue
            else:
                errors, notes = check_effects(result, version)

            for note in notes:
                print(f"  note: {note}")
            if errors:
                failed = True
                print(f"FAIL {test}:")
                for error in errors:
                    print(f"  {error}")
            else:
                print(f"ok   {test}")

        if display:
            display[0].kill()

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
