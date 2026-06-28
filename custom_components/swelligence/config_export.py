"""Pure builder for the hub config/setup source-of-truth payload (d1r.4).

Turns the entry's topology — spots, enabled sports, rider kit — into a
codegen-ready nested payload for ``sensor.swelligence_config``: the install's
spots and sports PLUS the **derived per-sport entity-ids and per-spot pill slots**,
so a build-time panel generator emits ESPHome substitutions/pill slots with zero
re-derivation. See ``docs/panel-config-sensor-spec.md``.

No Home Assistant import (HA-at-the-edges): ``slugify`` (HA's util) and
``resolve_entity_id`` (entity-registry lookup) are injected by the sensor wrapper,
so this whole module is unit-testable without HA. Secrets (API keys, the AI-task
entity, provider credentials) are **never** read here — topology only.
"""

from __future__ import annotations

import hashlib
import json

from .sports import SPORT_PROFILES


def _suitability_uid(spot_id: str, sport: str) -> str:
    """unique_id of the per-(spot, sport) suitability sensor (see entity.py)."""
    return f"swelligence_{spot_id}_{sport}_score"


def _detail_uid(spot_id: str) -> str:
    """unique_id of the per-spot panel-detail sensor (see entity.py)."""
    return f"swelligence_{spot_id}_detail"


def _config_hash(payload: dict) -> str:
    """Stable 8-char hash over the topology, excluding the volatile timestamp.

    Changes iff the topology changes, so automations can trigger on it and a
    generator can cache-bust / skip a no-op rebuild.
    """
    stable = {k: v for k, v in payload.items() if k not in ("generated_at", "config_hash")}
    blob = json.dumps(stable, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(blob.encode()).hexdigest()[:8]


def config_summary(payload: dict) -> str:
    """Human-readable one-line summary for the sensor STATE — ``"<n> spots · <m>
    sports"``. The precise change-detection signal stays in the ``config_hash``
    attribute; this is the legible at-a-glance value."""
    n_spots = len(payload.get("spots") or [])
    n_sports = len(payload.get("sports") or [])
    spot_w = "spot" if n_spots == 1 else "spots"
    sport_w = "sport" if n_sports == 1 else "sports"
    return f"{n_spots} {spot_w} · {n_sports} {sport_w}"


def build_config_payload(
    *,
    spots: list[dict],
    enabled_sports: list[str],
    rider: dict | None,
    manifest_version: str | None,
    generated_at: str,
    slugify,
    resolve_entity_id,
) -> dict:
    """Build the config/setup payload. See module docstring + the spec.

    ``slugify(text) -> str`` is HA's util (injected); ``resolve_entity_id(unique_id)
    -> str | None`` looks an entity up in the registry (authoritative), falling
    back to the derived slug pattern when it returns ``None`` (pre-registration).
    """
    # Enabled sports, in priority order, dropping any without a built-in profile
    # (a key with no profile can't produce a label/slug or score an entity).
    sports_meta: list[dict] = []
    for key in enabled_sports:
        profile = SPORT_PROFILES.get(key)
        if profile is None:
            continue
        sports_meta.append({"key": key, "label": profile.label,
                            "slug": slugify(profile.label)})
    enabled_keys = [s["key"] for s in sports_meta]

    rider = rider or {}
    rider_out = {
        "weight_kg": rider.get("weight_kg"),
        "quiver": rider.get("quiver", {}) or {},
    }

    spots_out: list[dict] = []
    for spot in spots:
        spot_id = spot["id"]
        name = spot.get("name", spot_id)
        spot_slug = slugify(name) if name else spot_id
        # Active sports = the spot's configured set ∩ enabled (with a profile).
        configured = [s for s in (spot.get("sports") or enabled_keys) if s in enabled_keys]

        detail_eid = (
            resolve_entity_id(_detail_uid(spot_id))
            or f"sensor.swelligence_{spot_slug}_panel_detail"
        )
        # Fixed superset of pill slots (every enabled sport), with the resolved
        # entity-id and whether this spot is configured for it — so the generator
        # emits a slot per entry and the panel hides/omits unconfigured ones.
        pills: list[dict] = []
        for s in sports_meta:
            sport = s["key"]
            eid = (
                resolve_entity_id(_suitability_uid(spot_id, sport))
                or f"sensor.swelligence_{spot_slug}_{s['slug']}_suitability"
            )
            pills.append({
                "sport": sport,
                "label": s["label"],
                "slug": s["slug"],
                "entity_id": eid,
                "configured": sport in configured,
            })

        spots_out.append({
            "id": spot_id,
            "name": name,
            "slug": spot_slug,
            "water_type": spot.get("water_type", "sea"),
            "latitude": spot.get("latitude"),
            "longitude": spot.get("longitude"),
            "tide_state": spot.get("tide_state", "any"),
            "sports": configured,
            "detail_entity_id": detail_eid,
            "pills": pills,
        })

    payload = {
        "manifest_version": manifest_version,
        "generated_at": generated_at,
        "sports": sports_meta,
        "rider": rider_out,
        "spots": spots_out,
    }
    payload["config_hash"] = _config_hash(payload)
    return payload
