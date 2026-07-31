# CLAUDE.md

Guidance for Claude (Code or chat) working on this repository.

**Doc map**: this file is *how to operate* day to day. `DECISIONS.md` is
*why* things are the way they are (ADR log -- read it before
reconsidering something that looks arbitrary). `HANDOVER.md` is *what
happened*, session by session, and what to do first if you're resuming
cold (e.g. after `/clear`).

## Language policy (DECISIONS.md D8)

- Converse with Hidenori (chat, CLI turns, questions) in **Japanese**.
- Everything that lands in the repository -- code, comments, docstrings,
  `.md` prose, commit messages, PR descriptions -- stays in **English**,
  matching the rest of the optgeo family. Don't mix: a Japanese-language
  commit message or doc section is as wrong here as an English chat
  reply.

## Repo metadata (for whoever runs `gh repo create`)

- Description (English, GitHub repo field): "Generator for COGs from GSI
  emergency-response aerial imagery"
- License: CC0-1.0, matching sibling optgeo repos.

## Mission

Reassemble GSI (国土地理院) disaster-response XYZ tile layers -- served
via `hfu/layers-martin` (a Martin `/catalog` front end that mirrors GSI's
own `cyberjapandata.gsi.go.jp/xyz/{layer}/{z}/{x}/{y}.{ext}` tile IDs) --
into Cloud-Optimized GeoTIFFs (COGs), catalog them as a static STAC, and
make them usable in OpenAerialMap.

Pipeline: **layers-martin catalog → probe → download → georef → COG →
Source Cooperative upload → static STAC → GitHub Pages → OpenAerialMap**.

This is one instance of the `optgeo` "Adopt Geodata" pattern: adopt an
open geospatial dataset, convert it cloud-native, publish it durably on
Source Cooperative, and make it discoverable via a thin static catalog
on GitHub Pages. See sibling repos: `optgeo/fabdem-contour-fiji`,
`optgeo/c2`, etc.

## Facts about the data source

- `layers-martin`'s tile IDs are identical to GSI's own 地理院タイル IDs.
  Confirmed by cross-referencing `hfu/layers-martin/catalog.json` against
  `maps.gsi.go.jp/development/ichiran.html` (地理院タイル一覧).
- **Always read layers-martin's catalog from its canonical live URL,
  `https://hfu.github.io/layers-martin/catalog.json` (equivalently
  `/catalog`), never assume a local `git clone` of `layers-martin` is
  fresh.** Rationale and the incident that caught this: DECISIONS.md D7.
- GSI tiles are **256px**. If you ever compare zoom levels against a
  512px-tile system (vector tiles, most modern basemaps), the effective
  equivalent zoom is **one less** (z18 @ 256px ≈ z17 @ 512px). This
  matters when deciding what raster zoom to treat as "native" resolution
  for STAC `gsd` and for downstream MapLibre configs.
- `_do` / `_do_sokuho` (正射画像 / 正射画像速報, i.e. emergency ortho)
  layers almost always document `ズームレベル 10～18` on ichiran.html.
  Treat 18 as native/maxzoom and 10 as a safe probe starting point unless
  the specific layer's ichiran.html entry says otherwise (DECISIONS.md
  D5).
- **`mokuroku.csv.gz` (official tile inventory) is NOT reliable for these
  layers**, and **`cocotile`/`daicho` are dead ends** for discovering a
  layer's coverage. See DECISIONS.md D1 for why, and for the
  quadtree-pruning probe strategy (`src/cogenerate/probe.py`) used
  instead.
- **GSI's own `ichiran.html` can itself lag behind the live tile
  server** -- don't wait for it before running the pipeline. See
  DECISIONS.md D9 for the disaster-response principle this pipeline
  follows and what stays gated on `ichiran.html` regardless (attribution
  fields in published STAC items).
- **GSI serves nothing below the documented minzoom (almost always 10)
  for these layers** -- confirmed live (z9 down to z6 all 404 against a
  tile known to have real z10 data). Don't try to search lower zooms
  for a more reliable seed; see DECISIONS.md D18 for what actually
  helps (a small tile grid *at* minzoom) and D17 for why a single seed
  tile isn't enough by itself (it can only ever find coverage within
  its own minzoom cell, never a sibling cell with real data).
- **Picking "which layer next"**: `src/cogenerate/candidates.py` ranks
  not-yet-published layers by a municipality-count proxy (parsed from
  ichiran.html's 提供範囲 field -- no real bbox/km² exists on GSI's
  side, confirmed 2026-07-31). It filters to real disaster-response
  layers by checking which catalog IDs actually have an ichiran.html
  entry with that field, **not** by pattern-matching the ID string --
  an ID-suffix regex (`ends with "do"`) picks up false positives from
  unrelated layers (`gsjgeomap_*`, `*hirado`, `*mikado`) and also
  undercounts (missed non-`_do`-suffixed variants like
  `20190828_kyusyu_0828dansaizu`). The correct count is **194** real
  disaster-response layers as of 2026-07-31, not the ~74-75 an
  ID-regex guess produces -- always re-run the tool rather than
  trusting a cached number.
