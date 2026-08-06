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

**Source Cooperative, not out/, is the master copy once uploaded**
(D20): `out/<layer>.tif` is routinely deleted after upload+STAC-item
generation to reclaim disk. So every field here is sourced with a
local-file fast path but a **remote fallback that doesn't need
out/<layer>.tif at all**:
  - geometry/bbox/embedded D15 `-mo` tags: `gdalinfo -json` on either
    the local COG path or, if that's gone, `/vsicurl/<asset_url>`
    directly -- GDAL's COG driver only needs a few header/overview
    byte ranges over HTTP range requests, not the whole multi-GB file
    (confirmed live against `data.source.coop`, which serves
    `Accept-Ranges: bytes`). Never osgeo Python bindings (D2).
  - file size: local `stat()`, or an HTTP HEAD's `Content-Length`.
  - checksum: local sha256 (cheap, no network) when the file's still
    there; otherwise carried forward from `--previous-item`'s already-
    recorded checksum (the whole point of D20's "run stac-item before
    cleanup-cog" ordering -- this is the normal path once out/ is
    gone); downloading-and-hashing from `asset_url` is a last resort
    only, and prints a warning since it's slow.
  - datetime: the layer ID's embedded capture-date fragment (D4) --
    year from the ID's leading 4 digits, month/day from its last
    `_MMDDdo` fragment.
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

**`asset_url` must be the actual data endpoint, not the web UI**:
`https://source.coop/<account>/<product>/<file>` is Source
Cooperative's Next.js product *page* (HTML, not openable by GDAL) --
`https://data.source.coop/<account>/<product>/<file>` is the real
`image/tiff` endpoint with range-request support. Caught live
2026-07-31: every Item generated before this fix used the wrong
(web-UI) URL.

