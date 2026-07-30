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
        gdal_translate -of COG \
            -co COMPRESS=DEFLATE \
            -co OVERVIEW_RESAMPLING=AVERAGE \
            -co BLOCKSIZE=512 \
            "$src" "$tmp"
        mv "$tmp" "$dst"
    fi
    gdalinfo "$dst" | head -30

# Run the full pipeline for one layer end to end
run: probe download georef cog
    echo "done: {{out_dir}}/{{layer}}.tif"

# Remove intermediate tiles (keep out/ COGs)
clean:
    rm -rf tiles

lint:
    uv run ruff check src/

test:
    uv run pytest -q
