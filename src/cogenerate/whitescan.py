"""Scan every already-published layer for D25's opaque pure-white
nodata problem, without downloading full files or needing local tiles.

For each STAC Item's asset, `gdal_translate` a small overview-level PNG
(a handful of range requests, not the whole COG) and, from that same
downsample, both:
  - classify the layer monochrome-or-not (same signal as `georef.py`'s
    `sample_is_monochrome()`, applied to overview pixels instead of
    source tiles -- the original tiles are long gone once a layer is
    cleaned up, D20), and
  - measure what fraction of opaque pixels are exact pure white.

This only *scopes* which already-published layers plausibly need a
D24-style local-download + rebuild + re-upload patch -- it doesn't
patch anything itself. Monochrome layers are reported but never
flagged, matching D25's georef-time behavior.

Usage:
    uv run python -m cogenerate.whitescan --items-dir docs/items/
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import typer
from PIL import Image
from rich.console import Console
from rich.progress import track
from rich.table import Table

app = typer.Typer(add_completion=False)
err = Console(stderr=True)

# Same reasoning as georef.py's D25 constant: a true grayscale-into-RGB
# source has zero color variation anywhere; keep the two in lockstep.
MONOCHROME_SPREAD_THRESHOLD = 0.99
OVERVIEW_WIDTH = 800
FLAG_WHITE_FRACTION = 0.01  # >1% opaque-white is well beyond plausible real content


def scan_one(asset_url: str) -> tuple[bool, float, int]:
    """Returns (is_monochrome, white_fraction, opaque_pixel_count)."""
    with tempfile.TemporaryDirectory() as tmp:
        out_png = Path(tmp) / "overview.png"
        subprocess.run(
            ["gdal_translate", "-of", "PNG", "-outsize", str(OVERVIEW_WIDTH), "0",
             f"/vsicurl/{asset_url}", str(out_png)],
            check=True, capture_output=True, timeout=120,
        )
        arr = np.array(Image.open(out_png).convert("RGBA"))
    opaque = arr[:, :, 3] > 200
    n_opaque = int(opaque.sum())
    if n_opaque == 0:
        return False, 0.0, 0
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    spread = np.maximum(np.maximum(r, g), b).astype(int) - np.minimum(np.minimum(r, g), b).astype(int)
    is_monochrome = (spread[opaque] == 0).sum() / n_opaque >= MONOCHROME_SPREAD_THRESHOLD
    white = (r == 255) & (g == 255) & (b == 255) & opaque
    white_fraction = int(white.sum()) / n_opaque
    return is_monochrome, white_fraction, n_opaque


@app.command()
def main(
    items_dir: Path = typer.Option(Path("docs/items"), help="Directory of Item JSON files"),
):
    """Scan every Item's live asset for D25's white-nodata problem, report a sorted table."""
    item_files = sorted(items_dir.glob("*.json"))
    if not item_files:
        err.print(f"[red]error[/red] no Item JSON files found in {items_dir}")
        raise typer.Exit(1)

    results = []
    for path in track(item_files, description="scanning", console=err):
        item = json.loads(path.read_text())
        layer = item["id"]
        asset_url = item["assets"]["imagery"]["href"]
        try:
            is_monochrome, white_fraction, n_opaque = scan_one(asset_url)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            err.print(f"[yellow]warn[/yellow] {layer}: scan failed, {e!r}")
            continue
        results.append((layer, is_monochrome, white_fraction, n_opaque))

    flagged = [r for r in results if not r[1] and r[2] >= FLAG_WHITE_FRACTION]
    flagged.sort(key=lambda r: r[2], reverse=True)
    monochrome = [r for r in results if r[1]]

    table = Table(title=f"White-nodata scan: {len(results)} layer(s), {len(flagged)} flagged, {len(monochrome)} monochrome-origin")
    table.add_column("layer")
    table.add_column("white fraction", justify="right")
    table.add_column("opaque px (overview)", justify="right")
    for layer, _, white_fraction, n_opaque in flagged:
        table.add_row(layer, f"{white_fraction:.1%}", str(n_opaque))
    err.print(table)

    if monochrome:
        err.print(f"[cyan]monochrome-origin, excluded from flagging:[/cyan] {', '.join(r[0] for r in monochrome)}")

    if not flagged:
        err.print("[green]OK[/green] no layer exceeds the white-fraction flag threshold")


if __name__ == "__main__":
    app()
