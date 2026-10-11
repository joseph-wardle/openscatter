# OpenScatter

A free scattering add-on for Blender, built on geometry nodes. It scatters any
object over a surface and lets you control density, scale and rotation, and
layer effects, for quickly building environments like meadows or forests.

OpenScatter is a community-maintained fork of **GScatter** 0.12.0 by Graswald
GmbH, which is no longer maintained. It is not affiliated with or endorsed by
Graswald GmbH. See [`NOTICE`](NOTICE) for credits and licensing.

## Using OpenScatter

Open the *OpenScatter* tab in the 3D Viewport's sidebar (<kbd>N</kbd>), pick
the surface to scatter on as the *Emitter*, select the objects to scatter, and
click *Scatter selected*. Add effects to a system to control where instances go
and how they're scaled and rotated.

OpenScatter's interface is the same as GScatter's, so GScatter's
[documentation](https://www.notion.so/graswald/Help-Support-Documentation-8822cee19a4944beb30bc6f80c6c699a)
by Graswald and GScatter tutorials on YouTube apply. What's different:

- The panel, menus and messages say OpenScatter, and the Graswald logos are
  gone.
- Effects share the node groups that show no settings, so editing one of those
  by hand in the node editor changes it for every effect that uses it.
- Voronoi Texture gives a different pattern on Blender 5.0 and later.
- Downloaded assets, environments and your own effects and presets are kept
  in Blender's extension data folder, or in GScatter's `Documents/GScatter`
  if you have it, unless you choose a folder in the preferences.

Report bugs and ask questions on the
[issue tracker](https://github.com/joseph-wardle/openscatter/issues).

## Status

Works on Blender 4.2 to 5.2. Every bundled effect gives the same result on
5.2 as GScatter 0.12.0 does on 4.2, except Voronoi Texture, because Blender
5.x changed the output of the 4D Voronoi node itself.

Effects are stored as JSON node trees from older Blender versions and are
upgraded when loaded (`effects/store/legacy.py`). If a future Blender
version renames node sockets or changes node defaults, that is where to add
the mapping.

## Compatibility with GScatter scenes

Internal identifiers (`gscatter.*` operators, the `gscatter` property groups,
"GScatter" node and collection names) are unchanged on purpose, so scenes made
with GScatter keep working. Because of this, don't enable GScatter and
OpenScatter at the same time; they register the same identifiers.

## Building

```sh
blender --command extension build --source-dir . --output-dir dist
```

Install the resulting `.zip` via *Edit → Preferences → Get Extensions →
Install from Disk*.

The effect icons in `icons/` are drawn by `tools/draw_icons.py` (needs NumPy);
run `python tools/draw_icons.py` after changing it to redraw them.

## Testing

```sh
python testing/run_tests.py                          # uses `blender` on PATH
python testing/run_tests.py --blender /path/to/blender smoke
```

This builds the extension and installs it into a throwaway Blender profile
and home folder, so your own setup and library aren't touched. Then it runs:

- `smoke`: the extension enables, scatters, every effect can be added and
  every icon loads, dropdowns built from the scene keep their option names,
  nothing would stop background Blender from exiting, and disabling it
  removes all its handlers.
- `effects`: every version of every effect, added alone to a fresh scatter
  in each of its categories, gives the same result as
  `testing/reference/effects.json`, with default settings and with influence,
  invert and each blend type changed in turn. That file was recorded from the
  original GScatter 0.12.0 on the Blender each effect was made for (3.6 for
  effects saved in Blender 3.x, 4.2 for those saved in 4.x); see
  `testing/run_tests.py` for how to record it again.
- `custom`: every version of every effect, saved as a custom effect on the
  running Blender, exported, imported and reloaded from the user effect
  store, gives the same result as before it was saved.
- `shared`: effects share the node groups that show no settings, and
  deleting or duplicating a system, reloading the file and editing a shared
  group all keep the scatter working.
- `files`: the library is kept in the extension's user folder, or GScatter's
  if there is one, unless another is chosen; nothing is made in Documents;
  the popups don't save your preferences; the extension's own folder isn't
  changed; Python's shared logging is left alone; and disabling it removes
  the asset library it added.
- `free_assets`: the free asset list and a download, from a fake local
  server, work; nothing is requested with online access off; and a broken or
  slow server or a cancelled download leaves things as they were. With
  experimental features on, the downloaded asset is added to the asset
  browser, with its preview converted to PNG.
- `undo`: each operator that changes the scene can be undone in one step.
  Undo needs Blender's interface, so this runs Blender on a virtual display
  and is skipped if [Xvfb](https://www.x.org/releases/current/doc/man/man1/Xvfb.1.xhtml)
  isn't installed (or set `XVFB` to its path).

GitHub Actions runs them all on Blender 4.2 and 5.2 for every push. Run them
yourself against any other version you support, especially new releases.

## License

GPL-3.0-or-later. See [`LICENSE`](LICENSE).
