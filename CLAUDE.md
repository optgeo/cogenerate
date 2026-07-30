# CLAUDE.md

Guidance for Claude (Code or chat) working on this repository.

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

## Why this exists (context, not to be re-litigated each session)

- `layers-martin`'s tile IDs are identical to GSI's own 地理院タイル IDs.
  Confirmed by cross-referencing `hfu/layers-martin/catalog.json` against
  `maps.gsi.go.jp/development/ichiran.html` (地理院タイル一覧).
- **Always read the catalog from the canonical live URL,
  `https://hfu.github.io/layers-martin/catalog.json` (equivalently
  `/catalog`), not from a local `git clone` of `layers-martin`.** GitHub
  Actions there rebuilds and commits `docs/catalog.json` on a daily
  cron (`build-catalog.yml`, 18:00 UTC), so a local checkout that isn't
  freshly `git pull`ed silently drifts stale -- confirmed 2026-07-31: a
  local clone last touched 2026-07-17 was missing 15 days of rebuilds,
  including the entry for the very layer this pipeline was tested
  against. If you do work from a local clone for convenience, `git
  pull --ff-only` it first and don't trust its age otherwise.
- GSI tiles are **256px**. If you ever compare zoom levels against a
  512px-tile system (vector tiles, most modern basemaps), the effective
  equivalent zoom is **one less** (z18 @ 256px ≈ z17 @ 512px). This
  matters when deciding what raster zoom to treat as "native" resolution
  for STAC `gsd` and for downstream MapLibre configs.
- `_do` / `_do_sokuho` (正射画像 / 正射画像速報, i.e. emergency ortho)
  layers almost always document `ズームレベル 10～18` on ichiran.html.
  Treat 18 as native/maxzoom and 10 as a safe probe starting point unless
  the specific layer's ichiran.html entry says otherwise.
- **`mokuroku.csv.gz` (official tile inventory) is NOT reliable for these
  layers.** Per `gsi-cyberjapan/mokuroku-spec`, as of the spec's writing
  only `std`, `pale`, `english` are regularly regenerated. Do not build
  a pipeline that assumes mokuroku exists for a disaster layer; treat its
  presence as a bonus fast path, not a dependency.
- **`cocotile` and `daicho` are dead ends for our purpose**, checked and
  rejected on 2026-07-30:
  - `cocotile` (`cyberjapandata.gsi.go.jp/xyz/cocotile/{z}/{x}/{y}.csv`)
    tells you which layer IDs exist *at a tile position you already
    know*. It does not help you find where a layer's coverage is.
  - `daicho` (`gsi-cyberjapan/daicho-spec`) is GSI's own internal SQLite
    cache used to accelerate mokuroku generation server-side. It is not
    a public endpoint at all.
- Therefore: **quadtree-pruning existence probing** (start low zoom,
  recurse into children only where the parent returned 200, treat 404 as
  "prune this subtree") is the primary strategy. See `src/cogenerate/probe.py`
  for the rationale and implementation.
- 404s are not errors to fear: since we probe first and download second,
  an unexpected 404 during download is logged and skipped, not fatal.
  Gaps left by skipped tiles are legitimate nodata and are handled by the
  alpha channel (`gdalbuildvrt -addalpha`), not by synthesizing blank
  tiles.

## Toolchain conventions

- **Python**: managed by `uv`. Never `pip install` directly; `uv run`,
  `uv add`, `uv sync`. Python does only what needs real logic (HTTP
  probing/downloading, tile-coordinate math). No GDAL Python bindings --
  call the `gdal_translate` / `gdalbuildvrt` binaries via `subprocess`,
  matching the existing stack (GDAL, Tippecanoe, PMTiles, Martin, Unix
  CLI tools) and keeping the dependency footprint light.
- **Task orchestration**: `Justfile`, not shell scripts or Makefiles.
  Each `just` recipe is one pipeline stage; `just run` chains them.
  Mirrors the Mapterhorn pipeline's style.
- **Small composable units**: one script, one responsibility (probe /
  download / georef). Prefer piping intermediate results (CSV, VRT) over
  in-memory hand-off between stages -- makes each stage independently
  re-runnable and debuggable, and matches the existing UNIX-philosophy
  preference (小さく分割された単位).
- **Naming**: Source Cooperative path follows the existing optgeo
  convention: `source.coop/smartmaps/cogenerate/<layer_id>.tif`.
- **License / attribution**: GSI tiles require "国土地理院" or "地理院
  タイル" attribution with a link to `maps.gsi.go.jp/development/ichiran.html`.
  Some individual layers require additional attribution beyond that --
  check the ichiran.html entry's 備考 (remarks) field per layer before
  publishing; do not assume blanket CC0/CC-BY treatment.

## Open decisions (do not silently pick one -- surface to Hidenori)

1. STAC item `datetime` extraction: parse from the layer ID's embedded
   date fragment (e.g. `20260729...0729do_sokuho` → 2026-07-29) vs. from
   ichiran.html's "提供開始" (publish date, which lags capture date by a
   day or more). Capture date is more correct; publish date is easier to
   scrape reliably. Needs a decision before the STAC generator is final.
2. Zoom-to-fetch: currently hardcoded to maxzoom=18 with COG overviews
   generated locally (not fetched per-zoom from GSI). Revisit only if a
   layer's native resolution genuinely exceeds z18 (unlikely for these
   ortho layers, per ichiran.html).
3. OpenAerialMap ingestion path (API push vs. STAC harvest) is still
   unresearched. Do not build STAC metadata fields blind to OAM's actual
   schema requirements -- check before finalizing `stac_item.py`.

## Commands

```sh
uv sync                          # install deps
LAYER=... SEED_X=... SEED_Y=... just probe   # quadtree existence probe (vars go BEFORE the recipe name -- they're env vars, not recipe args)
just download                    # fetch confirmed tiles
just georef                      # tile PNGs -> merged VRT (EPSG:3857)
just cog                         # VRT -> COG (overviews generated here)
just run                         # all of the above, one layer
just lint / just test
```

## Non-goals

- Not building a general-purpose GSI tile downloader (that's `qdltc`,
  already exists, CC0, use it directly for std/pale/english).
- Not re-implementing mokuroku/cocotile/daicho server-side -- client-side
  probing only.
