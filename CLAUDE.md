# CLAUDE.md

Guidance for Claude (Code or chat) working on this repository.

**Doc map**: this file is *how to operate* day to day, and also the
**reusable playbook** if you're adapting this approach to a different
tile source. `DECISIONS.md` is *why* things are the way they are (ADR
log -- read it before reconsidering something that looks arbitrary,
and read it for the full incident writeups this file only summarizes).
`HANDOVER.md` is *what happened*, session by session, and what to do
first if you're resuming cold (e.g. after `/clear`).

## Language policy (DECISIONS.md D8)

- Converse with Hidenori (chat, CLI turns, questions) in **Japanese**.
- Everything that lands in the repository -- code, comments, docstrings,
  `.md` prose, commit messages, PR descriptions -- stays in **English**,
  matching the rest of the optgeo family. Don't mix.

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
on GitHub Pages. Sibling repos: `optgeo/fabdem-contour-fiji`, `optgeo/c2`,
`optgeo/oam-starc`.

## Reusable pattern: adapting this to a different tile source

If you're building an analogous pipeline against a *different* tile
server (a different agency's disaster imagery, another country's
aerial-photo archive), carry over these decisions rather than
re-deriving them. Each links to the ADR with the full reasoning and
the incident that motivated it.

1. **No inventory API? Quadtree-pruning probe, not a bbox brute force**
   (D1). Start from known-good seed tile(s) at the source's lowest
   documented zoom; recurse into children only where the parent
   returned 200 -- request volume then scales with the coverage
   polygon's *boundary*, not bbox × zoom-levels. Two refinements that
   turned out to matter in practice, not just in theory:
   - **Flood-fill at the seed zoom first** (D17) -- a pure
     parent→child descent can never discover a *sibling* minzoom cell,
     even an adjacent one, so a single seed silently misses real
     coverage on any elongated or multi-part polygon.
   - **Search a small grid around each seed, not just the seed itself**
     (D18) -- tolerates an imprecise seed by up to `radius` tiles.
     Do **not** try to compensate for a wrong-looking seed by
     searching *lower* zooms than the server documents -- confirmed
     live that GSI serves nothing at all below its documented minzoom;
     a lower-zoom search there isn't just wasteful, it's non-functional.
   - Retry transient network errors/5xx during the maxzoom descent (3
     attempts, linear backoff) but **never** retry a real 404 -- a
     single un-retried transient failure on an intermediate-zoom
     ancestor permanently prunes its whole subtree, indistinguishable
     from a correct 404 until someone notices a hole in the output
     (D24).
2. **Idempotent stages, skip-by-default, one `FORCE=1` escape hatch**
   (D11). Every stage checks whether its own output already exists
   before repeating (often rate-limited, always re-crawlable) work.
   Makes interrupted runs and post-bugfix re-runs cheap by
   construction instead of re-hammering the source server or redoing
   hours of work from zero.
3. **Small composable stages, plain files as the interface** (D2). One
   script per concern (probe / download / georeference / build),
   handed off through plain files (CSV, VRT) rather than in-memory
   state -- each stage independently re-runnable and inspectable with
   off-the-shelf tools (`wc -l`, `gdalinfo`).
4. **Minimize technical footprint**: CLI tools over SDKs/bindings
   wherever a CLI already does the job (GDAL via `subprocess`, never
   `osgeo`'s Python bindings; a package manager -- `uv` here -- only
   for the one place real application logic lives: HTTP + coordinate
   math). Add a library dependency only when a CLI genuinely can't do
   the job, and say so explicitly in an ADR rather than assuming it's
   fine (D12/D25's `numpy`/`pillow`, for exact-pixel-value NODATA
   masking GDAL's CLI has no simple way to express, is the one
   exception here -- still just two small, narrowly-scoped libraries,
   not a raster-processing framework).
