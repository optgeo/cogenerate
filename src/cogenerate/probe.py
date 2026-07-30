"""Quadtree-pruning existence prober for GSI (chiriin) XYZ tile layers.

Design rationale (from 2026-07-30 planning session):
  - GSI does not reliably publish mokuroku.csv.gz for disaster-response
    ("_do" / "_do_sokuho") layers; only std/pale/english are guaranteed.
  - cocotile and daicho are not usable here: cocotile requires already
    knowing the tile position, and daicho is GSI's internal cache, not a
    public API.
  - So: start at the layer's documented minzoom (see ichiran.html; for
    "_do*" layers this is almost always 10) and recurse. A 404 prunes the
    whole subtree under that tile -- children are never requested. Only
    tiles that return 200 spawn the 4 children at the next zoom level.
  - This keeps wasted requests roughly proportional to the boundary of
    the coverage polygon, not to the full bounding box x maxzoom.

Output: newline-delimited "z,x,y" for every CONFIRMED (200) tile at the
target (max) zoom. Feed this list to download.py, then gdalbuildvrt.

Usage:
    uv run python -m cogenerate.probe \\
        --layer 20260729kumamoto_yatsushiro_0729do_sokuho \\
        --minzoom 10 --maxzoom 18 \\
        --seed-x 883 --seed-y 414 \\
        > tiles/20260729kumamoto_yatsushiro_0729do_sokuho.z18.csv

Note: this script has NOT been network-tested. The sandbox used to write
it has an egress allowlist that rejects cyberjapandata.gsi.go.jp
(x-deny-reason: host_not_allowed). Test from an environment with real
network access before relying on it. See HANDOVER.md.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
import typer
from rich.console import Console

app = typer.Typer(add_completion=False)
err = Console(stderr=True)

BASE = "https://cyberjapandata.gsi.go.jp/xyz"


@dataclass(frozen=True)
class Tile:
    z: int
    x: int
    y: int

    def children(self) -> list[Tile]:
        return [
            Tile(self.z + 1, self.x * 2 + dx, self.y * 2 + dy)
            for dx in (0, 1)
            for dy in (0, 1)
        ]

    def url(self, layer: str, ext: str) -> str:
        return f"{BASE}/{layer}/{self.z}/{self.x}/{self.y}.{ext}"


async def exists(client: httpx.AsyncClient, layer: str, tile: Tile, ext: str) -> bool:
    try:
        r = await client.head(tile.url(layer, ext), timeout=10.0)
        if r.status_code == 405:  # some GSI endpoints don't support HEAD
            r = await client.get(tile.url(layer, ext), timeout=10.0)
        return r.status_code == 200
    except httpx.HTTPError as e:
        err.print(f"[yellow]warn[/yellow] {tile} -> {e!r}")
        return False


async def probe(
    layer: str,
    seeds: list[Tile],
    maxzoom: int,
    ext: str,
    concurrency: int,
) -> list[Tile]:
    """BFS quadtree probe. Returns confirmed leaf tiles at maxzoom."""
    sem = asyncio.Semaphore(concurrency)
    confirmed_leaves: list[Tile] = []
    frontier = list(seeds)
    requests_made = 0

    async with httpx.AsyncClient(headers={"User-Agent": "optgeo/cogenerate probe (contact via github.com/optgeo)"}) as client:
        async def check(t: Tile) -> tuple[Tile, bool]:
            nonlocal requests_made
            async with sem:
                requests_made += 1
                return t, await exists(client, layer, t, ext)

        while frontier:
            results = await asyncio.gather(*(check(t) for t in frontier))
            next_frontier: list[Tile] = []
            for tile, ok in results:
                if not ok:
                    continue  # prune: subtree never visited
                if tile.z >= maxzoom:
                    confirmed_leaves.append(tile)
                else:
                    next_frontier.extend(tile.children())
            frontier = next_frontier

    err.print(f"[green]done[/green] {layer}: {requests_made} requests, "
               f"{len(confirmed_leaves)} confirmed tiles at z{maxzoom}")
    return confirmed_leaves


@app.command()
def main(
    layer: str = typer.Option(..., help="GSI tile ID, e.g. 20260729kumamoto_yatsushiro_0729do_sokuho"),
    minzoom: int = typer.Option(10, help="Starting zoom (see ichiran.html for the layer)"),
    maxzoom: int = typer.Option(18, help="Target zoom to fetch for COG source (256px tiles)"),
    seed_x: list[int] = typer.Option(..., help="Seed tile X at --minzoom (repeatable)"),
    seed_y: list[int] = typer.Option(..., help="Seed tile Y at --minzoom (repeatable, paired by position)"),
    ext: str = typer.Option("png", help="Tile extension (png for most _do*/_do_sokuho layers)"),
    concurrency: int = typer.Option(8, help="Max in-flight requests; be a good citizen to a gov server"),
):
    """Probe a GSI disaster-response tile layer and print confirmed z/x/y at --maxzoom."""
    if len(seed_x) != len(seed_y):
        err.print("[red]error[/red] --seed-x and --seed-y counts must match")
        raise typer.Exit(1)
    seeds = [Tile(minzoom, x, y) for x, y in zip(seed_x, seed_y)]
    leaves = asyncio.run(probe(layer, seeds, maxzoom, ext, concurrency))
    for t in sorted(leaves, key=lambda t: (t.x, t.y)):
        print(f"{t.z},{t.x},{t.y}")


if __name__ == "__main__":
    app()
