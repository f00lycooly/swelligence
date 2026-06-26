# Spot card redesign — medallion selector + graphical kit + space fillers

**Date:** 2026-06-26
**Status:** Design — pending implementation plan
**Related beads:** `swelligence-c1v` (v1 epic), `swelligence-c1v.24` (expose now/week detail as attributes), `swelligence-slh` (safety markers — future), `swelligence-48w.1` (confidence — future)

## Context

A frontend-design review of the live Lovelace `spot` card (`custom_components/swelligence/frontend/swelligence-card.js`) found three problems:

1. **The wing/kite-size recommendation is computed but never shown on this card.** `sizing.py` produces a quiver-aware `KitRecommendation` (ideal size from rider weight ÷ wind, nearest owned size, a `power` verdict, and a `factor` that already blends into the score via `blend_kit`). It surfaces in `podium`/`timeline` modes and on entity attributes, but the `spot` card's data source — `_spot_detail()` in `__init__.py` — omits kit from each sport's `now` block, so the hero has nothing to render.
2. **Redundancy + wasted space.** The sport-selector pills (`_pills`) and the hero score ring (`_selNow`/`_selWeek`) are separate stacked blocks that print the same score twice. The detail row is left-heavy with dead mid-row space, and the left column has a gap below the tide module in NOW view.
3. **Under-graphical.** The card leans on text where the subject (marine/wind sports) rewards graphical, colour-coded instruments.

This redesign consolidates the selector and hero into one **medallion** element, adds a **graphical colour-coded kit gauge**, and fills the dead space with high-value, data-backed modules. It follows the project's thin-renderer rule: the integration produces ready-to-render data points; the card only renders.

## Decisions (agreed via visual companion)

