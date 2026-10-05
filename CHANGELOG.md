# Changelog

## Unreleased

- Moving and editing objects is no longer slowed down by the number of
  effects in the file. The add-on searched every effect for an Active Camera
  input on every scene update; it now does so only when the scene camera or
  a node tree changes.
- Disabling the add-on now removes all its handlers, so they no longer cause
  errors once it's unloaded.
- The Info panel is shown even when Blender's online access is off, and has a
  Report an Issue button that opens OpenScatter's GitHub issues. GScatter's
  tutorial playlist was removed, so Tutorials now searches YouTube instead.
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
