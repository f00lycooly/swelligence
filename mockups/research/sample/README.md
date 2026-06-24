# Real spot data samples

Live data from the **Southbourne** spot (50.718, −1.7825), to feed the
spot-detail card design. See [`docs/data-model.md`](../../../docs/data-model.md)
for the field reference.

| File | Source | Contents |
|---|---|---|
| `southbourne-sensors.json` | HA recorder (real entity states) | the 9 Southbourne entities — suitability scores + every attribute (`factors`, `reasons`, `completeness`, `nudges`, `best_*`, `data_quality`, `data_sources`), the `*_suitable` binaries, and the `source_advice` diagnostic |
| `southbourne-forecast.json` | `scripts/sample_spot.py` (integration provider + scorer vs live Open-Meteo) | `now_raw` (all 27 `ForecastPoint` fields), per-sport `scores`, and a 24 h `get_forecast`-style hourly timeline per sport |

The two agree (e.g. surf 35.8, same factors/reasons/completeness/nudges) — the
forecast sample reproduces HA's output exactly, so it's a faithful stand-in and
is reproducible without HA:

```bash
python3 scripts/sample_spot.py Southbourne 50.718 -1.7825 sea surf,kitesurf,wingfoil,sup \
  > mockups/research/sample/southbourne-forecast.json
```

> Snapshot — a flat, near-windless low-tide hour, so most sports read
> marginal/poor and SUP wins (calm). Re-run for livelier conditions.
