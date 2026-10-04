#!/usr/bin/env python3
"""Build the extension, install it into a throwaway Blender profile and test it.

    python testing/run_tests.py                      # all tests, with `blender` on PATH
    python testing/run_tests.py --blender ~/blender-5.2/blender smoke

Tests:
  smoke    The extension enables, scatters, and every effect can be added.
  effects  Each effect version, added alone to a fresh scatter in each of its
           categories, gives the same instance count and transforms as in
           reference/effects.json, with default settings and with influence,
           invert and each blend type changed in turn.

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
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

TESTING = Path(__file__).resolve().parent
REPO = TESTING.parent
REFERENCE = TESTING / "reference" / "effects.json"
TESTS = ("smoke", "effects")

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


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("tests", nargs="*", metavar="test", help="smoke, effects (default: all)")
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
        env = dict(os.environ, BLENDER_USER_RESOURCES=str(tmp / "profile"))

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
        for test in tests:
            output = tmp / f"{test}.json"
            try:
                code, log = run(
                    [args.blender, "-b", "--python-exit-code", "1",
                     "--python", str(TESTING / "blender_tests.py"),
                     "--", module, test, str(output)],
                    env, args.timeout,
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

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
