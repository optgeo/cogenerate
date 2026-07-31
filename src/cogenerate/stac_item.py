"""Build one STAC Item (v1.0.0) from one already-built COG.

Design rationale (DECISIONS.md D6/D19): the goal is a static STAC
catalog on GitHub Pages, eventually pitched to HOTOSM/OAM (D6's
roadmap note: OAM v2 plans to "map publicly available STACs" from
external providers). `optgeo/oam-starc` -- a sibling repo that mirrors
OpenAerialMap's own metadata API into static STAC -- is this session's
reference for schema/asset conventions, so a future HOTOSM pitch lands
on ground they already recognize: hand-built JSON (no STAC SDK
dependency, matching D2's "small inspectable units" preference),
`imagery`/`metadata` asset keys with `roles` classifying image type,
`stac_extensions` only declared when actually populated.

Every field is sourced from data already on disk -- no new scraping:
  - geometry/bbox: `gdalinfo -json` on the COG already reports
    `wgs84Extent` (lon/lat polygon) -- shelled out to, per D2's "GDAL
    via subprocess, never osgeo bindings" rule.
  - datetime: the layer ID's embedded capture-date fragment (D4) --
    year from the ID's leading 4 digits, month/day from its last
    `_MMDDdo` fragment (the naming convention across every `_do`/
    `_do_sokuho`-style layer seen in layers-martin's catalog).
  - title/source URL/copyright: already embedded as COG-level
    TIFFTAG/`-mo` metadata by the `cog` Justfile step (D15) -- read
    back via the same `gdalinfo -json` call's `metadata` block.
  - gsd: computed from maxzoom=18 (D5, fixed for every layer), not
    scraped -- standard Web Mercator meters/pixel at the equator.
  - license: GSI's tile terms are the Japanese government's standard
    usage terms (政府標準利用規約), CC-BY-4.0-compatible -- distinct
    from the CC0-1.0 that covers only this pipeline's own code (D3).
    STAC's `license` property is set to the SPDX ID `"CC-BY-4.0"`
    (Hidenori, 2026-07-31: avoid `"other"`, which reads as evasive/
    untrustworthy to a downstream consumer when a real SPDX ID
    applies), plus a `license` link to GSI's terms page for the
    specifics (attribution wording, etc.) CC-BY-4.0 alone doesn't
    capture.

Usage:
    uv run python -m cogenerate.stac_item \\
        --layer 20260729kumamoto_yatsushiro_0729do_sokuho \\
        --cog out/20260729kumamoto_yatsushiro_0729do_sokuho.tif \\
        --asset-url https://source.coop/smartmaps/cogenerate/20260729kumamoto_yatsushiro_0729do_sokuho.tif \\
        > docs/items/20260729kumamoto_yatsushiro_0729do_sokuho.json
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(add_completion=False)
err = Console(stderr=True)

STAC_VERSION = "1.0.0"
GSI_TERMS_URL = "https://maps.gsi.go.jp/development/ichiran.html"
# Standard Web Mercator ground sample distance at the equator, 256px
# tiles, zoom 18 -- matches D5 (maxzoom fixed at 18 for every layer).
GSD_Z18_M = 156543.03392804097 / 2**18


def gdalinfo_json(path: Path) -> dict:
    out = subprocess.run(
        ["gdalinfo", "-json", str(path)], capture_output=True, check=True, text=True
    ).stdout
    return json.loads(out)


def parse_capture_date(layer_id: str) -> str:
    """Capture date embedded in the layer ID (DECISIONS.md D4): year
    from the ID's leading 4 digits, month/day from its last `_MMDDdo`
    fragment. Covers every `_do`/`_do_sokuho`/`dol`/`doh`-style layer
    ID seen in layers-martin's catalog census."""
    year = layer_id[:4]
    if not year.isdigit():
        raise ValueError(f"layer ID {layer_id!r} doesn't start with a 4-digit year")
    match = None
    for m in re.finditer(r"(?:^|_)(\d{2})(\d{2})do(?:_|$)", layer_id):
        match = m  # take the last match: closest to the "do" suffix
    if match is None:
        raise ValueError(f"no _MMDDdo capture-date fragment found in {layer_id!r}")
    month, day = match.group(1), match.group(2)
    return f"{year}-{month}-{day}T00:00:00Z"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def bbox_of(geometry: dict) -> list[float]:
    lons = [pt[0] for ring in geometry["coordinates"] for pt in ring]
    lats = [pt[1] for ring in geometry["coordinates"] for pt in ring]
    return [min(lons), min(lats), max(lons), max(lats)]


def build_item(
    layer: str, cog: Path, asset_url: str, item_url: str, catalog_url: str
) -> dict:
    info = gdalinfo_json(cog)
    geometry = info["wgs84Extent"]
    tags = info.get("metadata", {}).get("", {})
    title = tags.get("TIFFTAG_IMAGEDESCRIPTION", layer)

    return {
        "stac_version": STAC_VERSION,
        "stac_extensions": [],
        "type": "Feature",
        "id": layer,
        "geometry": geometry,
        "bbox": bbox_of(geometry),
        "properties": {
            "datetime": parse_capture_date(layer),
            "title": title,
            "gsd": GSD_Z18_M,
            "license": "CC-BY-4.0",
            "platform": "aircraft",
            "providers": [
                {
                    "name": "Geospatial Information Authority of Japan (GSI)",
                    "roles": ["producer", "licensor"],
                },
                {
                    "name": "optgeo/cogenerate",
                    "roles": ["processor"],
                    "url": tags.get("PIPELINE", "https://github.com/optgeo/cogenerate"),
                },
            ],
            "gsi:layer_id": layer,
            "gsi:source_url": tags.get("SOURCE_URL"),
            "gsi:attribution": tags.get("TIFFTAG_COPYRIGHT"),
        },
        "links": [
            {"rel": "self", "href": item_url, "type": "application/json"},
            {"rel": "root", "href": catalog_url, "type": "application/json"},
            {"rel": "license", "href": GSI_TERMS_URL, "title": "GSI usage terms (CC-BY-4.0-compatible, attribution required)"},
        ],
        "assets": {
            "imagery": {
                "href": asset_url,
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "title": title,
                "roles": ["ortho", "data"],
                "file:size": cog.stat().st_size,
                "file:checksum_sha256": sha256_of(cog),
            },
            "metadata": {
                "href": item_url,
                "type": "application/json",
                "roles": ["metadata"],
            },
        },
    }


@app.command()
def main(
    layer: str = typer.Option(..., help="GSI tile ID, e.g. 20260729kumamoto_yatsushiro_0729do_sokuho"),
    cog: Path = typer.Option(..., help="Path to the already-built COG (out/<layer>.tif)"),
    asset_url: str = typer.Option(..., help="Public URL of the uploaded COG (e.g. Source Cooperative)"),
    items_base_url: str = typer.Option(
        "https://optgeo.github.io/cogenerate/items",
        help="Base URL where this Item's own JSON will be hosted (self-referencing link/metadata asset)",
    ),
    catalog_url: str = typer.Option(
        "https://optgeo.github.io/cogenerate/catalog.json",
        help="URL of the top-level Catalog this Item belongs to",
    ),
):
    """Build one STAC Item JSON for an already-built COG, printed to stdout."""
    if not cog.exists():
        err.print(f"[red]error[/red] {cog} does not exist")
        raise typer.Exit(1)
    item_url = f"{items_base_url}/{layer}.json"
    item = build_item(layer, cog, asset_url, item_url, catalog_url)
    print(json.dumps(item, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
