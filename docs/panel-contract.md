# Swelligence panel-detail entity contract

**Audience:** the ESPHome / LVGL wall-panel implementation (Tinkernet/HomeAutomation,
epic `HomeAutomation-4uq`, `esphome/design/swelligence-panel-spec.md`). This is the
data contract the Swelligence Home Assistant integration publishes for the panel to
bind. It is generated from the integration source (`custom_components/swelligence/
detail.py::flatten_detail`); when the two disagree, the code wins — re-check this doc
against the entity's live attributes in **Developer Tools → States**.

Reflects the integration as of PR #35 (the per-spot detail entity + full week
payload). Core NOW fields landed in v0.2.1–v0.2.3; the WEEK peak-hour conditions,
day/hour axes, `wind_wave_m`, `*_week_peak_idx`, and `*_factors` land in the release
following PR #35.

---

## 1. The entity

One **`sensor` entity per spot**, created by the integration:

- **Unique ID:** `swelligence_<spot_id>_detail`
- **Friendly name:** `Swelligence: <spot name> Panel detail`
- **Entity ID:** typically `sensor.swelligence_<spot_slug>_panel_detail` — **confirm
  the exact ID per spot in Developer Tools → States** (HA slugifies the device + entity
  name; it depends on the spot name).
- **State:** the spot's **best current suitability score** across all its sports
  (integer `0–100`, or `unknown`). This is the headline number for the spot tab.
- **All other data rides in `attributes`** (below).

Every panel-bound value is a **flat scalar or a delimited string** — there are no
nested objects or arrays in the attributes, because an ESPHome LVGL panel binds HA
entity attributes and has no on-device JSON parser. The panel splits the delimited
strings in a lambda (see §6).

> The same data is also available as a rich nested object via the
> `swelligence.get_spot_detail` **service** (response-only) — that's what the Lovelace
> card consumes. The panel uses **this entity** because it can't cleanly call a
> response-returning service. Both come from one source of truth, so they never drift.

---

## 2. Encoding rules (read first)

| Rule | Detail |
|---|---|
| **Units** | speeds = **knots**, heights = **metres**, temperatures = **°C**, directions = **degrees, "from"** (meteorological). |
| **Unknown** | A missing/unavailable value is **empty**, never `0`. In a CSV it is an **empty field** (`"0.7,,0.5"` → middle hour unknown). Scalars come back as an empty string / `unknown`. |
| **CSV arrays** | Comma-separated, **positional** — index `i` is the same time slot across every related array. Never skip a slot; hold it with an empty field. |
| **Pipe arrays** | `sports` and `sport_labels` use **`|`** (pipe), because labels contain spaces/parens (e.g. `Wing foil`, `Wakeboard (inland)`). |
| **Verdict codes** | 1 char: `e`=epic, `g`=great, `o`=good, `m`=marginal, `p`=poor. (Keeps per-hour/-day CSVs tiny.) |
| **Rounding** | wind/gust/wave/swell/period/water → 1 dp; directions → integer; tide height → 2 dp; scores → integer. |
| **Recorder** | All array/CSV attributes are **excluded from the HA recorder** — the panel reads **live state**, not history. Don't expect these in long-term stats. |

**Honesty rules (do not break in the UI):**
- Tide highs/lows are **modelled** from sea-level unless a real overlay (UKHO/NOAA)
  covers the spot. The source is labelled — show it (`tide_source`, `*_week_tide_*`).
- The weekly metric is the **daytime-only** daily peak (sunrise..sunset).
- Onshore/offshore safety labelling is **not provided** (needs per-spot shore bearing)
  — do not fabricate it.

---

## 3. Spot-level attributes

### Identity & time
| Attribute | Type | Notes |
|---|---|---|
| `name` | string | Spot name. |
| `water_type` | string | `sea` / `sheltered` / … |
| `now_time` | `HH:MM` | Forecast "now" anchor (local). |
| `lat`, `lon` | float | For the static map pin. |

### Daylight (NOW header / sun marker)
| Attribute | Type | Notes |
|---|---|---|
| `sunrise`, `sunset` | `HH:MM` | Today's sun window. |
| `daylight_remaining_min` | int | Minutes of daylight left. |
| `daylight_progress` | float `0–1` | Elapsed fraction of the daylight window (place a sun marker). |

