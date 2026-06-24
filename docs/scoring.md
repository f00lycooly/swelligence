# Swelligence Scoring Reference

How a normalised forecast becomes a 0–100 suitability score per (spot, sport,
timestep). All of this is **deterministic and LLM-free** (`scoring.py`); the LLM
layer only explains the score, never overrides it.

Source of truth: `custom_components/swelligence/scoring.py`,
`sports.py` (profiles + weights), `tide.py` (tide gate), `sizing.py` (kit),
`confidence.py` (model agreement), `quality.py` (data-quality summary).

---

## 1. The pipeline (`score_point`)

```
ForecastPoint + SportProfile
        │
        ▼
┌─────────────────────────────────────────────┐
│ 1. Compute 6 factors, each → 0.0..1.0 or None │   wind, gust, direction,
│    (None = not scored / no data)              │   wave, swell, temp
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│ 2. Weighted mean of the *available* factors   │   score = 100 · Σ(fᵢ·wᵢ) / Σwᵢ
│    (None and weight≤0 dropped)                │   over factors that apply
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│ 3. HARD-FAIL cap: if wind OR wave factor == 0 │   score = min(score, 30)
│    → cap at 30 (gust is exempt — see §2)       │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│ 4. TIDE gate: score ·= tide_factor (0.3..1.0) │   wrong-tide spots capped,
│    if the spot is tide-dependent              │   never zeroed (floor 0.3)
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│ 5. (optional) KIT blend for kite/wing if the  │   score ·= 0.4 + 0.6·kit
│    rider has weight + quiver configured       │   (only when kit < 1.0)
└─────────────────────────────────────────────┘
        │
        ▼
   score → verdict band  +  suitable = score ≥ 55
```

The weighted **mean** (not sum) means a sport is scored only on the factors it
cares about and has data for — a missing field lowers nothing; it just drops out
of the denominator.

---

## 2. The six factors

Each returns `(factor 0..1 | None, note)`. `None` ⇒ excluded from the mean.

### Wind speed — `_wind_factor` (weight `weight_wind`)
A trapezoid over the sport's `[min, ideal, max]` knots window:

| Condition | Factor | Note |
|---|---|---|
| `speed < min` | `0.4 · speed/min` (ramp 0→0.4) | "under-powered" |
| `min ≤ speed ≤ ideal` | `0.6 → 1.0` linear | "{n}kn" |
| `ideal ≤ speed ≤ max` | `1.0 → 0.6` linear | "{n}kn" |
| `speed > max` | **0.0** | "too strong" → **hard-fail** |

### Gust — `_gust_factor` (weight `weight_gust`)
A *graduated* penalty (never a hard-fail):
- `gust ≤ gust_max` → `1.0`
- above → `1.0 − (gust − max) / (0.5·max)`, floored at 0. A gust 50 % over the
  ceiling reaches 0; slightly over just nudges the score.

### Wind direction — `_dir_factor` (weight `weight_dir`)
Smallest angular distance from the wind bearing to any preferred sector
(`wind_dirs`, per-spot offshore directions):
- `≤ 22.5°` (one sector) → `1.0`
- `≥ 90°` → `0.0` "wrong wind direction"
- between → linear taper. No `wind_dirs` set ⇒ `None` (direction-agnostic).

### Wave height — `_wave_factor` (weight `weight_wave`)
Two modes, chosen by whether `wave_ideal_m` is set:

**Waves-desired (surf):** `wave_ideal_m > 0`
| Condition | Factor | Note |
|---|---|---|
| `h < wave_min` | `0.5 · h/min` | "flat" |
| `min ≤ h ≤ ideal` | `0.6 → 1.0` | "{h}m" |
| `ideal ≤ h ≤ max` | `1.0 → 0.6` | "{h}m" |
| `h > wave_max` | **0.0** | "too big" → **hard-fail** |

**Flat-preferred (wind/flat sports):** `wave_ideal_m = None`, `wave_max_m` set
- `h ≤ 0.4·max` (comfort plateau) → `1.0`
- `0.4·max < h < max` → linear `1.0 → 0.0` ("choppy" past 0.7·max)
- `h ≥ max` → `0.0` "too choppy" → **hard-fail**

