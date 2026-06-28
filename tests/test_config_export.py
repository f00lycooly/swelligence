"""Unit tests for the hub config/setup payload builder (d1r.4).

Pure builder: turns the entry topology (spots/sports/rider) into the codegen-ready
nested payload for sensor.swelligence_config. slugify + entity-id resolution are
injected, so this runs without Home Assistant. Spec: docs/panel-config-sensor-spec.md.
"""

from __future__ import annotations

from swelligence.config_export import build_config_payload


def _slug(s: str) -> str:
    """Stand-in for homeassistant.util.slugify covering the test labels."""
    return s.lower().replace(" ", "_").replace("(", "").replace(")", "")


_SPOTS = [
    {
        "id": "mudeford",
        "name": "Mudeford",
        "water_type": "sea",
        "latitude": 50.73,
        "longitude": -1.74,
        "tide_state": "any",
        "sports": ["kitesurf", "wingfoil"],
    },
]
_ENABLED = ["kitesurf", "wingfoil", "surf"]  # priority order; superset of pills
_RIDER = {"weight_kg": 82, "quiver": {"kitesurf": [7, 9, 12], "wingfoil": [4.5, 6]}}


def _build(*, spots=None, enabled=None, rider=None, resolver=None, generated_at="T0"):
    return build_config_payload(
        spots=_SPOTS if spots is None else spots,
        enabled_sports=_ENABLED if enabled is None else enabled,
        rider=_RIDER if rider is None else rider,
        manifest_version="0.2.3",
        generated_at=generated_at,
        slugify=_slug,
        resolve_entity_id=(resolver or (lambda uid: None)),
    )


def test_top_level_shape():
    p = _build()
    assert p["manifest_version"] == "0.2.3"
    assert p["generated_at"] == "T0"
    assert p["config_hash"] == p["config_hash"] and len(p["config_hash"]) == 8
    assert {"config_hash", "generated_at", "manifest_version", "sports", "rider",
            "spots"} <= set(p)


def test_sports_carry_key_label_slug_in_priority_order():
    sports = _build()["sports"]
    assert [s["key"] for s in sports] == ["kitesurf", "wingfoil", "surf"]
    wing = next(s for s in sports if s["key"] == "wingfoil")
    assert wing["label"] == "Wing foil" and wing["slug"] == "wing_foil"


def test_rider_exposes_only_weight_and_quiver():
    p = _build(rider={"weight_kg": 82, "quiver": {"kitesurf": [9]},
                      "api_key": "SECRET", "ai_task_entity_id": "x"})
    assert p["rider"] == {"weight_kg": 82, "quiver": {"kitesurf": [9]}}


def test_no_secrets_leak_from_spot_fields():
    spot = {**_SPOTS[0], "provider": "open_meteo", "api_key": "SECRET"}
    p = _build(spots=[spot])
    flat = repr(p)
    assert "SECRET" not in flat
    assert "api_key" not in p["spots"][0]
    assert "provider" not in p["spots"][0]


def test_spot_topology_fields():
    s = _build()["spots"][0]
    assert s["id"] == "mudeford" and s["slug"] == "mudeford"
    assert s["water_type"] == "sea" and s["tide_state"] == "any"
    assert s["latitude"] == 50.73 and s["longitude"] == -1.74
    assert s["sports"] == ["kitesurf", "wingfoil"]  # configured (active) only


def test_pills_are_fixed_superset_with_configured_flag():
    pills = _build()["spots"][0]["pills"]
    # One pill per ENABLED sport (the fixed superset), priority order.
    assert [p["sport"] for p in pills] == ["kitesurf", "wingfoil", "surf"]
    by = {p["sport"]: p for p in pills}
    assert by["kitesurf"]["configured"] is True
    assert by["wingfoil"]["configured"] is True
    assert by["surf"]["configured"] is False  # not in the spot's sports
    assert by["wingfoil"]["slug"] == "wing_foil"


def test_entity_ids_resolved_from_registry_when_available():
    resolver = {
        "swelligence_mudeford_kitesurf_score": "sensor.kite_resolved",
        "swelligence_mudeford_detail": "sensor.detail_resolved",
    }.get
    s = _build(resolver=resolver)["spots"][0]
    assert s["detail_entity_id"] == "sensor.detail_resolved"
    kite = next(p for p in s["pills"] if p["sport"] == "kitesurf")
    assert kite["entity_id"] == "sensor.kite_resolved"


def test_entity_ids_fall_back_to_derived_pattern():
    # No registry hit -> derived slug pattern (pre-registration / first boot).
    s = _build()["spots"][0]
    assert s["detail_entity_id"] == "sensor.swelligence_mudeford_panel_detail"
    wing = next(p for p in s["pills"] if p["sport"] == "wingfoil")
    assert wing["entity_id"] == "sensor.swelligence_mudeford_wing_foil_suitability"


def test_hash_ignores_generated_at_but_tracks_topology():
    a = _build(generated_at="T0")["config_hash"]
    b = _build(generated_at="T1")["config_hash"]
    assert a == b  # generated_at must not perturb the hash
    # A real topology change moves the hash.
    moved = _build(spots=[{**_SPOTS[0], "name": "Avon Beach"}])["config_hash"]
    assert moved != a


def test_unknown_enabled_sport_is_dropped():
    # A sport key with no built-in profile can't produce a label/slug -> skip it.
    p = _build(enabled=["kitesurf", "not_a_sport"])
    assert [s["key"] for s in p["sports"]] == ["kitesurf"]
    assert [pill["sport"] for pill in p["spots"][0]["pills"]] == ["kitesurf"]
