"""Build one top-level STAC Catalog (v1.0.0) from a directory of
already-generated Item JSON files (`stac_item.py`'s output).

Design rationale (DECISIONS.md D6/D19): unlike `optgeo/oam-starc`
(this session's schema reference), which embeds full Item objects
inline under a non-standard `items` array, this Catalog uses proper
`links` with `rel: "item"` pointing at each Item's own hosted JSON
file (DECISIONS.md D19) -- spec-compliant, and keeps `catalog.json`
small regardless of how many layers get added (each Item carries its
own COG checksum/geometry, no reason to duplicate that into the
Catalog document too).

Usage:
    uv run python -m cogenerate.stac_catalog \\
        --items-dir docs/items/ \\
        --catalog-url https://optgeo.github.io/cogenerate/catalog.json \\
        > docs/catalog.json
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(add_completion=False)
err = Console(stderr=True)

STAC_VERSION = "1.0.0"


def build_catalog(items_dir: Path, catalog_url: str, items_base_url: str) -> dict:
    item_files = sorted(items_dir.glob("*.json"))
    links = [
        {"rel": "self", "href": catalog_url, "type": "application/json"},
        {"rel": "root", "href": catalog_url, "type": "application/json"},
    ]
    for path in item_files:
        item = json.loads(path.read_text())
        links.append(
            {
                "rel": "item",
                "href": f"{items_base_url}/{path.name}",
                "type": "application/json",
                "title": item.get("properties", {}).get("title", item.get("id")),
            }
        )
    return {
        "stac_version": STAC_VERSION,
        "type": "Catalog",
        "id": "cogenerate",
        "title": "GSI Disaster-Response Aerial Imagery (COGs)",
        "description": (
            "Cloud-Optimized GeoTIFFs reassembled from GSI (国土地理院) "
            "disaster-response aerial imagery tiles, published on Source "
            "Cooperative. See https://github.com/optgeo/cogenerate."
        ),
        "links": links,
    }


@app.command()
def main(
    items_dir: Path = typer.Option(..., help="Directory of Item JSON files (stac_item.py output)"),
    catalog_url: str = typer.Option(
        "https://optgeo.github.io/cogenerate/catalog.json",
        help="Public URL this Catalog will be hosted at",
    ),
    items_base_url: str = typer.Option(
        "https://optgeo.github.io/cogenerate/items",
        help="Base URL where Item JSON files are hosted",
    ),
):
    """Build the top-level STAC Catalog JSON from a directory of Items, printed to stdout."""
    if not items_dir.is_dir():
        err.print(f"[red]error[/red] {items_dir} is not a directory")
        raise typer.Exit(1)
    catalog = build_catalog(items_dir, catalog_url, items_base_url)
    n = len(catalog["links"]) - 2  # minus self/root
    err.print(f"[green]done[/green] {n} item(s) linked from {items_dir}")
    print(json.dumps(catalog, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
