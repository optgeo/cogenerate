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
this layer. Re-checked against 3 more, much larger layers the same
session (noto/tamagawa/yatsushironishi, 200-tile random samples each):
100% RGBA in every sample, no palette-mode or plain-RGB tiles seen
anywhere. `write_vrt()` below still falls back to the slower
`gdal_translate` subprocess for any tile whose PIL mode isn't `RGB`/
`RGBA` specifically, so an actual palette-mode tile (should one ever
show up) degrades to the old, GDAL-verified-correct path instead of
silently mis-describing its bands.

Per-tile VRT generation, performance (Hidenori asked 2026-07-31: georef
felt like the slow step): the original approach spawned one
`gdal_translate` subprocess per tile -- benchmarked at ~250ms/tile on
real noto tiles (cold-cache PNGs, not a cached repeat of one file),
completely process-spawn/GDAL-driver-init overhead for what a VRT
sidecar actually needs (a few hundred bytes of XML, no pixel copy).
Replaced with `write_vrt()`, which hand-writes that same XML directly
in Python using facts already in hand from `clean_nodata_colors()`'s
already-open PIL image (width/height/band count) -- benchmarked at
~3.7ms/tile on the same real tiles, a **~68x** speedup, verified
byte-identical (`gdalinfo -checksum`) against `gdal_translate`'s own
output and confirmed `gdalbuildvrt` merges it identically. For a
270k-tile layer like noto, this is the difference between ~19 hours
and ~17 minutes for this one step.

NODATA via pure-black pixels (DECISIONS.md D12): GSI tiles sometimes
encode "no data" as literal opaque black (0,0,0) rather than alpha=0 --
a real, quantified problem in the sibling `optgeo/kitaphoto` project
(13.2% of its seed tiles had meaningful black content). `clean_nodata_colors()`
below applies the same detection (exact-black pixel mask via numpy) but
the simpler fix Hidenori chose for this pipeline: turn those pixels
transparent (alpha=0), not backfill them with other imagery -- there's
no fallback data source for a disaster-response ortho layer the way
kitaphoto had satellite imagery to fall back on. Checked 2026-07-31
against the same layer: 0 opaque pure-black pixels in a 300-tile
sample (~19.6M pixels) -- this specific layer didn't need the fix, but
it's implemented as a general safeguard, unexercised by this run.

