#!/usr/bin/env python3
"""Build the extension, install it into a throwaway Blender profile and test it.

    python testing/run_tests.py                      # all tests, with `blender` on PATH
    python testing/run_tests.py --blender ~/blender-5.2/blender smoke

Tests:
  smoke    The extension enables, scatters, and every effect can be added.
  effects  Each effect, added alone to a fresh scatter, gives the same instance
           count and transforms as in reference/effects.json.

reference/effects.json was recorded from the original GScatter 0.12.0 on
Blender 4.2, where GScatter worked as designed. To record it again:

    python testing/run_tests.py --blender <blender 4.2> \\
        --extension-zip gscatter-0.12.0.zip --update-reference effects
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


def check_effects(result: dict, version: tuple) -> tuple[list[str], list[str]]:
    reference = json.loads(REFERENCE.read_text())
    errors, notes = [], []

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
        if got is None:
            errors.append(f"{label}: missing")
        elif not same(got, expected):
            known = KNOWN_DIFFERENCES.get(key.split("@")[0])
            if known and version >= known[0]:
                notes.append(f"{label}: differs as expected ({known[1]})")
            else:
                errors.append(f"{label}: expected {show(expected)}, got {show(got)}")
    for key in result["effects"].keys() - reference["effects"].keys():
        notes.append(f"{key}: not in the reference, not checked")
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

        zip_path = args.extension_zip
        if zip_path is None:
            code, out = run(
                [args.blender, "--command", "extension", "build",
                 "--source-dir", str(REPO), "--output-dir", str(tmp)],
                env, args.timeout,
            )
            zips = list(tmp.glob("*.zip"))
            if code != 0 or not zips:
                sys.exit("Build failed:\n" + out)
            zip_path = zips[0]
        ext_id = extension_id(zip_path)

        code, out = run(
            [args.blender, "-b", "--command", "extension", "install-file",
             "-r", "user_default", "-e", str(zip_path)],
            env, args.timeout,
        )
        if code != 0:
            sys.exit("Install failed:\n" + out)

        version = blender_version(args.blender)
        print(f"Testing {zip_path.name} ({ext_id}) on Blender {version[0]}.{version[1]}")
        failed = False
        for test in tests:
            output = tmp / f"{test}.json"
            try:
                code, log = run(
                    [args.blender, "-b", "--python-exit-code", "1",
                     "--python", str(TESTING / "blender_tests.py"),
                     "--", ext_id, test, str(output)],
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
                REFERENCE.parent.mkdir(exist_ok=True)
                del result["enabled"], result["blocking_threads"]
                result["recorded_with"] = zip_path.name
                REFERENCE.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
                print(f"Saved {len(result['effects'])} effects to {REFERENCE.relative_to(REPO)}")
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
