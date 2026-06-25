# Real spot data samples

Live data from three configured spots, to feed the spot-detail card design. See
[`docs/data-model.md`](../../../docs/data-model.md) for the field reference.

| Spot | coords | water | sports |
|---|---|---|---|
| Southbourne | 50.718, −1.7825 | sea | surf, kitesurf, wingfoil, sup |
| Mudeford | 50.7264, −1.7406 | **sheltered** (harbour — waves suppressed) | kitesurf, wingfoil, sup |
| Sandbanks | 50.6971, −1.9327 | sea | kitesurf, wingfoil, sup |

For each spot, two files:

| `*-sensors.json` | HA recorder (real entity states) | every entity — suitability score + all attributes (`factors`, `reasons`, `completeness`, `nudges`, `best_*`, `data_quality`, `data_sources`), the `*_suitable` binaries, and the `source_advice` diagnostic |
|---|---|---|
| `*-forecast.json` | `scripts/sample_spot.py` (integration provider + scorer vs live Open-Meteo) | `now_raw` (the `ForecastPoint` fields — fewer for sheltered, which suppresses waves), per-sport `scores`, and a 24 h `get_forecast`-style hourly timeline |

Regenerate (pass the spot's **real** water type — it changes which fields exist).
`sample_spot.py` now pulls a **7-day** forecast and anchors `now_raw` at local
**mid-day** (12:00), emitting the full forward hourly series (`forecast[sport]` ≈
150 pts) so consumers can show the near-term timeline *and* the weekly outlook:

```bash
python3 scripts/sample_spot.py Mudeford 50.7264 -1.7406 sheltered kitesurf,wingfoil,sup \
  > mockups/research/sample/mudeford-forecast.json
```

## Which file is authoritative

- **`*-forecast.json` is the source for the mockups' scoring + time series.** It
  carries `now_raw` (raw fields at the mid-day anchor), the per-sport `scores`
  at that instant, and the multi-day hourly `forecast`. `scripts/build_card_data.py`
  single-sources the cards' **score / verdict / factors / best / hourly series /
  weekly peaks** from here, so the "now" gauge, `series[0]`, and the weekly
  outlook all agree. It does **not** apply the tide gate / per-spot overrides, so
  it can read higher than the live entity when a spot is at the wrong tide.
- **`*-sensors.json`** (a prior HA-recorder capture) is now used only for
  **time-invariant metadata** in the mockups — sport label/icon, model grid
  distance, per-domain sources, and `source_advice`. Its scores reflect an older
  snapshot (incl. the tide gate) and are intentionally *not* used for the cards'
  "now" values, to avoid `now ≠ series[0]`.

> The three spots have **no per-spot offshore wind/swell directions set**, so
> every score carries `completeness: {direction: not_configured}` + the nudge.
> Re-run after tuning. Tide high/low in the cards is **derived from the modelled
> `sea_level_m`** trajectory (Open-Meteo), not a station tide table.
