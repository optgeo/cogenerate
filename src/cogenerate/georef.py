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

Band counts: originally flagged as an untested risk (fully-interior
tiles as RGB, boundary tiles as RGBA). Checked 2026-07-31 against
20260729kumamoto_yatsushiro_0729do_sokuho: all 26,982 source PNGs are
RGBA (PNG color_type=6), boundary and interior alike -- no mixing for
this layer. Not proven true for every layer, but the specific failure
mode didn't materialize here.

NODATA via pure-black pixels (DECISIONS.md D12): GSI tiles sometimes
encode "no data" as literal opaque black (0,0,0) rather than alpha=0 --
a real, quantified problem in the sibling `optgeo/kitaphoto` project
(13.2% of its seed tiles had meaningful black content). `clean_black_nodata()`
below applies the same detection (exact-black pixel mask via numpy) but
the simpler fix Hidenori chose for this pipeline: turn those pixels
transparent (alpha=0), not backfill them with other imagery -- there's
no fallback data source for a disaster-response ortho layer the way
kitaphoto had satellite imagery to fall back on. Checked 2026-07-31
against the same layer: 0 opaque pure-black pixels in a 300-tile
sample (~19.6M pixels) -- this specific layer didn't need the fix, but
it's implemented as a general safeguard, unexercised by this run.

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

import numpy as np
import typer
from PIL import Image
from rich.console import Console
from rich.progress import track

app = typer.Typer(add_completion=False)
err = Console(stderr=True)

ORIGIN_SHIFT = 2 * math.pi * 6378137 / 2.0  # 20037508.342789244


def clean_black_nodata(src: Path) -> tuple[Path, bool]:
    """Turn exact-(0,0,0) pixels transparent; returns (path, cleaned).
    `path` is a cleaned copy if any black pixels were found, else `src`
    unchanged (common case, no extra I/O). See DECISIONS.md D12."""
    img = Image.open(src).convert("RGBA")
    arr = np.array(img)
    black = (arr[:, :, 0] == 0) & (arr[:, :, 1] == 0) & (arr[:, :, 2] == 0)
    if not black.any():
        return src, False
    arr[black, 3] = 0
    cleaned = src.with_suffix(".cleaned.png")
    Image.fromarray(arr, "RGBA").save(cleaned)
    return cleaned, True


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
    cleaned_count = 0
    for z, x, y, src in track(tiles, description="georeferencing", console=err):
        vrt_path = src.with_suffix(".vrt")
        if vrt_path.exists() and not force:
            skipped += 1
            vrt_paths.append(str(vrt_path))
            continue
        ulx, uly, lrx, lry = tile_bounds_3857(z, x, y)
        src_for_vrt, was_cleaned = clean_black_nodata(src)
        if was_cleaned:
            cleaned_count += 1
        subprocess.run(
            [
                "gdal_translate",
                "-of", "VRT",
                "-a_srs", "EPSG:3857",
                "-a_ullr", str(ulx), str(uly), str(lrx), str(lry),
                str(src_for_vrt),
                str(vrt_path),
            ],
            check=True,
            capture_output=True,
        )
        vrt_paths.append(str(vrt_path))

    merged.parent.mkdir(parents=True, exist_ok=True)
    # Pass the (potentially tens of thousands of) source paths via
    # -input_file_list, not as individual argv entries -- large layers
    # blow past the OS's ARG_MAX ("Argument list too long") otherwise.
    file_list_path = merged.with_suffix(".input_file_list.txt")
    file_list_path.write_text("\n".join(vrt_paths) + "\n")
    subprocess.run(
        ["gdalbuildvrt", "-addalpha", "-input_file_list", str(file_list_path), str(merged)],
        check=True,
    )
    file_list_path.unlink()
    err.print(
        f"[green]done[/green] merged {len(vrt_paths)} tiles -> {merged} "
        f"({skipped} per-tile .vrt already present, not regenerated; "
        f"{cleaned_count} tiles had opaque-black pixels cleaned to transparent, D12)"
    )


if __name__ == "__main__":
    app()
