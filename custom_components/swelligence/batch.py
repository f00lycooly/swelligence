"""Shared Open-Meteo batch loader — two calls serve every spot.

Open-Meteo is the only forecast provider, so a single batched fetch covers all
spots. Each per-spot :class:`SpotCoordinator` calls :meth:`get`; the first call
after the TTL expires fetches every registered coordinate in two batched
Open-Meteo calls (one forecast + one marine) and caches the per-spot results. An
``asyncio.Lock`` dedups concurrent refreshes so a cycle of coordinators triggers
exactly one batch, not one fetch each.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from .providers.base import SpotForecast
from .providers.open_meteo import OpenMeteoProvider


class OpenMeteoBatchLoader:
    """TTL-cached batched Open-Meteo fetch shared across spot coordinators."""

    def __init__(self, session, registry, *, days: int = 7, ttl_minutes: int) -> None:
        # registry: spot_id -> (latitude, longitude, want_marine)
        self._session = session
        self._registry: dict[str, tuple[float, float, bool]] = dict(registry)
        self._order = list(self._registry)
        self._days = days
        self._ttl = timedelta(minutes=max(1, ttl_minutes))
        self._cache: dict[str, SpotForecast] = {}
        self._fetched_at: datetime | None = None
        self._lock = asyncio.Lock()

    async def get(self, spot_id: str) -> SpotForecast | None:
        """Return the cached forecast for a spot, refreshing the batch if stale."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            if (
                self._fetched_at is None
                or now - self._fetched_at >= self._ttl
                or spot_id not in self._cache
            ):
                await self._refresh(now)
            return self._cache.get(spot_id)

    async def _refresh(self, now: datetime) -> None:
        provider = OpenMeteoProvider(self._session)
        coords = [self._registry[sid] for sid in self._order]
        forecasts = await provider.async_fetch_many(coords, days=self._days)
        self._cache = dict(zip(self._order, forecasts))
        self._fetched_at = now
