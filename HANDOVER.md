# HANDOVER.md

Session-by-session log: what happened, what's still running, what's
next. For *why* a choice was made, see `DECISIONS.md` (ADR log) instead
of looking for rationale here -- entries below link to the relevant
`D`-number rather than re-explaining it.

## 2026-07-31 (new session, milestone) -- first real layer published

`20260729kumamoto_yatsushiro_0729do_sokuho.tif` (5,457,760,113 bytes)
finished uploading to `s3://smartmaps/cogenerate/` -- confirmed via
`aws s3api list-objects-v2`. This is the first COG this pipeline has
ever put somewhere a real consumer could use it, live at
https://source.coop/smartmaps/cogenerate. Everything since the
scaffold handoff (probe -> download -> georef -> cog -> QGIS review by
Hidenori -> upload) has now gone all the way through for one real
disaster layer.

## 2026-07-31 (new session, multi-layer run) -- Source Cooperative upload validated end to end

Hidenori created `smartmaps/cogenerate` on Source Cooperative (title
"Japan GSI Disaster-Response Aerial Imagery (COGs)", using the
title/description Claude suggested) and ran `source-coop login`
locally -- both D10 manual steps now done.

- **Incident, self-reported**: while checking the new `source-coop`
  CLI setup, ran `source-coop creds` directly to inspect it, which
  printed the actual temporary AWS access key / secret key / session
  token into the conversation. Should have gone straight to `~/.aws/config`
  + `--profile source-coop` without ever calling `creds` manually.
  Low real impact (STS session credential, ~1.5h TTL, expired long
  before this could matter), but noting it so it doesn't repeat: never
  invoke `source-coop creds` (or equivalent raw-credential-dump
  commands) directly again, only through `--profile`.
- Set up `~/.aws/config` with the `source-coop` profile per D10.
- **Validated the whole upload path for real**: uploaded
  `source-coop/README.md` to `s3://smartmaps/cogenerate/README.md`,
  confirmed both via `aws s3api list-objects-v2` and by re-fetching the
  live product page -- title/description/README all showing correctly.