5. **Don't assume the alpha channel alone marks NODATA** -- inspect
   real tiles first. This class of tile server has been observed
   encoding "no data" as literal solid colors (opaque black *and*
   white, D12/D25), not just alpha=0. Detect via an exact-pixel mask
   per tile (skip tiles with none, the common case), and watch for
   **genuinely monochrome source content** (old grayscale photography
   stored as RGB) where a blanket white/black-is-nodata rule would
   carve holes in real content -- tell the two apart with a structural
   signal (R≈G≈B everywhere vs. real color variance somewhere), not a
   per-ID allowlist (D25's `sample_is_monochrome()`). Also set an
   explicit classic NODATA tag (`-a_nodata`) on the final COG in
   addition to the alpha band -- not every downstream viewer honors
   the alpha band alone (D15).
6. **Publish to durable, S3-compatible object storage; catalog
   separately and cheaply** (D10, D19-D21). Local disk is staging, not
   the permanent home for a finished product (D20) -- verify the
   remote copy via a **public, unauthenticated** check before deleting
   anything local, so cleanup never blocks on a login session (D21).
   Build the discovery catalog (STAC here) as small, independently
   fetchable files -- one Item per asset, a thin Catalog linking to
   them -- not one ever-growing inlined JSON blob.
7. **Pipeline network-bound and CPU-bound work across concurrent
   items** -- an upload and a COG build don't contend for the same
   resource. Run one of each rather than serializing; keep ~2-3
   concurrent CPU-bound builds going against a backlog, watching core
   count (`ps aux | grep gdal_translate | wc -l`).
8. **A catalog can itself be stale or lag the live server** -- read
   canonical live URLs, never a local clone assumed fresh (D7). Treat
   the live tile server as more authoritative than its own
   documentation page when the two disagree, but keep
   attribution/legal-sensitive fields gated on the documentation
   catching up (D9) -- don't assert unverified attribution as settled
   fact just to unblock production.
9. **Long-running steps must run through a tracked background-task
   mechanism, not a loose `command &`** -- a bare backgrounded shell
   can be silently killed when its owning session ends, with no error
   and nothing left in `ps aux` to notice. A multi-hour COG build is
   exactly the kind of work this has bitten in practice.

## Facts about this data source (GSI)

- `layers-martin`'s tile IDs are identical to GSI's own 地理院タイル IDs
  (cross-referenced against `ichiran.html`, 地理院タイル一覧).
- Always read `layers-martin`'s catalog from its canonical live URL
  (`https://hfu.github.io/layers-martin/catalog.json`), never assume a
  local clone is fresh -- D7.
- GSI tiles are 256px; z18 here ≈ z17 on a 512px-tile system when
  comparing zoom levels against a different basemap stack.
- `_do`/`_do_sokuho` layers document `ズームレベル 10～18` on
  `ichiran.html` *almost* always, but **check every layer's own entry**
  -- a few observed series (Kuchinoerabujima/Nishinoshima volcano UAV
  captures) document `14～18` instead. A standard z10 seed then finds
  nothing and looks exactly like a wrong-seed failure, but D18's
  seed-grid widening won't fix it -- it's a real minzoom mismatch, not
  an imprecise seed. Convert the `ichiran.html` tilejump coordinate to
  the *layer's actual* minzoom (`coord >> (tilejump_z - real_minzoom)`)
  before assuming a probe failure means a bad seed.
- A `candidates.py`/layers-martin catalog ID can itself be flat-out
  wrong (an extra/missing character vs. the real GSI tile path) --
  always sanity-`curl -I` a brand-new candidate's real tile URL (or at
  least read its `ichiran.html` source-URL line) before trusting "none
  of the seeds returned 200" as a seed problem. Two different root
  causes (wrong minzoom, wrong ID) that look identical from the
  outside -- check both before concluding the seed math is wrong.
- `mokuroku.csv.gz`/`cocotile`/`daicho` are all dead ends for
  discovering these layers' coverage -- D1 has the full reasoning.
- `ichiran.html` itself can lag the live tile server for a brand-new
  disaster layer -- don't block COG *production* on it, only the
  attribution text asserted as final in a published STAC item (D9).
