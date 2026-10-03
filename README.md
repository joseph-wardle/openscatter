# OpenScatter

A free scattering add-on for Blender, built on geometry nodes. It scatters any
object over a surface and lets you control density, scale and rotation, and
layer effects, for quickly building environments like meadows or forests.

OpenScatter is a community-maintained fork of **GScatter** 0.12.0 by Graswald
GmbH, which is no longer maintained. It is not affiliated with or endorsed by
Graswald GmbH. See [`NOTICE`](NOTICE) for credits and licensing.

## Status

Work in progress: porting to Blender 5.x. Known issues on Blender 5.2:

- The bundled Pillow wheels are built for Python 3.11, so Blender refuses to
  enable the extension.
- The bundled `attrs` wheel conflicts with Blender's own extension system.
- Scattering fails because the Random Value node is indexed by socket position
  (`scatter/functions.py`).
- Effect node trees lose links whose socket identifiers changed in 5.x, such as
  `A_STR`/`B_STR` on Compare nodes.
- With the add-on enabled, `blender -b` never exits because the `t3dn_bip`
  reader threads aren't daemon threads.

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
