# DECISIONS.md

Architecture Decision Records (ADR) for `cogenerate`. Each entry has:

- **Status**: current state (`Accepted` / `Open` / `Superseded`)
- **Context**: why the decision was needed
- **Decision**: what was decided
- **Consequences**: what follows from it, and when to reconsider

This file is the *why*, kept stable. Session-by-session narrative --
what happened, what's still running, what broke -- lives in
`HANDOVER.md` instead; don't duplicate rationale into both files. Same
split as the sibling `hfu/layers-martin` repo's `DECISIONS.md` /
`HANDOVER.md`, reused here for consistency across the `optgeo` family.

## Table of contents

| # | Title | Status | Date |
|---|---|---|---|
| [D1](#d1-quadtree-pruning-existence-probing-as-the-primary-discovery-strategy) | Quadtree-pruning existence probing as the primary discovery strategy | Accepted | 2026-07-30 |
| [D2](#d2-toolchain-uv--justfile--direct-gdal-cli-via-subprocess-src-layout) | Toolchain: uv + Justfile + direct GDAL CLI via subprocess, src-layout | Accepted | 2026-07-30 |
| [D3](#d3-cc0-10-license) | CC0-1.0 license | Accepted | 2026-07-30 |
| [D4](#d4-stac-datetime-source-capture-date-vs-publish-date) | STAC `datetime` source: capture date vs. publish date | Accepted | 2026-07-31 |
| [D5](#d5-zoom-to-fetch-fixed-at-maxzoom18-cog-overviews-generated-locally) | Zoom-to-fetch fixed at maxzoom=18, COG overviews generated locally | Accepted | 2026-07-30 |
| [D6](#d6-openaerialmap-ingestion-path-still-open-now-with-research-notes) | OpenAerialMap ingestion path: still open, now with research notes | Open | 2026-07-30 |
| [D7](#d7-read-layers-martins-catalog-from-its-canonical-live-url-never-a-local-clone) | Read layers-martin's catalog from its canonical live URL, never a local clone | Accepted | 2026-07-31 |
| [D8](#d8-language-policy-japanese-chat-english-repository) | Language policy: Japanese chat, English repository | Accepted | 2026-07-31 |
| [D9](#d9-disaster-response-principle-build-what-the-tile-server-confirms-dont-block-on-gsis-own-catalog-page) | Disaster-response principle: build what the tile server confirms, don't block on GSI's own catalog page | Accepted | 2026-07-31 |
| [D10](#d10-source-cooperative-publishing-path) | Source Cooperative publishing path | Accepted (blocked on 1 manual step) | 2026-07-31 |

---

## D1: Quadtree-pruning existence probing as the primary discovery strategy

**Status**: Accepted

**Context**: GSI's `mokuroku.csv.gz` tile inventory is not reliably
regenerated for disaster-response (`_do` / `_do_sokuho`) layers -- per
`gsi-cyberjapan/mokuroku-spec`, only `std`/`pale`/`english` are
regularly regenerated. `cocotile` requires already knowing a tile
position to answer "what layers exist here" -- it can't discover where
a layer's coverage is. `daicho` is GSI's own internal SQLite cache used
server-side to accelerate mokuroku generation; it's not a public
endpoint at all. So there is no server-side inventory API to lean on for
these specific layers.

**Decision**: `probe.py` implements a BFS quadtree prune: start at the
layer's documented low zoom (`minzoom`, almost always 10 for `_do*`
layers per `ichiran.html`), request each candidate tile; a 404 prunes
the whole subtree (children are never requested); only a 200 spawns the
4 children at the next zoom. Confirmed leaves at `maxzoom` feed
`download.py`.

**Consequences**: Request volume scales with the coverage polygon's
*boundary*, not with bbox × zoom-levels -- validated live 2026-07-31
(37,141 requests -> 26,982 confirmed z18 tiles for one 八代-sized
layer). A 404 during probing is expected/routine, not an error to alert
on. An unexpected 404 during the later `download` step (for a tile
already confirmed by `probe`) is logged and skipped, not fatal -- the
resulting gap is legitimate nodata, handled by the alpha channel
(`gdalbuildvrt -addalpha`), never synthesized as a blank tile.

## D2: Toolchain: uv + Justfile + direct GDAL CLI via subprocess, src-layout

**Status**: Accepted

**Context**: Python is only needed for the parts requiring real logic
(HTTP probing/downloading, tile-coordinate math); mosaicking and COG
creation are GDAL's job. The existing optgeo/hfu stack (GDAL,
Tippecanoe, PMTiles, Martin, the Mapterhorn pipeline) already favors
small, inspectable, CLI-driven stages over embedding data-processing
libraries.

**Decision**: Python is managed by `uv` (`uv sync` / `uv run` / `uv
add`; never bare `pip install`). The package is laid out as
`src/cogenerate/` (hatchling `packages = ["src/cogenerate"]`; no
separate `[project.scripts]` entry points needed since each stage is
invoked as `python -m cogenerate.<stage>`). GDAL is called as
`gdal_translate` / `gdalbuildvrt` subprocesses, never the `osgeo` Python
bindings. Task orchestration lives in `Justfile` (one recipe per
pipeline stage; `just run` chains them), not shell scripts or
Makefiles, mirroring the Mapterhorn pipeline's style.

**Consequences**: Each stage (`probe` / `download` / `georef` / `cog`)
is independently re-runnable via its own `just` recipe, handing off
through plain files (CSV, VRT) rather than in-memory state -- matches
the existing small-composable-units convention. Cost, discovered
2026-07-31: `just`'s recipe variables are environment variables read
*before* the recipe name (`LAYER=... just probe`), not trailing recipe
arguments (`just probe LAYER=...` errors with "justfile does not
contain recipe `LAYER=...`") -- a real gotcha, since corrected in this
file's own command examples and in `README.md`.

## D3: CC0-1.0 license

**Status**: Accepted

**Context**: Matching sibling `optgeo` repos' licensing convention for
the "Adopt Geodata" family.

**Decision**: CC0-1.0. License text fetched verbatim from GitHub's API
(`gh api licenses/cc0-1.0 --jq '.body'`) rather than hand-typed, to
guarantee the canonical legal text.

**Consequences**: Covers `cogenerate`'s own code, not the GSI tile data
it processes -- the source imagery's own attribution terms are a
separate question (see D9).

## D4: STAC `datetime` source: capture date vs. publish date

**Status**: Accepted

**Context**: A layer ID embeds a capture-date fragment (e.g.
`20260729...0729do_sokuho`), while `ichiran.html`'s "提供開始" (publish
date) typically lags actual capture by a day or more and is easier to
scrape reliably than parsing every layer-ID naming variant's embedded
date.

**Decision** (Hidenori, 2026-07-31): use the **capture date**, parsed
from the layer ID's embedded date fragment. More correct than publish
date, and per D9, `ichiran.html` (the easier-to-scrape source) can't be
relied on to even exist yet for a brand-new disaster layer -- so the
harder-to-parse-but-always-available source is also the more robust
one operationally, not just the more accurate one.

**Consequences**: `stac_item.py` needs a date-fragment parser that
handles the naming variants seen so far (`_do`, `_do_sokuho`, `dol`,
`dol2`, `doh`, `doh2`, etc. -- see the `layers-martin` catalog census
for real examples) rather than a single fixed regex.

## D5: Zoom-to-fetch fixed at maxzoom=18, COG overviews generated locally

**Status**: Accepted (revisit condition noted below)

**Context**: `_do` / `_do_sokuho` layers document `ズームレベル 10～18`
on `ichiran.html` for essentially every layer surveyed so far; GSI
doesn't serve finer resolution than z18 for these.

**Decision**: Hardcode `maxzoom=18` as the COG source resolution;
generate overviews locally in the `cog` stage (`gdal_translate -of COG
... -co OVERVIEW_RESAMPLING=AVERAGE`) rather than fetching per-zoom
tiles from GSI beyond 18.

**Consequences**: Revisit only if a specific layer's `ichiran.html`
entry documents native resolution beyond z18 (not observed in any
layer surveyed as of this writing).

## D6: OpenAerialMap ingestion path: still open, now with research notes

**Status**: Open

**Context**: The pipeline's stated end goal (`README.md`) is "make them
usable in OpenAerialMap," but OAM's actual ingestion mechanism (API
push vs. static-STAC harvest) had not been researched as of 2026-07-30.

**Research, 2026-07-31**: OAM's current (v1) uploader API
(`hotosm/oam-uploader-api`) is **token-authenticated, direct-file-upload
based** -- tokens are issued through a separate `oam-uploader-admin`
interface, which reads as an account/access-request step, not
something scriptable without a human going through OAM/HOTOSM's own
signup first. Public docs (`docs.openaerialmap.org`) mark the
upload/processing sections as literally "To be developed." Separately,
OAM v2 (in progress per HOTOSM's own announcements) is being rebuilt on
pgstac/stac-fastapi/TiTiler, with a stated roadmap goal of *"engaging
more providers ... to map publicly available STACs to the OAM metadata
schema"` -- i.e. static-STAC harvesting is a planned direction, not
something confirmed available today.

**Decision**: Still not made -- this needs either (a) Hidenori
contacting HOTOSM/OAM directly once we have a real static STAC catalog
to show them (the "map publicly available STACs" roadmap item suggests
this is the right conversation to have, and is a much better pitch with
working output in hand), or (b) going through OAM's own account/token
flow for the current v1 uploader if (a) stalls. Either way: **do not
block finishing this pipeline's own static STAC + GitHub Pages
catalog** (already-decided, in `CLAUDE.md`'s Mission) on resolving
this -- that catalog is useful on its own, matching the rest of the
`optgeo` "Adopt Geodata" family, regardless of whether/how OAM
ultimately ingests it.

**Consequences**: `stac_item.py`/`stac_catalog.py` can proceed using
plain STAC spec conventions without OAM-specific schema contortions;
revisit field choices only if/when an actual OAM ingestion conversation
clarifies requirements.

**Consequences**: Blocks the pipeline's final stage (OAM ingestion
itself) and constrains `stac_item.py`'s design until resolved.

## D7: Read layers-martin's catalog from its canonical live URL, never a local clone

**Status**: Accepted

**Context**: `layers-martin` rebuilds and commits `docs/catalog.json`
on a daily GitHub Actions cron (`build-catalog.yml`, 18:00 UTC). A
local `git clone` of that repo is only as fresh as its last `git pull`.
Caught live 2026-07-31: a local clone last touched 2026-07-17 was 15
daily rebuilds behind, missing the entry for the exact layer this
pipeline was being validated against.

**Decision**: Always read `https://hfu.github.io/layers-martin/catalog.json`
(equivalently `/catalog`) directly. If working from a local clone for
convenience, `git pull --ff-only` it first and don't otherwise trust
its age.

**Consequences**: One fewer thing that can silently go stale between
sessions. Costs one HTTP round-trip per lookup instead of a filesystem
read -- acceptable, this isn't called in a hot loop.

## D8: Language policy: Japanese chat, English repository

**Status**: Accepted

**Context**: Hidenori collaborates in Japanese; the repository (and the
rest of the `optgeo` family) is in English.

**Decision**: Converse with Hidenori (chat, CLI turns, questions) in
Japanese. Everything that lands in the repository -- code, comments,
docstrings, `.md` prose, commit messages, PR descriptions -- stays in
English.

**Consequences**: No mixing: a Japanese-language commit message or doc
section is as wrong here as an English chat reply.

## D9: Disaster-response principle: build what the tile server confirms, don't block on GSI's own catalog page

**Status**: Accepted

**Context**: GSI's own `ichiran.html` (地理院タイル一覧) is itself an
eventually-consistent catalog, not a real-time one. Confirmed
2026-07-31: `cyberjapandata.gsi.go.jp` was already serving all 26,982
z18 tiles of `20260729kumamoto_yatsushiro_0729do_sokuho` (probe and
download both succeeded), while `ichiran.html` had no entry for that
layer at all yet -- so its documented zoom-range and 備考
(remarks/attribution) fields couldn't be cross-checked. This echoes
D7's finding (a catalog can lag the live data) but here it's GSI's own
primary source, not a mirror -- there's no "just re-fetch the canonical
URL" fix, only "wait for GSI to publish it."

**Decision**: This pipeline runs in disaster-response mode: if the
quadtree probe confirms a layer's tiles exist on the live GSI server,
proceed through `download` / `georef` / `cog` without waiting for
`ichiran.html` to catch up. Do not gate COG *production* on official
metadata availability. What *does* stay gated on it: any
attribution/備考 field written into a published STAC item -- mark it
explicitly provisional (e.g. "attribution not yet cross-checked against
ichiran.html as of `<date>`; re-verify before treating as final")
rather than either blocking the whole pipeline or asserting unverified
attribution as settled fact.

**Consequences**: COGs can and should be produced and made available to
whoever wants to accept that risk, ahead of GSI's own documentation
catching up; re-run/regenerate once `ichiran.html` lists the layer, and
treat that later documentation pass as a cheap top-up (re-check
attribution, zoom range) rather than a redo of the actual
tile-fetch/mosaic work. This **supersedes** the more cautious "don't
treat this layer as cleared for publishing" stance recorded in
`HANDOVER.md`'s first 2026-07-31 entry.

## D10: Source Cooperative publishing path

**Status**: Accepted (mechanism); blocked on one manual step

**Context**: `CLAUDE.md`'s naming convention already assumed
`source.coop/smartmaps/cogenerate/<layer_id>.tif`, but the upload auth
mechanism was unconfirmed (S3-compatible credentials? something else?).

**Research, 2026-07-31**: the `smartmaps` org already exists on Source
Cooperative, owned by Hidenori, with 14 public products already live
there (mostly PMTiles -- Japan terrain tiles, GTFS, PLATEAU, etc.).
Upload is S3-compatible: either the web UI (per-file, manual), or
`source-coop login` (one-time human auth) followed by scriptable `aws
s3 cp` / `aws s3 sync --profile source-coop ... --acl
bucket-owner-full-control` targeting
`s3://us-west-2.opendata.source.coop/smartmaps/cogenerate/`. A
`cogenerate` product does not exist yet under `smartmaps` -- creating
one requires the source.coop web UI, i.e. a human (Hidenori) action;
this is account/product creation, not something Claude should do on
its own (see this project's standing safety rules on account
creation). Once the product exists and Hidenori runs `source-coop
login` once locally, the actual upload calls can be scripted and run
by Claude without any credential ever passing through chat.

**Decision**: Use the `source-coop login` + AWS CLI path for uploads
(scriptable as its own `just` recipe later), not the web UI. Product
creation and the one-time `source-coop login` stay manual, human-only
steps.

**Consequences**: Nothing else in the pipeline is blocked by this --
`probe`/`download`/`georef`/`cog` don't touch Source Cooperative at
all. Only the eventual upload step needs Hidenori to: (1) create the
`smartmaps/cogenerate` product on source.coop, (2) run `source-coop
login` once. Until then, produced COGs stay local/on GitHub only.
