# Safety flags as first-class output (bd swelligence-slh.2)

**Date:** 2026-06-29
**Bead:** `swelligence-slh.2` (parent epic `swelligence-slh` — Scoring fairness + safety markers)
**Status:** design approved

## Problem

The scorer answers *how good* conditions are (`score`) and *how trustworthy*
the data is (`confidence`, dormant). It has no first-class answer to *why a slot
may be unsafe*. Today the wind/wave hard-fails (too strong / too big / too
choppy) only exist implicitly: they cap the score to 30 and drop a string into
`reasons`, mixed in with ordinary observations. There is no machine-readable,
severity-tagged safety signal a consumer (card Safety cell, automations, LLM)
can act on.

This adds `safety_flags` as a first-class scored-result field, **separate from
score and confidence**, derived conservatively from data the provider already
supplies.

## Scope (v1)

Two flags, both **advisory** — they never introduce new score capping:

| kind | severity | fires when | source |
|------|----------|-----------|--------|
| `too_strong` | `danger` | wind factor `== 0.0` (wind over `wind_max_kn`) | existing wind eval |
| `too_big` | `danger` | wave factor `== 0.0` on a waves-desired profile | existing wave eval |
| `too_choppy` | `danger` | wave factor `== 0.0` on a flat-preferred profile | existing wave eval |
| `gusty` | `caution` | gust factor `< 1.0` (gust over `gust_max_kn`) | existing gust eval |

The hard-fail flags **re-surface conditions that already cap the score** (the
"unify, don't parallel" requirement of the bead): the flag and the existing cap
come from the *same* factor evaluation, so they can never disagree. `gusty`
mirrors the gust factor's own ceiling — the graduated gust penalty is unchanged;
the flag is just an explicit marker that gusts are over the sport's limit.

**Score math is untouched.** No recalibration (`validate_spots.py` /
`analyze_history.py`) is required — scores are identical with and without this
change.

### Explicitly deferred (follow-up beads, not this PR)

- **offshore-wind-risk** — needs a true offshore vector; deferred to
  `swelligence-slh.6` (AI-inferred shore orientation).
- **cold-water** — conservative absolute water-temp threshold, sharpened for
  sea-swim.
- **strong-current** — `current_speed_kn` as a *model hint* only.
- **elevated-rip-risk** — inferred marker; highest over-flagging risk; overlaps
  shore orientation. Deferred deliberately to keep v1 honest.

## Architecture

Data flow is unchanged: provider → normalised model → **deterministic scorer**
→ entities/LLM. Safety-flag derivation lives at the scorer, the single choke
point every consumer (now / best / hourly / timelines) already passes through.

### New module `safety.py` (pure)

Mirrors `hazards.py`: pure logic, **no `homeassistant` import, no domain
import**, runs under the stubbed unit suite. It is *not* added to
`tests_ha/test_ha_guard.py` (that guard is for HA-touching modules only).

```python
DANGER = "danger"
CAUTION = "caution"

@dataclass(slots=True, frozen=True)
class SafetyFlag:
    kind: str       # "too_strong" | "too_big" | "too_choppy" | "gusty"
    severity: str   # DANGER | CAUTION
    message: str    # conservative human text, reused from the factor note

    def as_dict(self) -> dict[str, str]: ...

def derive_safety_flags(profile, factors) -> list[SafetyFlag]:
    """factors: {name: (value: float|None, note: str)} for wind/wave/gust.

    Pure. Reuses the factor values + notes already computed by score_point —
    no thresholds are re-evaluated here, so a flag can never disagree with the
    score it accompanies.
    """
```

Derivation rules (read-only over the eval results):

- `factors["wind"]` value `== 0.0` → `SafetyFlag("too_strong", DANGER, note)`.
  `_wind_factor` returns `0.0` **only** for over-max ("too strong"); under-power
  returns `> 0`, so the `0.0` test is an exact, non-string-matched signal.
- `factors["wave"]` value `== 0.0` → `too_big` when the profile is waves-desired
  (`wave_ideal_m and wave_ideal_m > 0`), else `too_choppy`. `_wave_factor`
  returns `0.0` only for "too big" / "too choppy".
- `factors["gust"]` value not `None` and `< 1.0` → `SafetyFlag("gusty",
  CAUTION, note)`. `_gust_factor` returns `1.0` at/under the ceiling, `< 1.0`
  only once gusts exceed `gust_max_kn`.

`message` is the factor's existing note verbatim, with a plain fallback if a
note is somehow empty (`"overpowering wind"`, `"oversized waves"`, `"choppy
water"`, `"strong gusts"`).

### `scoring.py` changes

- `ScoreResult` gains `safety_flags: list[SafetyFlag] = field(default_factory=list)`.
- In `score_point`, during the existing factor loop, capture
  `{name: (ev.value, ev.note)}` for `wind`/`wave`/`gust` (only when the factor is
  `APPLICABLE` — the only state with a numeric value), then
  `safety_flags = derive_safety_flags(profile, captured)` and pass to
  `ScoreResult`. No change to `num`/`den`/`score`/cap logic.
- `blend_kit` carries `safety_flags` through unchanged (kit power doesn't change
  why conditions are unsafe), exactly as it already carries `warnings`.

### Surfacing (mirrors `warnings` end-to-end)

`safety_flags` is exposed as `list[{kind, severity, message}]` (structured,
unlike `warnings`' `list[str]`, so a consumer can render severity):

- `sensor.py` `extra_state_attributes`: `attrs["safety_flags"] = [...]` only when
  non-empty (mirrors the `warnings` guard).
- `forecast.py` per-slot dict: `"safety_flags": [f.as_dict() for f in res.safety_flags]`.
- `detail.py` `now` and `hourly` rich payload: same structured list.

**Out of scope (belongs to `swelligence-erf`):** the `detail.py` flat/delimited
panel attributes (`*_now_*`), `docs/panel-contract.md`, and the card Safety cell.
The structured `now`/`hourly` payload this PR adds is the data those will bind to.

## Testing

New `tests/test_safety.py` (pure suite):

- **Per-flag fire:** over-max wind → `too_strong`/danger; oversized waves on surf
  → `too_big`/danger; over-choppy water on a flat-preferred sport → `too_choppy`;
  gust over ceiling → `gusty`/caution. Assert `kind` + `severity` + that
  `message` matches the factor note.
- **Restraint guards (the "no over-flagging" acceptance criterion):**
  - calm/benign point → `safety_flags == []`.
  - under-powered wind (factor `> 0`) → no `too_strong`.
  - comfortable chop (under comfort plateau) → no wave flag.
  - gust exactly at `gust_max_kn` → no `gusty`.
- **Integration via `score_point`:** a hard-fail point yields the flag *and* the
  existing cap (30) — proving unification (flag and cap co-occur, never diverge).
- **`blend_kit` carry-through:** flags survive a kit blend unchanged.

`tests_ha` is unaffected (no new HA-touching module); existing guard list stays.

## Build / quality gates

`pytest` (pure suite) green; `pytest tests_ha` green; hassfest unchanged. No
`.tool-output` linter concerns beyond the standard run. No manifest version bump
(that's a release concern).
