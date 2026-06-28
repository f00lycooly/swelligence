# Spec — per-sport sensor entities for the panel NOW right column

**Status:** proposed · **Audience:** swelligence integration
**Consumer:** the HomeAutomation ESPHome wall panel (epic `HomeAutomation-4uq`,
specifically the NOW-dashboard right column: sport pills `4uq.16`,
selected-sport detail `4uq.17`, 24 h outlook `4uq.18`).
**Related:** [`docs/panel-contract.md`](panel-contract.md) (the existing
per-spot detail-sensor contract), [`docs/data-model.md`](data-model.md).

---

## 1. Context & the question

The panel's right column needs **per-sport** NOW data: a row of sport "pills"
(each a mini score gauge), a detail panel for the selected sport (verdict, best
slot, kit recommendation, factor breakdown), and a 24 h outlook.

An ESPHome/LVGL panel binds **HA entity state + attributes by fixed name**. It has
no on-device JSON parser and cannot bind a *dynamically-named* attribute
(`<sport>_now_score`). Two ways to deliver per-sport scores were considered:

1. **Pack per-sport scalars into CSV/pipe attributes** on the one per-spot
   `Panel detail` sensor (aligned to the `sports` list), mirroring how the
   time-series arrays are already delivered.
2. **Expose per-sport HA sensor entities** — one entity per (spot, sport) — and
   let the panel bind them directly.

**Decision: (2), sensor entities.** It is the idiomatic HA model (native history,
Lovelace cards, automations, the recorder), it is *simpler* for the panel (direct
`homeassistant` sensor binding, no lambda string-splitting), and — the key point —
**it already exists** (see §2). Live per-sport scalars do not belong in a
serialized string blob when HA's entity model expresses them natively.

**Scalars → entities; time-series arrays → detail-sensor attributes.** A 24-point
hourly curve or a 7-day array cannot sensibly be one-entity-per-sample, so those
stay as recorder-excluded aligned arrays on the `Panel detail` sensor (unchanged).
This spec only concerns the per-sport **NOW / best / kit scalars**.

---

## 2. What already exists (no change required)

`sensor.py::SuitabilitySensor` already creates **one sensor per (spot, sport)**:

- **Entity id:** `sensor.swelligence_<spot_slug>_<sport_label_slug>_suitability`
  (HA slugifies `Swelligence: <spot>` device + `<label> suitability` name).
  Observed live: `sensor.swelligence_mudeford_kitesurf_suitability`,
  `…_wing_foil_suitability`, `…_sup_suitability`, `…_surf_suitability`.
- **unique_id:** `swelligence_<spot_id>_<sport>_score` (`entity.py`).
- **state:** now suitability score `0–100` (`%`, `measurement`).
- **attributes:** `sport`, `sport_label`, `verdict`, `suitable`, `factors`
  (`{wind,gust,kit,…}`), `reasons`, `best_score`, `best_in_hours`,
  `best_verdict`, `recommended_size_m2`, `rig_size_m2`, `power`, `kit_summary`,
  plus `confidence`, `data_quality`, `data_sources`, `completeness`, `nudges`,
  `ai_rating` where available.

This already serves the **pills** (state + `verdict` + `sport_label`) and almost
all of the **selected-sport detail** (`verdict`, `best_*`, `factors`, `reasons`,
and the full kit recommendation).

### The varying-sport-count solution falls out for free

A spot is only configured for some sports (Mudeford: kitesurf/wing foil/SUP;
Southbourne adds surf). Crucially, **a sport the spot does not score yields an
`unavailable` entity** rather than a missing one (observed: Mudeford's
`…_surf_suitability` = `unavailable`). So the panel binds a **fixed superset of
sport slots** per spot and **hides any pill whose sensor is `unavailable`** — no
array, no dynamic names, no count negotiation.

---

## 3. The gap to close (small integration additions)

### 3.1 Add `best_time` (clock) to `SuitabilitySensor`  — required

The per-sport sensor exposes `best_in_hours` but not the clock time of the best
slot. The `Panel detail` sensor already derives it
(`detail.py`: `hourly[best_offset_h]["datetime"][11:16]`). Add the same to
`SuitabilitySensor.extra_state_attributes` so the selected-detail panel can show
"best · HH:MM" without computing it on-device:

```python
if res.best is not None:
    attrs["best_score"] = res.best.score
    attrs["best_in_hours"] = res.best_offset_h
    attrs["best_verdict"] = res.best.verdict
    attrs["best_time"] = _best_clock(self.coordinator, self._sport, res.best_offset_h)
```

`best_time` = local `HH:MM` (string) or omitted/`None` when there is no best slot.
Factor the clock derivation out of `detail.py` into a shared helper so both the
detail sensor and the per-sport sensor stay in lock-step.

### 3.2 Document the entity contract in `panel-contract.md`  — required

Add a "Per-sport sensors (pills / selected-detail)" section: the canonical
`entity_id` pattern, the `unavailable = hide` rule, the attribute table, and the
**scalars→entities / arrays→detail-sensor** principle. Pin the `sport_label`→slug
mapping that produces the entity id (e.g. `Wing foil` → `wing_foil`,
`Wakeboard (inland)` → `wakeboard_inland`) so the panel's substitutions are exact.

### 3.3 Guard entity-id stability  — required

The panel hard-references these entity ids via substitutions. The id derives from
`sport_label`. Add a test asserting the `(sport → entity_id suffix)` mapping for
the current `SPORT_PROFILES` labels, so a future label rename can't silently break
the panel binding. If a label must change, it's then a conscious, tested change.

---

## 4. Out of scope (stays as-is)

- **24 h outlook & WEEK** (`4uq.18` / `4uq.7`): the panel keeps binding the
  `Panel detail` sensor's aligned `<s>_hourly_*` / `<s>_week_*` arrays. Arrays are
  not entity-shaped; no change.
- **Spot-level NOW scalars** (wind, gust, tide, daylight): already consumed from
  the detail sensor by the panel's left column; not refactored here.
- The panel-side LVGL implementation (pills/detail widgets + binding) lives in
  the HomeAutomation repo (`4uq.16/.17`), not here.

---

## 5. Panel binding model (informative — lives in HomeAutomation)

- **Pills:** per spot, a fixed set of slots bound to
  `sensor.swelligence_<spot>_<sport>_suitability`; hide slot if `unavailable`;
  ring colour from `verdict`; centre = state (score); caption = `sport_label`.
- **Selected detail:** bind the selected sport's sensor — `verdict`, `best_score`
  + `best_time` + `best_verdict`, `power` + `rig_size_m2` + `recommended_size_m2`
  (+ `kit_summary`), `factors` (bar rows), top `reasons` line.

---

## 6. Acceptance criteria

- `SuitabilitySensor` exposes `best_time` (local `HH:MM`) when a best slot exists,
  absent/`None` otherwise; derived from the same helper as the detail sensor.
- `panel-contract.md` documents the per-sport sensor contract + the
  scalars-vs-arrays principle + the label→entity-id mapping.
- A test pins the `sport → entity_id suffix` mapping for current sport labels.
- No breaking change to existing sensor/attribute names; additive only.
- `CHANGELOG.md` notes the additive `best_time` attribute.
