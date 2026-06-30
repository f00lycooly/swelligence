# Scoring-weights review vs. industry "good session" best practices

Date 2026-06-30 (bead `swelligence-mx7.2`). Audits the per-sport factor weights
and wind/wave windows in `sports.py` against published industry definitions of
what a *good session* looks like. Sources at the bottom.

**Verdict:** the weights are mostly well-aligned. The real gaps are not weight
values but two missing/under-modelled *factors* — wind **steadiness** (gust
spread) and the **offshore-wind safety asymmetry** — plus two minor window
calibrations.

---

## What the industry says is a "good session"

| Sport | Headline drivers of a good session | Industry notes |
|---|---|---|
| **Surf** | wave size + **offshore wind** + **long-period groundswell** + clean sea | period: 8 s normal, 11 s good, **14 s+ great**; less wind = cleaner faces |
| **Kite / Wing / Windsurf** | enough **steady** wind; **side / side-onshore** direction; manageable chop | **gusty wind is the #1 quality+safety killer** after strength; offshore is *dangerous* (blown out to sea); windsurf 18 kn "perfect", 25+ "getting tricky" |
| **Sea swim** | **flat + warm + clean**; low wind | offshore wind *carries swimmers out* (danger); events cancelled ~18 mph (~15 kn); 2–3 ft (0.6–0.9 m) waves already hazardous |
| **SUP** | **flat, low wind** | calm water dominates |
| **Sailing** | steady wind, direction-tolerant | dinghy freeride works across most directions |

---

## Per-sport alignment

| Sport | Current weights (wind/dir/wave/swell/clean/gust/temp) | Aligned? |
|---|---|---|
| Surf | 0.6 / 0.8 / **1.0** / 0.7 / 0.5 / 0.3 / 0.2 | ✅ matches "size + offshore + groundswell + clean" |
| Kitesurf | **1.0** / 0.7 / 0.5 / – / – / 0.3 / 0.2 | ⚠️ steadiness under-modelled (see Gap 1) |
| Wingfoil | **1.0** / 0.6 / 0.5 / – / – / 0.3 / 0.2 | ⚠️ same |
| Windsurf | **1.0** / 0.5 / 0.5 / – / – / 0.3 / 0.2 | ⚠️ same + `wind_max` high (Gap 3) |
| Sea swim | 0.7 / 0.1 / **1.0** / – / – / 0.3 / **1.0** | ✅ flat+warm; ⚠️ offshore safety (Gap 2) |
| SUP | 0.8 / 0.5 / 0.8 / – / – / 0.3 / 0.2 | ✅ calm-water aligned |
| Sailing | **1.0** / 0.3 / 0.5 / – / – / 0.3 / 0.2 | ✅ aligned |
| Wakeboard (in/sea) | ~1.0 / 0.1–0.2 / ~1.0 / – / – / 0.3 / 0.2 | ✅ aligned |

---

## Gaps & recommendations

### Gap 1 — Wind **steadiness** is under-modelled (highest value)
Every kite/wing/windsurf source ranks *steady vs gusty* as the top quality and
safety factor after raw strength. But our `gust` factor only penalises gust
**magnitude above `gust_max_kn`** (weight 0.3, graduated). It does **not** measure
the gust-vs-lull **spread** (`gust − mean`, or `gust/mean`), which *is*
"gustiness". A 20 kn-steady day and a 14-gusting-26 day can score identically.
- **Strategic fix:** add a steadiness factor from the data we already carry
  (`wind_speed_kn` + `wind_gust_kn`): penalise large `gust/mean` ratios.
  Surface it as a factor for wind sports (kite/wing/windsurf/sailing) and as a
  `gusty`-style safety flag. Prefer this over merely bumping the gust weight —
  the weight can't fix a factor that measures the wrong thing.
- Bead: `swelligence-mx7.3`.

### Gap 2 — Offshore-wind **safety asymmetry** not modelled
Offshore wind is *good* for surf but *dangerous* for kite / wing / SUP / swim
(can't self-rescue / carried out to sea). Today `direction` is a symmetric
"preferred sectors" **quality** factor; nothing flags offshore as a hazard for
the sports where it's dangerous. The safety-flag
framework already exists (`swelligence-slh.2`, closed) but offshore detection
needs shore-orientation, which is owned by the open bead `swelligence-slh.6`
("AI-inferred shore orientation + onshore/offshore classification"). See also
`docs/scoring.md` §7. **Not a weights problem** — cross-linked, not duplicated.

### Gap 3 — Windsurf `wind_max_kn = 40` overstates high-wind suitability
Industry: 18 kn "perfect", 25 kn+ "getting tricky / blown out" for freeride
(40 kn is wave-sailor territory). For a general "good session" the upper window
is too generous, so 35–40 kn still reads near-suitable. Consider `wind_max ≈ 35`,
`gust_max ≈ 40`. **Requires recalibration** (`validate_spots.py` +
`analyze_history.py`). Bead: `swelligence-mx7.4`.

### Gap 4 (minor) — Surf `swell_period_ideal_s = 11` flattens "great" groundswell
Industry calls 11 s *good* and **14 s+ *great***. At ideal=11 the period factor
saturates to 1.0 by 11 s, so a 14 s+ epic groundswell scores the same as a merely
good 11 s. Consider raising `swell_period_ideal_s` to ~13–14 so true groundswell
is distinguished. **Requires recalibration.** Folded into `swelligence-mx7.4`.

---

## Not changed (deliberately)
Surf, SUP, sea-swim (quality), sailing and wakeboard weights match the industry
picture and need no change. No weight is altered in this review commit — per the
project convention, any weight/window edit must be paired with a recalibration
run, so the changes are filed as beads (mx7.3 / mx7.4) rather than applied blind.

## Sources
- Surf: en.wikipedia.org/wiki/Surf_forecasting; windy.app surf-forecast guide;
  surfspotguide.com onshore-vs-offshore.
- Kite: kitestars.com wind guide; thekitespot.com wind directions;
  mackiteboarding.com onshore-vs-sideshore.
- Windsurf: windsurf.co.uk (Peter Hart); boards.co.uk windsurfing-weather;
  en.wikipedia.org/wiki/Windsurfing.
- Sea swim: swimming.org open-water; outdoorswimmer.com wind; seaswimcornwall.co.uk.
