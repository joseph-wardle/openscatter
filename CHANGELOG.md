# Changelog

## Unreleased

- Moving and editing objects is no longer slowed down by the number of
  effects in the file. The add-on searched every effect for an Active Camera
  input on every scene update; it now does so only when the scene camera or
  a node tree changes.
- Effects now share the node groups inside them that show no settings,
  instead of each building its own copy. With 20 systems of 5 effects, the
  file has half as many node groups and is half the size (34 MB instead of
  67 MB), and scattering and adding effects are two to three times faster.
  Editing one of these shared groups by hand changes it for every effect that
  uses it; effects added afterwards get a fresh copy.
- Icons and asset previews are loaded by OpenScatter itself instead of the
  bundled t3dn-bip package, which added the user's Python packages folder to
  Blender's import path. Asset previews load about five times faster.
- The Documentation button opens a short guide in OpenScatter's README, which
  links to GScatter's documentation and lists what's different.
- Creating an environment no longer hangs Blender on Linux and macOS. If
  making its data.blend fails, it now shows an error instead of waiting forever.
- Free asset downloads no longer change Blender's data from a background
  thread, which could crash Blender, and a slow or unreachable server now
  gives an error instead of waiting forever. Cancel Download works, and if
  the list of free assets can't be downloaded, the last one is shown. With
  Blender's online access off, nothing is downloaded, not even icons, and the
  Download button says why it's disabled.
- Syncing old assets with the asset browser no longer changes Blender's data
  from a background thread.
- Ctrl+Z now undoes changing a system's preset, linking a system, moving,
  selecting or swapping an effect, painting a weight map, updating an old
  system, realizing or applying a system, using an asset, and the effect
  manager's create, edit and update buttons, instead of also undoing the step
  before. Undoing Apply Scatter System no longer crashes Blender.
- Dropdowns whose options depend on the scene, like presets, blend types,
  effects and systems, keep their option names in memory as Blender requires,
  so the names can't turn into garbage or crash Blender.
- Disabling the add-on now removes all its handlers, so they no longer cause
  errors once it's unloaded.
- The Info panel is shown even when Blender's online access is off, and has a
  Report an Issue button that opens OpenScatter's GitHub issues. GScatter's
  tutorial playlist was removed, so Tutorials now searches YouTube instead.
- The effect icons are redrawn for OpenScatter and released as CC0, as
  extensions.blender.org requires. The effect select button, proxy toggle and
  environment picker use Blender's own icons, and unused icons were removed.
- Removed version 1.1.0 of Distribute on Vertices from the effect manager. It
  was written for an older scatter system and couldn't be added in GScatter
  0.12 either. Scenes that use it are unaffected, and 2.1.1 replaces it.

## 0.13.0

The first OpenScatter release, based on GScatter 0.12.0 by Graswald.

- Renamed to OpenScatter and removed the Graswald logos. Internal names are
  unchanged, so .blend files made with GScatter keep working.
- Works on Blender 4.2 to 5.2. Effects saved by older Blender versions are
  upgraded when they are added, so they behave as they did in GScatter.
  Voronoi Texture is the exception: Blender 5.x changed the 4D Voronoi node.
- Fixed a crash when adding an effect whose node group has no influence,
  blend mode or invert input, which used an API removed in Blender 4.0.
- Background Blender (`blender -b`) no longer hangs on exit with the add-on
  enabled.
- Removed the bundled Pillow, jsonschema, attrs and pyrsistent packages,
  which stopped the extension from enabling on Blender 5.x.
- The version warning now covers Blender 4.2 to 5.2.
- Added a test suite that checks every effect against GScatter 0.12.0.
