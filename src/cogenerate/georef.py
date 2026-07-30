"""Georeference bare XYZ tile PNGs into small VRT sidecars, then merge.

Each GSI XYZ tile is a 256x256 PNG with NO embedded georeferencing --
position is implied only by its z/x/y path. This script computes the
WebMercator (EPSG:3857) corner coordinates for each tile from its path
and calls `gdal_translate -a_ullr ... -a_srs EPSG:3857` to produce a
cheap .vrt (no pixel data copy) per tile. gdalbuildvrt then merges all
per-tile VRTs into one mosaic VRT, which gdal_translate -of COG turns
into the final Cloud-Optimized GeoTIFF.

This keeps each step a small, single-purpose, inspectable unit --
consistent with the existing GDAL/Tippecanoe/Unix-CLI workflow.

Requires: gdal_translate, gdalbuildvrt on PATH (system GDAL, not a
Python binding -- deliberately, to match the existing toolchain).

UNTESTED RISK: GSI ortho PNGs may mix band counts -- fully-interior
tiles as RGB (3 band) and boundary tiles that straddle the coverage
polygon as RGBA (4 band, transparent outside coverage). `gdalbuildvrt`
generally handles this by promoting everything to the superset band
count, but this has not been verified against real GSI tiles from this
sandbox (no network access). If `gdalbuildvrt` errors or produces a
mosaic with wrong colors at tile boundaries, check band counts first:
`gdalinfo <one interior tile>.vrt` vs `gdalinfo <one boundary tile>.vrt`.

Usage:
    uv run python -m cogenerate.georef \\
        --dir tiles/20260729kumamoto_yatsushiro_0729do_sokuho/ \\
        --ext png \\
        --merged out/20260729kumamoto_yatsushiro_0729do_sokuho.vrt
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import track

app = typer.Typer(add_completion=False)
err = Console(stderr=True)

ORIGIN_SHIFT = 2 * math.pi * 6378137 / 2.0  # 20037508.342789244


def tile_bounds_3857(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Return (ulx, uly, lrx, lry) in EPSG:3857 for a 256px XYZ tile."""
    n = 2**z
    tile_size = (2 * ORIGIN_SHIFT) / n
    ulx = -ORIGIN_SHIFT + x * tile_size
    uly = ORIGIN_SHIFT - y * tile_size
    lrx = ulx + tile_size
    lry = uly - tile_size
    return ulx, uly, lrx, lry


def discover_tiles(root: Path, ext: str) -> list[tuple[int, int, int, Path]]:
    tiles = []
    for p in root.glob(f"*/*/*.{ext}"):
        y = int(p.stem)
        x = int(p.parent.name)
        z = int(p.parent.parent.name)
        tiles.append((z, x, y, p))
    return tiles


@app.command()
def main(
    tiles_dir: Path = typer.Option(..., "--dir", help="Root of z/x/y.ext downloaded tiles"),
    ext: str = typer.Option("png"),
    merged: Path = typer.Option(..., help="Output path for the merged mosaic .vrt"),
    force: bool = typer.Option(
        False, "--force", help="Regenerate every per-tile .vrt even if it already exists"
    ),
):
    tiles = discover_tiles(tiles_dir, ext)
    if not tiles:
        err.print(f"[red]error[/red] no .{ext} tiles found under {tiles_dir}")
        raise typer.Exit(1)

    vrt_paths: list[str] = []
    skipped = 0
    for z, x, y, src in track(tiles, description="georeferencing", console=err):
        vrt_path = src.with_suffix(".vrt")
        if vrt_path.exists() and not force:
            skipped += 1
            vrt_paths.append(str(vrt_path))
            continue
        ulx, uly, lrx, lry = tile_bounds_3857(z, x, y)
        subprocess.run(
            [
                "gdal_translate",
                "-of", "VRT",
                "-a_srs", "EPSG:3857",
                "-a_ullr", str(ulx), str(uly), str(lrx), str(lry),
                str(src),
                str(vrt_path),
            ],
            check=True,
            capture_output=True,
        )
        vrt_paths.append(str(vrt_path))

    merged.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["gdalbuildvrt", "-addalpha", str(merged), *vrt_paths],
        check=True,
    )
    err.print(
        f"[green]done[/green] merged {len(vrt_paths)} tiles -> {merged} "
        f"({skipped} per-tile .vrt already present, not regenerated)"
    )


if __name__ == "__main__":
    app()