### Swell quality — `_swell_factor` (weight `weight_swell`, surf-type only)
Scores swell **quality**, not just height: `period × direction`.
- `f_period = clamp01((period − 4) / (ideal − 4))` — below ~4 s is wind-chop;
  long-period groundswell scores higher (`swell_period_ideal_s`, surf = 11 s).
- `f_dir` from the spot's `swell_dirs` window (gated **only** when the provider
  reports `swell_dir_deg`).
- `factor = f_period · f_dir` (or just `f_period` if no swell direction).
- `None` when the sport has no `swell_period_ideal_s` or no period data.

### Water temperature — `_temp_factor` (weight `weight_temp`)
- `t ≥ water_temp_min_c` → `1.0`
- below → `1.0 − deficit/6` (floored 0). Drives the sea-swim "cold water" penalty.

---

## 3. Per-sport profiles (`sports.py`)

Defaults (UK-calibrated; user-overridable per-spot). Wind/gust knots, wave metres.

| Sport | water | wind min/ideal/max | gust max | wave (min/ideal/max) | swell ideal | temp min | weights (wind/dir/wave/swell/gust/temp) |
|---|---|---|---|---|---|---|---|
| kitesurf | sea | 12/20/35 | 40 | –/–/3.0 (flat) | – | – | 1.0 / 0.7 / 0.5 / 0 / 0.3 / 0.2 |
| windsurf | sea | 12/22/40 | 45 | –/–/2.5 (flat) | – | – | 1.0 / 0.5 / 0.5 / 0 / 0.3 / 0.2 |
| wingfoil | sea | 10/16/33 | 40 | –/–/2.5 (flat) | – | – | 1.0 / 0.6 / 0.5 / 0 / 0.3 / 0.2 |
| **surf** | sea | 0/5/15 | 20 | 0.6/1.5/3.5 (desired) | 11 s | – | 0.6 / 0.8 / 1.0 / 0.7 / 0.3 / 0.2 |
| sup | any | 0/4/12 | 15 | –/–/0.5 (flat) | – | – | 0.8 / 0.5 / 0.8 / 0 / 0.3 / 0.2 |
| sailing | sea | 6/14/25 | 30 | –/–/2.0 (flat) | – | – | 1.0 / 0.3 / 0.5 / 0 / 0.3 / 0.2 |
| seaswim | sea | 0/2/12 | 16 | –/–/0.6 (flat) | – | 12 °C | 0.7 / 0.1 / 1.0 / 0 / 0.3 / 1.0 |
| wakeboard (inland) | inland | 0/3/12 | 16 | –/–/0.3 (flat) | – | – | 1.0 / 0.1 / 0.9 / 0 / 0.3 / 0.2 |
| wakeboard (sea) | sea | 0/4/14 | 18 | –/–/0.6 (flat) | – | – | 0.9 / 0.2 / 1.0 / 0 / 0.3 / 0.2 |

Read a row as: surf is mostly **wave (1.0) + direction (0.8, offshore) + swell
quality (0.7)** with light wind; wind sports are **wind-dominant (1.0)** with
chop only mildly penalised; sea-swim is **calm + warm** (wave 1.0, temp 1.0).

> **Calibration:** the profiles are tuned against real Open-Meteo data for the
> Christchurch spot set. **Re-run `validate_spots.py` + `analyze_history.py`
> after any profile/weight change** (see the `sport-profiles…` bd memory).

---

## 4. The gates and blends

### Hard-fail (cap 30)
If the **wind** or **wave** factor is exactly `0.0` (too strong, too big, too
choppy, dead-flat surf) the whole timestep caps at 30 ("marginal/poor") no matter
how good everything else is. Gusts are deliberately exempt — they only graduate.

### Tide gate (`tide.py`)
Tide-dependent spots (`CONF_TIDE_STATE` = high/low/mid) get a per-timestep
`tide_factor ∈ [0.3, 1.0]` precomputed by the coordinator from the resolved tide
events:
`factor = max(0.3, 1 − 0.3·(hours_from_target / window_h))`.
The score is multiplied by it — wrong tide caps the score (floor 30 % of
conditions), it never hard-zeros. `state = any`/no events ⇒ no gate.