NODATA via pure-white pixels (DECISIONS.md D25, 2026-08-02): Hidenori
spotted a visible grid pattern of opaque pure-white (255,255,255)
tiles in the already-published `20140831dol` overview -- ~29% of
sampled opaque pixels in that layer, far beyond plausible real content
for a non-snow disaster-response photo, and the same GSI-side
"nodata encoded as a solid color" pattern D12 already handles for
black. `clean_nodata_colors()` treats white the same way -- **but only
for layers whose real content is actually in color**: a handful of
this catalog's oldest layers (`19480000dol`/`19620000dol`, 1947-48/1962
Hiroshima reference imagery, D23) are genuinely monochrome photos
merely encoded as RGB, where real content legitimately hits pure white
(bright highlights) or pure black (deep shadow) -- treating those as
nodata would carve real holes in real (if grayscale) photo content.
`sample_is_monochrome()` distinguishes the two with a real structural
signal, not a layer-ID allowlist: sample a handful of tiles and check
whether R, G, and B are exactfully equal across virtually every opaque
pixel (confirmed live: exactly 0 channel spread across ~150k-227k
sampled pixels each for 19480000dol/19620000dol, vs a clear ~11.2
mean spread for 20140831dol's real color content) -- a true
grayscale-into-RGB source has zero color variation anywhere, which no
real color aerial photo does even where individual pixels happen to
be neutral gray. Monochrome-classified layers get black-nodata
cleaning only (D12's original behavior, unchanged); every other layer
gets both.

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


VRT_BAND_COLORS = {"RGB": ("Red", "Green", "Blue"), "RGBA": ("Red", "Green", "Blue", "Alpha")}


# D25: a real color aerial photo shows *some* chromatic variation
# somewhere (vegetation, water, roofing) -- a genuinely monochrome
# source encoded as RGB shows exactly none, anywhere. 99% of sampled
# opaque pixels at zero channel spread is a wide margin below the 100%
# both known monochrome layers actually hit and well above what real
# color content could produce by coincidence.
MONOCHROME_SPREAD_THRESHOLD = 0.99
MONOCHROME_SAMPLE_TILES = 20


def sample_is_monochrome(tiles: list[tuple[int, int, int, Path]]) -> bool:
    """Sample up to MONOCHROME_SAMPLE_TILES tiles spread across the
    layer and check whether R==G==B holds for virtually every opaque
    pixel -- see the module docstring's D25 section for why this beats
    a layer-ID allowlist."""
    if not tiles:
        return False
    step = max(1, len(tiles) // MONOCHROME_SAMPLE_TILES)
    sample = tiles[::step][:MONOCHROME_SAMPLE_TILES]
    gray = total = 0
    for _, _, _, path in sample:
        arr = np.array(Image.open(path).convert("RGBA"))
        opaque = arr[:, :, 3] > 0
        if not opaque.any():
            continue
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        spread = np.maximum(np.maximum(r, g), b).astype(int) - np.minimum(np.minimum(r, g), b).astype(int)
        gray += int((spread[opaque] == 0).sum())
        total += int(opaque.sum())
    if total == 0:
        return False
    return (gray / total) >= MONOCHROME_SPREAD_THRESHOLD


def clean_nodata_colors(src: Path, mask_white: bool) -> tuple[Path, bool, int, int, str]:
    """Turn exact-(0,0,0) pixels transparent, always (D12); also exact-
    (255,255,255) pixels if `mask_white` (D25, skipped for
    monochrome-origin layers where real content can legitimately be
    pure white/black). Returns (path, cleaned, width, height, mode).
    `path` is a cleaned copy (always RGBA) if any matching pixels were
    found, else `src` unchanged with its own original mode (common
    case, no extra I/O) -- preserves D12's original behavior of not
    forcing every untouched tile to RGBA."""
    img = Image.open(src)
    width, height = img.size
    mode = img.mode
    img_rgba = img.convert("RGBA")
    arr = np.array(img_rgba)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    nodata = (r == 0) & (g == 0) & (b == 0)
    if mask_white:
        nodata = nodata | ((r == 255) & (g == 255) & (b == 255))
    if not nodata.any():
        return src, False, width, height, mode
    arr[nodata, 3] = 0
    cleaned = src.with_suffix(".cleaned.png")
    Image.fromarray(arr, "RGBA").save(cleaned)
    return cleaned, True, width, height, "RGBA"


def write_vrt(
    src: Path, vrt_path: Path, width: int, height: int, mode: str,
    ulx: float, uly: float, lrx: float, lry: float,
) -> bool:
    """Hand-write the same single-source georeferenced VRT
    `gdal_translate -of VRT -a_srs EPSG:3857 -a_ullr ...` would produce,
    skipping the ~250ms/tile subprocess-spawn+GDAL-init cost entirely
    (see module docstring) -- verified byte-identical pixel checksums
    against the subprocess's own output. Returns False (caller should
    fall back to the subprocess) for any mode other than plain RGB/RGBA
    -- palette or grayscale tiles haven't been seen in this data source
    (checked across 4 layers this session) but this keeps an unexpected
    one correct rather than silently wrong."""
    band_colors = VRT_BAND_COLORS.get(mode)
    if band_colors is None:
        return False
    xres = (lrx - ulx) / width
    yres = (uly - lry) / height
    bands_xml = "".join(
        f"""
  <VRTRasterBand dataType="Byte" band="{i + 1}">
    <ColorInterp>{color}</ColorInterp>
    <SimpleSource>
      <SourceFilename relativeToVRT="1">{src.name}</SourceFilename>
      <SourceBand>{i + 1}</SourceBand>
      <SrcRect xOff="0" yOff="0" xSize="{width}" ySize="{height}"/>
      <DstRect xOff="0" yOff="0" xSize="{width}" ySize="{height}"/>
    </SimpleSource>
  </VRTRasterBand>"""
        for i, color in enumerate(band_colors)
    )
    vrt_path.write_text(
        f'<VRTDataset rasterXSize="{width}" rasterYSize="{height}">\n'
        f"  <SRS>EPSG:3857</SRS>\n"
        f"  <GeoTransform>{ulx}, {xres}, 0, {uly}, 0, {-yres}</GeoTransform>{bands_xml}\n"
        f"</VRTDataset>\n"
    )
    return True


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
    """Bug caught live 2026-07-31 re-running amakusa's rebuild: this glob
    also matches `clean_nodata_colors()`'s own `<y>.cleaned.<ext>` output
    sidecars left over from an earlier run (D12) -- `Path.stem` on
    `106049.cleaned.png` is `"106049.cleaned"`, not an int, crashing
    `int(p.stem)` below. Those are outputs of this pipeline, not source
    tiles to enumerate independently -- skip them."""
    tiles = []
    for p in root.glob(f"*/*/*.{ext}"):
        if p.stem.endswith(".cleaned"):
            continue
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

    monochrome = sample_is_monochrome(tiles)
    if monochrome:
        err.print(
            "[yellow]note[/yellow] layer sampled as monochrome-origin (D25) -- "
            "white-nodata cleaning skipped, black-nodata (D12) still applies"
        )

    vrt_paths: list[str] = []
    skipped = 0
    cleaned_count = 0
    fallback_count = 0
    for z, x, y, src in track(tiles, description="georeferencing", console=err):
        vrt_path = src.with_suffix(".vrt")
        if vrt_path.exists() and not force:
            skipped += 1
            vrt_paths.append(str(vrt_path))
            continue
        ulx, uly, lrx, lry = tile_bounds_3857(z, x, y)
        src_for_vrt, was_cleaned, width, height, mode = clean_nodata_colors(src, mask_white=not monochrome)
        if was_cleaned:
            cleaned_count += 1
        wrote_fast = write_vrt(src_for_vrt, vrt_path, width, height, mode, ulx, uly, lrx, lry)
        if not wrote_fast:
            fallback_count += 1
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
    nodata_desc = "opaque-black" if monochrome else "opaque-black/white"
    err.print(
        f"[green]done[/green] merged {len(vrt_paths)} tiles -> {merged} "
        f"({skipped} per-tile .vrt already present, not regenerated; "
        f"{cleaned_count} tiles had {nodata_desc} pixels cleaned to transparent, D12/D25; "
        f"{fallback_count} needed the gdal_translate subprocess fallback -- non-RGB/RGBA mode)"
    )


if __name__ == "__main__":
    app()