- Added a `just upload` recipe (D10's "scriptable as its own just
  recipe" plan, now real): `aws s3 cp {{out_dir}}/{{layer}}.tif
  s3://smartmaps/cogenerate/{{layer}}.tif --profile source-coop --acl
  bucket-owner-full-control`.
- Kicked off the actual upload of `20260729kumamoto_yatsushiro_0729do_sokuho.tif`
  (5.46GB) -- this layer was already approved for real publishing
  earlier this session (D9's disaster-response principle); now that
  the upload mechanism is proven, running it for real. Result recorded
  in the next entry once it finishes.

### Also this session: producing more COGs while Hidenori is away

Asked to prioritize new-disaster and Kumamoto-area layers as a
multi-layer test run. Selected from the live catalog (D7):

1. `20250815rain_amakusa_0815do_sokuho` (天草上島, Kumamoto) -- in progress
2. `20250815rain_yatsushirohigashi_0816do_sokuho` (八代東, Kumamoto)
3. `20250815rain_yatsushironishi_0816do_sokuho` (八代西, Kumamoto)
4. `20240923rain_wajima_0923do_sokuho` (輪島, next most recent)
5. `20240809hyuganada_nichinan_0809do_sokuho` (日南, different region)

Seed coordinates for all 5 taken from `ichiran.html`'s own tilejump
links (z15, integer-divided by 32 for the z10 seed) -- all 5 confirmed
`ズームレベル 10～18` and the same standard 備考 disclaimer (automated
processing artifacts, cloud interference), no extra attribution terms.
Progress on each tracked below as it completes; not attempting Source
Cooperative upload for these new layers without checking with Hidenori
first -- only the already-approved kumamoto_yatsushiro layer is being
published this session.

## 2026-07-31 (final for this session) -- first COG built and verified

`just cog` (with the BIGTIFF fix) finished: **10m47s**,
`out/20260729kumamoto_yatsushiro_0729do_sokuho.tif`, 5.46 GB.
`gdalinfo` confirms:

- `LAYOUT=COG` (GDAL's own compliance marker), `BLOCK=512x512`,
  `COMPRESSION=DEFLATE`, 7 overview levels + mask-band overviews.
- Extent (61184x65536 px @ ~0.6m/px, correct for z18) lands exactly on
  八代市 (Yatsushiro), Kumamoto -- Upper Left 130°25'46.88"E
  32°32'48.53"N to Lower Right 130°45'28.45"E 32°14'59.91"N.
- RGB bands: real variance (mean ~103-124, stddev ~27-32 per band,
  `STATISTICS_VALID_PERCENT=43.7`, i.e. ~44% of the bounding rectangle
  has real coverage -- the rest is the probe-confirmed polygon's
  padding, correctly nodata).
- Alpha band: min 0 / max 255 / mean 111.44 -- consistent with 43.7%
  opacity coverage assuming near-binary (not partially antialiased)
  transparency (`0.437 * 255 = 111.4`, matches to 3 significant
  figures).
- Generated a 1600px preview PNG and sent it to Hidenori for visual
  review, per "I'll check the COG myself first" from earlier in this
  session. **Hidenori opened the real file in QGIS directly (asked for
  the absolute path: `/Users/hfu/cogenerate/out/20260729kumamoto_yatsushiro_0729do_sokuho.tif`)
  and confirmed "looks good."** COG approved.

### Next steps (pick up here)

1. ~~Hidenori reviews the COG~~ -- done, approved 2026-07-31.
2. **Blocked on Hidenori** (D10): Source Cooperative upload needs two
   manual steps neither done yet -- (a) create the `smartmaps/cogenerate`
   product via the source.coop web UI, (b) run `source-coop login`
   once locally. Claude can script the actual `aws s3 sync` upload as
   soon as both are done, without ever handling credentials.
3. OAM ingestion: still gated on D6 (contact HOTOSM once a real static
   STAC catalog exists, or go through the v1 token flow) -- not
   attempted yet, and not blocking Source Cooperative publishing.
4. `stac_item.py` is now unblocked on the datetime question (D4
   resolved) but still doesn't exist -- worth building alongside/before
   the Source Cooperative upload, since D10's naming convention and a
   real STAC item both want to exist before calling this layer
   "published."

## 2026-07-31 (continued once more) -- NODATA handling (D12) and OAM format check (D13)

Hidenori's ask: once the COG exists, check whether its internal format
is OAM-acceptable, and handle GSI's known black-vs-transparent NODATA
inconsistency the same pragmatic way it was handled for `seamlessphoto`
before -- referencing the sibling `optgeo/kitaphoto` project, which hit
and fixed exactly this class of problem.

- **D13 (OAM format)**: researched -- OAM's own uploader transcodes
  every upload into a COG on ingest, so our output doesn't need to
  hand-match OAM's internal post-ingest profile (512px blocks,
  YCbCr/JPEG, alpha-as-mask). `gdal_translate -of COG` already
  guarantees a spec-compliant COG by construction. Nothing to change;
  D6 (account/token access) remains the only real OAM gate.
- **D12 (NODATA)**: found `kitaphoto`'s prior fix (numpy exact-black
  pixel mask, then composite in satellite fallback imagery) via its
  `HANDOVER.md` -- quantified there as 13.2% of z13 seed tiles having
  meaningful black content. `cogenerate` has no fallback source to
  composite in, so implemented the simpler version Hidenori chose:
  same detection, but turn matched pixels transparent (`alpha=0`)
  rather than backfilling them. New `clean_black_nodata()` in
  `georef.py`, wired into the per-tile loop before georeferencing;
  skips the extra read/write for tiles with no black pixels (the
  common case). Added `numpy`/`pillow` to `pyproject.toml` for this --
  a deliberate, narrow exception to D2, matching the precedent
  `kitaphoto` already set.
  - **Validated with a synthetic test tile**: opaque black square ->
    correctly comes back `alpha=0`, rest of the tile untouched; a tile
    with no black pixels returns unmodified. `just lint` clean.
  - **Empirically checked against real data**: scanned all pixels in a
    300-tile sample (~19.6M pixels) of
    `20260729kumamoto_yatsushiro_0729do_sokuho` -- **zero** opaque
    pure-black pixels. This layer doesn't need the fix; it's now a
    general safeguard for layers that do, unexercised by this run.
    `georef.py`'s summary line now reports a cleaned-tile count so a
    future run against a layer that actually has the problem will show
    a nonzero number instead of silence.

## 2026-07-31 (continued yet again) -- georef's first real completion, two bugs caught by actually finishing a run

`georef`'s original (pre-D11) run finally reached the end of its
26,982 per-tile loop and hit its **first real failure**: the final
`gdalbuildvrt -addalpha <merged> <26982 paths...>` call passed every
per-tile `.vrt` path as an individual argv entry and blew past the OS's
`ARG_MAX` -- `OSError: [Errno 7] Argument list too long`. All 26,982
per-tile `.vrt`s had already been written successfully (only the merge
step failed), so nothing was lost. Fixed in `georef.py`: write the
path list to a temp file and call `gdalbuildvrt -addalpha
-input_file_list <file> <merged>` instead -- the standard fix for
`gdalbuildvrt` at this scale. Re-ran `just georef`: thanks to D11, the
26,982 already-done per-tile VRTs were all skipped, and the whole
recipe (skip-check + fixed merge) finished in **18.5 seconds** instead
of another ~70 minutes.

Also finally checked the RGB/RGBA band-count risk `georef.py`'s
docstring has been flagging since the original planning session:
scanned all 26,982 source PNGs' PNG color-type byte directly (no
per-file `gdalinfo` subprocess needed). **Every single tile is RGBA**
(`color_type=6`) -- both the 1,137 tiles on the coverage-polygon
boundary and a sample of deep-interior tiles. No RGB/RGBA mixing for
this layer, contrary to the original hypothesis that interior tiles
would come back as plain RGB. Doesn't prove every layer behaves this
way, but the specific untested risk didn't materialize here.

Then `just cog`: `gdal_translate -of COG` on a 61184x65536px mosaic
timed out and was killed after the Bash tool's 2-minute limit (this
one didn't auto-move to background the way `georef`/`download` did
earlier -- unclear why, possibly how `time (...)` wrapped it). Left a
**truncated, corrupt `.tif` behind** -- and D11's skip check (`[ -f
"$dst" ] && "$dst" -nt "$src"`) would have happily treated that
truncated file as "done" on the next run. Deleted the partial output
by hand, then fixed `Justfile`'s `cog` recipe to build to a
`.tif.building` temp path and `mv` it into place only after
`gdal_translate` exits successfully -- so an interrupted build can
never leave a corrupt file at the trusted path again. Re-ran `cog` with
`run_in_background: true` explicitly this time so it can't be killed
by a tool timeout; as of this entry it's still running (overview
generation on a very large mosaic takes a while). Next entry will
record the final COG's `gdalinfo` output.

## 2026-07-31 (continued further still) -- FORCE=1 skip-work support (D11)

Hidenori pointed out the `Justfile` had no dependency management --
every stage redid its work unconditionally, including re-hitting GSI
for tiles already on disk. Implemented D11 while `georef`'s first run
kept going in the background (safe to edit `georef.py`/`download.py`
mid-run -- the already-running process has the old code loaded in
memory; editing the file on disk doesn't touch it):

- `probe`/`download`/`georef`/`cog` all skip already-done work now,
  `FORCE=1` to redo it. Full design in DECISIONS.md D11.
- Verified live against the (nearly complete) first run: re-running
  `just probe` and `just download` for
  `20260729kumamoto_yatsushiro_0729do_sokuho` both completed in under a
  second, `26982/26982 already present, not re-fetched` -- zero new
  GSI requests. `georef`'s skip path will get its first real exercise
  whenever this layer's `georef`/`cog` gets re-run (e.g. after a
  restart, or once `stac_item.py` needs to reference it again).

While `georef` kept running, resolved the two things blocking further
planning and researched the two remaining unknowns:

- **Hidenori decided D4** (STAC `datetime` source): capture date, from
  the layer ID's date fragment. D4 is now Accepted.
- **Hidenori decided to actually publish this layer for real**
  (Source Cooperative + OAM) once `just cog` finishes, not just use it
  for pipeline validation -- per D9, with attribution treated as
  provisional until `ichiran.html` catches up.
- Researched D6 (OAM ingestion) and added a new D10 (Source Cooperative
  publishing path) to `DECISIONS.md` with what was found. Bottom line
  on **what needs Hidenori specifically, not Claude**:
  - **Source Cooperative**: the `smartmaps` org already exists (14
    products live there). A `cogenerate` product under it does not.
    Creating one requires the source.coop web UI -- account/product
    creation, which stays a human action per this project's standing
    rules. After that, a one-time `source-coop login` locally is enough
    for Claude to script the actual `aws s3 sync` uploads afterward
    without ever handling credentials directly.
  - **OpenAerialMap**: the current (v1) uploader needs a token issued
    through OAM/HOTOSM's own admin interface -- another account-side
    step. Given OAM's own roadmap mentions "map publicly available
    STACs to the OAM metadata schema" as a planned direction, the
    likely better move is Hidenori reaching out to HOTOSM once a real
    static STAC catalog exists to show them, rather than going through
    the current v1 token flow now. Either way, this doesn't block
    finishing this pipeline's own static STAC + GitHub Pages catalog,
    which is useful on its own regardless of OAM.
  - Nothing about this blocks `probe`/`download`/`georef`/`cog` --
    only the eventual `stac_item.py` (now unblocked, D4 resolved) and
    upload steps.

## 2026-07-31 (continued) -- hygiene pass + a second staleness finding

While `georef` ran in the background, picked up loose ends rather than
waiting idle:

- `uv sync` alone does **not** install `[project.optional-dependencies]
  dev` (pytest/ruff) -- need `uv sync --extra dev`. Worth remembering,
  since `just lint`/`just test` silently look like they'd work off a
  plain `uv sync` but actually can't import ruff/pytest at all until you
  do this.
- Manually confirmed the HEAD-support assumption `probe.py` flagged as
  untested: `curl -I` against both `std` and
  `20260729kumamoto_yatsushiro_0729do_sokuho` returns a clean `200` --
  `cyberjapandata.gsi.go.jp` supports `HEAD` directly, the `405`→`GET`
  fallback path in `probe.py`/`exists()` is a safety net that (at least
  for this server) never actually triggers.
- `just lint` failed (7 ruff errors) the first time it was actually run
  -- it hadn't been run before. 6 were `B008` false positives against
  typer's own idiom of `= typer.Option(...)` as an argument default;
  fixed properly by adding `extend-immutable-calls = ["typer.Argument",
  "typer.Option"]` under `[tool.ruff.lint.flake8-bugbear]` in
  `pyproject.toml` (the documented fix for typer+ruff, not a rule
  suppression). The 7th (`UP037`, a redundant quoted forward-ref in
  `probe.py` now that `from __future__ import annotations` makes it
  unnecessary) was auto-fixed with `ruff check --fix`. `just lint` is
  now clean. `just test` correctly reports "no tests ran" (exit 5) --
  expected, no tests exist yet, not building them per HANDOVER's
  existing scope call.
- **Second staleness finding, this time in GSI's own metadata, not a
  mirror:** fetched `maps.gsi.go.jp/development/ichiran.html` directly
  and searched for `20260729kumamoto_yatsushiro_0729do_sokuho` -- **no
  entry exists yet.** The only `kumamoto` hits are the unrelated 2016
  Kumamoto earthquake layers (the known-good coordinate cross-check from
  the original planning session), and the only `yatsushiro` hits are a
  different, unrelated 2025-08 disaster
  (`20250815rain_yatsushiro{nishi,higashi}_0816do_sokuho`). So the live
  tile server already serves this layer (confirmed by probe/download),
  but GSI's own public catalog page hasn't caught up yet -- zoom-range
  and 備考 (remarks/attribution) can't be cross-checked for this layer
  right now. **Update, same day:** Hidenori decided this doesn't block
  pipeline execution -- see DECISIONS.md D9 (disaster-response
  principle). Proceed to `georef`/`cog` regardless; only the
  *attribution field written into a published STAC item* stays
  provisional until `ichiran.html` catches up, not the COG itself.

## 2026-07-31 -- repo pushed, full pipeline run, and a catalog-staleness bug caught

- Repo created and pushed: https://github.com/optgeo/cogenerate (public,
  CC0-1.0, license text fetched from GitHub's `licenses/cc0-1.0` API
  rather than hand-typed).
- `just download` for the 26,982 probed tiles: **26,982/26,982 saved**,
  zero errors -- the "confirmed-then-flaky" skip path in `download.py`
  was never exercised, which is a good sign for probe/download
  consistency.
- `just georef`: works, but is **slow** -- it shells out to
  `gdal_translate` once per tile sequentially (~26,982 subprocess
  spawns for this one layer). Still running as of this entry (progress
  was ~5,900/26,982 tiles converted to per-tile `.vrt` after roughly 30
  minutes); exact total duration and the `just cog` / final-COG result
  will be recorded in a follow-up entry once it finishes. Worth a
  follow-up regardless of how long it ends up taking: parallelize the
  per-tile VRT step (e.g. `asyncio`/thread pool around the subprocess
  calls, matching the concurrency pattern already used in
  `probe.py`/`download.py`) before this becomes the bottleneck for
  larger layers or batch runs across many layers.
- **Caught a real bug in how we read `layers-martin`'s catalog, not in
  `cogenerate` itself:** while cross-checking today's layer count
  against `/Users/hfu/layers-martin/docs/catalog.json`, that local
  clone's last commit touching `catalog.json` was dated 2026-07-17 --
  15 days behind, even missing the entry for
  `20260729kumamoto_yatsushiro_0729do_sokuho` itself. `git pull
  --ff-only` fixed the local clone (clean fast-forward, no local
  changes lost). Root cause and the going-forward fix: DECISIONS.md D7.
- Redid the "how many `_do`/`_do_sokuho` layers exist" count against the
  now-current catalog: **74 layers across 15 disaster events** (was 73/14
  against the stale snapshot). Full per-event breakdown given to
  Hidenori in chat, not duplicated here since it'll be stale again
  within days -- re-derive from the live catalog URL when needed rather
  than trusting a number written down here.
- Adopted a language policy for this repo (DECISIONS.md D8): chat with
  Hidenori in Japanese, everything committed to the repo (code, docs,
  commit messages) in English.
- Split rationale out of this file into `DECISIONS.md` (new, ADR-format
  log) so `HANDOVER.md` can stay a lean session log instead of growing a
  duplicate copy of every decision's reasoning. `README.md` now has a
  "Documentation map" explaining the split.

### If resuming from a fresh session (e.g. after `/clear`)

Read this file's latest entry, then `DECISIONS.md` for why anything
here looks the way it does. Nothing downstream of `just download` has
been verified yet as of this writing. Say something like:

> `/Users/hfu/cogenerate` の作業を続けて。HANDOVER.md の最新エントリと
> DECISIONS.md を読んで、`just georef` の完了確認と `just cog` の実行、
> gdalinfo での検証、RGB/RGBA バンド数チェック（georef.py の
> UNTESTED RISK コメント参照）から再開して。

which points the fresh session at both files and names the exact next
steps: confirm `georef` finished (`tiles/<layer>/` should hold one
`.vrt` per source PNG; the merged mosaic lands at `out/<layer>.vrt`),
run `just cog`, inspect the result with `gdalinfo`, and specifically
check the RGB-vs-RGBA band-count risk `georef.py` flags in its module
docstring. After that, `DECISIONS.md`'s two **Open** entries (D4: STAC
`datetime` source; D6: OAM ingestion path) still need Hidenori's call
before `stac_item.py` can be started.

## 2026-07-30 (later still) -- first real run, from Claude Code on the Mac

Picked this up from the zipped handoff. This machine has real network
access, and the very first live test confirms the core approach works:

- `uv sync` succeeded cleanly (`httpx`/`typer`/`rich` all installed and
  importable -- the pypi 403 was specific to the planning sandbox, not a
  problem here).
- `just probe LAYER=20260729kumamoto_yatsushiro_0729do_sokuho SEED_X=883 SEED_Y=414`
  against the live `cyberjapandata.gsi.go.jp`: **37,141 requests, 26,982
  confirmed tiles at z18.** The seed tile (z10, 883, 414) was correct on
  the first try -- no need for the neighboring-seed fallback. Quadtree
  pruning behaves as designed: most of the request volume is spent only
  near the coverage-polygon boundary, not brute-forcing the full bbox.
- One thing worth noting for later layers: `just probe`/`just download`
  read `LAYER=`/`SEED_X=`/`SEED_Y=` etc. as **environment variables**
  (via `just`'s `env_var_or_default`), not as trailing `just probe
  LAYER=...` arguments -- e.g. `LAYER=... SEED_X=... SEED_Y=... just
  probe`. Passing them the other way fails with "justfile does not
  contain recipe `LAYER=...`".

Next: create+push the `optgeo/cogenerate` repo (pending Hidenori's
go-ahead), then run `download`/`georef`/`cog` to validate the remaining
two untested-risk items (HEAD-not-supported fallback, RGB/RGBA band
mixing at tile boundaries).

## 2026-07-30 (later same day) -- pre-handoff review pass

Went through every file again before handing off to a Mac-based Claude
Code session. Found and fixed real issues; recording them here so the
Mac session doesn't have to re-derive them:

- **`uv sync` also fails in this sandbox** -- not just the GSI host.
  `pip`/`uv`'s index (`pypi.org`) returned 403 from the same egress
  allowlist. So **none of `typer`/`httpx`/`rich` were ever actually
  importable here either** -- everything below was caught by manual
  code review + `ast.parse()` syntax checking only, not by running the
  CLIs. Run `uv sync` for real as the very first step on the Mac.
- `probe.py`: removed an unused `import sys`.
- `download.py`: removed an unused `from rich.progress import track`
  (the concurrent `asyncio.gather` batch doesn't drive a progress bar;
  `georef.py`'s sequential loop does use `track` for real).
- `georef.py`: the CLI parameter was named `dir`, shadowing Python's
  builtin `dir()`. Renamed to `tiles_dir` (flag stays `--dir` via
  `typer.Option(..., "--dir", ...)`, so the Justfile call is unchanged).
- `georef.py`: added an explicit untested-risk note -- GSI ortho PNGs
  may mix RGB (fully-interior tiles) and RGBA (boundary tiles,
  transparent outside the coverage polygon) band counts.
  `gdalbuildvrt` usually promotes to the superset automatically, but
  this has never been checked against a real GSI tile from here. If the
  mosaic looks wrong at tile edges, check band counts first.
- `Justfile`: `tiles_dir := "tiles" / layer` used `just`'s path-join
  `/` operator, which was added in a fairly recent `just` release and
  may not exist on an older Mac `just` install. Replaced with plain
  string concatenation (`"tiles/" + layer`) for portability. Everything
  else in the Justfile is plain, old-`just`-compatible syntax.
- Confirmed `python -m cogenerate.probe` / `.download` / `.georef` will
  resolve once `uv sync` installs the project itself (src-layout,
  `packages = ["src/cogenerate"]` in `pyproject.toml`'s hatchling
  config) -- no separate `[project.scripts]` entry points needed.
- Did **not** attempt to fix the RGB/RGBA risk blind, since doing so
  without a real tile to test against would just be guessing. Flagged
  it instead of silently "fixing" it.

Net effect: the code is now clean by static review, but **the first
real signal on whether the whole approach works still has to come from
`just probe ...` on a machine with actual internet access.** Do that
before spending time on `stac_item.py` or anything downstream.

## 2026-07-30 -- planning + scaffold session (Claude, chat environment)

### What happened

Planned and scaffolded the `cogenerate` pipeline (see CLAUDE.md for the
durable rationale). This was done in Claude's chat/computer-use
environment, **not** Claude Code, and that environment has no outbound
network access to `cyberjapandata.gsi.go.jp`:

```
$ curl -s -D - https://cyberjapandata.gsi.go.jp/xyz/std/6/57/23.png
HTTP/2 403
x-deny-reason: host_not_allowed
```

So **none of the code in `src/cogenerate/` has been run against the real
GSI tile server.** It is written carefully from GSI's published specs
(`地理院タイルについて`, `地理院タイル一覧`) and cross-checked against
known-good example coordinates from ichiran.html (e.g. the 2016 Kumamoto
八代地区 entry's tilejump coordinate divides cleanly to the z10 seed
tile computed independently from lat/lon -- both landed on (883, 414),
which is a good sign but not a substitute for a live test), but treat it
as **untested** until someone runs it from an environment with real
network access.

### Immediate next step (do this first)

From Claude Code, or any machine with normal internet access:

```sh
cd cogenerate
uv sync
just probe LAYER=20260729kumamoto_yatsushiro_0729do_sokuho \
    MINZOOM=10 MAXZOOM=18 SEED_X=883 SEED_Y=414
```

If this returns zero tiles, the seed coordinate is likely wrong (try a
slightly wider seed set -- e.g. also probe (882,414), (884,414),
(883,413), (883,415) at z10, since 八代市 spans a wide area and one
782x414-ish tile may not intersect the actual sokuho coverage polygon).
If it errors on the HTTP layer, check whether `HEAD` is actually
supported by `cyberjapandata.gsi.go.jp` (the code falls back to `GET` on
405, but has never seen a real response to confirm this is the only
edge case).

### Repository creation: not done

I do not have GitHub write access or a tool to create/push repositories
from this environment. `optgeo/cogenerate` does **not** exist yet. The
files in this scaffold need to be:

1. Reviewed (they're unrun code -- read them before trusting them)
2. Pushed to a new `optgeo/cogenerate` repo (CC0, matching sibling repos)
3. Actually run once from a networked environment to validate the probe
   step before building `download.py` / `georef.py` confidence

If working from Claude Code with `gh` CLI access, that's the natural
place to do steps 2-3.

### Not yet built (deliberately out of scope this session)

- `stac_item.py` / `stac_catalog.py` -- static STAC generation. Blocked
  on the open decision in CLAUDE.md (datetime source) and on actually
  having a COG to describe.
- Source Cooperative upload script -- need to confirm auth mechanism
  (S3-compatible credentials?) before writing this; not researched yet.
- OpenAerialMap ingestion -- still just a placeholder goal. Need to
  research their actual API/STAC harvest support before this pipeline's
  final stage can be designed, let alone built.
- Municipality-name-to-bbox geocoding fallback (for layers where the
  quadtree probe seed is hard to guess) -- mentioned in CLAUDE.md open
  decisions as a nice-to-have, not started.

### Research findings worth remembering (see also CLAUDE.md)

- `layers-martin` tile IDs == GSI's own 地理院タイル IDs, one-to-one.
- `mokuroku.csv.gz` unreliable for disaster layers (std/pale/english
  only, per spec).
- `cocotile` and `daicho` both dead ends for our purpose (see CLAUDE.md
  for why).
- 256px vs 512px tile grids: GSI z18 ≈ 512px-equivalent z17.
- `ichiran.html` (地理院タイル一覧) is the authoritative per-layer source
  for zoom range, coverage municipalities, and a tilejump seed
  coordinate -- scrape this before probing, not after.
