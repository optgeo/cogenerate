# cogenerate: GSI disaster-response tiles -> COG -> STAC -> Source Cooperative
#
# Style note: task orchestration lives here (Justfile), not in Python.
# Python (via `uv run`) does only the parts that need real logic
# (quadtree probing, downloading, georeferencing math). Mosaicking and
# COG creation stay as direct GDAL CLI calls -- small, inspectable,
# swappable. This mirrors the Mapterhorn pipeline's Justfile + uv style.

set dotenv-load := true

layer := env_var_or_default("LAYER", "20260729kumamoto_yatsushiro_0729do_sokuho")
minzoom := env_var_or_default("MINZOOM", "10")
maxzoom := env_var_or_default("MAXZOOM", "18")
seed_x := env_var_or_default("SEED_X", "883")
seed_y := env_var_or_default("SEED_Y", "414")
# (2r+1)x(2r+1) grid of candidate tiles checked at minzoom around each
# seed -- tolerates an imprecise seed. See DECISIONS.md D18; must match
# probe.py's DEFAULT_SEED_GRID_RADIUS if you change the default here.
seed_grid_radius := env_var_or_default("SEED_GRID_RADIUS", "2")
# FORCE=1 re-does work that would otherwise be skipped because its
# output already exists -- see DECISIONS.md D11. Every other value
# (including unset) means "skip what's already done."
force := env_var_or_default("FORCE", "")
force_flag := if force == "1" { "--force" } else { "" }
# Plain string concatenation (not the `/` path-join operator) for
# portability across `just` versions -- `/` as path-join was added in a
# fairly recent just release and may not exist on an older Mac install.
tiles_dir := "tiles/" + layer
out_dir := "out"

default:
    just --list

# Step 1: quadtree-probe which tiles exist at maxzoom, no full-extent brute force.
# Skips re-probing (no GSI requests at all) if the output CSV already
# exists -- FORCE=1 to redo. probe.py itself has no --force flag: the
# skip decision lives here, one level up, since it's about not invoking
# the network round at all, not about a per-file check inside Python.
probe:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p tiles
    out="tiles/{{layer}}.z{{maxzoom}}.csv"
    if [ -f "$out" ] && [ "{{force}}" != "1" ]; then
        echo "skip: probe already done ($out exists; FORCE=1 to re-probe)" >&2
    else
        uv run python -m cogenerate.probe \
            --layer {{layer}} --minzoom {{minzoom}} --maxzoom {{maxzoom}} \
            --seed-x {{seed_x}} --seed-y {{seed_y}} \
            --seed-grid-radius {{seed_grid_radius}} \
            > "$out"
    fi
    wc -l "$out"

# Step 2: download only the confirmed tiles from step 1.
# download.py skips any tile whose file already exists (FORCE=1 to
# re-fetch it anyway) -- this is the main lever for not re-hitting GSI.
download:
    uv run python -m cogenerate.download \
        --layer {{layer}} \
        --tiles tiles/{{layer}}.z{{maxzoom}}.csv \
        --out {{tiles_dir}}/ \
        {{force_flag}}

# Step 3: georeference + merge into one mosaic VRT (EPSG:3857).
# georef.py skips regenerating a per-tile .vrt that already exists
# (FORCE=1 to redo); the merge step itself always re-runs since it's
# metadata-only and cheap, and must reflect the current tile set.
georef:
    mkdir -p {{out_dir}}
    uv run python -m cogenerate.georef \
        --dir {{tiles_dir}}/ \
        --merged {{out_dir}}/{{layer}}.vrt \
        {{force_flag}}