**`--output`, not shell redirection, to avoid a self-truncation race**:
`--previous-item` may point at the same path `--output` writes to
(the common case: refreshing a layer's own existing Item). A plain
`> file.json` shell redirect truncates the destination *before* this
process even starts, so passing the same path via `--previous-item`
would read back an empty file. `--output` reads the old content fully
into memory first, then overwrites -- safe regardless of whether the
two paths are the same.

Usage:
    uv run python -m cogenerate.stac_item \\
        --layer 20260729kumamoto_yatsushiro_0729do_sokuho \\
        --cog out/20260729kumamoto_yatsushiro_0729do_sokuho.tif \\
        --asset-url https://data.source.coop/smartmaps/cogenerate/20260729kumamoto_yatsushiro_0729do_sokuho.tif \\
        --output docs/items/20260729kumamoto_yatsushiro_0729do_sokuho.json

    # Regenerating after out/<layer>.tif has already been cleaned up (D20):
    # no --cog needed at all -- reads directly from --asset-url, carries
    # the checksum forward from the existing Item at --output/--previous-item.
    uv run python -m cogenerate.stac_item \\
        --layer 20260729kumamoto_yatsushiro_0729do_sokuho \\
        --asset-url https://data.source.coop/smartmaps/cogenerate/20260729kumamoto_yatsushiro_0729do_sokuho.tif \\
        --output docs/items/20260729kumamoto_yatsushiro_0729do_sokuho.json \\
        --previous-item docs/items/20260729kumamoto_yatsushiro_0729do_sokuho.json
"""

from __future__ import annotations

import calendar
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import httpx
import typer
from rich.console import Console

app = typer.Typer(add_completion=False)
err = Console(stderr=True)

STAC_VERSION = "1.0.0"
GSI_TERMS_URL = "https://maps.gsi.go.jp/development/ichiran.html"
LAYERS_MARTIN_CATALOG_URL = "https://hfu.github.io/layers-martin/catalog.json"
# STAC common metadata `platform` / OAM extension `oam:platform_type` share
# this vocabulary (DECISIONS.md D6 update, 2026-08-06): the OAM extension's
# JSON schema enum is kite/balloon/uav/aircraft/satellite (its own README
# prose says "airplane", but the schema -- the thing that actually
# validates -- says "aircraft"; schema wins).
PLATFORM_TYPES = {"kite", "balloon", "uav", "aircraft", "satellite"}
OAM_EXTENSION_URL = "https://hotosm.github.io/stactools-hotosm/oam/v0.1.0/schema.json"
# Decided 2026-08-06 (Hidenori): GSI is the actual imagery producer: UN
# Smart Maps Group (DWG7 of the UN Open GIS Initiative, unopengis.org) is
# the community/hosting context this pipeline (and the `smartmaps`
# Source Cooperative account it publishes under) operates within. Spelled
# out in full rather than as "GSI/dwg7" since oam:producer_name is a
# public, HOTOSM-validated field an outside viewer needs to understand
# without knowing UN Open GIS Initiative's internal working-group numbering.
OAM_PRODUCER_NAME = "GSI / UN Smart Maps Group"
COLLECTION_ID = "cogenerate"
# Standard Web Mercator ground sample distance at the equator, 256px
# tiles, zoom 18 -- matches D5 (maxzoom fixed at 18 for every layer).
GSD_Z18_M = 156543.03392804097 / 2**18


def platform_type_of(layer: str, client: httpx.Client) -> str:
    """UAV vs. aircraft, from layers-martin's own `name` field (DECISIONS.md
    D6 update, 2026-08-06) -- GSI's own 名称 text says "無人航空機（UAV）撮影"
    for UAV captures and is silent (plain "撮影"/"ヘリ撮影"/"空中写真"/
    "航空機SAR画像") for manned-aircraft ones. Checked against all 154
    already-published layers before trusting this: 9 UAV, 143 aircraft,
    2 not found in the live catalog (a known ID-typo case and a
    brand-new layer layers-martin hasn't indexed yet) -- both fall back
    to "aircraft" here, this pipeline's long-standing default, with a
    warning rather than a hard failure."""
    try:
        data = client.get(LAYERS_MARTIN_CATALOG_URL, timeout=30.0).json()
        name = data["tiles"][layer]["name"]
    except (httpx.HTTPError, KeyError) as e:
        err.print(
            f"[yellow]warn[/yellow] couldn't look up {layer!r} in layers-martin's catalog "
            f"({e!r}) -- defaulting platform to 'aircraft'"
        )
        return "aircraft"
    return "uav" if ("UAV" in name or "無人航空機" in name) else "aircraft"


def gdalinfo_json(cog: Path | None, asset_url: str) -> dict:
    """Local file if it still exists (D20); otherwise read the COG
    directly over HTTP via GDAL's /vsicurl/ -- cheap even for a
    multi-GB file since only header/overview ranges are fetched."""
    source = str(cog) if cog is not None and cog.exists() else f"/vsicurl/{asset_url}"
    out = subprocess.run(
        ["gdalinfo", "-json", source], capture_output=True, check=True, text=True
    ).stdout
    return json.loads(out)


def file_size_of(cog: Path | None, asset_url: str) -> int:
    if cog is not None and cog.exists():
        return cog.stat().st_size
    resp = httpx.head(asset_url, timeout=30.0, follow_redirects=True)
    resp.raise_for_status()
    return int(resp.headers["content-length"])


def sha256_of_local(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_of_remote(asset_url: str) -> str:
    h = hashlib.sha256()
    with httpx.stream("GET", asset_url, timeout=None, follow_redirects=True) as resp:
        resp.raise_for_status()
        for chunk in resp.iter_bytes(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def checksum_of(cog: Path | None, asset_url: str, previous: dict | None) -> str:
    if cog is not None and cog.exists():
        return sha256_of_local(cog)
    if previous is not None:
        checksum = previous.get("assets", {}).get("imagery", {}).get("file:checksum_sha256")
        if checksum:
            return checksum
    err.print(
        f"[yellow]warn[/yellow] no local COG and no --previous-item checksum for "
        f"{asset_url} -- downloading the whole file to hash it (slow)"
    )
    return sha256_of_remote(asset_url)


def bbox_of(geometry: dict) -> list[float]:
    lons = [pt[0] for ring in geometry["coordinates"] for pt in ring]
    lats = [pt[1] for ring in geometry["coordinates"] for pt in ring]
    return [min(lons), min(lats), max(lons), max(lats)]


def created_at(previous: dict | None) -> str:
    """STAC common metadata `created` -- when this Item was added to the
    catalog, distinct from `properties.datetime` (the photo's capture
    date, D4). Carries the value forward from `--previous-item` once set,
    so refreshing an existing Item (new checksum, re-run after a fix)
    never bumps its original catalog-addition date -- only a genuinely
    new Item gets "now". DECISIONS.md D6 update, 2026-08-06: this is the
    "what's new since last sync" signal an incremental harvester (ours or
    HOTOSM's) needs, which capture date can't provide for a pipeline that
    regularly publishes decades-old disaster imagery."""
    if previous is not None:
        prev_created = previous.get("properties", {}).get("created")
        if prev_created:
            return prev_created
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_item(
    layer: str,
    cog: Path | None,
    asset_url: str,
    item_url: str,
    catalog_url: str,
    collection_url: str,
    previous: dict | None,
    platform: str,
    sensor: str = "optical",
) -> dict:
    info = gdalinfo_json(cog, asset_url)
    geometry = info["wgs84Extent"]
    tags = info.get("metadata", {}).get("", {})
    title = tags.get("TIFFTAG_IMAGEDESCRIPTION", layer)

    properties = {
        **parse_capture_date(layer),
        "created": created_at(previous),
        "title": title,
        "gsd": GSD_Z18_M,
        "license": "CC-BY-4.0",
        "platform": platform,
        "oam:producer_name": OAM_PRODUCER_NAME,
        "oam:platform_type": platform,
        "providers": [
            {
                "name": "Geospatial Information Authority of Japan (GSI)",
                "roles": ["producer", "licensor"],
            },
            {
                "name": "UN Smart Maps Group",
                "roles": ["host"],
                "url": "https://source.coop/smartmaps",
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
    }
    # D27: SAR layers get a distinct asset role and an explicit sensor
    # note so a downstream STAC consumer doesn't mistake grayscale radar
    # amplitude imagery for an optical orthophoto. "amplitude" is drawn
    # from the community `sar` STAC extension's recommended asset-role
    # vocabulary (stac-extensions/sar) -- used here as a plain asset
    # role without formally declaring stac_extensions, since GSI
    # publishes no instrument_mode/frequency_band/polarization metadata
    # for these layers to actually populate the extension's own fields
    # with (D19's "don't declare what you don't use" applies here too).
    if sensor == "sar":
        imagery_roles = ["amplitude", "data"]
        properties["gsi:sensor"] = (
            "aircraft SAR (grayscale amplitude imagery, not optical photography)"
        )
    else:
        imagery_roles = ["ortho", "data"]

    return {
        "stac_version": STAC_VERSION,
        "stac_extensions": [OAM_EXTENSION_URL],
        "type": "Feature",
        "id": layer,
        "geometry": geometry,
        "bbox": bbox_of(geometry),
        "properties": properties,
        "collection": COLLECTION_ID,
        "links": [
            {"rel": "self", "href": item_url, "type": "application/json"},
            {"rel": "root", "href": catalog_url, "type": "application/json"},
            {"rel": "collection", "href": collection_url, "type": "application/json"},
            {"rel": "license", "href": GSI_TERMS_URL, "title": "GSI usage terms (CC-BY-4.0-compatible, attribution required)"},
        ],
        "assets": {
            "imagery": {
                "href": asset_url,
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "title": title,
                "roles": imagery_roles,
                "file:size": file_size_of(cog, asset_url),
                "file:checksum_sha256": checksum_of(cog, asset_url, previous),
            },
            "metadata": {
                "href": item_url,
                "type": "application/json",
                "roles": ["metadata"],
            },
        },
    }


def parse_capture_date(layer_id: str) -> dict[str, str | None]:
    """Capture date embedded in the layer ID (DECISIONS.md D4): year
    from the ID's leading 4 digits, month/day from its last `_MMDDdo`
    fragment. Covers every `_do`/`_do_sokuho`/`dol`/`doh`-style layer
    ID seen in layers-martin's catalog census.

    Returns the STAC datetime properties to merge into an Item, not a
    bare string -- most layers get an exact `{"datetime": "..."}`, but
    a `dol`-suffixed ID with a leading `YYYYMM00` or `YYYY0000`
    placeholder (GSI's own way of saying "somewhere in this month/year",
    seen on `19480000dol`/`19620000dol`, historical reference imagery
    of Hiroshima kept alongside the 2014 landslide-disaster layers) has
    no exact day. STAC's core common-metadata date-and-time-range
    fields (`datetime: null` + `start_datetime`/`end_datetime`, no
    extension needed) represent that honestly instead of guessing a
    single date -- decided live 2026-08-01 rather than left as the
    hard error this function raised before that."""
    year = layer_id[:4]
    if not year.isdigit():
        raise ValueError(f"layer ID {layer_id!r} doesn't start with a 4-digit year")
    match = None
    for m in re.finditer(r"(?:^|_)(\d{2})(\d{2})do(?:_|$)", layer_id):
        match = m  # take the last match: closest to the "do" suffix
    if match is not None:
        month, day = match.group(1), match.group(2)
        return {"datetime": f"{year}-{month}-{day}T00:00:00Z"}
    if layer_id[:8].isdigit():
        month, day = layer_id[4:6], layer_id[6:8]
        if month == "00":
            return {
                "datetime": None,
                "start_datetime": f"{year}-01-01T00:00:00Z",
                "end_datetime": f"{year}-12-31T23:59:59Z",
            }
        if day == "00":
            last_day = calendar.monthrange(int(year), int(month))[1]
            return {
                "datetime": None,
                "start_datetime": f"{year}-{month}-01T00:00:00Z",
                "end_datetime": f"{year}-{month}-{last_day:02d}T23:59:59Z",
            }
        return {"datetime": f"{year}-{month}-{day}T00:00:00Z"}
    raise ValueError(f"no _MMDDdo capture-date fragment found in {layer_id!r}")


@app.command()
def main(
    layer: str = typer.Option(..., help="GSI tile ID, e.g. 20260729kumamoto_yatsushiro_0729do_sokuho"),
    asset_url: str = typer.Option(
        ..., help="Public data URL of the uploaded COG -- must be data.source.coop, NOT source.coop (the web UI page, not GDAL-readable)"
    ),
    cog: Path = typer.Option(
        None,
        help="Path to the local COG if it still exists (optional -- falls back to reading "
        "directly from --asset-url once out/<layer>.tif has been cleaned up, D20)",
    ),
    previous_item: Path = typer.Option(
        None,
        help="Path to this layer's previously-generated Item JSON, if any -- carries its "
        "checksum forward when no local COG exists, avoiding a slow re-download just to re-hash",
    ),
    output: Path = typer.Option(
        None,
        help="Write the Item JSON here instead of stdout (required if --previous-item is the "
        "same path, to avoid a shell-redirection truncation race)",
    ),
    items_base_url: str = typer.Option(
        "https://optgeo.github.io/cogenerate/items",
        help="Base URL where this Item's own JSON will be hosted (self-referencing link/metadata asset)",
    ),
    catalog_url: str = typer.Option(
        "https://optgeo.github.io/cogenerate/catalog.json",
        help="URL of the top-level Catalog this Item belongs to",
    ),
    collection_url: str = typer.Option(
        "https://optgeo.github.io/cogenerate/collection.json",
        help="URL of the STAC Collection this Item belongs to (properties.collection + rel:collection link)",
    ),
    sensor: str = typer.Option(
        "optical",
        help="'optical' (default, aerial/UAV photography) or 'sar' (aircraft SAR grayscale "
        "amplitude imagery, DECISIONS.md D27) -- sar sets the imagery asset's roles to "
        "['amplitude', 'data'] instead of ['ortho', 'data'] and records properties.gsi:sensor, "
        "so a downstream STAC consumer doesn't mistake radar imagery for an optical orthophoto",
    ),
    platform: str = typer.Option(
        None,
        help="Override auto-detected 'uav'/'aircraft' platform type (kite/balloon/uav/aircraft/"
        "satellite) -- by default, looked up from layers-martin's own 名称 text for this layer "
        "(DECISIONS.md D6 update, 2026-08-06), which says 無人航空機（UAV）撮影 for UAV captures "
        "and is silent for manned-aircraft ones",
    ),
):
    """Build one STAC Item JSON for an already-built (or already-uploaded, even if since
    cleaned up locally) COG."""
    if sensor not in ("optical", "sar"):
        raise typer.BadParameter("--sensor must be 'optical' or 'sar'")
    if platform is not None and platform not in PLATFORM_TYPES:
        raise typer.BadParameter(f"--platform must be one of {sorted(PLATFORM_TYPES)}")
    if cog is not None and not cog.exists():
        err.print(f"[yellow]warn[/yellow] {cog} doesn't exist -- reading from {asset_url} instead")
        cog = None
    previous = None
    if previous_item is not None and previous_item.exists():
        previous = json.loads(previous_item.read_text())

    with httpx.Client(headers={"User-Agent": "optgeo/cogenerate stac_item (contact via github.com/optgeo)"}) as client:
        resolved_platform = platform if platform is not None else platform_type_of(layer, client)

    item_url = f"{items_base_url}/{layer}.json"
    item = build_item(
        layer, cog, asset_url, item_url, catalog_url, collection_url, previous, resolved_platform, sensor
    )
    text = json.dumps(item, indent=2, ensure_ascii=False)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    app()
