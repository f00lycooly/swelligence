"""Unit tests for the shared Open-Meteo batch loader."""

from __future__ import annotations

import asyncio

from swelligence import batch
from swelligence.providers.base import SpotForecast


class _FakeProvider:
    """Records calls and returns one SpotForecast per requested coord."""

    instances: list["_FakeProvider"] = []

    def __init__(self, session):
        self.calls = 0
        _FakeProvider.instances.append(self)

    async def async_fetch_many(self, coords, *, days=7):
        self.calls += 1
        return [
            SpotForecast(provider="open_meteo", latitude=lat, longitude=lon)
            for lat, lon, _ in coords
        ]


def _loader(monkeypatch, ttl_minutes=30):
    monkeypatch.setattr(batch, "OpenMeteoProvider", _FakeProvider)
    _FakeProvider.instances.clear()
    registry = {
        "a": (50.0, -1.0, True),
        "b": (51.0, -2.0, False),
    }
    return batch.OpenMeteoBatchLoader(None, registry, ttl_minutes=ttl_minutes)


def test_loader_returns_per_spot_forecast(monkeypatch):
    loader = _loader(monkeypatch)
    fa = asyncio.run(loader.get("a"))
    assert fa.latitude == 50.0 and fa.longitude == -1.0


def test_loader_one_batch_serves_all_spots(monkeypatch):
    loader = _loader(monkeypatch)

    async def scenario():
        a = await loader.get("a")
        b = await loader.get("b")  # within TTL -> reuse the same batch
        return a, b

    a, b = asyncio.run(scenario())
    assert a.latitude == 50.0 and b.latitude == 51.0
    # Both spots served by a single batched fetch (one async_fetch_many call).
    assert sum(p.calls for p in _FakeProvider.instances) == 1


def test_loader_unknown_spot_is_none(monkeypatch):
    loader = _loader(monkeypatch)
    assert asyncio.run(loader.get("missing")) is None