# Step 4: VRT -> COG. Overviews are generated here, not fetched from GSI.
# Skips rebuilding if the .tif is already newer than its source .vrt --
# FORCE=1 to rebuild anyway.
cog:
    #!/usr/bin/env bash
    set -euo pipefail
    src="{{out_dir}}/{{layer}}.vrt"
    dst="{{out_dir}}/{{layer}}.tif"
    tmp="{{out_dir}}/{{layer}}.tif.building"
    if [ -f "$dst" ] && [ "{{force}}" != "1" ] && [ "$dst" -nt "$src" ]; then
        echo "skip: $dst is newer than $src (FORCE=1 to rebuild)" >&2
    else
        # Build to a temp path and mv into place only on success, so a
        # killed/interrupted build (this took long enough to hit that in
        # practice) never leaves a truncated file at $dst that a later
        # run's -nt skip-check would wrongly trust as done.
        rm -f "$tmp"
        # -a_nodata 0: nodata regions (both in-tile transparent padding
        # and mosaic gaps outside any confirmed tile) render as opaque
        # black to viewers that don't respect the alpha band -- observed
        # directly on Source Cooperative's own COG previewer (DECISIONS.md
        # D15). Declaring NODATA=0 explicitly fixes that for such tools,
        # on top of (not instead of) the real alpha band, which stays
        # correct for alpha-aware tools (QGIS etc.). Safe here because
        # D12 already guarantees no genuine photo content is (0,0,0) by
        # the time this step runs.
        # -mo tags: self-describing metadata that travels with the file
        # even if someone only has the .tif (no STAC item yet -- D6).
        gdal_translate -of COG \
            -co COMPRESS=DEFLATE \
            -co OVERVIEW_RESAMPLING=AVERAGE \
            -co BLOCKSIZE=512 \
            -co BIGTIFF=YES \
            -a_nodata 0 \
            -mo TIFFTAG_IMAGEDESCRIPTION="GSI disaster-response ortho imagery: {{layer}}" \
            -mo TIFFTAG_SOFTWARE="optgeo/cogenerate" \
            -mo TIFFTAG_COPYRIGHT="Source imagery (c) Geospatial Information Authority of Japan (GSI); attribution required, see https://maps.gsi.go.jp/development/ichiran.html" \
            -mo LAYER_ID="{{layer}}" \
            -mo SOURCE_URL="https://cyberjapandata.gsi.go.jp/xyz/{{layer}}/{z}/{x}/{y}.png" \
            -mo PIPELINE="https://github.com/optgeo/cogenerate" \
            "$src" "$tmp"
        mv "$tmp" "$dst"
    fi
    gdalinfo "$dst" | head -30

# Run the full pipeline for one layer end to end
run: probe download georef cog
    echo "done: {{out_dir}}/{{layer}}.tif"

# Step 5 (manual, not part of `run`): publish one layer's COG to Source
# Cooperative. Needs `source-coop login` done once already (D10) --
# this repo/Claude never handles the actual credentials, only invokes
# `aws` with --profile source-coop, which reads them via
# ~/.aws/config's credential_process.
upload:
    aws s3 cp {{out_dir}}/{{layer}}.tif \
        s3://smartmaps/cogenerate/{{layer}}.tif \
        --profile source-coop --acl bucket-owner-full-control

# Step 6 (manual, needs `upload` already done): build one layer's STAC
# Item JSON from its already-built, already-uploaded COG (D6/D19).
# asset_url must be data.source.coop (the real image/tiff endpoint,
# range-request-capable, GDAL-readable via /vsicurl/) -- NOT
# source.coop (that's the Next.js product *page*, HTML, gdalinfo can't
# open it; caught live 2026-07-31, every Item generated before this fix
# used the wrong one). Override with ASSET_URL=... if a layer was
# published somewhere else. --cog is passed even if the file's already
# been cleaned up (D20) -- stac_item.py detects that itself and falls
# back to reading from --asset-url directly; --previous-item/--output
# both point at the same path so a refresh carries the old checksum
# forward instead of needing the file at all (never plain `>`
# redirection here -- see stac_item.py's own docstring for the
# self-truncation race that would otherwise cause).
docs_dir := "docs"
asset_url := env_var_or_default("ASSET_URL", "https://data.source.coop/smartmaps/cogenerate/" + layer + ".tif")
# SENSOR=sar for aircraft SAR layers (D27) -- changes the imagery
# asset's roles from ['ortho','data'] to ['amplitude','data'] and
# records properties.gsi:sensor, so a downstream STAC consumer doesn't
# mistake grayscale radar amplitude imagery for an optical orthophoto.
sensor := env_var_or_default("SENSOR", "optical")
stac-item:
    mkdir -p {{docs_dir}}/items
    uv run python -m cogenerate.stac_item \
        --layer {{layer}} \
        --cog {{out_dir}}/{{layer}}.tif \
        --asset-url {{asset_url}} \
        --previous-item {{docs_dir}}/items/{{layer}}.json \
        --output {{docs_dir}}/items/{{layer}}.json \
        --sensor {{sensor}}

# Step 7: rebuild the top-level catalog.json from every Item generated
# so far (docs/items/*.json). Re-run after any `stac-item`.
stac-catalog:
    uv run python -m cogenerate.stac_catalog \
        --items-dir {{docs_dir}}/items/ \
        > {{docs_dir}}/catalog.json

# stac-item + stac-catalog for one layer, in order
stac: stac-item stac-catalog
    echo "done: {{docs_dir}}/items/{{layer}}.json, {{docs_dir}}/catalog.json refreshed"

