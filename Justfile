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
# Plain string concatenation (not the `/` path-join operator) for
# portability across `just` versions -- `/` as path-join was added in a
# fairly recent just release and may not exist on an older Mac install.
tiles_dir := "tiles/" + layer
out_dir := "out"

default:
    just --list

# Step 1: quadtree-probe which tiles exist at maxzoom, no full-extent brute force
probe:
    mkdir -p tiles
    uv run python -m cogenerate.probe \
        --layer {{layer}} --minzoom {{minzoom}} --maxzoom {{maxzoom}} \
        --seed-x {{seed_x}} --seed-y {{seed_y}} \
        > tiles/{{layer}}.z{{maxzoom}}.csv
    wc -l tiles/{{layer}}.z{{maxzoom}}.csv

# Step 2: download only the confirmed tiles from step 1
download:
    uv run python -m cogenerate.download \
        --layer {{layer}} \
        --tiles tiles/{{layer}}.z{{maxzoom}}.csv \
        --out {{tiles_dir}}/

# Step 3: georeference + merge into one mosaic VRT (EPSG:3857)
georef:
    mkdir -p {{out_dir}}
    uv run python -m cogenerate.georef \
        --dir {{tiles_dir}}/ \
        --merged {{out_dir}}/{{layer}}.vrt

# Step 4: VRT -> COG. Overviews are generated here, not fetched from GSI.
cog:
    gdal_translate -of COG \
        -co COMPRESS=DEFLATE \
        -co OVERVIEW_RESAMPLING=AVERAGE \
        -co BLOCKSIZE=512 \
        {{out_dir}}/{{layer}}.vrt \
        {{out_dir}}/{{layer}}.tif
    gdalinfo {{out_dir}}/{{layer}}.tif | head -30

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
