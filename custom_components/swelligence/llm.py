"""AI Task (LLM) enrichment layer.

Uses Home Assistant's ``ai_task.generate_data`` action with a JSON ``structure``
so the configured conversation agent (Claude/OpenAI/local) returns a *structured*
suitability verdict, not free prose. The deterministic score is always passed in
as context — the LLM is asked to interpret and add nuance ("offshore and
building — go early"), and its rating sits alongside, never replaces, the number.

The structured-output result is written back onto the matching ``SportResult``.
"""

from __future__ import annotations

import json
import logging

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# JSON schema for the structured AI Task response.
_STRUCTURE = {
    "type": "object",
    "properties": {
        "spots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sport": {"type": "string"},
                    "rating": {
                        "type": "integer",
                        "description": "0-100 suitability rating",
                    },
                    "summary": {
                        "type": "string",
                        "description": "One concise sentence of advice",
                    },
                },
                "required": ["sport", "rating", "summary"],
            },
        }
    },
    "required": ["spots"],
}


def _build_prompt(spot: dict, forecast, results, profiles) -> str:
    current = forecast.current()
    lines = [
        f"Spot: {spot['name']} ({spot['latitude']:.3f}, {spot['longitude']:.3f}).",
        f"Provider: {forecast.provider}. {forecast.source_meta}.",
        "Current conditions:",
        f"  wind {getattr(current, 'wind_speed_kn', None)}kn "
        f"gust {getattr(current, 'wind_gust_kn', None)}kn "
        f"dir {getattr(current, 'wind_dir_deg', None)}°, "
        f"wave {getattr(current, 'wave_height_m', None)}m, "
        f"water {getattr(current, 'water_temp_c', None)}°C.",
        "",
        "Deterministic scores (your rating should broadly agree unless you can "
        "justify otherwise):",
    ]
    for sport, res in results.items():
        prof = profiles.get(sport)
        label = prof.label if prof else sport
        line = (
            f"  - {label} ({sport}): now={res.now.score} ({res.now.verdict}); "
            f"factors={res.now.factors}; notes={res.now.reasons}"
        )
        if getattr(res, "kit", None) and res.kit.summary:
            line += f"; kit: {res.kit.summary} ({res.kit.power})"
        lines.append(line)
    lines.append(
        "\nReturn a rating (0-100) and a one-sentence verdict per sport, written "
        "for an experienced rider deciding whether to go."
    )
    return "\n".join(lines)


async def async_semantic_verdict(
    hass: HomeAssistant,
    *,
    ai_entity_id: str,
    spot: dict,
    forecast,
    results,
    profiles,
) -> None:
    """Call ai_task.generate_data and merge results back onto SportResults."""
    prompt = _build_prompt(spot, forecast, results, profiles)
    response = await hass.services.async_call(
        "ai_task",
        "generate_data",
        {
            "task_name": f"swelligence_{spot['id']}",
            "entity_id": ai_entity_id,
            "instructions": prompt,
            "structure": _STRUCTURE,
        },
        blocking=True,
        return_response=True,
    )

    data = (response or {}).get("data")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            _LOGGER.debug("AI Task returned non-JSON data; skipping enrichment")
            return
    if not isinstance(data, dict):
        return

    for item in data.get("spots", []):
        sport = item.get("sport")
        if sport in results:
            results[sport].llm_rating = item.get("rating")
            results[sport].llm_summary = item.get("summary")
