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

Regenerate (pass the spot's **real** water type — it changes which fields exist):

```bash
python3 scripts/sample_spot.py Mudeford 50.7264 -1.7406 sheltered kitesurf,wingfoil,sup \
  > mockups/research/sample/mudeford-forecast.json
```

## Which file is authoritative

- **`*-sensors.json` is the ground truth for scores** — it's the actual entity
  state, so it includes the **tide gate** and any **per-spot overrides** the
  coordinator applies.
- **`*-forecast.json` is the ground truth for raw fields + the timeline**, and
  reproduces the score from the deterministic scorer. It matches the live entity
  when given the right water type *and* when no tide gate / override is active
  (verified: Southbourne, Sandbanks, Mudeford all match at this snapshot). It
  does **not** apply the tide gate or per-spot overrides, so it can read higher
  than the entity when a spot is at the wrong tide.

> Snapshot caveat — a flat, near-windless hour, so wind sports read marginal and
> SUP wins (calm). The three spots have **no per-spot offshore wind/swell
> directions set**, so every score carries `completeness: {direction:
> not_configured}` + the nudge. Re-run for livelier conditions / after tuning.
