# cogenerate

> Generator for COGs from GSI emergency-response aerial imagery

Reassemble GSI (国土地理院) disaster-response XYZ tiles -- as surfaced by
[hfu/layers-martin](https://github.com/hfu/layers-martin) -- into
Cloud-Optimized GeoTIFFs, catalog them as static STAC, publish via
Source Cooperative + GitHub Pages, and make them usable in OpenAerialMap.

Part of the [optgeo](https://github.com/optgeo) "Adopt Geodata" family.

## Goal

`layers-martin`'s catalog currently carries **74+ emergency-ortho layers
across 15+ disaster events** (`_do` / `_do_sokuho`-suffixed layer IDs;
re-derive the current count from
[the live catalog](https://hfu.github.io/layers-martin/catalog.json)
rather than trusting this number, since new layers are added whenever a
new disaster response starts and this file won't always be updated the
same day). The goal is to run all of them through this pipeline and get
them into OpenAerialMap, not just the one layer used so far to validate
the pipeline itself.

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
