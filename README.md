# OpenScatter

A free scattering add-on for Blender, built on geometry nodes. It scatters any
object over a surface and lets you control density, scale and rotation, and
layer effects, for quickly building environments like meadows or forests.

OpenScatter is a community-maintained fork of **GScatter** 0.12.0 by Graswald
GmbH, which is no longer maintained. It is not affiliated with or endorsed by
Graswald GmbH. See [`NOTICE`](NOTICE) for credits and licensing.

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

## License

GPL-3.0-or-later. See [`LICENSE`](LICENSE).