- **Before queuing a `candidates.py` result, check two things**: (1)
  fetch `layers-martin`'s catalog `name` field for that layer ID and
  confirm it says "撮影" (photographed) -- some `ichiran.html`-matched
  entries are non-photo products (`_dansaizu` = 段彩図 color-relief
  hazard map, `_shinsui` = 浸水図 inundation map); skip those, this
  pipeline is for aerial photo ortho only. (2) A same-prefecture/city
  sub-district entry with a *different* capture date than an
  already-published layer (e.g. `wazimatobu`/`wazimaseibu` vs. the
  already-published `wajima`, or the Noto earthquake response's
  1/2/1/5/1/11/1/14/1/17-captured sub-district batches, all distinct
  from each other and from the later comprehensive `noto_0405_0426do`)
  is real additional coverage, not a duplicate -- the `name` field's
  capture date confirms this before queuing.
- **A source tile can be genuinely corrupt on GSI's own server**, not
  just a bad local download -- confirmed live (2026-08-01,
  `noto_nanao_0117do`) by re-fetching the same tile URL fresh via
  `curl` and getting an identical corrupt PNG (`OSError: unrecognized
  data stream contents` from Pillow, a truncated/broken zlib stream
  inside an otherwise well-formed PNG header). `georef.py`'s
  `discover_tiles()` globs whatever tile files actually exist on disk
  (not the probe CSV), so the fix is just: delete the one corrupt tile
  file and re-run `just georef` -- it's silently absent from the
  mosaic rather than crashing the whole layer. Losing one 256px tile
  out of tens of thousands is negligible; don't spend time trying to
  repair the source PNG.
- 404s are not errors to fear: since we probe first and download second,
  an unexpected 404 during download is logged and skipped, not fatal.
  Gaps left by skipped tiles are legitimate nodata and are handled by the
  alpha channel (`gdalbuildvrt -addalpha`), not by synthesizing blank
  tiles. Pure-black pixels get the same treatment even *within* an
  otherwise-present tile -- see DECISIONS.md D12.

## Toolchain conventions (DECISIONS.md D2)

- **Python**: managed by `uv`. Never `pip install` directly; `uv run`,
  `uv add`, `uv sync`. No GDAL Python bindings -- call `gdal_translate` /
  `gdalbuildvrt` via `subprocess`.
- **Task orchestration**: `Justfile`, one recipe per pipeline stage.
  Recipe variables are environment variables read *before* the recipe
  name (`LAYER=... just probe`), not trailing recipe arguments (`just
  probe LAYER=...` errors).
- **Small composable units**: one script, one responsibility (probe /
  download / georef). Hand off through files (CSV, VRT), not in-memory
  state, so each stage is independently re-runnable and debuggable.
- **Naming**: Source Cooperative path follows the existing optgeo
  convention: `source.coop/smartmaps/cogenerate/<layer_id>.tif`.
- **License / attribution**: GSI tiles require "国土地理院" or "地理院
  タイル" attribution with a link to `maps.gsi.go.jp/development/ichiran.html`.
  Some individual layers require additional attribution beyond that --
  check the ichiran.html entry's 備考 (remarks) field per layer, subject
  to DECISIONS.md D9 (don't let this block COG *production*, only what
  you assert as final attribution).
- **COGs get an explicit `-a_nodata 0` and embedded `-mo` provenance
  metadata** (description, copyright/attribution text, layer ID, source
  URL, pipeline URL) -- see DECISIONS.md D15 for why the alpha band
  alone wasn't enough for every downstream viewer.
- **Already-done work is skipped by default** across every stage
  (`probe`/`download`/`georef`/`cog`); `FORCE=1` redoes it. See
  DECISIONS.md D11 -- this makes reruns after an interruption, or after
  a probe/recipe fix like D17/D18, cheap and mostly incremental instead
  of starting over.
- **Local disk is not infinite -- clean up per-layer once the remote
  copy is verified, don't just let `tiles/`/`out/` grow forever.**
  `just verify` checks a layer's `out/{{layer}}.tif` against Source
  Cooperative before anything gets deleted; `just cleanup-tiles` (safe,
  routine) then removes `tiles/{{layer}}/`, and `just cleanup-cog`
  (only once that layer's STAC Item already exists, D19) removes the
  local COG too. See DECISIONS.md D20 -- never delete a layer's
  `tiles/` while it's still mid-download/rebuild (D11's incremental
  skip-if-present logic needs it there).
