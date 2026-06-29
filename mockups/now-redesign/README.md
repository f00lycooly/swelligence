# NOW-view redesign study

Synced from the Claude Design project **"Swelligence Spot Detail"**
(`c0f84bd3-3fe1-4017-bd03-214650747649`) on 2026-06-29. These are mockups /
design studies — the source of truth for the shipped card remains
`custom_components/swelligence/frontend/swelligence-card.js`.

## Files

| File | What it is |
|------|------------|
| `spot-detail-now-cardA.html` | **The developed design** — the NOW view as an interactive *scrubber*. Self-contained (data harness + helpers + controller inline). Tap/drag the 24h outlook to scrub every element (map compass, suitability ring, kit arc, factor bars, sun/moon marker) to that hour. |
| `now-timeline-3-approaches.html` | Side-by-side study of three ways to make the 24h outlook interactive: **A Scrubber** (chosen), **B Filmstrip**, **C Windows**. Loads the two `swell-*.js` modules below. |
| `swell-data.js` | Shared data harness + helpers (`window.SW`): verdict palette, sport icons, compass/ring/kit-arc renderers, map mosaic, and a small per-hour physical model (`SPORT_MODEL`) that turns a per-hour MET series → factor breakdown → score → kit. |
| `swell-variants.js` | The three timeline treatments (`bodyScrubber` / `bodyFilmstrip` / `bodyBlocks`) + shared chrome + the mount controller. |
| `spot-detail-shipped.html` | The **current shipped** Lovelace card embedded verbatim with dummy single-source data — the baseline the redesign departs from. |

## Key design change vs the shipped card

The shipped harness only kept a per-hour *score*, so the factor bars and kit arc
could only ever show "now" and the timeline was static. The redesign drives a
**per-hour MET series → factor breakdown → score → kit** through one model, so
scrubbing to any hour updates every element coherently. The production
`swelligence.get_spot_detail` already returns this per-hour shape.

The "Safety" cell is a placeholder (`conditions module`) — wiring it to the
existing weather-hazard / safety-gate data is a follow-up.

## To view

Open any `.html` directly in a browser. The `now-timeline-3-approaches.html`
expects `swell-data.js` and `swell-variants.js` alongside it (they are).
