# cogenerate

> Generator for COGs from GSI emergency-response aerial imagery

Reassemble GSI (国土地理院) disaster-response XYZ tiles -- as surfaced by
[hfu/layers-martin](https://github.com/hfu/layers-martin) -- into
Cloud-Optimized GeoTIFFs, catalog them as static STAC, publish via
Source Cooperative + GitHub Pages, and make them usable in OpenAerialMap.

Part of the [optgeo](https://github.com/optgeo) "Adopt Geodata" family.

## Goal

`layers-martin`'s catalog carries emergency-ortho layers across many
disaster events -- **194 confirmed as of 2026-07-31** (re-derive with
`uv run python -m cogenerate.candidates`, which checks each catalog
entry against `ichiran.html`'s actual disaster-response table
structure rather than guessing from the ID string; don't trust a fixed
number here, new layers are added whenever a new disaster response
starts). The goal is to run all of them through this pipeline and get
them into OpenAerialMap, not just the handful published so far.

## Documentation map

| File | Purpose | Audience |
|---|---|---|
| `README.md` | What this is, why, quickstart | Humans |
| `CLAUDE.md` | How to operate this repo day to day (conventions, facts about the data source, commands) | Claude sessions, and humans who want the same grounding |
| `DECISIONS.md` | *Why* things are the way they are -- ADR log, stable | Both; read before reconsidering something that looks arbitrary |
| `HANDOVER.md` | *What happened*, session by session, and what to do first if resuming cold (e.g. after `/clear`) | Whoever (human or Claude) picks this up next |

Each file has one job -- decisions don't get re-explained in
`HANDOVER.md`, and session narrative doesn't get buried in
`DECISIONS.md`.

```sh
uv sync
LAYER=20260729kumamoto_yatsushiro_0729do_sokuho SEED_X=883 SEED_Y=414 just run
just upload       # publish to Source Cooperative (needs source-coop login once, D10)
just stac         # build/refresh this layer's STAC Item + the catalog (D19)
```

(`just`'s recipe variables are read as environment variables -- set them
*before* the recipe name, not after; `just run LAYER=...` fails with
"justfile does not contain recipe `LAYER=...`".)

## Static STAC catalog

Every published layer gets a STAC 1.0.0 Item (`stac_item.py`) linked
from a top-level Catalog (`stac_catalog.py`), served via GitHub Pages:

- Catalog: https://optgeo.github.io/cogenerate/catalog.json
- One Item: https://optgeo.github.io/cogenerate/items/20260729kumamoto_yatsushiro_0729do_sokuho.json

View an Item in a STAC browser, e.g.
[moregeo.it's](https://browser.moregeo.it/external/optgeo.github.io/cogenerate/items/20260729kumamoto_yatsushiro_0729do_sokuho.json?.asset=asset-imagery)
(`?.asset=asset-imagery` selects the COG asset for preview).

Schema/asset conventions are modeled on sibling repo
[optgeo/oam-starc](https://github.com/optgeo/oam-starc) -- see
`DECISIONS.md` D6/D19 for why, and for the eventual OpenAerialMap
ingestion plan this catalog is meant to support.
