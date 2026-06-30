# Kit-sizing calibration data (manufacturer + industry charts)

Collected 2026-06-30 to recalibrate `sizing.py` (`KITE_CONSTANT`, `WING_CONSTANT`)
against real published wind-range data instead of hand-tuned anchors.

Model under test: `ideal_size_m² = constant · rider_weight_kg / wind_kn` (linear,
inverse-wind). Current constants: kite **2.25**, wing **1.0**.

For each chart, the implied linear constant is `c = size · wind / weight`, taking
the **midpoint** of each published wind range as the "ideal wind" for that size.

---

## KITES

### Cabrinha Moto X Lite (manufacturer, 75 kg rider)
Source: cabrinha.com/pages/wind-weight-chart-html

| Size m² | Wind kn | mid | c = size·mid/75 |
|---|---|---|---|
| 6 | 21–40 | 30.5 | 2.44 |
| 7 | 19–38 | 28.5 | 2.66 |
| 8 | 17–36 | 26.5 | 2.83 |
| 9 | 15–34 | 24.5 | 2.94 |
| 10 | 13–32 | 22.5 | 3.00 |
| 11 | 11–30 | 20.5 | 3.01 |
| 12 | 9–25 | 17.0 | 2.72 |

Mean c ≈ **2.8** (midpoints of wide survival ranges skew high).

### kitesurftheworld.com grid (industry, recommended size per wind bin)
70–80 kg row, wind-bin mid → size mid:

| Wind kn (mid) | Size m² | c (W=75) |
|---|---|---|
| 15 | 13.5 | 2.70 |
| 19 | 11.5 | 2.91 |
| 23 | 9.5 | 2.91 |
| 26 | 7.5 | 2.60 |
| 33.5 | 5.5 | 2.46 |

Mean c ≈ **2.7**.

### windance.com twin-tip freeride (industry, 75–85 kg)
| Wind kn (mid) | Size m² (mid) | c (W=80) |
|---|---|---|
| 13.5 | 15 | 2.53 |
| 17.5 | 11.5 | 2.52 |
| 22 | 9.5 | 2.61 |
| 27.5 | 7.5 | 2.58 |

Mean c ≈ **2.56** (remarkably consistent → this chart is near-linear).

### thekitespot.com calculators (physics-based, 1/wind² law)
`size = weight / wind² × K`, K = 2.0 (kitesurf) / 2.2 (independent). Numbers fit
an exponent ≈ 1.7–2.0 — steeper than any manufacturer chart actually prints.

### Ozone Edge (anecdotal, forum, ~80 kg): 11 m @ 15–25, 9 m @ 20–30.

**Kite verdict:** real charts cluster at linear **c ≈ 2.5–2.8, central ~2.6**.
Current 2.25 under-sizes by ~13 %.

---

## WINGS

### Cabrinha wings (manufacturer, 75 kg rider)
Source: cabrinha.com/pages/wind-weight-chart-wings

| Size m² | Wind kn | mid | c = size·mid/75 |
|---|---|---|---|
| 1.0 | 30–50 | 40 | 0.53 |
| 1.3 | 28–47 | 37.5 | 0.65 |
| 1.6 | 25–42 | 33.5 | 0.71 |
| 2.0 | 22–37 | 29.5 | 0.79 |
| 3.0 | 18–32 | 25 | 1.00 |
| 4.0 | 13–27 | 20 | 1.07 |
| 5.0 | 11–26 | 18.5 | 1.23 |

c rises with size (small wings need disproportionately more wind). Fits a
**square** law well (k = size·wind²/75 ≈ 21–24, near-constant). Typical 3–5 m
band: c ≈ 1.0–1.2.

### Duotone Unit 2025 (manufacturer)
Source: mackiteboarding.com/2025-duotone-unit-wing (weight not stated; ~78 kg typ.)

| Size m² | Wind kn | mid | c = size·mid/78 |
|---|---|---|---|
| 2.0 | 27–45 | 36 | 0.92 |
| 3.0 | 19–37 | 28 | 1.08 |
| 4.0 | 14–30 | 22 | 1.13 |
| 5.0 | 10–25 | 17.5 | 1.12 |
| 6.0 | 8–20 | 14 | 1.08 |
| 6.5 | 7–18 | 12.5 | 1.04 |

Strongly **linear**, c ≈ **1.05–1.13** across 3–6.5 m (only the tiny 2 m deviates).
Square law over-corrects here (k falls 30→15).

### windance.com wing chart (industry)
>75 kg rider, wind-bin mid → size mid: c ≈ 1.0–1.2 across the band.

**Wing verdict:** the two manufacturers disagree on curvature (Cabrinha ≈ square,
Duotone ≈ linear), but both pass through **linear c ≈ 1.1** in the normal 3–5 m /
12–22 kn riding band. Current 1.0 under-sizes by ~10 %.

---

## Recommendation

Keep the linear model (practical charts are ~linear, n≈1–1.2; pure 1/wind² over-
corrects vs. what manufacturers print), recalibrate constants:

| Constant | Current | Proposed | Basis |
|---|---|---|---|
| `KITE_CONSTANT` | 2.25 | **2.6** | Cabrinha ~2.8, kitesurftheworld ~2.7, windance ~2.56 |
| `WING_CONSTANT` | 1.0 | **1.1** | Duotone ~1.1, Cabrinha mid-band ~1.1, windance ~1.1 |

Both bumps make the model recommend slightly bigger kit for a given wind (current
model under-sizes). Turn the tables above into a `test_sizing.py` fixture so the
fit is regression-locked. A tunable exponent (`size = c·W/wind^n`, n≈1.0–1.3) is a
possible strategic follow-up but the data does not clearly justify leaving linear.
</content>
</invoke>