### Now conditions (NOW-strip)
| Attribute | Type | Notes |
|---|---|---|
| `wind_kn` | float | |
| `gust_kn` | float | |
| `wind_dir_deg` | float | Degrees **from**; needle "flow" direction = `+180`. |
| `wave_m` | float | Total significant wave. **May be empty** on sheltered spots → fall back to `wind_wave_m`. |
| `wind_wave_m` | float | Wind-wave height; the NOW-strip Wave fallback when `wave_m` is empty. |
| `swell_m` | float | |
| `swell_period_s` | float | |
| `water_temp_c` | float | |

### Tide (NOW tide module)
| Attribute | Type | Notes |
|---|---|---|
| `tide_state` | string | `rising` / `falling` / `high` / `low` / `slack`. |
| `tide_source` | string | `modelled` or the overlay authority — **display it** (honesty). |
| `tide_now_m` | float | Current sea level (provider datum). |
| `tide_levels` | CSV float | ~24-pt sea-level series for the sparkline (positional; empties allowed). |
| `tide_next_type` | string | `high` / `low`. |
| `tide_next_time` | `HH:MM` | |
| `tide_next_in_h` | int | Hours until next high/low. |
| `tide_next_level_m` | float | |

### Axes & sport list (shared across all sports for this spot)
| Attribute | Type | Notes |
|---|---|---|
| `hours` | CSV `HH:MM` | x-axis for the **24h timeline**. `*_hourly_*` arrays align index-for-index with this. |
| `week_days` | CSV string | Day labels for the **7 day rows**: index `0` is **`Today`**, the rest are weekday abbreviations (`Fri`, `Sat`, …). |
| `week_dates` | CSV `YYYY-MM-DD` | ISO date per day row (header date-range). Aligns with `week_days`. |
| `sports` | **pipe** CSV | Sport **keys** in display order — drives the selector pills and the `<sport>_*` attribute lookups. |
| `sport_labels` | **pipe** CSV | Human labels, aligned with `sports`. |

