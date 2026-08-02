# cogenerate

> Generator for COGs from GSI emergency-response aerial imagery

GSI (国土地理院) has a strong, decades-long track record of publishing
new aerial imagery as ZXY tiles within days of a disaster -- as
surfaced by [hfu/layers-martin](https://github.com/hfu/layers-martin).
This project complements that with a distribution format suited to
cloud-native GIS and ML workflows: reassemble the same imagery into
Cloud-Optimized GeoTIFFs, catalog it as static STAC alongside the
existing tiles, publish via Source Cooperative + GitHub Pages, and
make it usable in OpenAerialMap.

Part of the [optgeo](https://github.com/optgeo) "Adopt Geodata" family.

## About this data

This pipeline reprocesses real disaster-response aerial photography --
landslides, floods, earthquake damage, volcanic activity -- captured
in the days after events that, in a number of cases, caused
significant loss of life and property (the 2014 Hiroshima landslides,
the 2016 Kumamoto earthquake, and the 2024 Noto Peninsula earthquake,
among others, are all represented in this archive). GSI already
publishes this imagery openly as part of its own disaster-response and
public-transparency mission; this project's role is narrowly to make
the same imagery easier to use in cloud-native GIS/ML tooling and
humanitarian mapping platforms (OpenAerialMap) -- not to originate,
curate for impact, or editorialize on it. Any prose this pipeline
produces (commit messages, STAC item text, this README) sticks to
location, date, and capture method; damage assessment and human impact
are out of scope for what a tile-reprocessing pipeline is positioned
to say.

## License and attribution

This repository's own code (the pipeline, not the imagery it
processes) is **CC0-1.0** -- see `LICENSE`.

The GSI aerial imagery itself is a **separate matter, not covered by
that CC0 grant**. GSI publishes it under Japan's government-standard
usage terms (政府標準利用規約), CC-BY-4.0-compatible but requiring
attribution: credit "国土地理院" (Geospatial Information Authority of
Japan) with a link to
<https://maps.gsi.go.jp/development/ichiran.html>. Every published
STAC Item carries this in its `license`/`links` fields (`DECISIONS.md`
D19); `source-coop/README.md` is the canonical data-facing statement
of this requirement for anyone consuming the COGs directly from Source
Cooperative without ever visiting this repository.

## Goal

`layers-martin`'s catalog carries emergency-ortho layers across many
disaster events -- **194 confirmed as of 2026-07-31** (re-derive with
`uv run python -m cogenerate.candidates`, which checks each catalog
entry against `ichiran.html`'s actual disaster-response table
structure rather than guessing from the ID string; don't trust a fixed
number here, new layers are added whenever a new disaster response
starts). The goal is to run all of them through this pipeline and get
them into OpenAerialMap. **48/194 published as of 2026-08-01** --
re-run `candidates.py` (its stderr summary line reports both numbers)
rather than trusting this fraction, it moves often.

The archive turns out to span further than expected: this year's
Kumamoto/Noto-era disaster response back through 1947-48 and 1962
reference imagery of Hiroshima (kept by GSI alongside its 2014
landslide-disaster layers, for land-use comparison against the
present day) -- all 10 Hiroshima-area layers are published as of
2026-08-01, prioritized ahead of FOSS4G 2026 Hiroshima
(`candidates.py --keyword <text>` supports this kind of temporary
geographic priority; see `HANDOVER.md` for the current pick order).

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
