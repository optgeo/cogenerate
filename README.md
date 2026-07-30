# cogenerate

> Generator for COGs from GSI emergency-response aerial imagery

Reassemble GSI (国土地理院) disaster-response XYZ tiles -- as surfaced by
[hfu/layers-martin](https://github.com/hfu/layers-martin) -- into
Cloud-Optimized GeoTIFFs, catalog them as static STAC, publish via
Source Cooperative + GitHub Pages, and make them usable in OpenAerialMap.

Part of the [optgeo](https://github.com/optgeo) "Adopt Geodata" family.

See `CLAUDE.md` for architecture and rationale, `HANDOVER.md` for the
current session's status and untested parts.

```sh
uv sync
LAYER=20260729kumamoto_yatsushiro_0729do_sokuho SEED_X=883 SEED_Y=414 just run
```

(`just`'s recipe variables are read as environment variables -- set them
*before* the recipe name, not after; `just run LAYER=...` fails with
"justfile does not contain recipe `LAYER=...`".)