Possible sport keys (a spot only lists those it's configured for):
`kitesurf`, `windsurf`, `wingfoil`, `surf`, `sup`, `sailing`, `seaswim`,
`wakeboard_inland`, `wakeboard_sea`.

### Headline (best-scoring sport right now)
Statically named so the NOW gauge binds without knowing each spot's sport list.
| Attribute | Type | Notes |
|---|---|---|
| `headline_sport` | string | Sport key of the best current sport. |
| `headline_label` | string | Its human label. |
| `headline_score` | int | = the entity **state**. |
| `headline_verdict` | string | Full word (`epic`…`poor`). |
| `headline_suitable` | bool | |

---

## 4. Per-sport attributes

For each sport key `s` in `sports`, the following attributes exist as `<s>_<field>`
(e.g. `kitesurf_now_score`, `surf_week_wave`). All `*_week_*` and `*_hourly_*` arrays
are positional and aligned with the spot-level axes (`week_days` / `hours`).

### NOW — selected sport
| Attribute | Type | Notes |
|---|---|---|
| `<s>_now_score` | int | Score right now. |
| `<s>_now_verdict` | string | Full word. |
| `<s>_now_suitable` | bool | |
| `<s>_best_score` | int | Best score in the next 24h. |
| `<s>_best_in_h` | int | Hours from now to that best slot. |
| `<s>_best_verdict` | string | |
| `<s>_best_time` | `HH:MM` | Clock time of the best slot. |
| `<s>_kit_power` | string | Rig sports only (e.g. `powered`); empty for swim/SUP/surf. |
| `<s>_kit_rig_m2` | float | Recommended owned rig size; empty if N/A. |
| `<s>_kit_ideal_m2` | float | Ideal rig size; empty if N/A. |
| `<s>_factors` | `k:score,…` | Optional factor breakdown — `key:score` pairs (rounded int), in the scorer's own order (factor set differs by sport). e.g. `wind:66,gust:100,wave:100`. |

### NOW — 24h timeline (aligns with `hours`)
| Attribute | Type | Notes |
|---|---|---|
| `<s>_hourly_scores` | CSV int | One score per hour in `hours`. |
| `<s>_hourly_verdicts` | CSV code | Verdict code per hour (bar colour). |

### WEEK — daytime peak per day (all align with `week_days` / `week_dates`)
| Attribute | Type | Notes |
|---|---|---|
| `<s>_week_scores` | CSV int | Peak score per day. |
| `<s>_week_times` | CSV `HH:MM` | Clock time of that day's peak (per-sport — differs by sport). |
| `<s>_week_verdicts` | CSV code | Verdict code per day. |
| `<s>_week_peak_idx` | int | **Index of the best (max-score) day** in the week arrays — anchor the best-day pane to `week_days[idx]` etc. without computing an argmax on-device. |
| `<s>_week_wind` | CSV float | Wind at each day's peak hour. |
| `<s>_week_gust` | CSV float | Gust at each day's peak hour. |
| `<s>_week_dir` | CSV int | Wind direction (deg from) at peak hour. |
| `<s>_week_wave` | CSV float | Wave height at peak hour (empty where unknown). |
| `<s>_week_swell` | CSV float | Swell height at peak hour. |
| `<s>_week_per` | CSV float | Swell period (s) at peak hour. |
| `<s>_week_water` | CSV float | Water temp (°C) at peak hour. |
| `<s>_week_tide_state` | CSV string | Tide phase at peak hour (`rising`/`falling`/`high`/`low`/`slack`). |
| `<s>_week_tide_h` | CSV float | Tide height (m, 2 dp) at peak hour. |

**Best-day pane** = read `idx = <s>_week_peak_idx`, then index every `<s>_week_*`
array (and `week_days` / `week_dates`) at `idx` for the `{day, peak time, conditions}`
detail readout. **Good-days count** = number of `<s>_week_verdicts` entries that are
`o`/`g`/`e` (good or better).

---

## 5. Alignment guarantees (the indexing contract)

- `<s>_hourly_*[i]` ⟷ `hours[i]` — same hour, every sport.
- `<s>_week_*[i]` ⟷ `week_days[i]` ⟷ `week_dates[i]` — same day, every sport.
- `<s>_week_peak_idx` is a valid index into the week arrays for that sport.
- `sport_labels[j]` ⟷ `sports[j]` (pipe-split).
- `week_days[0]` is always **today** (matches the Lovelace card's `daily[0] == today`
  convention).
- A spot only publishes `<s>_*` attributes for sports it's configured for; iterate
  `sports`, don't assume a fixed set.

---

## 6. ESPHome / LVGL consumption notes

- Bind each scalar attribute to a `homeassistant` **`sensor`** (numeric) or
  **`text_sensor`** (string), then drive labels/arcs/needles from `on_value`.
- For the delimited strings, bind a `text_sensor` and split in a lambda. Comma-split
  for CSV, pipe-split for `sports` / `sport_labels`, and treat an **empty field as
  "unknown"** (don't render `0`).
- Verdict colour = map the 1-char code → your semantic palette
  (`e`/`g`/`o`/`m`/`p`). Keep the palette fixed/semantic.
- The map tile is **out of scope for this entity** — render it separately (HA
  camera / `online_image` PNG), per the panel spec.
- These arrays are excluded from the recorder; they update each coordinator cycle —
  bind to **live state**, not history/statistics.

Minimal split helper (illustrative):

```cpp
// split "a,b,,d" -> std::vector<std::string> with "" for empty slots
std::vector<std::string> csv(const std::string &s) {
  std::vector<std::string> out; size_t i = 0, j;
  while ((j = s.find(',', i)) != std::string::npos) { out.push_back(s.substr(i, j - i)); i = j + 1; }
  out.push_back(s.substr(i));
  return out;
}
// usage: auto wind = csv(id(kitesurf_week_wind).state);
//        auto v = wind[ id(kitesurf_week_peak_idx).state ];  // best-day wind ("" = unknown)
```

---

## 7. Versioning

The integration's `manifest.json` `version` is the contract version. Pin the panel
config against a known version and re-check this table after upgrading. Additive
fields (new attributes) are backward-compatible; a removal or rename will bump and be
called out in `CHANGELOG.md`.
