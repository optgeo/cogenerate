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
| [D6](#d6-openaerialmap-ingestion-path-still-open-now-with-research-notes) | OpenAerialMap ingestion path: still open, now with research notes | Accepted | 2026-07-30 |
| [D7](#d7-read-layers-martins-catalog-from-its-canonical-live-url-never-a-local-clone) | Read layers-martin's catalog from its canonical live URL, never a local clone | Accepted | 2026-07-31 |
| [D8](#d8-language-policy-japanese-chat-english-repository) | Language policy: Japanese chat, English repository | Accepted | 2026-07-31 |
| [D9](#d9-disaster-response-principle-build-what-the-tile-server-confirms-dont-block-on-gsis-own-catalog-page) | Disaster-response principle: build what the tile server confirms, don't block on GSI's own catalog page | Accepted | 2026-07-31 |
| [D10](#d10-source-cooperative-publishing-path) | Source Cooperative publishing path | Accepted, validated end to end | 2026-07-31 |
| [D11](#d11-skip-already-done-work-by-default-force1-to-redo-it) | Skip already-done work by default; FORCE=1 to redo it | Accepted | 2026-07-31 |
| [D12](#d12-nodata-via-pure-black-pixels-treat-as-transparent-not-backfilled) | NODATA via pure-black pixels: treat as transparent, not backfilled | Accepted | 2026-07-31 |
| [D13](#d13-cog-internal-format-vs-oams-ingestion-profile) | COG internal format vs. OAM's ingestion profile | Accepted | 2026-07-31 |
| [D14](#d14-a-separate-readmemd-for-the-source-cooperative-product-itself) | A separate README.md for the Source Cooperative product itself | Accepted | 2026-07-31 |
| [D15](#d15-explicit-a_nodata-0-and-embedded-metadata-on-the-cog) | Explicit `-a_nodata 0` and embedded metadata on the COG | Accepted | 2026-07-31 |
| [D16](#d16-pixel-values-are-untouched-a-brightness-difference-vs-地理院地図-is-the-previewers-not-ours) | Pixel values are untouched: a brightness difference vs. 地理院地図 is the previewer's, not ours | Investigated, no action | 2026-07-31 |
| [D17](#d17-flood-fill-at-minzoom-a-single-seed-tile-can-miss-real-coverage-in-a-neighboring-cell) | Flood-fill at minzoom: a single seed tile can miss real coverage in a neighboring cell | Accepted | 2026-07-31 |
| [D18](#d18-seed-grid-expansion-tolerate-an-imprecise-seed-not-a-lower-zoom) | Seed-grid expansion: tolerate an imprecise seed, not a lower zoom | Accepted | 2026-07-31 |
| [D19](#d19-stac-item--catalog-schema-hand-built-json-matching-oam-starcs-conventions) | STAC Item/Catalog schema: hand-built JSON, matching `oam-starc`'s conventions | Accepted | 2026-07-31 |
| [D20](#d20-local-storage-lifecycle-delete-tilesout-only-after-remote-is-the-verified-source-of-truth) | Local storage lifecycle: delete `tiles/`/`out/` only after remote is the verified source of truth | Accepted | 2026-07-31 |
| [D21](#d21-tooling-must-actually-work-with-source-cooperative-as-the-master-copy-not-assume-outlayertif-is-still-there) | Tooling must actually work with Source Cooperative as the master copy, not assume `out/<layer>.tif` is still there | Accepted | 2026-07-31 |
| [D22](#d22-georef-hand-write-per-tile-vrt-xml-in-python-instead-of-a-gdal_translate-subprocess) | `georef`: hand-write per-tile VRT XML in Python instead of a `gdal_translate` subprocess | Accepted | 2026-07-31 |
| [D26](#d26-a-sokuho-preliminary-report-layer-is-a-duplicate-when-a-same-day-non-sokuho-id-already-exists) | A `_sokuho` (preliminary-report) layer is a duplicate when a same-day non-`_sokuho` ID already exists | Accepted | 2026-08-02 |

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

**Status**: Accepted (2026-07-31: option (a) below is now underway --
see D19 for the concrete STAC Item/Catalog schema)

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

**Decision**: Option (a) -- Hidenori contacts HOTOSM/OAM directly once
a real static STAC catalog exists to show them (the "map publicly
available STACs" roadmap item suggests this is the right conversation
to have, and is a much better pitch with working output in hand).
Option (b) (OAM v1's own account/token upload flow) stays available as
a fallback if (a) stalls, not pursued first.

**Update, 2026-07-31**: found `optgeo/oam-starc` (a sibling repo,
created the same day) doing the *reverse* direction -- mirroring OAM's
own `/meta` API into a static STAC v1.0.0 catalog on GitHub Pages.
Different data flow from what `cogenerate` needs (pull vs. push), but
its STAC Item schema and operational pattern (hand-built JSON, GH
Actions cron regen + commit-only-on-diff, `stac-validator`/`stac-valid`
CI, GitHub Pages `docs/`) is a ready-made convention `cogenerate` now
follows too -- see D19. Matching it means a future HOTOSM pitch lands
on schema/tooling ground they (via this project's own author) already
recognize.

**Consequences**: `stac_item.py`/`stac_catalog.py` (D19) implement
this now. GitHub Pages is not yet enabled on `optgeo/cogenerate`
(checked 2026-07-31) -- turning it on, and actually approaching
HOTOSM, both still need Hidenori.

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

**Status**: Accepted and **validated end to end** (2026-07-31)

**Context**: `CLAUDE.md`'s naming convention already assumed
`source.coop/smartmaps/cogenerate/<layer_id>.tif`, but the upload auth
mechanism was unconfirmed (S3-compatible credentials? something else?).

**Research, 2026-07-31**: the `smartmaps` org already exists on Source
Cooperative, owned by Hidenori, with public products already live
there (mostly PMTiles -- Japan terrain tiles, GTFS, PLATEAU, etc.).
Upload is S3-compatible via the `source-coop` CLI
(`source-cooperative/source-coop-cli`, installed via `brew install
source-cooperative/tap/source-coop`): `source-coop login` does a
one-time human browser OAuth step and caches short-lived credentials
in the OS keyring; `~/.aws/config` gets a profile
(`credential_process = source-coop creds`, `endpoint_url =
https://data.source.coop`) so plain `aws s3 cp/sync --profile
source-coop --acl bucket-owner-full-control` works afterward. Product
creation itself needs the source.coop web UI -- account/product
creation, a human (Hidenori) action per this project's standing safety
rules, not something Claude does.

**Decision**: Use the `source-coop login` + AWS CLI path for uploads,
scripted as `just upload` (added 2026-07-31: `aws s3 cp
{{out_dir}}/{{layer}}.tif s3://smartmaps/cogenerate/{{layer}}.tif
--profile source-coop --acl bucket-owner-full-control`). Product
creation and the one-time `source-coop login` stay manual, human-only
steps; everything after that is scriptable without any credential
passing through chat.

**Validated live, 2026-07-31**: Hidenori created the `smartmaps/cogenerate`
product and ran `source-coop login`. Confirmed the **actual bucket
path is `s3://smartmaps/<product>/`**, not the
`us-west-2.opendata.source.coop` form this entry originally guessed
from docs alone -- corrected here after testing against the real
endpoint. Uploaded `source-coop/README.md` (D14) as a test; confirmed
via `aws s3api list-objects-v2` and by re-fetching the live product
page, both title/description (which Hidenori set from Claude's
suggestion) and the README content showing correctly.

**One process note for future sessions**: `source-coop creds` prints
the actual raw credential material (access key, secret key, session
token) to stdout -- it exists for `credential_process` to call
internally, not for a human or Claude to invoke directly to "check
that it works." Use `--profile source-coop` and let `aws` call it
internally instead; don't run `creds` directly.

**Consequences**: Nothing else in the pipeline is blocked by this --
`probe`/`download`/`georef`/`cog` don't touch Source Cooperative at
all, and the upload step is now a one-line `just upload` per layer.

## D11: Skip already-done work by default; FORCE=1 to redo it

**Status**: Accepted

**Context**: None of the four `Justfile` stages checked whether their
output already existed before doing the (sometimes expensive, sometimes
GSI-load-generating) work again. Watched live 2026-07-31: a plain
re-run of `just download` after the first full run would have
re-requested all 26,982 tiles from `cyberjapandata.gsi.go.jp` for no
reason, and `just georef` (already the slow stage at ~7 tiles/sec,
~70 min for one layer) would have re-spawned a `gdal_translate` per
tile even though a tile's `.vrt` is fully determined by its `z/x/y` and
never needs to change once written.

**Decision**: Every stage skips work whose output already exists,
unless `FORCE=1` is set (a single Justfile variable, `force :=
env_var_or_default("FORCE", "")`, threaded through as a `--force` flag
or an inline shell check):
- `probe`: skips re-running `probe.py` entirely (zero GSI requests) if
  the output CSV already exists. No `--force` flag inside `probe.py`
  itself -- the skip decision is "should we invoke the network round at
  all," which lives in the `Justfile`, one level up.
- `download`: `download.py` checks `dest.exists()` per tile before
  issuing the HTTP request; `--force` bypasses it. This is the main
  lever for reducing GSI server load on re-runs.
- `georef`: `georef.py` checks whether a tile's per-tile `.vrt` already
  exists before shelling out to `gdal_translate`; `--force` bypasses
  it. The final `gdalbuildvrt` merge step always re-runs regardless
  (metadata-only, cheap, and must reflect the current tile set even if
  most per-tile VRTs were skipped).
- `cog`: shell-level `mtime` check in the `Justfile` recipe -- skips
  rebuilding the `.tif` if it's newer than its source `.vrt`; `FORCE=1`
  bypasses it.

**Consequences**: Verified live 2026-07-31: re-running `just probe`
and `just download` against a fully-completed layer both finished in
well under a second, with zero GSI requests (`26982/26982 ... already
present, not re-fetched`). Re-running `just run` (or any single stage)
after a partial or interrupted prior run now only does the remaining
work, which matters in practice since `georef` is slow enough that
interrupted runs are a real scenario, not a hypothetical. Tradeoff: the
`probe` output filename only encodes `layer` + `maxzoom`
(`tiles/{layer}.z{maxzoom}.csv`), not `minzoom`/seed coordinates -- if
you deliberately want to re-probe with different seeds under the same
layer+maxzoom, use `FORCE=1`, since the skip check can't tell that the
seeds changed.

## D12: NODATA via pure-black pixels: treat as transparent, not backfilled

**Status**: Accepted

**Context**: GSI tiles sometimes encode "no data" as literal opaque
black (RGB `0,0,0`) rather than `alpha=0` transparency. This is a real,
quantified problem in the sibling `optgeo/kitaphoto` project (GSI
seamlessphoto-based aerial/satellite mosaic): 13.2% of its z13 seed
tiles had meaningful black content, including 31 tiles that were
*entirely* black despite decoding as valid JPEGs. `kitaphoto` fixed
this by masking exact-`(0,0,0)` pixels (numpy) and compositing in
GSI's own live satellite tile at the same z/x/y as a fallback --
appropriate there because a lower-quality-but-real fallback source
exists at every zoom.

**Decision** (Hidenori, 2026-07-31): `cogenerate` has no equivalent
fallback source for disaster-response ortho imagery -- there's nothing
sensible to composite in. So: treat pure-black pixels as NODATA and
make them **transparent**, don't backfill them with anything. Same
detection technique as `kitaphoto` (exact-`(0,0,0)` pixel mask via
numpy), simpler outcome (alpha=0, not a composite). Implemented as
`clean_black_nodata()` in `georef.py`, applied per-tile before the
`gdal_translate -a_ullr` georeferencing step; skips the extra
read/write entirely for a tile with no black pixels (the common case,
consistent with D11's skip-what's-unnecessary philosophy).

**Consequences**: New dependencies (`numpy`, `pillow`) added to
`pyproject.toml` -- a deliberate, narrow exception to D2's "no
image-processing libraries" preference, justified the same way
`kitaphoto` already established the pattern within the `optgeo`
family: GDAL's CLI has no simple way to do exact-pixel-value masking
combined with conditional alpha rewriting, and reimplementing that in
raw GDAL VRT pixel functions would be far less legible than a dozen
lines of numpy. **Validated with a synthetic test tile** (2026-07-31):
an opaque black square correctly comes back with `alpha=0` and
unchanged RGB elsewhere; a tile with no black pixels returns its
original path unmodified (no needless copy). **Not yet exercised by
real data**: `20260729kumamoto_yatsushiro_0729do_sokuho` has zero
opaque pure-black pixels in a 300-tile empirical sample (~19.6M
pixels) -- the fix is correct by construction and by synthetic test,
but this run doesn't prove it against a real positive case. Re-check
`clean_black_nodata`'s actual trigger count (should be printed in
future output, currently only the per-tile-VRT skip count is reported)
the first time it runs against a layer that actually has black-nodata
content.

## D13: COG internal format vs. OAM's ingestion profile

**Status**: Accepted

**Context**: Before treating a produced `.tif` as ready to hand to
OpenAerialMap (D6), needed to know whether its *internal* format
(block size, compression, band layout) has to match some specific
profile OAM requires.

**Research, 2026-07-31**: OAM's own uploader **transcodes every
upload into a COG on ingest** -- per Planet's own writeup of OAM's
architecture ("all data inserted ... is processed on upload, so that
every piece of imagery on OpenAerialMap is a Cloud Optimized GeoTIFF"),
and separately, OAM's resulting internal profile is documented
elsewhere as 512x512 internal tiling, RGB bands converted to
YCbCr+JPEG, with a 4th band (if present) extracted as an alpha mask
rather than kept as a literal band. That's what OAM *produces*, not a
constraint on what must be *submitted* -- since it transcodes
regardless. Separately: `gdal_translate -of COG` (the dedicated COG
driver we already use, not manual tiling+overview flags) is
constructed specifically to always emit spec-compliant COGs -- that's
the entire reason the driver exists, distinct from the older
manual-tiling approach that could accidentally produce a "COG-ish"
but non-compliant file.

**Decision**: No format changes needed before OAM ingestion. Our COG
(`BLOCKSIZE=512` -- already matching OAM's own internal block size
coincidentally, `COMPRESS=DEFLATE`, RGBA) is a valid COG by
construction and is exactly the kind of source OAM's uploader expects
to transcode. Don't hand-tune our output to imitate OAM's *post-ingest*
profile (JPEG/YCbCr, alpha-as-mask) -- that would be solving a problem
OAM's own pipeline already solves.

**Consequences**: Nothing blocks handing this COG to OAM on format
grounds; D6 (account/token access) remains the only real gate on
actual ingestion.

## D14: A separate README.md for the Source Cooperative product itself

**Status**: Accepted

**Context**: This repo's `README.md` is for people working on the
pipeline code (`git clone`, `uv sync`, `just run`). Source Cooperative
products are plain S3 buckets (per D10) -- anyone browsing or
`aws s3 sync`-ing the `smartmaps/cogenerate` product directly, without
ever visiting GitHub, needs a description of the *data*, not the code:
what it is, GSI's attribution requirement, the NODATA convention (D12),
and the D9 provisional-attribution caveat for very new layers.

**Decision**: `source-coop/README.md` in this repo is the file that
gets uploaded to the product root on Source Cooperative (per D10's
upload path, `smartmaps/cogenerate/`) -- data-facing documentation,
kept separate from the repo root's engineering-facing `README.md`.
Deliberately does **not** hardcode a layer list or count, having
already been burned twice this session (D7, and the `ichiran.html`
finding in D9) by numbers/lists that go stale between sessions --
points at the product's own file listing and the (future) static STAC
catalog instead.

**Consequences**: Needs to be re-read for accuracy whenever D9's
provisional-attribution handling or D12's NODATA behavior changes, but
otherwise should stay stable -- it describes the dataset's nature, not
its current contents.

## D15: Explicit `-a_nodata 0` and embedded metadata on the COG

**Status**: Accepted

**Context**: Hidenori reviewed the published
`20260729kumamoto_yatsushiro_0729do_sokuho.tif` on Source Cooperative's
own COG previewer: "auto (from COG)" nodata handling rendered nodata
regions as solid black; manually specifying nodata value `0` in the
previewer rendered them cleanly transparent. Investigated why:

- Checked pixel content directly. Within an individual source PNG, a
  tile's own transparent (alpha=0) padding has RGB `(255,255,255)`
  (white) -- 0 counterexamples in a 400-tile / ~490k-pixel sample.
- But at the **final mosaic level** (sampled from the actual published
  COG's coarsest overview, ~245k px), every alpha=0 pixel has RGB
  `(0,0,0)` (black) -- 100% match, 0 counterexamples. The much larger
  share of nodata area is `gdalbuildvrt`'s own default fill for
  bounding-rectangle gaps with no confirmed source tile at all (most
  of the ~56% of the bbox outside the coverage polygon), which GDAL
  fills with `(0,0,0,0)` by default -- this dominates over the smaller
  in-tile white padding.
- So: our COG's actual nodata color *is* black, and the only mechanism
  marking it as "no data" was the alpha band (`ColorInterp=Alpha`,
  `Mask Flags: PER_DATASET ALPHA`) -- no classic `GDAL_NODATA` tag was
  ever set (confirmed via `gdalinfo`: no "NoData Value" line existed
  on any band before this fix). Tools that check the classic NODATA
  tag rather than inspecting the alpha band/mask (apparently including
  Source Cooperative's own "auto" previewer mode) had nothing to go
  on, and evidently render alpha=0 as opaque black rather than
  transparent.

**Decision**: Add `-a_nodata 0` to the `cog` recipe's `gdal_translate`
call, on top of (not instead of) keeping the real alpha band. Verified
this is **safe, not just convenient**: D12 already guarantees no
genuine photo content reaches this step as opaque `(0,0,0)` (pure
black pixels are cleaned to transparent during georeferencing), so
declaring `0` as NODATA can't misclassify real dark photo content.
GDAL warns `Raster band 1 has several conflicting mask sources ...
Only the nodata value will be taken into account` when both an alpha
band and `-a_nodata` are present -- tested this doesn't corrupt
anything: `ColorInterp=Alpha` and the actual alpha byte values on band
4 are preserved untouched; the warning just means GDAL's own reporting
of *which* masking mechanism is authoritative shifts toward the
simpler nodata value, which is exactly the behavior needed here.

Also added embedded self-describing metadata (`-mo` tags) while
touching this recipe, since the file currently had none beyond the
default `AREA_OR_POINT=Area` -- worth having even before `stac_item.py`
exists (D6), since a COG can travel (get downloaded, re-shared)
separately from any STAC catalog entry:
`TIFFTAG_IMAGEDESCRIPTION`, `TIFFTAG_SOFTWARE`, `TIFFTAG_COPYRIGHT`
(attribution text matching D9/`source-coop/README.md`'s wording),
and custom `LAYER_ID` / `SOURCE_URL` / `PIPELINE` tags for
traceability back to GSI's own tile server and this repo.

**Consequences**: All layers processed after this change get correct
nodata + embedded metadata automatically. `20260729kumamoto_yatsushiro_0729do_sokuho.tif`
was already built and uploaded *before* this fix -- needs a `FORCE=1
just cog` rebuild and re-upload to pick it up (tracked in
`HANDOVER.md`, not done automatically by this decision alone).

## D16: Pixel values are untouched: a brightness difference vs. 地理院地図 is the previewer's, not ours

**Status**: Investigated, no action

**Context**: Hidenori noticed the COG looks brighter on Source
Cooperative's own previewer than the same imagery does on GSI's own
地理院地図 viewer. Worth ruling out whether our pipeline (georeferencing,
COG creation, or overview generation) alters pixel values before
assuming it's a display-side effect.

**Investigation, 2026-07-31**: fetched one real source tile directly
from `cyberjapandata.gsi.go.jp` (z18, `20260729kumamoto_yatsushiro_0729do_sokuho`)
and compared its RGB statistics against the same geographic area
extracted from the published COG:
- Native resolution: **identical** (R/G/B min/max/mean match to the
  decimal -- e.g. R min 35, max 216, mean 71.635...).
- Coarsest overview level (`AVERAGE`-resampled, per D2/D5): R/G/B
  means shift by <1% (71.6->72.1, 87.5->88.0, 82.0->82.4) -- not
  visually meaningful, and not a "brighter" bias (some channels moved
  up, none dramatically).

**Conclusion**: this pipeline's output is pixel-faithful to GSI's
source imagery at both native resolution and in COG overviews. The
brightness difference Hidenori observed is a rendering effect on
Source Cooperative's own COG previewer (likely an automatic
contrast/percentile stretch or gamma handling applied at display
time, not something in the file itself) -- not a data problem, and
not something to fix in `cogenerate`.

**Consequences**: None for this pipeline. If this becomes a recurring
complaint from data consumers, it'd be a Source Cooperative
previewer-configuration question, not a reason to alter COG generation
here.

## D17: Flood-fill at minzoom: a single seed tile can miss real coverage in a neighboring cell

**Status**: Accepted

**Context**: Hidenori noticed the published `20260729kumamoto_yatsushiro_0729do_sokuho.tif`
was visibly missing part of the northern coverage area when compared
against a basemap. D1's quadtree-pruning probe only ever descends into
a seed tile's own *children* -- it never discovers a *sibling* minzoom
tile, even one immediately adjacent, since siblings aren't reachable
by parent->child recursion from a different starting cell.

**Confirmed directly, 2026-07-31**: manually probed the 8 neighbors of
the original seed (z10, 883, 414) for this layer. `883,413` (north)
and `883,415` (south) both return `200` -- real coverage, silently
missed by the single-seed probe -- while every other neighbor (and
their further-out neighbors) returns `404`. The true coverage is a
north-south strip of exactly 3 adjacent z10 tiles; 八代市's coastline
is long and thin, so this isn't surprising in hindsight -- any
elongated coverage polygon can straddle more than one minzoom grid
cell, and a single point-seed has no way to know that in advance.

**Decision**: `probe.py` now flood-fills at minzoom before the
existing top-down descent: starting from the given seed(s), check each
confirmed tile's up-to-8 neighbors at the *same* zoom, follow any that
are also `200`, repeat until no new minzoom tiles are found
(`expand_seeds_at_minzoom()`). The resulting full set of minzoom tiles
feeds the unchanged top-down quadtree descent (D1) from every one of
them, not just the original seed(s). No CLI change needed -- existing
single-seed usage (`--seed-x --seed-y` once) now transparently finds
the full extent instead of requiring the caller to already know how
many minzoom tiles a layer spans.

**Consequences**: Request cost is bounded by the coverage polygon's
minzoom-grid footprint (typically single digits of tiles), negligible
next to the thousands of maxzoom requests the descent itself makes.
Every layer already probed with a single-cell-only result should be
**re-probed with `FORCE=1`** to check whether it was similarly
incomplete -- prioritized first for `20260729kumamoto_yatsushiro_0729do_sokuho`
(the one Hidenori caught visually), tracked in `HANDOVER.md`.

## D18: Seed-grid expansion: tolerate an imprecise seed, not a lower zoom

**Status**: Accepted

**Context**: D17's flood-fill still needs at least one *correct*
starting seed -- if the given seed tile itself is wrong (e.g. an
imprecise `ichiran.html` tilejump-coordinate conversion, off by more
than one tile), it 404s and the flood-fill finds nothing. Hidenori
asked whether lowering the seed's zoom (e.g. z9/8/7) would help find a
correct starting point more mechanically/reliably.

**Investigated, 2026-07-31**: **no** -- confirmed live that GSI serves
literally nothing below z10 for these layers. Checked z9 down to z6
directly against the parent tiles of a z10 coordinate known to have
real data (`20260729kumamoto_yatsushiro_0729do_sokuho`, 883,414):
**every one 404**, matching every surveyed layer's `ichiran.html`
entry documenting exactly "ズームレベル 10～18". A lower-zoom seed
search isn't just wasteful here, it's non-functional -- there's
nothing to find.

**Decision**: instead, check a small square **grid of candidate tiles
at minzoom itself** around each given seed before flood-filling --
`Tile.grid(radius)`, a `(2*radius+1)^2` square, `DEFAULT_SEED_GRID_RADIUS
= 2` (5x5) in `probe.py`, overridable via `--seed-grid-radius` /
`just probe`'s `SEED_GRID_RADIUS` env var. Every grid cell across every
given seed becomes a candidate start for D17's flood-fill (deduplicated).
Tolerates the seed being off by up to `radius` tiles in any direction,
at a cost of only `(2r+1)^2 - 1` extra minzoom requests per seed --
negligible next to the thousands of maxzoom requests that follow.

**Validated live**: probed `20260729kumamoto_yatsushiro_0729do_sokuho`
with a seed deliberately offset 2 tiles east of the real one (885,414
instead of 883,414) and `--seed-grid-radius 2`: still found all 3 real
minzoom tiles correctly (`3 minzoom tile(s) found via flood-fill from
25 seed(s), 49 requests total`).

**Consequences**: `radius=2` is a starting guess, not a proven-optimal
value -- revisit if a future layer's seed is off by more than 2 tiles
and the probe fails to find anything (raise the radius for that call
via `SEED_GRID_RADIUS`, no code change needed).

## D19: STAC Item/Catalog schema: hand-built JSON, matching `oam-starc`'s conventions

**Status**: Accepted

**Context**: D6 needed a concrete STAC schema before `stac_item.py`/
`stac_catalog.py` could be written. `optgeo/oam-starc` (found
2026-07-31, same day it was created) already mirrors OAM's own
metadata into static STAC and is a live, working reference for
schema/asset conventions HOTOSM-adjacent consumers would recognize --
using it as a template (rather than inventing a schema from scratch or
adopting a generic STAC SDK's defaults) makes a future HOTOSM pitch
(D6) land on familiar ground.

**Decision**:
- No STAC SDK dependency (`pystac` etc.) -- Items/Catalog are built as
  plain Python dicts and `json.dumps`, matching both `oam-starc`'s own
  approach (hand-built JSON in Ruby) and D2's "small, inspectable
  units, no unnecessary embedded libraries" preference.
- `stac_catalog.py`'s Catalog uses proper `links` with `rel: "item"`
  pointing at each Item's own hosted JSON file -- **not**
  `oam-starc`'s inlined `items` array (non-standard: bundling full
  Item objects, including large geometries/checksums, into one
  ever-growing `catalog.json` doesn't scale the way this pipeline's
  COGs do). Items and Catalog are separate files under `docs/`
  (`docs/items/<layer>.json`, `docs/catalog.json`), each independently
  fetchable and validatable.
- Asset key/role convention borrowed directly from `oam-starc`'s
  table: the COG asset is keyed `imagery` with `roles: ["ortho",
  "data"]` and `type: image/tiff; application=geotiff;
  profile=cloud-optimized`; a `metadata` asset (`roles: ["metadata"]`)
  self-links to the Item's own JSON. No `thumbnail` asset yet (would
  need a new render step -- future extension, not blocking).
- `stac_extensions` stays `[]` until a field that actually needs one
  is populated (e.g. `eo` if/when band-level metadata exists) --
  matching `oam-starc`'s "don't declare what you don't use" rule.
- Every field is sourced from data already on disk, no new scraping:
  geometry/bbox from `gdalinfo -json`'s `wgs84Extent` (shelled out to,
  per D2 -- never `osgeo` Python bindings); `datetime` from the layer
  ID's embedded capture-date fragment (D4); title/source URL/copyright
  from the COG's own D15 `-mo` tags, read back via the same `gdalinfo
  -json` call; `gsd` computed from maxzoom=18 (D5), not scraped.
- **License**: GSI's tile terms are Japan's government-standard usage
  terms (政府標準利用規約), CC-BY-4.0-compatible -- distinct from the
  CC0-1.0 that covers only this pipeline's own code (D3). The STAC
  Item's `properties.license` is the real SPDX ID `"CC-BY-4.0"`, not
  `"other"` (Hidenori, 2026-07-31: `"other"` reads as evasive to a
  downstream consumer when a real SPDX ID applies -- correct this even
  though `"other"` would have validated fine against the schema).

**Consequences**: `stac_item.py --layer ... --cog ... --asset-url ...`
produces one validated Item; `stac_catalog.py --items-dir docs/items/`
rebuilds the Catalog from whatever Items exist so far. Both validated
2026-07-31 against STAC 1.0.0 via `stac-valid`'s `stac-validator` CLI
(not the deprecated `stac-validator` PyPI package -- it now prints a
"please upgrade" notice pointing at `stac-valid`, so `pyproject.toml`'s
`dev` extra uses the renamed package) -- all 6 already-published
layers' Items plus the Catalog they produce are schema-valid. GitHub
Pages is not yet enabled on `optgeo/cogenerate`; `docs/` exists and is
ready to serve once it is (D6).

## D20: Local storage lifecycle: delete `tiles/`/`out/` only after remote is the verified source of truth

**Status**: Accepted

**Context**: Scaling from 6 to (eventually) ~194 layers (`candidates.py`)
makes local disk a real constraint, not a hypothetical one -- hit
directly 2026-07-31, running 6 layers' pipelines in parallel: a single
huge layer's `tiles/` can be 28GB+, and `gdal_translate -of COG` writes
a full `.tif.building` temp file alongside the still-present source
tiles before its final `mv`, so source + in-progress output coexist at
that step's peak. The Mission (`CLAUDE.md`) already treats Source
Cooperative as the durable, canonical home for a finished COG -- local
`out/*.tif` was never meant to be the permanent copy, matching the
`optgeo` "Adopt Geodata" pattern's whole point (adopt data, publish it
durably elsewhere, don't keep hoarding it locally forever).

**Decision**: A layer's local artifacts are deleted in two independent
steps, each gated on its own verification, never on a time-based or
"probably done" guess:
- **`tiles/<layer>/`** (the downloaded PNGs + per-tile `.vrt`
  sidecars): safe to delete once `out/<layer>.tif` exists, passes a
  `gdalinfo` sanity check (`LAYOUT=COG` present), **and** `aws s3api
  head-object` against Source Cooperative confirms the same file is
  live there (size match). Never delete `tiles/` for a layer whose
  download/rebuild is still in progress -- `download.py`'s D11
  skip-if-present logic depends on partial `tiles/` contents to make
  re-runs incremental rather than a full re-fetch.
- **`out/<layer>.tif`** (the final local COG): safe to delete once the
  upload check above passes **and** `docs/items/<layer>.json` (D19)
  already exists -- the STAC Item captures the file's size/sha256
  checksum permanently, so deleting the local copy doesn't lose the
  ability to verify what was actually published, even after it's gone
  from this machine. Ordering matters: run `stac-item` *before*
  deleting `out/<layer>.tif`, never after.

Applied retroactively this session for `kumamoto_yatsushiro`/`wajima`/
`nichinan`'s `tiles/` (all 3 conditions already held: uploaded,
confirmed, and -- for the STAC-item condition on `out/` specifically --
their Items already existed too, so those 3 layers already satisfy
both steps if disk pressure ever calls for reclaiming their `out/*.tif`
too, not just `tiles/`).

**Consequences**: `Justfile`'s `cleanup-tiles`/`cleanup-cog`/`cleanup`
recipes automate the two checks above instead of relying on remembering
to do it manually every time (as happened ad hoc for the first 3
layers, prompted by an actual near-miss on disk space this session). A
persistent background disk-space monitor (started 2026-07-31, warns
<25GB free, critical <10GB) is a safety net for catching problems
between cleanup passes, not a replacement for running cleanup as each
layer settles. Investigated and cleaned up a related but separate
project's (`~/photosynthesis`, the Mapterhorn/Freetown pipeline) own
stale intermediates the same session (~150GB reclaimed: a completed
pipeline's now-redundant merge component, its now-unneeded
per-zoom-level PMTiles store, a stale partial download superseded by
the real source, and -- Hidenori's call, after confirming the OAM
hosting URL still resolves -- the 110GB original source COG itself)
-- same underlying principle (don't keep local copies of data a
finished pipeline has already durably published elsewhere), different
repo, not itself part of `cogenerate`'s own lifecycle policy.

## D21: Tooling must actually work with Source Cooperative as the master copy, not assume `out/<layer>.tif` is still there

**Status**: Accepted

**Context**: D20 established that `out/<layer>.tif` gets deleted once
uploaded and its STAC Item exists -- but D20 itself only covered
*when* to delete, not whether the rest of the toolchain could actually
cope with the file being gone afterward. Hidenori asked directly: does
every process actually treat Source Cooperative as the master, or do
some still quietly assume `out/` is the real copy? Auditing found two
real bugs, not hypothetical ones:

1. **`stac_item.py` had no path forward once `out/<layer>.tif` was
   deleted** -- `--cog` was required, `gdalinfo`/checksum/size all read
   the local file unconditionally. Regenerating an Item after cleanup
   (a schema fix, D19 changing, anything) was simply impossible for an
   already-cleaned-up layer.
2. **Every Item generated so far had the wrong asset `href`**:
   `https://source.coop/<account>/<product>/<file>` is Source
   Cooperative's Next.js product *page* (`content-type: text/html`) --
   not a file GDAL (or any STAC client expecting `image/tiff`) can
   open. `https://data.source.coop/<account>/<product>/<file>` is the
   real data endpoint (`content-type: image/tiff`, `Accept-Ranges:
   bytes`, confirmed live). This wasn't a D20 side-effect -- it was
   wrong from the very first Item generated, D20 just made it visible
   because reasoning about "what does a client actually fetch" forced
   checking the URL instead of trusting it.

**Decision**:
- `stac_item.py`'s `--cog` is now optional. When absent or the path
  doesn't exist, every field falls back to a remote source: `gdalinfo
  -json /vsicurl/<asset_url>` for geometry/bbox/D15 tags (cheap even
  for a multi-GB COG -- GDAL's COG driver only pulls header/overview
  byte ranges over HTTP range requests, confirmed against
  `data.source.coop`), an HTTP HEAD for file size, and the checksum
  carried forward from `--previous-item` (an already-generated Item
  for the same layer) rather than ever assumed -- downloading and
  re-hashing the whole object from `asset_url` is a last resort only,
  used and logged loudly, never silent.
- Added `--output` (writes the file directly) as an alternative to
  stdout redirection, specifically because `--previous-item` and
  `--output` are routinely the *same path* (refreshing a layer's own
  Item) -- a plain `command > file.json` shell redirect truncates
  `file.json` before the process even starts, so reading it back via
  `--previous-item` would see an empty file, not the old content.
  `--output` reads-then-writes inside the one process, avoiding the
  race entirely.
- `Justfile`'s `asset_url` default fixed to `data.source.coop`; `stac-item`
  now always passes `--previous-item`/`--output` at the same path.
- `just verify` (D20's pre-deletion gate) no longer requires
  `out/<layer>.tif` to exist: falls back to the file size already
  recorded in `docs/items/<layer>.json` when the local COG is gone,
  and switched from authenticated `aws s3api head-object` to a plain
  public HTTPS HEAD on `data.source.coop` -- reading already-public
  data doesn't need Source Cooperative credentials at all, so `verify`
  (and everything gated on it) now works even if `source-coop login`'s
  session has expired.
- All 6 already-published layers' Items regenerated with the corrected
  `href`; 3 whose `out/*.tif` was already gone (kumamoto_yatsushiro,
  wajima, nichinan) exercised the new remote-fallback path for real,
  not just in theory -- confirmed identical checksums to their prior
  Items (carried forward, not re-hashed) and re-validated against STAC
  1.0.0.

**Consequences**: A STAC client (or a human) that actually tries to
fetch the `imagery` asset of any Item generated before this fix would
have gotten an HTML page, not a COG -- worth being aware of if
anything cached/mirrored those earlier Items before 2026-07-31.
Regenerating or fixing any layer's Item is now possible regardless of
whether its local COG still exists, which is the normal state of
affairs for most layers going forward (D20). `candidates.py` and
`stac_catalog.py` were already remote/live-source-only (D7-style) and
needed no changes.

## D22: `georef`: hand-write per-tile VRT XML in Python instead of a `gdal_translate` subprocess

**Status**: Accepted

**Context**: Hidenori's own sense, 2026-07-31, that `georef` felt like
the slow pipeline step, prompted actually measuring it rather than
guessing. The original per-tile step spawned one `gdal_translate`
subprocess per tile to produce a georeferenced VRT sidecar (D2's
"GDAL via subprocess" rule, applied uniformly to every GDAL call in
the pipeline at the time). Benchmarked on real, cold-cache noto tiles
(not a repeated single cached file): **~250ms/tile**, essentially all
process-spawn + GDAL-driver-registration overhead -- the actual output
is a few hundred bytes of XML describing one full-tile source, no
pixel data copy, nowhere near 250ms of real work. At noto's scale
(270,378 tiles) that step alone projected to **~19 hours**.

**Decision**: `georef.py`'s `clean_black_nodata()` already opens every
tile with PIL (for D12's black-nodata check) -- extended it to also
return the width/height/mode it already has in hand, and added
`write_vrt()`, which hand-writes the identical single-source
`VRTDataset` XML `gdal_translate` would have produced, directly in
Python (no subprocess). Only handles plain `RGB`/`RGBA` PIL modes
(the only two ever seen in this data source, per D2's original
band-count note and a fresh 2026-07-31 check across 3 more, larger
layers -- 100% RGBA, zero palette/grayscale tiles in any sample);
falls back to the original `gdal_translate` subprocess for anything
else, so an unanticipated mode degrades to the slow-but-GDAL-verified
path instead of silently mis-describing band structure.

**Verification**: benchmarked ~3.7ms/tile on the same real tiles (a
**~68x** speedup) with `gdalinfo -checksum` confirming byte-identical
per-band pixel checksums against `gdal_translate`'s own output, and
`gdalbuildvrt` merging the hand-written VRTs identically. Applied live,
mid-session, to two already-running layers (`noto`, `yatsushironishi`)
by killing their in-flight `georef` processes and re-running `just
run` -- safe only because D11's skip-if-`.vrt`-exists logic resumed
from exactly where each left off rather than restarting; confirmed
`yatsushironishi` (35,256 tiles, ~30% remaining) finished its
remaining per-tile work in under a minute post-restart.

**Consequences**: `gdalbuildvrt` (the mosaic merge) and the final
`gdal_translate -of COG` build both stay subprocess calls, unchanged
-- D2's rule still holds for anything that does real raster work
(pixel resampling, compression, overview generation). This is narrowly
scoped to the one step that was pure metadata generation being paid
for at full subprocess cost. Revisit if a layer ever legitimately needs
a non-RGB/RGBA tile (would silently fall back to the slow path,
correctly but without comment -- watch the `cog` recipe's fallback
count if `georef` unexpectedly stays slow for a specific layer).

**Unrelated pre-existing bug caught while re-running amakusa's rebuild
the same session**: `discover_tiles()`'s glob (`*/*/*.{ext}`) also
matched `clean_black_nodata()`'s own leftover `<y>.cleaned.<ext>`
output from an *earlier* run (D12) -- `Path("106049.cleaned.png").stem`
is `"106049.cleaned"`, not an int, so `int(p.stem)` crashed the whole
`georef` step. Not a D22 side-effect -- this glob is original code,
just never exercised against a directory containing a real `.cleaned`
file until amakusa's rebuild (the first layer whose *first* build had
actually triggered D12's cleaning, so the *second* build was also the
first to re-scan a directory containing one). Fixed by skipping any
`p.stem.endswith(".cleaned")` match in `discover_tiles()`. Caught the
same day because the rebuild's `cog` step was correctly skipped
(mtime-based, D11) when `georef` crashed rather than silently
publishing stale output -- but it's worth noting the `run` recipe's
final `echo "done: ..."` prints unconditionally, so a silent skip
downstream of a crash isn't obviously distinguishable from a real
success without checking the actual file mtime/size, as happened here.

## D23: STAC `datetime` for approximate historical dates: `null` + `start_datetime`/`end_datetime`, not a guessed single date

**Status**: Accepted

**Context**: D4 parses a layer ID's leading digits/`_MMDDdo` fragment
for STAC `datetime`. Two live IDs don't fit that: `19480000dol` and
`19620000dol` -- historical reference imagery of Hiroshima (1947-48
and 1962) that GSI itself kept alongside its 2014 landslide-disaster
layers, for land-use comparison against the present day. Both use
GSI's own `0000` placeholder for "month/day unknown within this year"
(`19620000dol`'s `ichiran.html` title is literally "1962年", no
month/day at all). `stac_item.py`'s `parse_capture_date()` originally
just raised on these (caught live 2026-08-01, picking up Hiroshima-area
layers ahead of FOSS4G 2026 Hiroshima) rather than silently emitting a
fabricated `-01-01` date.

**Decision** (2026-08-01, made to keep the pipeline moving per
Hidenori's standing directive not to block on decisions rather than
escalate a two-layer edge case): use STAC's core common-metadata
date-and-time-range fields -- `"datetime": null` plus
`start_datetime`/`end_datetime` spanning the known precision (full
calendar year for a `YYYY0000` ID, full month for `YYYYMM00`) -- no
STAC extension needed, this is core spec. Represents genuine
uncertainty honestly instead of picking an arbitrary day.

**Consequences**: `parse_capture_date()`'s return type changed from a
bare ISO string to a dict of STAC properties to merge in (exact-date
layers get `{"datetime": "..."}`, imprecise ones get the null+range
form) -- `build_item()` updated to `**parse_capture_date(layer)` into
`properties` accordingly. Known gap: `19480000dol`'s own
`ichiran.html` title says "1947年～1948年" (spans two years) but the
layer ID's leading digits are `1948`, so this produces a 1948-only
range, not 1947-1948 -- deliberately not special-cased from the
scraped title text (would break D4's ID-first parsing consistency for
one single historical layer); the STAC record is accurate to what the
ID encodes, just not maximally precise for this one edge case.

## D24: `probe.py`: retry transient network errors / 5xx instead of treating them as 404

**Status**: Accepted

**Context**: Hidenori spotted visible black square holes in the
published `20240102noto_0405_0426do` mosaic (reported live, GSI's own
地理院地図 shows no gap at the same coordinates -- ruling out a real
GSI-side coverage absence). Investigated by cross-referencing the
probe's saved CSV against the published COG's alpha channel and
directly re-fetching candidate tiles from GSI: found **49 tiles across
11 clusters**, each fully surrounded by confirmed neighbors (detected
by flood-filling "outside" from the CSV's bounding-box border and
finding the unconfirmed cells that flood-fill never reaches -- true
enclosed holes, not coastline/open-water boundary), each returning a
normal `HTTP 200` with valid image data when fetched directly.

**Root cause**: the module docstring's own design already documents
that the minzoom flood-fill (D17) only re-checks horizontally *at
minzoom* -- past that, `probe()`'s maxzoom descent is a pure top-down
quadtree walk with no sibling re-check. `exists()` had no retry: a
single transient network error or 5xx on any intermediate-zoom
ancestor tile, during a run fetching hundreds of thousands of tiles
over multiple hours, permanently prunes that whole subtree (up to
2^(maxzoom-z) tiles) as if it were a real 404 -- indistinguishable
from the correct pruning signal the whole strategy depends on.

**Decision**: retry on network exceptions and 5xx responses (3
attempts, linear backoff starting at 0.5s) -- but **never retry a real
404**, since treating 404 as possibly-transient would undermine the
core pruning strategy (module docstring: "a 404 prunes the whole
subtree... only tiles that return 200 spawn the 4 children") and waste
requests against a government server for a signal that's actually
fast and reliable.

**Consequences**: doesn't retroactively fix layers already built
before this change -- `20240102noto_0405_0426do`'s 49 known-missing
tiles need a manual patch (re-probe/download just those tiles, merge
into the existing published COG, re-upload). Worth an occasional spot
check on other large already-published layers using the same
enclosed-hole detection method (flood-fill the probe CSV's bounding
box from its border, anything unreached is a true interior gap) if
one is suspected -- not run exhaustively across all 52 published
layers as of this decision, only reactively when something looks off.

**Patch applied, 2026-08-01**: rebuilt `20240102noto_0405_0426do` from
a VRT merging the original COG with the 49 patch tiles, re-uploaded
with `FORCE=1` (checksum/size changed: 48647237551 -> 48655094466
bytes). First attempt streamed the ~45GB original over HTTPS via
`/vsicurl` *during* the `gdal_translate -of COG` encode itself -- that
connection died silently after ~4h9m (no crash, no OOM, just a clean
TCP close) partway through writing the full-resolution base layer,
leaving a structurally-valid-looking COG header (`gdalinfo` succeeds)
whose entire pixel payload was unwritten zeros -- confirmed via
`gdallocationinfo` spot-checks, not `gdalinfo` alone, which cannot
tell a two-pass COG's header-written-but-data-pending state from a
genuinely complete file. Second attempt downloaded the original to a
local file first (plain resumable `curl -C -`, no GDAL/network
coupling), then rebuilt purely from local files -- succeeded in under
an hour. **Lesson for any future large (>10GB) COG rebuild that reads
a remote original as a VRT source**: download it locally first, don't
let `gdal_translate` stream it over the network mid-encode.

## D25: NODATA via pure-white pixels too (D12's black fix, extended) -- except for monochrome-origin layers

**Status**: Accepted

**Context**: Hidenori spotted a visible grid pattern of opaque
pure-white (255,255,255) tiles in the already-published `20140831dol`
overview. Quantified: ~29% of sampled opaque pixels in that layer are
exact pure white -- implausible as real content for a non-snow
disaster-response photo, the same "GSI encodes nodata as a solid
color" pattern D12 already handles for black.

**Complication**: a handful of this catalog's oldest layers
(`19480000dol`/`19620000dol`, 1947-48/1962 Hiroshima reference
imagery, D23) are genuinely monochrome photos merely encoded as RGB.
Real content in those legitimately hits pure white (bright highlights)
or pure black (deep shadow) -- blindly treating white-as-nodata
catalog-wide would carve real holes into real (if grayscale) photo
content on exactly the layers where D23 already went out of its way to
represent approximate historical dates honestly.

**Decision**: `georef.py`'s `clean_black_nodata()` became
`clean_nodata_colors()`, which always cleans black (D12, unchanged)
and additionally cleans white unless the layer samples as
monochrome-origin. Monochrome detection (`sample_is_monochrome()`)
uses a structural signal, not a layer-ID allowlist: sample ~20 tiles
spread across the layer and check whether R, G, and B are exactly
equal for virtually every opaque pixel (`MONOCHROME_SPREAD_THRESHOLD =
0.99`). Rationale: a true grayscale-into-RGB source has *zero* color
variation anywhere; a real color aerial photo always has some,
somewhere (vegetation, water, roofing), even where individual pixels
happen to be neutral gray. Confirmed live: exactly 0 channel spread
(`max(R,G,B) - min(R,G,B)`) across ~150k-227k sampled opaque pixels
each for `19480000dol`/`19620000dol`, vs. a clear ~11.2 mean spread for
`20140831dol`'s real color content -- a wide, unambiguous margin.

**Consequences**: fixed going forward for any layer built after this
change.

**Retroactive scan + patch, 2026-08-02**: built `cogenerate.whitescan`
(`just whitescan`) to scope the already-published catalog cheaply
(overview-level `/vsicurl` reads, no local files) -- 106 layers
scanned, 5 flagged above the 1% white-fraction threshold, 2 correctly
excluded as monochrome-origin. Of the 5 flagged, 2 were visually
confirmed as **false positives** before patching anything --
`20230202_nishinoshima_dol` (1.8%, real volcanic steam/lava
brightness) and `20190618yamagata_tsuruokamurakami_0620do` (1.0%, real
cloud cover) -- a reminder that the fraction alone isn't sufficient
signal at low percentages; a quick visual/overview check before
patching is worth the two minutes it costs. The remaining 3
(`20140828dol` 23.7%, `20140830dol` 33.2%, `20140831dol` 29.4%, all
from the 2014 Hiroshima landslide response batch) were confirmed as
genuine nodata via full-resolution `gdallocationinfo` and patched:
download the original locally, compute a corrected alpha band with
`gdal_calc.py` (`where((R==255)*(G==255)*(B==255), 0, alpha)` --
GDAL's bundled CLI accessory, not an osgeo Python binding, keeping D2's
rule intact), merge that alpha with the original RGB via a VRT, then
`gdal_translate -of COG` the VRT with the same `-co`/`-mo` flags as the
standard `cog` recipe. All 3 verified post-patch: white fraction
dropped to ~0.2-0.3% (residual plausibly real small bright features),
real color content spot-checked unchanged. `FORCE=1` re-uploaded,
verified, STAC regenerated, committed -- same lifecycle as D24.

## D26: A `_sokuho` (preliminary-report) layer is a duplicate when a same-day non-`_sokuho` ID already exists

**Status**: Accepted

**Context**: A `--top 194` full-pool pass (2026-08-02, after finishing
the 2013-2015 batch) turned up 3 candidates that looked new but
weren't: `20190828kyusyu_sagachiku_0830do_sokuho`,
`..._0831do_sokuho`, and `20210705oame_0706do_sokuho`. Each has an
already-published counterpart with the exact same district, capture
date, and `ichiran.html` tilejump coordinate --
`20190828kyusyu_sagachiku_0830do`/`_0831do` and
`20210705oame_0706do` respectively.

**Investigated**: `ichiran.html`'s own title text distinguishes them
precisely -- the already-published ID's title reads plain "正射画像"
(ortho imagery), while the candidate's title reads "正射画像（速報）"
(ortho imagery, **preliminary report**), otherwise word-for-word
identical including the parenthetical capture date. GSI's own naming
convention marks `_sokuho` as the rapid/preliminary release of a
capture that later also gets published under a non-`_sokuho`,
presumably-reprocessed-or-finalized ID -- not a second, independent
photograph of the same place. This is a real GSI convention, not a
`candidates.py` bug (contrast with the D9-documented
`atsumtoubu`/`atsumatoubu` case, which *was* a catalog typo).

**Decision**: When a candidate's `ichiran.html` title contains "（速報）"
and an already-published layer exists with an identical district +
capture date (only differing by the `_sokuho` suffix and the "（速報）"
marker), treat the `_sokuho` candidate as a duplicate -- skip it, don't
build it. This is a **narrower** rule than "any `_sokuho`-suffixed
layer is skippable": several already-published layers in this catalog
(`20250815rain_amakusa_0815do_sokuho`,
`20191025oame_sakura_1026do_sokuho`, etc.) are themselves `_sokuho`
IDs with **no** non-`_sokuho` counterpart ever published by GSI --
those are the *canonical* ID for that capture and were correctly built
as-is. The distinguishing check is specifically "does a matching
non-`_sokuho` sibling ID already exist," not the suffix alone.

**Consequences**: These 3 IDs will keep resurfacing in future
`candidates.py --top 194` runs (their own `ichiran.html` entries are
real, just superseded) -- skip by hand like the
`_dansaizu`/`_shinsui`/typo'd-ID false positives already documented
(CLAUDE.md). Worth a similar sibling-ID check the next time a
`_sokuho`-suffixed candidate turns up: check whether the same district
+ date already has a non-`_sokuho` counterpart published before
assuming it's new coverage.
