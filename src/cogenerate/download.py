"""Download confirmed tiles (from probe.py output) into z/x/y.ext layout,
ready for `gdalbuildvrt` to consume via a small XYZ->georeferenced VRT step.

Only tiles that probe.py already confirmed (200) are requested here, so
this step should see ~0 errors. Any error is logged and skipped rather
than aborting the whole run -- a missing tile just leaves a gap, which
gdalbuildvrt/COG creation treats as nodata via the alpha channel.

Usage:
    uv run python -m cogenerate.download \\
        --layer 20260729kumamoto_yatsushiro_0729do_sokuho \\
        --tiles tiles/20260729kumamoto_yatsushiro_0729do_sokuho.z18.csv \\
        --out tiles/20260729kumamoto_yatsushiro_0729do_sokuho/
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import typer
from rich.console import Console

app = typer.Typer(add_completion=False)
err = Console(stderr=True)

BASE = "https://cyberjapandata.gsi.go.jp/xyz"


def read_tiles(path: Path) -> list[tuple[int, int, int]]:
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        z, x, y = (int(v) for v in line.split(","))
        out.append((z, x, y))
    return out


async def fetch_one(client: httpx.AsyncClient, layer: str, z: int, x: int, y: int, ext: str, out: Path) -> bool:
    url = f"{BASE}/{layer}/{z}/{x}/{y}.{ext}"
    dest = out / str(z) / str(x) / f"{y}.{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = await client.get(url, timeout=20.0)
        if r.status_code != 200:
            err.print(f"[yellow]skip[/yellow] {z}/{x}/{y}: HTTP {r.status_code} (was confirmed earlier -- flaky?)")
            return False
        dest.write_bytes(r.content)
        return True
    except httpx.HTTPError as e:
        err.print(f"[yellow]skip[/yellow] {z}/{x}/{y}: {e!r}")
        return False


async def download_all(layer: str, tiles: list[tuple[int, int, int]], ext: str, out: Path, concurrency: int) -> None:
    sem = asyncio.Semaphore(concurrency)
    ok_count = 0

    async with httpx.AsyncClient(headers={"User-Agent": "optgeo/cogenerate download (contact via github.com/optgeo)"}) as client:
        async def bound_fetch(z: int, x: int, y: int) -> bool:
            async with sem:
                return await fetch_one(client, layer, z, x, y, ext, out)

        results = await asyncio.gather(*(bound_fetch(z, x, y) for z, x, y in tiles))
        ok_count = sum(results)

    err.print(f"[green]done[/green] {ok_count}/{len(tiles)} tiles saved to {out}")


@app.command()
def main(
    layer: str = typer.Option(...),
    tiles: Path = typer.Option(..., help="CSV from cogenerate.probe (z,x,y per line)"),
    out: Path = typer.Option(..., help="Output directory (z/x/y.ext layout)"),
    ext: str = typer.Option("png"),
    concurrency: int = typer.Option(8),
):
    tile_list = read_tiles(tiles)
    if not tile_list:
        err.print("[red]error[/red] no tiles in input CSV")
        raise typer.Exit(1)
    asyncio.run(download_all(layer, tile_list, ext, out, concurrency))


if __name__ == "__main__":
    app()
