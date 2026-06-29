# NOW-view scrubber redesign (bd swelligence-erf)

**Date:** 2026-06-29
**Bead:** `swelligence-erf` (depends on `swelligence-slh.2` ✓ merged; pulls in
`swelligence-0no.9` item 1)
**Design source:** `mockups/now-redesign/spot-detail-now-cardA.html` (the
developed "Card A" synced from Claude Design)
**Status:** design approved

## Problem

The shipped spot card's NOW view (`swelligence-card.js` `_spot()`) shows a
static detail panel for "now" plus a read-only hourly timeline. The factor bars
and kit arc only ever reflect the current hour; the 24h outlook can't answer
"what's it like at 4pm?" on a touch panel. The Card A redesign makes the outlook
**interactive**: tap/drag any hour and every element (suitability ring, wind
compass, kit arc, factor bars, Safety cell, sun marker) scrubs to that hour.

This needs per-hour data the payload doesn't yet expose, a Safety cell (now
possible — `safety_flags` landed in `slh.2`), and a correct hazard glyph
(`0no.9` item 1).

## Scope

Full Card A NOW-view layout, shipped in committable stages:

1. **Data layer** (pure) — surface the per-hour data the scrubber binds to.
2. **Card** — rework `_spot()` NOW view into the scrubber; Week view and all
   other modes unchanged.
3. **Panel mirror** — extend `flatten_detail` + `docs/panel-contract.md` so the
   ESPHome/LVGL wall panel can scrub too.

Out of scope: a JS test harness (the card is dependency-free vanilla JS with no
bundler/test rig today); the deferred safety flags (`slh.7`/`slh.8`) and
offshore-risk (`slh.6`); the rest of `0no.9` (items 2–8).

## A. Data layer (pure, test-first)

### A1. Per-hour factor breakdown
`score_point` already computes the 0–100 `factors` dict; it is surfaced on the
`now` payload but not on each hourly slot. Add `"factors": res.factors` to
`forecast._slot`. The scrubber's per-hour factor bars read this.

### A2. Hazard tier on the payload (0no.9 item 1)
Today `warnings` (a list of hazard kind codes) loses the tier, so the card can't
tell a hard-gated slot from a merely-poor one — it uses `now.suitable === false`
as a proxy, which wrongly shows the storm glyph on an already-poor slot with
only a warn-tier hazard.

- Add `hard_gated: bool` to `ScoreResult` (True when a **hard**-tier hazard
  capped this slot). Set it where the safety gate already runs in `score_point`
  (`hz.tier == _TIER_HARD`). Carried through `blend_kit`.
- Surface `hard_gated` on `forecast._slot` and the `detail` `now`/`hourly`
  payload (mirrors `warnings`).

Score math is unchanged — `hard_gated` only *reports* the cap that already
happens.

### A3. safety_flags per hour
Already landed in `slh.2` (`_slot` carries `safety_flags`; `detail` now does
too). The scrubber reads it per hour for the Safety cell. No new work.

## B. Card (`swelligence-card.js`)

Rework only the `mode === "spot"`, `view === "now"` path. The Week view
(`_dayRows`) and the `heatgrid` / `medallions` / `timeline` / `podium` modes are
untouched.

### Layout (from Card A)
- **Hero:** map mosaic + wind compass + wind-from readout (reuse existing
  `_compass`, map tiles).
- **Readout row, 3 cells:** suitability ring (reuse `_ring`); kit arc (reuse
  `_kitArc`); **Safety cell** (new).
- **Factor bars:** per-factor 0–100 bars for the focused hour.
- **Outlook:** the 24h bar timeline, draggable/tappable; a daylight lane with a
  sun/moon marker.

### Interaction: render / paint split
Mirrors the mockup controller so scrubbing is cheap and DOM-stable:
- `_render()` builds the NOW-view DOM once for the active spot/sport.
- `state.hour` (0 = NOW) + `_paintHour()` patch only the dynamic nodes:
  ring offset+colour, compass needle, kit arc, factor bar widths/colours,
  Safety cell, the wind/score readout, the selected-bar highlight, sun marker.
- Tap a bar or drag across the outlook → update `state.hour` → `_paintHour()`.
  Changing sport/spot/view → full `_render()`.
- State lives on the element instance; re-entrancy and HA re-renders reset to
  hour 0 (NOW), consistent with current behaviour.

### Safety cell
- Content: the focused hour's `safety_flags` (each `{kind,severity,message}`),
  most-severe first; empty → a calm "no flags" state.
- Glyph/severity: `hard_gated` → storm/danger glyph; else any `danger`
  safety_flag → danger; else `caution` flag → caution; else clear. This is the
  `0no.9` item-1 fix (glyph from tier, not the suitable proxy).

## C. Panel mirror (`detail.flatten_detail` + panel-contract.md)

Add per-sport, per-now flat attributes so the LVGL panel can render/scrub the
same data:
- `<sport>_now_safety` (delimited `kind:severity` or messages) and
  `<sport>_now_hard_gated`.
- Per-hour `factors` for the panel's scrub is large; the panel already receives
  the hourly CSV — extend only if the panel build needs it. Document whatever is
  added in `docs/panel-contract.md`, ordered to match `flatten_detail` emission
  (consistent with `0no.9` item 7's intent).

## Testing

- **Pure suite:** `_slot` carries `factors`; `score_point` sets `hard_gated`
  True under a hard hazard and False otherwise; `blend_kit` carries `hard_gated`;
  `detail` now/hourly carry `factors`/`hard_gated`; `flatten_detail` emits the
  new flat attrs (extend `tests/test_panel_detail.py`).
- **Card JS:** no automated rig; verify against
  `mockups/now-redesign/spot-detail-now-cardA.html` and a manual render. Keep
  the dynamic logic in small functions that match the mockup's `paint()` so
  behaviour is reviewable.

## Build / quality gates

`pytest` + `pytest tests_ha` green; hassfest unchanged; no manifest bump. The
card ships inside the integration and auto-registers (no separate deploy step).
