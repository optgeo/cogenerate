"""Build the one STAC Collection object every Item (`stac_item.py`)
references via its top-level `collection` field, from the same
directory of already-generated Item JSON files `stac_catalog.py` reads.

Design rationale (DECISIONS.md D6 update, 2026-08-06): pgstac -- the
database backing OpenAerialMap's own ingestion pipeline, per the
`hotosm/stactools-hotosm` investigation -- requires every ingested Item
to reference a real Collection object; `cogenerate`'s catalog had none
(D19 deliberately skipped this for a GitHub-Pages-only static catalog,
before OAM ingestion was a concrete near-term goal). Extent (spatial
bbox union, temporal min/max) is computed from the real Items on disk
rather than hardcoded to a global bbox/open-ended interval -- more
useful to a downstream consumer than the placeholder-extent pattern
`stactools-hotosm`'s own `maxar/stac.py::create_collection()` uses,
and cheap here since every Item file is already local.

`catalog.json` keeps its existing flat `rel:item` links unchanged
(`candidates.py`'s `fetch_published_ids()` and other live consumers
depend on that shape, D7) -- this Collection is additive: `catalog.json`
gets one new `rel:child` link to it, and it independently links every
Item too via its own `rel:item` links, so it's a valid, browsable
Collection on its own regardless of how it's reached.

Usage:
    uv run python -m cogenerate.stac_collection \\
        --items-dir docs/items/ \\
        --catalog-url https://optgeo.github.io/cogenerate/catalog.json \\
        --collection-url https://optgeo.github.io/cogenerate/collection.json \\
        > docs/collection.json
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(add_completion=False)
err = Console(stderr=True)

STAC_VERSION = "1.0.0"
COLLECTION_ID = "cogenerate"
GSI_TERMS_URL = "https://maps.gsi.go.jp/development/ichiran.html"


def item_datetimes(item: dict) -> list[str]:
    """Every ISO8601 timestamp an Item's properties commit to -- exact
    `datetime` when known, `start_datetime`/`end_datetime` for the
    approximate-historical-date case (D23) where `datetime` is null."""
    props = item.get("properties", {})
    dts = [
        props[key]
        for key in ("datetime", "start_datetime", "end_datetime")
        if props.get(key)
    ]
    return dts


def bbox_union(boxes: list[list[float]]) -> list[float]:
    lons = [b[0] for b in boxes] + [b[2] for b in boxes]
    lats = [b[1] for b in boxes] + [b[3] for b in boxes]
    return [min(lons), min(lats), max(lons), max(lats)]


def build_collection(
    items_dir: Path, catalog_url: str, collection_url: str, items_base_url: str
) -> dict:
    item_files = sorted(items_dir.glob("*.json"))
    items = [json.loads(p.read_text()) for p in item_files]
    if not items:
        raise ValueError(f"no Item JSON files found in {items_dir}")

    bbox = bbox_union([item["bbox"] for item in items])
    all_dts = sorted(dt for item in items for dt in item_datetimes(item))

    links = [
        {"rel": "self", "href": collection_url, "type": "application/json"},
        {"rel": "root", "href": catalog_url, "type": "application/json"},
        {"rel": "parent", "href": catalog_url, "type": "application/json"},
        {
            "rel": "license",
            "href": GSI_TERMS_URL,
            "title": "GSI usage terms (CC-BY-4.0-compatible, attribution required)",
        },
    ]
    for item in items:
        links.append(
            {
                "rel": "item",
                "href": f"{items_base_url}/{item['id']}.json",
                "type": "application/json",
                "title": item.get("properties", {}).get("title", item["id"]),
            }
        )

    return {
        "stac_version": STAC_VERSION,
        "type": "Collection",
        "id": COLLECTION_ID,
        "title": "GSI Disaster-Response Aerial Imagery (COGs)",
        "description": (
            "Cloud-Optimized GeoTIFFs reassembled from GSI (国土地理院) "
            "disaster-response aerial imagery tiles, published on Source "
            "Cooperative. See https://github.com/optgeo/cogenerate."
        ),
        "license": "CC-BY-4.0",
        "extent": {
            "spatial": {"bbox": [bbox]},
            "temporal": {"interval": [[all_dts[0], all_dts[-1]]]},
        },
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
                "url": "https://github.com/optgeo/cogenerate",
            },
        ],
        "links": links,
    }


@app.command()
def main(
    items_dir: Path = typer.Option(..., help="Directory of Item JSON files (stac_item.py output)"),
    catalog_url: str = typer.Option(
        "https://optgeo.github.io/cogenerate/catalog.json",
        help="URL of the top-level Catalog this Collection is a child of",
    ),
    collection_url: str = typer.Option(
        "https://optgeo.github.io/cogenerate/collection.json",
        help="Public URL this Collection will be hosted at",
    ),
    items_base_url: str = typer.Option(
        "https://optgeo.github.io/cogenerate/items",
        help="Base URL where Item JSON files are hosted",
    ),
):
    """Build the STAC Collection JSON (extent computed from every Item in
    --items-dir), printed to stdout."""
    if not items_dir.is_dir():
        err.print(f"[red]error[/red] {items_dir} is not a directory")
        raise typer.Exit(1)
    collection = build_collection(items_dir, catalog_url, collection_url, items_base_url)
    n = len(collection["links"]) - 4  # minus self/root/parent/license
    err.print(f"[green]done[/green] {n} item(s) linked, extent {collection['extent']}")
    print(json.dumps(collection, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