- **`source-coop` credentials expire on their own** (session TTL) with
  no warning until an `upload`/`aws s3api` call fails with "Cached
  credentials have expired. Run 'source-coop login' to refresh." This
  is routine, not a bug -- happens repeatedly across a long session.
  Verify with `aws s3api head-object --bucket smartmaps --key
  cogenerate/README.md --profile source-coop --query LastModified
  --output text`. **Never try to work around it** (no raw
  `source-coop creds` calls either, see DECISIONS.md's incident note)
  -- ask Hidenori to run `source-coop login`, he handles it personally
  each time. While waiting, keep the credential-free pipeline stages
  going (probe/download/georef/cog) so finished COGs queue in `out/`
  for `upload` the moment it's refreshed, rather than the whole
  pipeline stalling.
- **Run one `upload` and one build-chain step concurrently, don't
  serialize them** -- `upload` is network-bound (a large layer's
  transfer can take 20-30+ minutes) while probe/download/georef/cog
  are CPU- or GSI-network-bound; they don't contend for the same
  resource, so idling one while the other runs wastes real time.
  Requested explicitly by Hidenori, 2026-08-01. Watch concurrent
  `gdal_translate` count (`ps aux | grep gdal_translate`) if queuing
  more than ~3-4 builds at once on top of that -- COG builds get
  CPU-hungry on large layers and this machine has 8 cores.
- **Long-running steps (anything that can outlive a single tool call --
  `cog` on a large layer especially) must run through the harness's
  tracked background-task mechanism, not a loose backgrounded shell
  (`command &`).** Confirmed the hard way, 2026-08-01: a `cog` build
  started via plain `&` was silently killed when its owning session
  ended, losing 5+ hours of work with no error, no `.tif` renamed, and
  no process left to notice -- indistinguishable from "still running"
  until you check `ps aux` and find nothing. A tracked background task
  survives a session boundary and reports completion/failure properly.
- **`just stac` (= `stac-item` + `stac-catalog`) already rebuilds
  `docs/catalog.json` from *every* Item in `docs/items/` each time it
  runs** -- the catalog is never stale between individual layer
  publishes, there's no separate "periodically refresh the catalog"
  step needed. What matters operationally is not letting a batch of
  `upload`-completed layers sit unpublished (no STAC Item yet, not in
  the catalog) while chasing the next build -- run the
  `verify -> stac -> stac-validate -> cleanup -> commit` tail promptly
  once each layer's `upload` finishes.
- **When reporting pipeline status, give a `published/pool` fraction,
  not just an absolute count** (requested by Hidenori, 2026-08-01) --
  `uv run python -m cogenerate.candidates --top 1 --sort-by date`'s
  stderr summary line has both numbers (published count from live
  STAC catalog census, pool count from `ichiran.html`). Re-run rather
  than trusting a cached fraction; the pool total drifts and a handful
  of `_dansaizu`/`_shinsui`-suffixed non-photo entries are baked into
  the raw pool count (see the candidate-filtering note above) so treat
  it as the working denominator, not a mathematically exact one.

## Decisions and open questions

Full ADR log: `DECISIONS.md` (19 entries as of 2026-07-31). No entry is
currently Open -- D6 (OAM ingestion path) was resolved to Accepted:
build a static STAC catalog first (schema in D19, matching sibling
repo `optgeo/oam-starc`'s conventions), approach HOTOSM once it's real.
Two things from D6/D19 still need Hidenori specifically, not something
to just do silently: turning on GitHub Pages for `optgeo/cogenerate`
(off as of 2026-07-31), and actually contacting HOTOSM/OAM.

(D4, STAC `datetime` source, was Open but Hidenori decided it
2026-07-31 -- capture-date fragment, not ichiran.html's publish date.)

## Commands

```sh
uv sync                          # install deps
uv run python -m cogenerate.candidates --top 10   # rank not-yet-published layers by a spatial-extent proxy (see below)
LAYER=... SEED_X=... SEED_Y=... just probe   # quadtree existence probe (vars go BEFORE the recipe name -- they're env vars, not recipe args)
just download                    # fetch confirmed tiles
just georef                      # tile PNGs -> merged VRT (EPSG:3857)
just cog                         # VRT -> COG (overviews generated here)
just run                         # all of the above, one layer
just upload                      # publish out/{{layer}}.tif to Source Cooperative (needs source-coop login done once, D10)
just stac-item                   # build docs/items/{{layer}}.json from the already-built, already-uploaded COG (D19)
just stac-catalog                # rebuild docs/catalog.json from every docs/items/*.json so far
just stac                        # stac-item + stac-catalog for one layer
just stac-validate                # validate every Item + the catalog against the STAC spec (needs `uv sync --extra dev`)
just verify                      # confirm out/{{layer}}.tif matches what's live on Source Cooperative (D20)
just cleanup-tiles               # delete tiles/{{layer}}/ once verify passes -- routine, safe any time after upload
just cleanup-cog                 # delete out/{{layer}}.tif too, once verify passes AND its STAC Item already exists (D20)

just lint / just test

# Useful env vars (all optional, see Justfile for full defaults):
#   FORCE=1              redo work a stage would otherwise skip (D11)
#   SEED_GRID_RADIUS=N   widen/narrow the initial seed-grid search (D18, default 2 = 5x5)
```

## Non-goals

- Not building a general-purpose GSI tile downloader (that's `qdltc`,
  already exists, CC0, use it directly for std/pale/english).
- Not re-implementing mokuroku/cocotile/daicho server-side -- client-side
  probing only.
