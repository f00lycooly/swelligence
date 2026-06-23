# Deploying Swelligence to live Home Assistant (smoke test — `c1v.14`)

Runbook for a manual (non-HACS) install onto the Tower HA instance. All facts
below were verified 2026-06-23.

> ⚠️ **Site-specific.** This file contains internal hostnames, IPs, container
> names and Vault paths (no secret *values*). **Sanitise or remove it before any
> public GitHub mirror** — see the "publishable position" note in CLAUDE.md.

## Target environment

| Item | Value |
| --- | --- |
| HA container (Unraid Docker) | `homeassistant` (`lscr.io/linuxserver/homeassistant`) |
| HA config dir (direct disk) | `/appdata/homeassistant` |
| HA API | `http://192.168.1.3:8123` |
| HA version | 2026.6.4 (≥ `hacs.json` min 2025.7.0 ✓) |
| `ai_task` integration | present ✓ (LLM verdict path viable) |
| Python deps to install | none (`manifest.json` `requirements: []`) |

## Secrets (HashiCorp Vault)

The HA tokens live in Vault — **never copy the values into this repo**. The admin
token authenticates retrieval.

| Secret | Vault path | Field |
| --- | --- | --- |
| HA service/API token (read + service calls) | `knowledge/homeautomation/dev/env` | `HA_TOKEN` |
| HA base URL (`http://192.168.1.3:8123`) | `knowledge/homeautomation/dev/env` | `HA_URL` |
| HA long-lived token | `knowledge/homeautomation/dev/api-keys` | `HA_LONG_LIVED_TOKEN` |

Retrieve into the shell for the verification steps:

```bash
export VAULT_ADDR="https://vault.int.bagofholding.co.uk"
export VAULT_TOKEN=$(cat ~/.vault-creds/admin-token)
HA_TOKEN=$(vault kv get -field=HA_TOKEN knowledge/homeautomation/dev/env)
HA_URL=$(vault kv get -field=HA_URL knowledge/homeautomation/dev/env)
```

## 1 — Deploy the files

Copy the package into HA's `custom_components` (excludes Python caches; does not
touch any other integration):

```bash
rsync -a --delete --exclude '__pycache__' \
  /workspace/swelligence/custom_components/swelligence/ \
  /appdata/homeassistant/custom_components/swelligence/
```

## 2 — Restart HA and wait for the API

> Briefly interrupts home automation. Restart deploys the new integration code.

```bash
docker restart homeassistant
until curl -sf -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/" >/dev/null; do
  sleep 3; echo "waiting for HA..."
done
echo "HA back up"
```

## 3 — Add the integration + spots (UI)

1. **Settings → Devices & Services → Add Integration → Swelligence**.
2. Choose sports + provider **Open-Meteo** (no key). Optionally enable AI Task.
3. Integration **options → Add a favourite spot** for each Christchurch spot:

   | Spot | Lat | Lon | Water | Sports |
   | --- | --- | --- | --- | --- |
   | Christchurch Harbour | 50.728 | -1.745 | sheltered | windsurf, wingfoil, sup, sailing, seaswim, wakeboard_sea |
   | Avon Beach | 50.736 | -1.733 | sea | surf, sup, kitesurf, windsurf |
   | Bournemouth Pier | 50.713 | -1.876 | sea | surf |
   | Sandbanks | 50.687 | -1.943 | sea | kitesurf, windsurf, wingfoil |
   | New Forest Water Park | 50.9016 | -1.7801 | inland | wakeboard_inland, sup |
   | Hurst Spit / Keyhaven | 50.711 | -1.553 | sea | kitesurf, windsurf, wingfoil |

4. Optionally **options → Rider profile & quiver** (weight + kite/wing sizes)
   and **options → Tune a spot's preferences** (e.g. surf offshore = N/NNW/NW for
   the south-facing beaches).

## 4 — Verify (API)

```bash
# Entities created per (spot × sport)?
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" \
  | python3 -c "import sys,json;[print(s['entity_id'],'=',s['state']) for s in json.load(sys.stdin) if s['entity_id'].startswith(('sensor.swelligence','binary_sensor.swelligence'))]"

# Inspect one sensor's attributes (score breakdown / kit advice)
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/states/sensor.swelligence_hurst_spit_keyhaven_kitesurf_suitability" | python3 -m json.tool

# Any load/runtime errors?
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/error_log" | grep -i swelligence
docker logs homeassistant --since 5m 2>&1 | grep -i swelligence
```

**Pass criteria:** integration loads without error; a device per spot; a
`sensor.*_suitability` + `binary_sensor.*_suitable_now` per (spot × sport);
scores in the same ballpark as `scripts/validate_spots.py`; inland NFWP shows no
wave/temp factors; kite/wing sensors carry `recommended_size_m2`/`power` when a
rider quiver is set.

## Rollback

```bash
rm -rf /appdata/homeassistant/custom_components/swelligence
docker restart homeassistant
```
