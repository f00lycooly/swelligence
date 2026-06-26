# Changelog

All notable changes per release. Versions follow semver; tags are `vX.Y.Z`.

## v0.1.7 — 2026-06-26

- feat(card): rework spot-detail mode to 720-panel layout + multi-spot tabs

## v0.1.6 — 2026-06-25

- fix(card): use after_dependencies for frontend/http; make card reg non-fatal

## v0.1.5 — 2026-06-25

- fix(manifest): declare frontend + http dependencies (hassfest)

## v0.1.4 — 2026-06-25

- feat(card): bundle the Lovelace card with the integration (auto-register)

## v0.1.3 — 2026-06-25

- feat(card): spot-detail mode — single-spot now/week (tide, outlook, best-day)
- feat(integration): get_spot_detail service — per-spot now/week data for the card
- fix(card): expose water_type for the medallions/heatgrid water chip
- feat(panel): Best-day pane shows peak-hour conditions incl. tide + water
- feat(mockup): make panel Now⇄Week a full view change, not just a chart swap
- feat(integration): tide_state + daytime weekly outlook as integration data points
- feat(mockup): 7-day midday samples + weekly outlook toggle on the panel
- feat(mockup): make the 720 panel time-aware — NOW, tide state, hourly outlook
- feat(mockup): 720x720 LVGL marine-instrument wall panel (touch, frontend-design)
- feat(mockup): always show wind needle in light wind (calm = no data only)
- feat(mockup): enlarge map hero; wind as a vane with speed/gust on it
- feat(mockup): map hero with at-a-glance wind overlay on spot-detail card
- feat(mockup): regenerate spot-detail card — HA-themed, single-source, real data
- docs(samples): add Mudeford + Sandbanks real samples (sensors + forecast)
- docs(data-model): document entities/attributes/services/raw fields + real spot sample

## v0.1.2 — 2026-06-24

- feat(config-flow): map picker + UK postcode search for add-spot
- fix(release): publish CHANGELOG summary as the GitHub Release body (HACS notes)

## v0.1.1 — 2026-06-24

- feat(config-flow): search-first add-spot (place-name geocoding primary)

## v0.1.0 — 2026-06-24

- ci(release): ignore HACS `brands` check for custom repository (ckl.3)
- feat(release): force push-mirror sync on release (sync-on-release model) (ckl.4)
- ci(release): HACS release pipeline — tag-triggered Action + bump helper (ckl.1)
- feat(scoring): factor completeness semantics + essential-missing cap (slh.1)
- docs(mockups): add spot-detail card mockup + template
- docs(scoring): record fairness/safety review limitations; file epic swelligence-slh
- docs: document single-source architecture + full scoring reference
- feat(open-meteo): batch all spots into two calls (akc)
- feat(open-meteo): capture 12 additional-detail fields (live-validated names)
- refactor(providers): remove Stormglass provider (single-source forecast)
- feat(providers): add NOAA CO-OPS tide provider (US, free/no-key, harmonic)
- feat(providers): Open-Meteo modeled tide fallback (keyless global, priority 0)
- refactor(providers): declarative overlay-capability model + region resolver
- refactor(providers): remove Windy provider (single-source simplification)
- docs(research): marine data API research — batching, field mapping, providers
- docs(claude): document deployment approach + build/test commands
- docs(readme): document o07 confidence & source-intelligence features
- feat(authority): provider-authority map + 'better source' nudges (o07.4)
- feat(llm): confidence + sources in the AI Task verdict (o07.5)
- feat(confidence): cross-provider ensemble spread + consensus blend (o07.3)
- feat(confidence): Stormglass intra-model agreement -> confidence (o07.2)
- feat(quality): per-sensor data_quality attribute (o07.1)
- fix(config_flow): define _PROVIDER_ROUTE_OPTIONS after _PROVIDER_OPTIONS
- feat(routing): per-spot, per-domain source routing (al8.4)
- feat(scoring): swell-quality scoring for surf (period + direction) — al8.3
- feat(coordinator): budget-aware marine gap-fill overlay (al8.2)
- feat(scoring): tide awareness for tide-dependent spots (M5 / c1v.6)
- feat(providers): per-domain source provenance in source_meta (al8.1)
- feat(providers): Free-tier toggle auto-throttles polling to the daily budget
- ci: re-trigger after runner workspace bind-mount fix
- fix(manifest): sort keys (domain, name, then alphabetical) for hassfest
- ci: run hassfest host-mode, drop HACS (Forgejo-incompatible)
- fix(ci): put repo root on sys.path for the HA guard suite
- ci: validate runner egress under new Proxmox firewall
- ci: re-trigger after docker_host=automount (test hassfest/hacs)
- ci: re-trigger after runner PATH fix (node toolcache now resolvable)
- ci: re-trigger workflow after runner label fix
- feat(card): move sport priority to a draggable card editor; drop integration option
- feat(providers,config-flow,ci): keyed providers, geocoding, spot editing, HA guard
- chore: gitignore .superpowers design artifacts and untrack them
- feat(card): optional score (show_score) on ring views
- fix(card): podium rings icon-led too (icon 22/26px, score 10/11px secondary)
- fix(card): medallions — icon is the hero, score secondary (ring shows score)
- fix(card): apply spot/sport filters to forecast modes + add days filter
- feat(card): visual editor (ha-form) + card picker preview
- feat(card): multi-mode Lovelace card — podium/timeline/heatgrid/medallions (c1v.19)
- feat(overview): get_overview service + pure overview.py (c1v.18)
- feat(preference): sport priority order + ranking helper (c1v.17)
- feat(card): M3 Lovelace suitability matrix + forecast drill-down
- feat(forecast): 7-day suitability forecast via get_forecast service (M9)
- docs(scope): finalize M9 forecast delivery per HA weather best-practice
- fix(config): NumberSelector step=0.0001 rejected by HA -> step=any for coords
- fix(entity): import DeviceInfo from device_registry (fixes live HA load)
- docs: live-HA deploy runbook + Vault token references for smoke test (c1v.14)
- feat(personalisation): quiver-aware kite/wing scoring + kit recommendation (M8)
- feat(sizing): rider sizing model — weight/wind -> ideal kite/wing size (M8)
- test(M7): pytest suite for scorer, overrides, policy, provider normalisation
- feat(config): M1 per-spot preference overrides (offshore wind dirs + windows)
- fix(scoring): recalibrate wing/kite upper end against 3 weeks of history
- fix(scoring): graduated wave factor + softer gust handling (profile calibration)
- fix(provider): suppress nearest-coastal marine data for inland/sheltered spots
- docs(scope): scope personalisation to a single local rider
- docs(scope): add rider personalisation (weight + quiver) to M8
- test: add live Open-Meteo spot validation runner + decouple base from aiohttp
- chore: onboard repo to beads
- bd init: initialize beads issue tracking
- chore: point project URLs at Forgejo instead of GitHub
- feat: scaffold Swelligence — water/wind-sports suitability integration
