# HANDOVER.md

Session-by-session log: what happened, what's still running, what's
next. For *why* a choice was made, see `DECISIONS.md` (ADR log) instead
of looking for rationale here -- entries below link to the relevant
`D`-number rather than re-explaining it.

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
