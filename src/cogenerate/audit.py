"""Cheap remote-only quality audit for every already-published STAC Item.

Two checks per layer, both against the live `data.source.coop` asset,
no full-file download and no local `out/<layer>.tif` needed (D20):
  - size: HTTP HEAD `Content-Length` vs the Item's recorded
    `file:size` -- catches a truncated/corrupted upload or a stale
    Item that wasn't regenerated after a re-upload.
  - structure: `gdalinfo -json` on `/vsicurl/<asset_url>` (only a few
    header/overview byte ranges fetched, same trick stac_item.py uses)
    -- confirms `LAYOUT=COG`, at least 3 bands, and that the file's own
    `wgs84Extent` roughly matches the Item's recorded `bbox` (tolerance
    `BBOX_TOLERANCE_DEG`, guards against a wrong-layer overwrite).

**Does not catch all-zero payload corruption** the way a targeted
`gdallocationinfo` spot-check would (D24's noto incident: `gdalinfo`
succeeded the whole time on a file whose actual pixel data was
unwritten zeros, because COG's two-pass layout writes the header
before the pixel data). This audit is the cheap, routine layer of
defense across the whole catalog; a `gdallocationinfo` sweep is for
investigating a specific already-suspected layer, not every layer
every time.

Usage:
    uv run python -m cogenerate.audit --items-dir docs/items/
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.progress import track
from rich.table import Table

app = typer.Typer(add_completion=False)
err = Console(stderr=True)

BBOX_TOLERANCE_DEG = 0.01


def check_size(asset_url: str, recorded_size: int) -> tuple[bool, str]:
    try:
        resp = httpx.head(asset_url, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        return False, f"HEAD failed: {e!r}"
    remote_size = int(resp.headers.get("content-length", -1))
    if remote_size != recorded_size:
        return False, f"size mismatch: recorded {recorded_size}, remote {remote_size}"
    return True, "ok"


def check_structure(asset_url: str, recorded_bbox: list[float]) -> tuple[bool, str]:
    try:
        out = subprocess.run(
            ["gdalinfo", "-json", f"/vsicurl/{asset_url}"],
            capture_output=True, check=True, text=True, timeout=60,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        return False, f"gdalinfo failed: {e!r}"
    info = json.loads(out)
    layout = info.get("metadata", {}).get("IMAGE_STRUCTURE", {}).get("LAYOUT")
    if layout != "COG":
        return False, f"LAYOUT={layout!r}, expected COG"
    bands = info.get("bands", [])
    if len(bands) < 3:
        return False, f"only {len(bands)} band(s), expected >=3"
    extent = info.get("wgs84Extent")
    if not extent:
        return False, "no wgs84Extent in gdalinfo output"
    lons = [pt[0] for ring in extent["coordinates"] for pt in ring]
    lats = [pt[1] for ring in extent["coordinates"] for pt in ring]
    remote_bbox = [min(lons), min(lats), max(lons), max(lats)]
    if any(abs(a - b) > BBOX_TOLERANCE_DEG for a, b in zip(remote_bbox, recorded_bbox)):
        return False, f"bbox mismatch: recorded {recorded_bbox}, remote {remote_bbox}"
    return True, "ok"


@app.command()
def main(
    items_dir: Path = typer.Option(Path("docs/items"), help="Directory of Item JSON files"),
):
    """Audit every Item in items_dir against its live Source Cooperative asset."""
    item_files = sorted(items_dir.glob("*.json"))
    if not item_files:
        err.print(f"[red]error[/red] no Item JSON files found in {items_dir}")
        raise typer.Exit(1)

    failures = []
    for path in track(item_files, description="auditing", console=err):
        item = json.loads(path.read_text())
        layer = item["id"]
        asset = item["assets"]["imagery"]
        asset_url = asset["href"]

        size_ok, size_msg = check_size(asset_url, asset["file:size"])
        struct_ok, struct_msg = check_structure(asset_url, item["bbox"])

        if not size_ok or not struct_ok:
            failures.append((layer, size_msg if not size_ok else "ok", struct_msg if not struct_ok else "ok"))

    table = Table(title=f"Audit: {len(item_files)} published layer(s), {len(failures)} issue(s)")
    table.add_column("layer")
    table.add_column("size check")
    table.add_column("structure check")
    for layer, size_msg, struct_msg in failures:
        table.add_row(layer, size_msg, struct_msg)
    err.print(table)

    if failures:
        err.print(f"[red]FAILED[/red] {len(failures)}/{len(item_files)} layer(s) have issues, see table above")
        raise typer.Exit(1)
    err.print(f"[green]OK[/green] all {len(item_files)} layer(s) passed size + structure checks")


if __name__ == "__main__":
    app()