### Kit blend (`blend_kit` + `sizing.py`, kite/wing only)
With rider weight + quiver configured: `ideal_size = const · weight / wind`
(kite 2.25, wing 1.0). The nearest owned size gives a power-match
`factor = 1 − deviation/0.40` (floor 0; "ideal" within ±12 %). When `factor < 1`,
`score ·= 0.4 + 0.6·factor` — a day you can't rig for reads marginal with kit
advice rather than vanishing. Other sports: neutral (no effect).

### Verdict bands & suitability
`≥85 epic · ≥70 great · ≥55 good · ≥35 marginal · else poor`.
The binary `*_suitable` sensor is `score ≥ 55`.

### Best window
`best_window` scans the next 24 h of timesteps and returns the highest-scoring
one (drives `best_in_hours` / the "best later today" hints).

---

## 5. Adjacent signals (not part of the 0–100 score)

- **Confidence** (`confidence.py`) — a separate 0..1 *model-agreement* signal
  from the spread across forecast models, weighted by the same factor weights.
  Currently **absent** (single-source) until it is re-sourced from Open-Meteo's
  multi-model `models=` request (bead `swelligence-48w.1`). It informs the LLM
  verdict's hedging, not the score.
- **Data quality** (`quality.py`) — a per-(spot, sport) summary of which source
  fed each domain, missing-data issues (no swell period, marine grid
  unavailable), and grid-cell distance. Surfaced as an attribute and in the LLM
  prompt; does not change the score.
- **Additional-detail fields** (captured by `unr`, not yet scored) — peak swell
  period, wind-wave vs swell split, secondary swell, currents, sea level,
  apparent temp, UV/visibility, weather code. Wiring these into scoring +
  recalibration is bead `swelligence-48w.7`.

---

## 6. Worked example — surf, one timestep

Spot offshore = N; conditions: wind 6 kn from N, gust 9 kn, wave 1.4 m, swell
12 s from the spot's swell window, water 14 °C.

| Factor | value | why | weight |
|---|---|---|---|
| wind | ~0.92 | 6 kn, just over ideal 5, well under max 15 | 0.6 |
| gust | 1.0 | 9 ≤ 20 | 0.3 |
| direction | 1.0 | N within an offshore sector | 0.8 |
| wave | ~0.97 | 1.4 m, just under ideal 1.5 | 1.0 |
| swell | ~0.99 | 12 s ≥ 11 s ideal, in-window | 0.7 |
| temp | (none) | surf doesn't score temp | 0.2→n/a |

Weighted mean ≈ `(0.92·0.6 + 1·0.3 + 1·0.8 + 0.97·1.0 + 0.99·0.7) / (0.6+0.3+0.8+1.0+0.7)` ≈ **0.96 → ~96/100 ("epic")**. No hard-fail, no tide gate ⇒ unchanged.

---

## 7. Known limitations & planned work

A scoring/safety review (2026-06-24) flagged fairness gaps and a missing safety
dimension, now tracked under epic **`swelligence-slh` (Scoring fairness + safety
markers)**:

- **Missing data is neutral → optimistic.** `None` factors drop from the
  denominator, so an *essential* missing field (surf without swell quality, swim
  without water temp) scores as if it didn't matter. Fix: factor **completeness
  semantics** — distinguish *not-applicable* / *not-configured* / *missing
  provider data*, and cap per sport when an essential field is missing
  (`slh.1`).
- **Untuned spots can score higher.** Direction only scores when `wind_dirs` /
  `swell_dirs` are set, so an unconfigured spot escapes strictness a tuned one
  gets. Treated as *not-configured* above, surfaced as a nudge (`slh.1`).
- **Safety is not modelled.** Planned as a **separate first-class output**
  (`safety_flags`), not another weight: offshore-wind risk (good for surf, unsafe
  for SUP/swim), gust, extremes (the current hard-fails surfaced explicitly),
  cold water, and *inferred* "elevated rip risk" (never "rip present"; currents
  are model hints, not beach truth). Flags may cap score only where
  sport-relevant (`slh.2`, with per-spot metadata `slh.3` and a strict tide gate
  `slh.4`).
- **Tide gate is soft** (floor 0.3, reached only after >2 windows) — weak for
  tide-critical launches; needs per-spot strictness (`slh.4`).
- **Calibration is narrow** (Christchurch only). Broader fixture matrix planned
  (`slh.5`).
- **Additional captured fields aren't scored yet** — peak period, wind-wave split,
  secondary swell, currents, etc. (`swelligence-48w.7`).
