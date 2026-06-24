# Project Instructions for AI Agents

This file provides instructions and context for AI coding agents working on this project.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:7510c1e2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->


## Build & Test

This is a Home Assistant custom integration (Python, no build step). Run the
pure-logic suite before any deploy or release:

```bash
pip install -r requirements-test.txt
pytest                              # pure-logic suite (stubs HA via tests/conftest.py)

# Optional / CI also runs:
pip install -r requirements-ha-test.txt
pytest tests_ha -o asyncio_mode=auto   # real-HA import + flow-schema guard
```

CI (`.github/workflows/validate.yml`) runs `pytest`, the HA guard, and hassfest
on every push/PR. There is no compile/bundle step for the integration; the
Lovelace card (`www/swelligence-card.js`) is dependency-free vanilla JS.

## Deployment

**Two distinct meanings — confirm which is intended.**

### 1. Deploy to the live Home Assistant (the usual "deploy")

The running HA instance lives at `/appdata/homeassistant/`. Deploying means
syncing the integration source into its `custom_components/` and restarting HA.
Deploy only from a clean, up-to-date `main` that has passed `pytest`.

```bash
cd /workspace/swelligence
git status --porcelain   # must be empty; deploy reflects committed code only
pytest                   # quality gate — green before deploy

# Sync the integration (exclude bytecode; --delete removes files dropped from the repo)
rsync -a --delete --exclude='__pycache__' \
  custom_components/swelligence/ /appdata/homeassistant/custom_components/swelligence/

# Clear stale bytecode so HA can't load an old .pyc
rm -rf /appdata/homeassistant/custom_components/swelligence/__pycache__ \
       /appdata/homeassistant/custom_components/swelligence/providers/__pycache__

# The Lovelace card is separate; only copy when www/swelligence-card.js changed:
# cp www/swelligence-card.js /appdata/homeassistant/www/swelligence-card.js
```

Then **verify**: `diff -rq custom_components/swelligence <dest>` (ignoring
`__pycache__`) should be clean, and `python3 -m py_compile` the deployed `.py`
files.

**The new code does NOT load until Home Assistant restarts** (Settings →
Developer Tools → Restart) or the integration is reloaded (Devices & Services →
Swelligence → ⋮ → Reload). **Do NOT restart HA without explicit confirmation** —
it interrupts a live home-automation system; that step is the user's call. New
config-flow options (e.g. cross-provider confidence toggles) only appear after a
restart, and the user must opt into them in the integration's options.

Notes:
- A file deploy does **not** bump `manifest.json` `version` — that's a release
  concern, kept separate (see below).
- `/appdata/homeassistant/` is its own git repo, so a bad deploy is recoverable
  there (`git diff` / `git checkout` inside that tree).

### 2. Cut a HACS release (version bump + tag)

For HACS consumers, "deploy" instead means bumping `custom_components/swelligence/
manifest.json` `version`, committing, and creating an annotated git tag +
Forgejo release. HACS reads tags/releases. Note: `hacs/action` store-validation
returns 401 against Forgejo (GitHub-only); run it on a GitHub mirror if needed.
Releases are public and hard to unpublish — confirm the version first.

## Architecture Overview

Home Assistant custom integration that turns marine/weather forecasts into a
0–100 **suitability score per (spot, sport)**. No build step; pure-Python logic
with HA-only glue at the edges.

**Data flow:** provider → normalised model → deterministic scorer → entities/LLM.

- **Providers** (`providers/`) — turn a coordinate into a normalised
  `SpotForecast` (list of `ForecastPoint`, plus `tide_events`). Two ABCs:
  `ForecastProvider` (wind/wave/swell/temp) and `TideProvider` (high/low events,
  an *overlay*). Registered in `PROVIDERS` / `TIDE_PROVIDERS` (`providers/__init__.py`).
- **Single forecast source:** **Open-Meteo only** (`open_meteo.py`, keyless).
  Stormglass and Windy were removed (epic `swelligence-48w`) — they repackaged
  the same public wave models Open-Meteo serves free. Open-Meteo is fetched for
  **all spots in two batched calls** via `OpenMeteoBatchLoader` (`batch.py`):
  comma-separated coords, results index-matched, TTL-cached + lock-deduped so one
  cycle of per-spot coordinators triggers a single fetch.
- **Tides — region-resolved overlay.** Each `TideProvider` *declares* its region
  (`covers(lat, lon)`) and `authority_rank`; `authority.resolve_overlay()` picks
  the best available source per coordinate. Stack: **UKHO** (UK, keyed),
  **NOAA CO-OPS** (US, keyless), **Open-Meteo modeled** (keyless, priority-0
  global fallback so every spot gets indicative tides with zero config).
- **Provider integration is a wiring point, not a rewrite.** Authority ranking is
  *derived from provider metadata* (no central table); adding a tide source =
  one leaf class declaring `covers()`/`authority_rank` + one registry line, with
  no coordinator/authority/config-flow edits. Removing one = delete + unregister.
- **Scoring** (`scoring.py` + `sports.py`) — deterministic, LLM-free. Full
  breakdown in [`docs/scoring.md`](docs/scoring.md). The LLM (`llm.py`) only
  *explains* the score; **never** let it silently override the deterministic result.
- **Coordinator** (`coordinator.py`) — one `SpotCoordinator` per spot: fetch
  (via batch loader) → water policy → tide gate → score each sport → optional LLM
  enrich. Entities (`sensor.py`, `binary_sensor.py`) expose the suitability score
  + `*_suitable`; raw values surface via the `get_forecast` service.
- **Confidence** (`confidence.py`) — model-agreement signal, provider-agnostic.
  Currently dormant (single source); to be re-sourced from Open-Meteo `models=`
  (bead `swelligence-48w.1`).

For the milestone history and module-level design, see [`docs/SCOPE.md`](docs/SCOPE.md).

## Conventions & Patterns

- **Pure logic, HA at the edges.** Scoring, sizing, tide, confidence, authority,
  overlay, domains are pure (no `homeassistant` import) so the unit suite runs
  without HA (`tests/`, stubbed via `tests/conftest.py`). HA-touching modules are
  guarded by `tests_ha/test_ha_guard.py` — **add any new module to its import
  list.**
- **Domains are constants, and legality is enforced.** Use the `WIND/WAVE/WATER/
  AIR/TIDE` constants from `providers/domains.py`, never bare strings. Anything
  keyed by domain (`provides_domains`, `authority_rank`, the authority maps) is
  validated by `assert_legal_domains` at the provider registry and at import —
  an illegal domain fails loudly rather than silently misrouting.
- **Normalised units:** speeds = **knots**, heights = **metres**, temps = **°C**,
  directions = **degrees ("from")**. Providers convert at the edge (m/s, km/h,
  Kelvin → these). Any field a provider can't supply is left `None` ("unknown",
  never 0).
- **Adding a provider** = a leaf class + a registry entry (+ `covers()`/
  `authority_rank` for tide authorities). Don't add provider-specific branches to
  the coordinator or authority.
- **Changing scoring profiles/weights requires recalibration** — re-run
  `validate_spots.py` + `analyze_history.py` (see the `sport-profiles…` bd memory).
- Beads (`bd`) is the task tracker; `bd remember` for durable notes. Research and
  design notes live under `mockups/research/` and `docs/`.