- **Picking "what's next"**: `candidates.py` ranks unpublished layers
  by extent or date, filtered to real aerial-photo disaster-response
  layers via `ichiran.html`'s 提供範囲 field plus layers-martin's
  `name` field containing 撮影/UAV撮影/ヘリ撮影/空中写真 -- not
  作成/観測 (map products) and not nationwide non-disaster products
  (e.g. `rinya`, national-forest aerial photos: real photos, but out
  of this pipeline's disaster-response scope per the Mission above).
- A same-district candidate with a *different* capture date than an
  already-published layer is real additional coverage, not a
  duplicate -- confirm via the `name` field's capture date, don't skip
  on district-name match alone.
- A source tile can be genuinely corrupt on GSI's own server, not just
  a bad local download (confirmed by re-fetching fresh and getting an
  identical corrupt PNG). `georef.py` globs whatever tile files
  actually exist on disk, so deleting the one corrupt file and
  re-running `georef` silently and correctly excludes it -- not worth
  trying to repair one bad tile out of tens of thousands.
- 404s during probing are the expected pruning signal, not an error.
  An unexpected 404 during *download* (for an already-probe-confirmed
  tile) is logged and skipped, not fatal -- the resulting gap is
  legitimate nodata via the alpha channel, never synthesized as blank.

## Toolchain conventions (DECISIONS.md D2)

- **Python**: managed by `uv` (`uv sync` / `uv run` / `uv add`; never
  bare `pip install`). GDAL is called as `gdal_translate` /
  `gdalbuildvrt` subprocesses, never `osgeo` Python bindings.
- **Task orchestration**: `Justfile`, one recipe per pipeline stage.
  Recipe variables are environment variables read *before* the recipe
  name (`LAYER=... just probe`), not trailing recipe arguments (`just
  probe LAYER=...` errors).
- **Naming**: Source Cooperative path follows the existing optgeo
  convention: `source.coop/smartmaps/cogenerate/<layer_id>.tif`.
- **License / attribution**: GSI tiles require "国土地理院"/"地理院
  タイル" attribution linking to `maps.gsi.go.jp/development/ichiran.html`.
  Some individual layers require more -- check each layer's 備考
  (remarks) field, subject to D9 (don't let this block COG
  *production*, only what's asserted as final attribution).

## Operational conventions

- **`source-coop` credentials expire on their own** with no warning
  until an `upload`/`aws s3api` call fails ("Cached credentials have
  expired. Run 'source-coop login' to refresh."). Routine, not a bug.
  Verify with `aws s3api head-object --bucket smartmaps --key
  cogenerate/README.md --profile source-coop --query LastModified
  --output text`. **Empirical lifetime estimate** (not authoritative,
  never inspect the raw token to pin this down further -- see the
  incident note below): nominal STS TTL ~90 minutes; in practice,
  expiry has been hit roughly every 30-60 minutes of active use across
  multiple sessions. Treat ~60-90 minutes of continuous work as the
  point to expect (or proactively ask for) a re-login, rather than
  waiting for an upload to fail first. **Never work around it and
  never call `source-coop creds` directly** (it prints raw credential
  material to stdout -- exists for `credential_process` to call
  internally, not for a human/Claude to inspect). Ask Hidenori to run
  `source-coop login`; while waiting, keep credential-free stages
  going (probe/download/georef/cog) so finished COGs queue in `out/`
  for `upload` the moment credentials return, rather than stalling the
  whole pipeline.
- **Always check the full/tail output of `just upload`, never a
  truncated preview** -- a mid-transfer Cloudflare 520 can fail
  silently in a preview that only shows early progress lines; the
  real success/failure line is at the very end. `just verify` (public,
  unauthenticated, D21) is the authoritative check either way, so run
  it after every upload regardless of how the upload output looked.
- **Run one `upload` and one build-chain step concurrently, don't
  serialize** -- `upload` is network-bound (a large layer can take
  20-30+ minutes) while probe/download/georef/cog are CPU- or
  GSI-network-bound; they don't contend. Pipeline across *multiple*
  layers too (start layer B's probe/download while layer A's `cog` is
  still building) rather than fully finishing one layer before
  starting the next. Target ~2-3 concurrent `gdal_translate` builds
  (`ps aux | grep gdal_translate | grep -v grep | wc -l`) on an 8-core
  machine; don't let two *foreground* commands touch the same layer at
  once (confirmed live: two concurrent `probe` calls for the same
  layer raced on the same output CSV).
- **Already-done work is skipped by default** across every stage
  (D11); `FORCE=1` redoes it. Note the `probe` skip check only keys on
  `layer`+`maxzoom` in the output filename -- if a probe failed and
  left an empty/wrong CSV (e.g. after discovering the real minzoom was
  different), `rm` that CSV or pass `FORCE=1` before retrying, or the
  skip check will trust the bad result.
- **Local disk is not infinite** -- `just verify` (D20/D21) confirms a
  layer's remote copy before `just cleanup-tiles` (routine, safe any
  time after upload) and `just cleanup-cog` (only once that layer's
  STAC Item exists) delete local copies. Never delete `tiles/` for a
  layer still mid-download/rebuild -- D11's skip-if-present logic
  needs it there.
- **`just stac` (= `stac-item` + `stac-catalog`) rebuilds
  `docs/catalog.json` from *every* Item each time it runs** -- never
  stale between publishes. What matters operationally is not letting
  a batch of `upload`-completed layers sit unpublished while chasing
  the next build -- run `verify → stac → stac-validate → cleanup →
  commit` promptly once each layer's `upload` finishes.
- **Report status as a `published/pool` fraction**, not just an
  absolute count -- `uv run python -m cogenerate.candidates --top 1
  --sort-by date`'s stderr summary line has both numbers. Re-run
  rather than trusting a cached fraction; the live STAC catalog census
  can lag a few minutes behind a just-pushed commit (GitHub Pages
  redeploy delay), and the pool count includes a handful of
  non-photo/mis-typo'd false positives skipped by hand as encountered
  -- a working denominator, not a mathematically exact one.
- **If working through a harness where a background task's own `cd`
  doesn't affect the interactive shell's cwd**: always use full paths
  (`/Users/hfu/cogenerate/...`) when checking on a background task's
  output or files from the interactive session, not a path relative
  to whatever the interactive cwd happens to be.

## Decisions and open questions

Full ADR log: `DECISIONS.md` (25 entries as of 2026-08-02). No entry is
currently Open. **Still needs Hidenori specifically, not something to
just do silently**: actually contacting HOTOSM/OAM now that a real,
public STAC catalog exists (D6) -- not urgent, no one's asked to move
on it yet.

## Commands

```sh
uv sync                          # install deps
uv run python -m cogenerate.candidates --top 10   # rank not-yet-published layers by a spatial-extent proxy (see below)
LAYER=... SEED_X=... SEED_Y=... just probe   # quadtree existence probe (vars go BEFORE the recipe name -- they're env vars, not recipe args)
# ...also MINZOOM=N if a layer's real ズームレベル isn't the usual 10 (see "Facts" above)
just download                    # fetch confirmed tiles
just georef                      # tile PNGs -> merged VRT (EPSG:3857)
just cog                         # VRT -> COG (overviews generated here)
just run                         # all of the above, one layer
just upload                      # publish out/{{layer}}.tif to Source Cooperative (needs source-coop login done once, D10)
just stac-item                   # build docs/items/{{layer}}.json from the already-built, already-uploaded COG (D19)
just stac-catalog                # rebuild docs/catalog.json from every docs/items/*.json so far
just stac                        # stac-item + stac-catalog for one layer
just stac-validate               # validate every Item + the catalog against the STAC spec (needs `uv sync --extra dev`)
just verify                      # confirm out/{{layer}}.tif matches what's live on Source Cooperative (D20/D21, no credentials needed)
just cleanup-tiles               # delete tiles/{{layer}}/ once verify passes -- routine, safe any time after upload
just cleanup-cog                 # delete out/{{layer}}.tif too, once verify passes AND its STAC Item already exists (D20)
just whitescan                   # cheap remote-only scan for the white-nodata pattern (D25) across already-published layers
just audit                       # cheap remote-only HEAD + gdalinfo sanity sweep across every published Item

just lint / just test

# Useful env vars (all optional, see Justfile for full defaults):
#   FORCE=1              redo work a stage would otherwise skip (D11)
#   SEED_GRID_RADIUS=N   widen/narrow the initial seed-grid search (D18, default 2 = 5x5)
#   MINZOOM=N            override the default 10 when a layer's real ズームレベル starts higher
```

## Non-goals

- Not building a general-purpose GSI tile downloader (that's `qdltc`,
  already exists, CC0, use it directly for std/pale/english).
- Not re-implementing mokuroku/cocotile/daicho server-side -- client-side
  probing only.
