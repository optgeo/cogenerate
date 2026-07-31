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

Two ranking modes (`--sort-by`): `extent` (default, municipality
count above) or `date` (newest disaster event first -- Hidenori asked
2026-07-31 to temporarily prioritize this way instead). Date is the
leading `YYYYMMDD` embedded in almost every layer ID (event date, not
necessarily the exact capture date D4 uses for STAC `datetime` --
close enough for "what's newest" triage, and far more layer IDs parse
this way than D4's stricter `_MMDDdo`-suffix pattern would allow: only
4 of 182 candidates checked 2026-07-31 lack a leading 8-digit date
(a couple of volcano-monitoring layers, `kuchinoerabured`, `rinya`) --
those sort last under `date` mode rather than erroring.

`--keyword` (e.g. `--keyword 広島市`) restricts to candidates whose
提供範囲 coverage text contains that substring, ranked the same way
(extent or date) within that subset -- added 2026-08-01 to temporarily
prioritize Hiroshima-area layers ahead of FOSS4G 2026 Hiroshima, per
Hidenori. Not a separate ranking mode: same sort, just pre-filtered.
**It's a plain substring match, not a real place/boundary lookup** --
confirmed live that `広島市` also matches 北海道's `北広島市`
(Kitahiroshima, Hokkaido -- genuinely named after settlers from
Hiroshima prefecture, but not the city FOSS4G cares about here).
Eyeball the result table before queuing, same as the existing
撮影-vs-作成 check.

Usage:
    uv run python -m cogenerate.candidates --top 10
    uv run python -m cogenerate.candidates --top 10 --sort-by date
    uv run python -m cogenerate.candidates --top 10 --json
    uv run python -m cogenerate.candidates --top 10 --sort-by date --keyword 広島
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


def extract_event_date(layer_id: str) -> str | None:
    """Leading YYYYMMDD embedded in the layer ID (event date, not the
    stricter capture-date fragment D4/stac_item.py parses) -- None if
    the ID doesn't start with 8 digits (rare, see module docstring)."""
    m = re.match(r"^(\d{8})", layer_id)
    return m.group(1) if m else None


@app.command()
def main(
    top: int = typer.Option(10, help="How many ranked candidates to show"),
    sort_by: str = typer.Option(
        "extent", help="Rank by 'extent' (municipality-count proxy, default) or 'date' (newest event first)"
    ),
    include_published: bool = typer.Option(
        False, help="Include layers already on the live STAC catalog (default: excluded)"
    ),
    keyword: str = typer.Option(
        "", help="Only rank candidates whose 提供範囲 coverage text contains this substring (e.g. 広島)"
    ),
    as_json: bool = typer.Option(False, "--json", help="Print JSON instead of a table"),
):
    """Rank not-yet-published `_do`/`_do_sokuho`-style layers by a
    municipality-count proxy for spatial extent, or by newest event
    date first (--sort-by date). --keyword pre-filters to candidates
    whose coverage text matches before ranking."""
    if sort_by not in ("extent", "date"):
        err.print(f"[red]error[/red] --sort-by must be 'extent' or 'date', got {sort_by!r}")
        raise typer.Exit(1)

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

    candidates = [(lid, text) for lid, text in coverage.items() if lid not in published]
    if keyword:
        candidates = [(lid, text) for lid, text in candidates if keyword in text]
        err.print(f"[green]filtered[/green] to {len(candidates)} candidate(s) matching {keyword!r}")
    if sort_by == "date":
        ranked = sorted(
            ((lid, text, extract_event_date(lid)) for lid, text in candidates),
            key=lambda row: row[2] or "",
            reverse=True,
        )[:top]
    else:
        ranked = sorted(
            ((lid, text, count_municipalities(text)) for lid, text in candidates),
            key=lambda row: row[2],
            reverse=True,
        )[:top]

    if as_json:
        key = "event_date" if sort_by == "date" else "municipalities"
        print(json.dumps([{"layer_id": lid, "coverage": text, key: n} for lid, text, n in ranked],
                          ensure_ascii=False, indent=2))
        return

    keyword_suffix = f" matching {keyword!r}" if keyword else ""
    if sort_by == "date":
        table = Table(title=f"Top {top} unpublished layers{keyword_suffix}, newest event first")
        table.add_column("Layer ID")
        table.add_column("Event date", justify="right")
        table.add_column("Coverage")
        for lid, text, event_date in ranked:
            table.add_row(lid, event_date or "?", text[:80])
    else:
        table = Table(title=f"Top {top} unpublished layers{keyword_suffix} by municipality count (spatial-extent proxy)")
        table.add_column("Layer ID")
        table.add_column("Munis", justify="right")
        table.add_column("Coverage")
        for lid, text, n in ranked:
            table.add_row(lid, str(n), text[:80])
    Console().print(table)


if __name__ == "__main__":
    app()
