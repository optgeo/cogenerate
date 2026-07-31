"""Rank not-yet-published disaster-response layers by likely spatial
extent, so "which layer next" doesn't need a one-off manual analysis
every session (as it did for picking noto/tamagawa/sagachiku).

Design rationale: GSI's `ichiran.html` has no real bbox/km² field per
layer (confirmed 2026-07-31 by reading the page's actual HTML, not
guessing) -- the only geographic signal beyond a single tilejump point
is the free-text 提供範囲 (coverage) table row, which lists
municipality names. Municipality count is a weak but real proxy for
area, used here the same way it was used ad hoc to pick noto (19
municipalities) / tamagawa (15) / sagachiku (10).

Filtering to "real disaster-response layers" is done by checking which
of layers-martin's catalog IDs actually have an `<h4 id="t<id>">` +
提供範囲 table row in `ichiran.html`, NOT by pattern-matching the ID
string. An early version of this analysis (this session, ad hoc)
matched IDs ending in "do" and picked up false positives from
unrelated geological-map layers whose IDs coincidentally end that way
(`gsjgeomap_g50_04_066kudo`, `...hirado`, `...mikado` -- place names,
not the `_do`/`_do_sokuho` disaster-ortho suffix). Checking against
ichiran.html's actual 近年の災害 section structure sidesteps that
entirely and also catches naming variants (`dol`, `doh`, etc. -- D4)
an ID-suffix regex might miss.

Usage:
    uv run python -m cogenerate.candidates --top 10
    uv run python -m cogenerate.candidates --top 10 --json
"""

from __future__ import annotations

import json
import re

import httpx
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(add_completion=False)
err = Console(stderr=True)

LAYERS_MARTIN_CATALOG_URL = "https://hfu.github.io/layers-martin/catalog.json"
ICHIRAN_URL = "https://maps.gsi.go.jp/development/ichiran.html"
STAC_CATALOG_URL = "https://optgeo.github.io/cogenerate/catalog.json"


def fetch_layer_ids(client: httpx.Client) -> set[str]:
    data = client.get(LAYERS_MARTIN_CATALOG_URL, timeout=30.0).json()
    return set(data["tiles"].keys())


def fetch_published_ids(client: httpx.Client) -> set[str]:
    """Layer IDs already on the live STAC catalog (D19) -- read from the
    canonical published URL, not a local `docs/` copy, matching D7's
    "always live" rule."""
    try:
        data = client.get(STAC_CATALOG_URL, timeout=15.0).json()
    except httpx.HTTPError as e:
        err.print(f"[yellow]warn[/yellow] couldn't fetch {STAC_CATALOG_URL}: {e!r} -- treating nothing as published")
        return set()
    ids = set()
    for link in data.get("links", []):
        if link.get("rel") == "item":
            ids.add(link["href"].rsplit("/", 1)[-1].removesuffix(".json"))
    return ids


def parse_ichiran_coverage(html: str, layer_ids: set[str]) -> dict[str, str]:
    """For every catalog layer ID that has a real `<h4 id="t<id>">` +
    提供範囲 row in ichiran.html, return {id: coverage_text}. This is
    the authoritative "is this a real disaster-response layer" check --
    see module docstring for why it's not an ID-pattern regex."""
    results: dict[str, str] = {}
    for m in re.finditer(r'<h4[^>]*id="t([^"]+)"', html):
        lid = m.group(1)
        if lid not in layer_ids:
            continue
        start = m.end()
        end = html.find("</table>", start)
        block = html[start:end]
        rm = re.search(r"<td>提供範囲</td>\s*<td>(.*?)</td>", block, re.DOTALL)
        if not rm:
            continue
        text = re.sub(r"<[^>]+>", "", rm.group(1))
        results[lid] = re.sub(r"\s+", "", text).strip()
    return results


def count_municipalities(coverage_text: str) -> int:
    """Weak proxy for spatial extent: number of municipality names in
    the free-text 提供範囲 field (see module docstring)."""
    total = 0
    for prefecture_block in re.split(r"[／/]", coverage_text):
        prefecture_block = prefecture_block.strip()
        if not prefecture_block:
            continue
        without_prefecture = re.sub(r"^.+?[都道府県]", "", prefecture_block)
        munis = [m for m in re.split(r"[、,]", without_prefecture) if m.strip()]
        total += max(len(munis), 1)
    return total


@app.command()
def main(
    top: int = typer.Option(10, help="How many ranked candidates to show"),
    include_published: bool = typer.Option(
        False, help="Include layers already on the live STAC catalog (default: excluded)"
    ),
    as_json: bool = typer.Option(False, "--json", help="Print JSON instead of a table"),
):
    """Rank not-yet-published `_do`/`_do_sokuho`-style layers by a
    municipality-count proxy for spatial extent."""
    with httpx.Client(headers={"User-Agent": "optgeo/cogenerate candidates (contact via github.com/optgeo)"}) as client:
        layer_ids = fetch_layer_ids(client)
        published = set() if include_published else fetch_published_ids(client)
        html = client.get(ICHIRAN_URL, timeout=30.0).text

    coverage = parse_ichiran_coverage(html, layer_ids)
    err.print(
        f"[green]done[/green] {len(coverage)} real disaster-response layers found in "
        f"ichiran.html ({len(layer_ids)} total catalog entries checked), "
        f"{len(published)} already published"
    )

    ranked = sorted(
        ((lid, text, count_municipalities(text)) for lid, text in coverage.items() if lid not in published),
        key=lambda row: row[2],
        reverse=True,
    )[:top]

    if as_json:
        print(json.dumps([{"layer_id": lid, "coverage": text, "municipalities": n} for lid, text, n in ranked],
                          ensure_ascii=False, indent=2))
        return

    table = Table(title=f"Top {top} unpublished layers by municipality count (spatial-extent proxy)")
    table.add_column("Layer ID")
    table.add_column("Munis", justify="right")
    table.add_column("Coverage")
    for lid, text, n in ranked:
        table.add_row(lid, str(n), text[:80])
    Console().print(table)


if __name__ == "__main__":
    app()