- **Layout A — medallion ring-row selector.** Each sport is a score-ring with its sport SVG icon *inside* it; the active sport's ring is outlined in the accent colour. Tapping a medallion selects that sport. This replaces both `_pills` and the separate `_selNow`/`_selWeek` hero.
- **Arc-gauge kit indicator.** A small arc gauge (matching the score-ring's gauge language) shows the recommended rig size, needle swept by power match, **colour-coded**:
  - 🟢 Green = suitable (ideal power)
  - 🟠 Orange = underpowered
  - 🔴 Red = overpowered
  - ⚪ Grey = not suitable (no kit in quiver / sport not sized)
- **Detail card** (active sport): sport label + verdict + best window on the left; arc-gauge kit on the right; **limiting-factor line + mini factor bars** fill the mid-row dead space.
- **Left-column gap:** add a **daylight / session arc** (sun arc + "light remaining") now; **reserve the slot for the future Safety strip** (`swelligence-slh`). Do not stack multiple widgets — one confident occupant.
- **Wind-direction compass on the map** (option B). A compass dial + needle overlaid on the map hero: needle points by `wind_dir_deg`, dial has an N marker, and the needle is **colour-coded by the active sport's direction suitability** (`now.factors.direction`): green favourable / amber marginal / red onshore-wrong / grey not-configured. The needle re-colours when you switch sports. Keep the small "from SW · NN kn" chip in the corner as the precise readout. This replaces the wind *text* currently duplicated in the metrics strip with a graphic, earning the map's space. (The shaded shore-line upgrade — literal on/offshore — is the future `slh.6` enhancement; the compass stays and the shore line is added underneath.)

## Scope — in

### 1. Integration: feed kit + daylight into the spot-detail `now` payload
File: `custom_components/swelligence/__init__.py`, function `_spot_detail()`.

- In the `for sport, res in data.results.items()` loop, `res.kit` (a `KitRecommendation`) is already available. Add a `kit` key to each sport's `now` block when `res.kit` is present and `res.kit.power != POWER_NA`:
  ```python
  "kit": {
      "rig_m2": res.kit.owned_size_m2,
      "ideal_m2": res.kit.ideal_size_m2,
      "power": res.kit.power,          # ideal | underpowered | overpowered | no_kit
  } if res.kit and res.kit.power != POWER_NA else None
  ```
- Add a spot-level `daylight` block derived from `forecast.daily_sun` for today, now-anchored:
  ```python
  "daylight": {"sunrise": "...", "sunset": "...", "remaining_min": <int|None>}
  ```
  The remaining-minutes computation is pure — put it in `forecast.py` (e.g. `daylight_remaining(forecast, now)`) so it is unit-testable in `tests/` without HA, mirroring the existing `_in_daylight` helper.

> Note: hourly slots already carry `kit_rig_m2`/`kit_ideal_m2`/`kit_power` (see `forecast.py`); only the `now` block and the new `daylight` block are missing.

### 2. Card: medallion ring-row selector (layout A)
File: `frontend/swelligence-card.js`.

- Replace `_pills()` + `_selNow()`/`_selWeek()` with:
  - `_medallions(sportsAll, active, view)` — the ring-row. Each medallion reuses the existing `_ring()` SVG for visual consistency with the score gauge, with the sport icon (`ICON(sport)`) and score inside; active ring outlined; `data-act="sport"` for tap handling (existing handler at the `sport` action already works).
  - `_detail(sp, view)` — the detail card: `sp.label` + verdict + best window, plus `_kitArc(sp.now.kit)` on the right, plus the limiting-factor line and `_factors(sp.now)` bars.
- `_kitArc(kit)` — new SVG arc-gauge component. Needle angle from size within the rider's range (or simply from `power`); fill + icon stroke coloured by a power→colour map (`ideal→good`, `underpowered→amber`, `overpowered→poor`, `no_kit→dim`). Renders a grey "—" state when `kit` is null.
- Limiting-factor line — derive from `sp.now.reasons` (show the first/limiting reason); fall back to the lowest-scoring entry in `sp.now.factors` if `reasons` is empty.
- Reuse the existing `_factors()` for the mini bars (already implemented).

### 3. Card: left-column daylight arc (NOW view)
File: `frontend/swelligence-card.js`.

- Add `_daylight(d)` rendering the sun arc + remaining-time from the new `d.daylight` payload, placed in the left column after `_tideModule(d)` in NOW view. Leave the slot composable so the future safety strip can sit alongside/above it.

### 4. Card: wind-direction compass on the map hero
File: `frontend/swelligence-card.js`, function `_mapHero()`.

- Overlay an SVG compass dial + needle on the map. The needle rotates to `c.wind_dir_deg` (a `from` bearing; render so the dial reads as "wind from X"), with an N marker on the dial.
- Colour the needle from the **active sport's** direction factor (`sp.now.factors.direction`) via the same factor→colour mapping used elsewhere (green/amber/red); grey when `direction` is `not_configured`/absent. Because it depends on the selected sport, `_mapHero` (or the needle bit) must receive the active sport so it re-colours on sport change.
- Keep the existing corner chip ("Wind from SW · 12 kn") as the precise readout; drop the now-redundant wind text only if it visually clashes.
- Structure the overlay so the future `slh.6` shore-line can be added beneath the compass without reworking it.

## Scope — out (follow-up beads)

- **Safety flags strip** — first-class output; belongs to epic `swelligence-slh`. The left-column slot is reserved for it.
- **Confidence badge** — dormant until `swelligence-48w.1` re-sources model agreement.
- **Wetsuit recommendation** — `water_temp_c` exists; needs a small temp→thickness mapping. New bead.
- **Map shore-line (literal on/offshore)** — the shaded coastline under the wind compass; delivers true onshore/offshore rather than colour-implied. Needs shore orientation from `swelligence-slh.6`. (The wind compass itself is now in scope — see §4.)
- **Sport SVG icon rework** — the kite glyph reads poorly small. Separate bead.
- Collapsing the duplicated wind-on-map vs wind-metric, and null-tile de-emphasis — minor polish, can ride along or be separate.

## Conventions / constraints

- **Thin renderer:** all new semantics (kit fields, daylight remaining) are produced by the integration as data points; the card only formats. No new derivation in card JS beyond layout/colour mapping.
- **Pure logic stays pure:** the daylight-remaining helper goes in `forecast.py` (no `homeassistant` import) and is tested in `tests/`. `__init__.py` is already HA-glue and guarded by `tests_ha/test_ha_guard.py` (no new module to register there unless a new HA-touching file is added).
- **Units unchanged:** sizes in m², knots/metres/°C elsewhere. Unknown = `None`, never 0 — the grey kit state and dimmed null tiles reflect this.
- Card is dependency-free vanilla JS, bundled and auto-served; cache-busted by manifest version.

## Verification

1. **Pure suite:** `pytest` — add a unit test for the new `daylight_remaining` helper in `tests/`.
2. **Kit-in-payload:** add/extend a test asserting `_spot_detail()` includes `now.kit` (rig/ideal/power) for a sized sport with a quiver, and `None` for an unsized sport / empty quiver.
3. **HA guard:** `pytest tests_ha -o asyncio_mode=auto` stays green.
4. **Manual, in the live card (read-only deploy to a temp dashboard):** confirm the medallion row selects sports, the arc gauge shows the correct colour for suitable/under/over/no-kit, the limiting-factor line matches `reasons`, and the daylight arc renders in NOW view. Use the visual companion / browser screenshots for the design check.
5. **No regression** to WEEK view (week reuses the medallion row with peak scores; arc-gauge/limiting-factor are NOW-view concerns).