# Validate every generated Item + the catalog against the STAC spec
# (D6/D19) -- needs `uv sync --extra dev` first for stac-valid.
stac-validate:
    uv run stac-validator batch {{docs_dir}}/items/*.json
    uv run stac-validator validate {{docs_dir}}/catalog.json

# Step 8 (D20): confirm a layer's COG matches what's actually live on
# Source Cooperative -- the gate every cleanup recipe below checks
# before deleting anything. Never trust "upload probably succeeded";
# always re-check the remote. Compares against local out/<layer>.tif
# when it still exists; once that's been cleaned up, falls back to the
# size already recorded in docs/items/<layer>.json (D19) -- Source
# Cooperative, not out/, is the master copy once uploaded (D20), so
# this stays meaningfully re-runnable at any point in a layer's
# lifecycle, not just right after upload. Plain public HTTPS HEAD on
# data.source.coop (no AWS credentials needed -- this only reads
# already-public data, unlike `upload` itself).
verify:
    #!/usr/bin/env bash
    set -euo pipefail
    item_json="{{docs_dir}}/items/{{layer}}.json"
    if [ -f "{{out_dir}}/{{layer}}.tif" ]; then
        local_size=$(stat -f%z "{{out_dir}}/{{layer}}.tif" 2>/dev/null || stat -c%s "{{out_dir}}/{{layer}}.tif")
        source_desc="local {{out_dir}}/{{layer}}.tif"
    elif [ -f "$item_json" ]; then
        local_size=$(uv run python -c "import json,sys; print(json.load(open(sys.argv[1]))['assets']['imagery']['file:size'])" "$item_json")
        source_desc="recorded in $item_json"
    else
        echo "NOT VERIFIED: {{layer}} -- no local {{out_dir}}/{{layer}}.tif and no $item_json to compare against" >&2
        exit 1
    fi
    remote_size=$(curl -sI "{{asset_url}}" | grep -i '^content-length:' | tr -d '\r' | awk '{print $2}')
    if [ -z "$remote_size" ]; then
        echo "NOT VERIFIED: {{layer}} -- couldn't reach {{asset_url}}" >&2
        exit 1
    fi
    if [ "$local_size" != "$remote_size" ]; then
        echo "NOT VERIFIED: {{layer}} -- $source_desc is $local_size bytes, remote is $remote_size bytes" >&2
        exit 1
    fi
    echo "verified: {{layer}} ($local_size bytes, $source_desc, matches {{asset_url}})"

# Step 9 (D20): delete tiles/<layer>/ once `verify` confirms the COG
# built from it is safely on Source Cooperative. Safe to run any time
# after that -- never for a layer still mid-download/rebuild (D11's
# incremental skip-if-present logic needs tiles/ around for that).
cleanup-tiles: verify
    rm -rf {{tiles_dir}}
    echo "removed {{tiles_dir}}/"

# Step 10 (D20, more aggressive -- not bundled into `cleanup-tiles`):
# delete the local out/<layer>.tif COG itself, once BOTH `verify`
# passes AND its STAC Item (docs/items/<layer>.json) already exists --
# the Item's embedded checksum/size is the permanent record of what
# was published, so this is safe only after `just stac-item` has run,
# never before.
cleanup-cog: verify
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -f "{{docs_dir}}/items/{{layer}}.json" ]; then
        echo "refusing: {{docs_dir}}/items/{{layer}}.json doesn't exist yet -- run 'just stac' first" >&2
        exit 1
    fi
    rm -f "{{out_dir}}/{{layer}}.tif"
    echo "removed {{out_dir}}/{{layer}}.tif (recorded in {{docs_dir}}/items/{{layer}}.json)"

# The routine end-of-layer disk reclaim: tiles/ only, not the COG
# itself (see cleanup-cog for that, a separate deliberate step).
cleanup: cleanup-tiles

# Remove intermediate tiles for EVERY layer, verified or not -- a blunt
# full reset, not the per-layer verified reclaim above. Prefer
# `cleanup`/`cleanup-tiles` for routine use.
clean:
    rm -rf tiles

# Step 11: cheap remote-only quality sweep across every Item published
# so far -- HEAD size check + gdalinfo header structure check (COG
# layout, band count, bbox sanity). No local out/ needed, no
# full-file downloads. Not a substitute for a targeted
# gdallocationinfo investigation if a specific layer is suspected
# (D24's noto incident -- gdalinfo alone doesn't prove pixel data is
# actually written), just the routine catalog-wide check.
audit:
    uv run python -m cogenerate.audit --items-dir {{docs_dir}}/items/

# Step 12 (D25): scope which already-published layers plausibly have
# the opaque-pure-white-nodata problem (georef.py now fixes this going
# forward) -- reports a sorted table, doesn't patch anything. Excludes
# layers that sample as monochrome-origin, where real content can
# legitimately be pure white.
whitescan:
    uv run python -m cogenerate.whitescan --items-dir {{docs_dir}}/items/

lint:
    uv run ruff check src/

test:
    uv run pytest -q
