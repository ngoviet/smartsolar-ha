# SmartSolar MPPT Home Assistant Integration

> **System info**: [../System_info/CLAUDE.md](../System_info/CLAUDE.md) — HA at 192.168.10.15, network, credentials
> **Code search**: `semble search "query" .` — intent-based, ~98% fewer tokens than grep

Home Assistant custom integration for SmartSolar MPPT solar charge controllers. Fetches real-time metrics via HTTP API from `api.smartsolar.io.vn` and MQTT WebSocket Secure from `mqttx.smartsolar.io.vn:8084`. **Current version: v2.0.2**. Verified live against HA **2026.9.4** on 2026-09-28 (v2.0.2 tree; the test extra pins that same version).

> ⚠️ **v2.0.0 renamed the domain from `smartsolar_mppt` to `smartsolar_ha`.**
> Home Assistant identifies an integration by its folder name, which must equal
> `manifest["domain"]` (`loader.Integration.resolve_from_root()` looks for
> `custom_components/<domain>/manifest.json`), and the domain may only contain
> lowercase letters and underscores — so this is a breaking change: existing
> config entries must be re-added. Entity names were left untouched, so entity
> IDs, dashboards and long-term statistics survive. `smartsolar_mppt` strings
> still appearing in this file are historical notes or entity-name-derived IDs.

## Project Structure

```
custom_components/smartsolar_ha/
├── __init__.py          # Integration entry point, setup/unload, service registration, async_migrate_entry
├── manifest.json        # v2.0.2, domain=smartsolar_ha, config_flow=true
├── const.py             # Constants, SENSOR_TYPES, AGGREGATION, MQTT config, build_device_info helper
├── helpers.py           # Pure helpers: coerce_float, device_logs, as_list, stream_dict, guid_sort_key
├── config_flow.py       # Multi-step config flow: auth → mode → device/project, reauth, reconfigure
├── api.py               # HTTP API client: login, token refresh, real retry/backoff, get_device_status
├── mqtt_client.py       # MQTT client: WSS connect, subscribe, payload parsing, auto-reconnect
├── coordinator.py       # DataUpdateCoordinator: polls API + merges MQTT real-time data + daily stats
├── sensor.py            # Sensor entities (device, project synthesis, project device, daily stats)
├── number.py            # Update-interval entity (RestoreEntity, 1-30s)
├── diagnostics.py       # Config entry diagnostics with secret redaction
├── brand/               # icon.png (256), icon@2x.png + logo.png (512) — HA serves these locally
├── services.yaml        # Service definitions
├── strings.json         # UI strings (English)
└── translations/        # en.json, vi.json
```

> ℹ️ **Brand images:** Home Assistant serves a custom integration's own logo from
> `custom_components/<domain>/brand/` (`loader.Integration.has_branding` checks
> that FOLDER). There is no `brand` key in the manifest schema — HA ignores one,
> so a manifest `brand` block only ever looks like branding that is configured.
> `.gitignore` re-includes `brand/logo.png` because the global `logo.png` rule
> would otherwise hide it from git.

Root-level files:
```
hacs.json                # HACS metadata (content_in_root=false, min HA 2026.9.0)
pyproject.toml           # Python project config: ruff, mypy, pytest, [test] extra with homeassistant
.pre-commit-config.yaml  # Pre-commit hooks: ruff, yaml/json checks
LICENSE                  # MIT License
upload_to_ha.py          # Minimal uploader: paramiko SSH + base64 + sudo tee
deploy_to_ha.py          # Full deploy gate: lint+types+tests → backup → upload → restart → wait
verify_live.py           # Asserts the deployed entities are correct on the live instance
tests/
├── conftest.py           # Shared fixtures: mock HA, recorded API responses (deep-copied), coordinator
├── test_api.py           # API client, error hierarchy, retry/backoff, expiry parsing, token invalidation
├── test_sensor.py        # Value extraction, naming, per-sensor aggregation, non-finite rejection
├── test_helpers.py       # coerce_float / as_list / device_logs / stream_dict / guid_sort_key
├── test_mqtt.py          # MQTT payload parsing (both firmware formats), field mapping, reconnect loop
├── test_number.py        # Interval get/set, bounds, RestoreEntity behaviour
├── test_config_flow.py   # Every config-flow step, error mapping, translations
├── test_coordinator.py   # Polling, GUID ordering, daily stats, malformed payloads, MQTT robustness
├── test_diagnostics.py   # Diagnostics content + secret redaction
├── test_const.py         # Sensor metadata invariants
├── test_packaging.py     # manifest.json / hacs.json / brand-asset invariants
├── test_verify_live.py   # verify_live.py payload handling and exit codes
├── test_deploy_script.py # deploy_to_ha.py prune/archive/wait + local-gate == CI
└── test_e2e.py           # Real async_setup_entry/unload_entry against a real HA core
.github/workflows/
├── ci.yml                # ruff check + format, mypy (hard gate), pytest with coverage
├── hacs-validation.yml   # HACS validation on push/PR
└── release.yml           # GitHub release on tag push (notes generated by GitHub)
```

> ℹ️ These workflows run directly now that the project is its own repository.
> Before the split (2026-09-27) the project lived in `smartsolar_mppt/` inside the
> private HA-Config repo, where GitHub ignored them because it only reads
> workflows from the repository root — a root shim re-ran the same gate, and the
> two copies drifted. That shim is gone.

## Architecture & Data Flow

### API (`api.smartsolar.io.vn`)

1. **Auth**: `POST /Auth/Login?Key=Content-Type` with `{username, password}` → token + expiry
2. **Token refresh**: Auto-refresh when within 7 days of expiry
3. **Retry logic**: Exponential backoff for network errors and 5xx responses. With `RETRY_MAX_ATTEMPTS = 3` the waits are 1 s then 2 s (`RETRY_BACKOFF_FACTOR ** attempt` over `attempts - 1` gaps)
4. **Device mode**: `GET /Device/Status?deviceGuid={guid}` → `{lastMessage: {dataStreams: [...]}, mqttConnection: {username, password}}`
5. **Project mode (by ID)**: `GET /Metric/ProjectMetrics?projectId={id}` → `{synthesisStreams, deviceLogs}`
6. **Project mode (by devices)**: `GET /Metric/SynthesisMetrics?deviceType={type}&deviceGuids={id1}&deviceGuids={id2}` → same structure
7. **MQTT Device Status**: `GET /Device/Status?deviceGuid={guid}` (used in project mode to extract mqttConnection credentials)

### MQTT (`mqttx.smartsolar.io.vn:8084`)

1. **Transport**: WebSocket Secure (WSS) at path `/mqtt`
2. **Credentials**: Auto-discovered from REST API `mqttConnection` field — username `web_app`, password base64-encoded
3. **Topics**: `manhquan/device/mppt_charger/log/+/<deviceGuid>` (single-level `+` wildcard for model)
4. **Payload format A** (newer firmware, `command: update_device_metrics`): `{dataStreams: [{name, value}, ...], signalQuality, command, deviceGuid, espId, firmwareVersion, messagesCounter}` — `signalQuality` is at the top level, NOT inside `dataStreams`
5. **Payload format B** (older firmware, `command: updateDeviceLog`): `{dataStreams: [{stream, name, value, unit}, ...], deviceGuid}` — carries **no** `signalQuality`, so that device's WiFi sensor stays `unknown`
6. **Payload format C** (legacy): flat dict with keys like `charging_power`, `yield_today`, mapped through `MQTT_FIELD_MAPPING`
7. **Restart-less upgrades are not supported: the MQTT subscription set and the
   entity set are both fixed at setup time.** A device that appears in a later
   poll is merged into `coordinator.data` and accepted by
   `coordinator._is_tracked_device()`, but it gets **no entities** (sensor.py
   only adds entities during `async_setup_entry`) and is **not subscribed to**
   for live data until Home Assistant restarts. Deliberate: per-device sensors
   are named `PV1`, `PV2`, … from the sorted GUID order, so inserting a device
   with a lower GUID would renumber the existing entities and break every
   dashboard reference to them.
8. **Reconnection**: Auto-reconnect every 5s on disconnect; graceful degradation to REST polling

> ⚠️ **The broker is shared by every SmartSolar customer.** A subscription to
> `manhquan/device/mppt_charger/log/+/#` receives hundreds of foreign devices.
> Only the per-device topics for this config entry are subscribed, and
> `coordinator._is_tracked_device()` rejects any other GUID in the callback.

### Data Flow

```
Config Entry (username, password, mode, chipset_ids/project_id)
    ↓
    ├── SmartSolarAPI ──────────────────────────────────────────────┐
    │   (login → token → periodic refresh, retry w/ backoff)        │
    │   POST /Auth/Login, GET /Metric/*, GET /Device/Status         │
    ↓                                                                │
    ├── SmartSolarMQTTClient ───────────────────────────────────────┤
    │   (WSS connect → subscribe topics → parse payloads)           │
    │   mqttx.smartsolar.io.vn:8084/mqtt                           │
    │   Auto-discovers mqttConnection from API response             │
    ↓                                                                │
SmartSolarDataUpdateCoordinator                                     │
    (polling every N seconds + real-time MQTT merge)                │
    async_process_mqtt_data() → _merge_mqtt_into_data()             │
    _schedule_mqtt_notify() → async_update_listeners()  (1 Hz cap)  │
    ↓
Sensor Entities (CoordinatorEntity + RestoreEntity, ×13 types)
Number Entity (Update Frequency, 1-30s)
```

### Sensor Types

13 sensor types per device: 10 live metrics (`pv_voltage`, `pv_current`, `bat_voltage`, `bat_current`, `charge_power`, `today_kwh`, `total_kwh`, `temperature`, `signal_quality` (WiFi %, via MQTT or REST), `status`) plus 3 daily stats (`peak_power_today`, `avg_power_today`, `production_hours_today`)

### Four Sensor Classes

| Class | Mode | Data Source |
|-------|------|-------------|
| `SmartSolarDeviceSensor` | Device | `data.lastMessage.dataStreams` |
| `SmartSolarProjectSynthesisSensor` | Project | `data.synthesisStreams` (fallback: per-type aggregation from deviceLogs) |
| `SmartSolarProjectDeviceSensor` | Project | `data.deviceLogs[deviceGuid].dataStreams` |
| `SmartSolarStatsSensor` | Both | `coordinator.get_daily_stats(guid)` — peak/avg/production-hours for today |

#### Cross-device aggregation (`const.AGGREGATION`)

When the project total comes from the individual device logs, each sensor type
has its own strategy. **Voltage and temperature are averaged, never summed** —
both chargers sit on the same 24 V bus, so summing reports ~53 V:

| Strategy | Sensor types |
|----------|--------------|
| `sum` | pv_current, bat_current, charge_power, today_kwh, total_kwh |
| `average` | pv_voltage, bat_voltage, temperature, signal_quality |
| `max` | status (worst case) |

Sensors in `const.UNRELIABLE_SYNTHESIS_SENSORS` (charge_power, currents,
signal_quality) always aggregate locally because the server's
`synthesisStreams` value is frequently stale or absent.

## v2.0.2 — Repository Rename (2026-09-28)

No integration code changed: the domain, entity names, `unique_id`s, services
and config-entry keys are identical to v2.0.1, so an existing entry keeps
working and no re-add is needed. This release republishes the metadata that
named the old repository.

- The GitHub repository was renamed `ngoviet/smartsolar-ha` →
  **`ngoviet/smartsolar_ha`**, so the repository slug, the integration domain and
  the manifest's `documentation`/`issue_tracker` finally agree. GitHub 301-
  redirects the old slug, so existing clones and HACS installs keep resolving;
  every README badge, link, the documented `git clone` command and the
  `my.home-assistant.io` HACS link now use the canonical URL. The repository
  name is still unrelated to the domain — HA resolves an integration from
  `custom_components/<domain>/`, never from GitHub.
- The README test badge is now the **CI workflow badge** rather than a
  hard-coded `N passed` shield. The static figure had gone stale twice — it read
  366 while the tree had 551, then 555 while the tree had 553 — so the badge now
  reports the CI run itself instead of a number that has to be remembered. The
  suite reports **561 passed, 1 skipped**.
- Added after the release tag, still without touching integration code:
  `deploy_to_ha.py` now waits until this integration's config entry reports
  `loaded` before it calls the deploy done, so `verify_live.py` can be chained
  straight to it (it used to see **zero** entities); and the `[test]` extra pins
  `homeassistant==2026.9.4` — the version the live instance actually runs — so
  the gate stops testing an older Home Assistant than production.
- Carried over from the deploy-extra review pass (already on `main`): the
  `deploy` extra is pinned precisely and covered by a behavioural import test
  instead of source parsing.

> The v2.0.1 section below records that audit's own numbers (tests 366 → 551).
> The suite has grown since — the deploy-extra pass changed it by +2 net and the
> deploy-readiness waits added 8 — which is why the current tree reports 561
> passed.

## v2.0.1 — Second Audit (2026-09-27)

Full re-audit of every module, script and workflow: 27 real bugs fixed, tests
**366 → 551**, ruff/format/mypy still clean. Every new unit test was verified to
FAIL against the pre-fix code (65 of them did). Two tests that *encoded* a bug
(device mode accepting several chipset ids) were corrected as well.

| # | Bug | Fix |
|---|-----|-----|
| 1 | **The synthesis path bypassed every value guard.** `SmartSolarProjectSynthesisSensor` read the server's `synthesisStreams` with a bare `float()`, so NaN/Infinity were published as entity states (poisoning long-term statistics — the exact failure v2.0.0 #2 fixed for the per-device path) and the per-sensor `max_value` ceiling was skipped, letting a firmware sentinel like `2147483.647` V become a voltage state | The server value now goes through the same `_convert_stream_value()` as the per-device path; an unusable value falls back to local aggregation instead of being published |
| 2 | **`OverflowError` escaped `native_value`.** Status mapping called `int(float(value))` guarded only by `except (ValueError, TypeError)`: `int(float("inf"))` raises `OverflowError`, and `int(nan)` raises `ValueError` in the synthesis path. One malformed status stream turned into an entity update error | New `_status_text()` maps through `coerce_float()` (which rejects every non-finite value), so the `int()` below is total; both paths use it |
| 3 | `api._normalize_device_guids()` iterated `data.get("deviceLogs", []) or []` directly, so `"deviceLogs": 5` raised `TypeError` and **failed the whole poll** — the same bug class v2.0.0 #1 fixed for the coordinator, sensors and diagnostics | Uses the shared `helpers.device_logs()` |
| 4 | **MQTT reconnected in a tight loop.** `_message_loop` only slept in the exception path, so a broker that closed the subscription *cleanly* sent the client straight back into connect, hammering a broker shared by every SmartSolar customer | A clean stream end now waits `MQTT_RECONNECT_DELAY` like a failure does |
| 5 | **Cancellation during the reconnect backoff skipped the cleanup tail.** The `await asyncio.sleep()` sat *inside* the `except` handler, so a `CancelledError` there propagated past `self._connected = False` / `self._client = None`, leaving diagnostics reporting a live connection and a dead client reference | The whole loop is wrapped in `try/finally`; `stop()` also clears `_client` |
| 6 | **`async_step_reconfigure` wrote credentials without validating them.** A blank field was stored as-is, and the next reload then failed `async_setup_entry`'s required-key check — so reconfiguring with an empty password silently took a working integration down. A typo was written just as blindly | Blank fields are rejected (`username_required` / `password_required`) and the credentials are proven with `test_connection()` before anything is written; reauth already did this |
| 7 | **The `refresh_token` service outlived its config entry.** It is registered in `async_setup_entry`, and Home Assistant only removes services an integration removes itself — so after deleting the integration the service stayed in the registry and every call raised `ServiceValidationError` | `async_unload_entry` removes it once no other entry of the domain remains |
| 8 | `verify_live.py` crashed with an uncaught `TypeError`/`AttributeError` on `"deviceLogs": null` (or a non-mapping entry) — the same payload the integration treats as "no device logs", in a script whose job is to *report*, not traceback | Defensive list handling and a wider `except` |
| 9 | **The reauth and reconfigure dialogs had no translations.** Both `async_show_form()` calls used step ids that `strings.json`/`translations/*.json` never declared, and `async_abort(reason="unknown_entry")` had no translation either, so the UI showed raw field keys and reason strings | Added `reauth`, `reconfigure` and `unknown_entry` to `strings.json`, `en.json` and `vi.json`; a test asserts all three files declare every step id the flow shows |
| 10 | `manifest.json` carried a **`brand` block that does nothing**: Home Assistant has no such manifest key, branding comes from a `custom_components/<domain>/brand/` folder (`loader.Integration.has_branding`), and the referenced `logo.png`/`icon.png` were not in that folder and gitignored | Removed the dead key and shipped real `brand/icon.png` (256), `brand/icon@2x.png` + `brand/logo.png` (512) from the existing 512×512 logo, re-included in `.gitignore` |
| 11 | `clear_entities.ps1` could **corrupt Home Assistant's registries**: a `Where-Object` pipeline unrolls a single result into a scalar, so `ConvertTo-Json` wrote `"entities": { ... }` — or `"entities": null` when everything was removed — where HA requires a list. It also only matched the *current* domain, so the legacy `smartsolar_mppt` entities/devices it exists to clean were left behind, and `Set-Content -Encoding UTF8` writes a BOM that breaks HA's JSON parsing | Every assignment is wrapped in `@()`; both domains are matched (by identifier *domain*, not by `-notmatch` on an array); UTF-8 without BOM; refuses to run while HA still answers on its API, because HA rewrites `.storage` on shutdown and would discard the edit |
| 12 | Deploy/upload scripts: `restart_ha` hardcoded `http://{HA_HOST}:8123` so a configured `HA_URL` was ignored (and `HA_URL` was otherwise dead code); `archive_remote` discarded tar's exit status and reported "archived 0 bytes" for a failed archive, silently leaving **no rollback point**; `upload_to_ha.py` died with `KeyError: 'HA_PASS'` before printing anything | `restart_ha` uses `HA_URL`; the archive warns loudly when there was nothing to archive; the legacy `smartsolar_mppt` folder on the host is now detected and reported; a missing `HA_PASS` reports instead of raising |
| 13 | **`async_migrate_entry` could fail or corrupt an entry.** Iterating a legacy scalar `chipset_ids` raised `TypeError`, so the migration never completed and the entry stayed at v1.1; a comma-separated *string* was iterated per character, turning `"547611,14756976"` into `["5", "4", "7", …]` | `_normalize_chipset_ids()` splits strings on commas and always stores a list (a scalar becomes `[]` instead of an un-iterable value) |
| 14 | **A zero/negative `update_interval` produced a tight polling loop.** The value comes from plain JSON on disk, and `DataUpdateCoordinator._schedule_refresh` schedules the next poll *in the past* for interval 0 — so a hand-edited entry hammered the cloud API. Garbage (`"abc"`, a bool) raised `TypeError` during setup | `_resolve_update_interval()` clamps to the same 1-30 s range the Number entity enforces, and falls back to the default for non-numeric values |
| 15 | **MQTT credentials were only read from the first device.** They are per-*server* credentials carried in `/Device/Status`, so one offline charger (or one whose payload omits `mqttConnection`) silently disabled real-time updates for the entire project | Up to `MQTT_CREDENTIAL_ATTEMPTS` (3) devices are probed, with per-device debug logging; the bound keeps a large project from making one call per device |
| 16 | **`discovered_devices` grew forever, so a removed device kept coming back.** The set is both the "is this ours?" guard for a shared broker and the switch that lets a cached MQTT payload be merged into the response — as a union it accepted a device the project had dropped, and that device's last MQTT values re-created a phantom `deviceLogs` entry (and were summed into the project totals) on every poll, forever | The set is replaced with the current response each poll; `chipset_ids` remains the independent config-based fallback |
| 17 | **`UpdateIntervalNumber` mangled values it accepted.** `int(10.7)` silently became 10, and both `int()` and `round()` raise on NaN/Infinity — which Home Assistant's `number.set_value` lets through, because NaN passes its min/max check (every NaN comparison is False). The restore path's `int(float("inf"))` raised `OverflowError`, aborting the entity being added | `coerce_float()` rejects non-finite/non-numeric input with a warning, then the value is **rounded** to the nearest whole second |
| 18 | **The deploy only ever added files.** A module deleted or renamed in the repository stayed on the HA host forever, so the deployed tree silently drifted from the repository | `prune_remote()` deletes remote files that no longer exist locally (byte-code caches excluded, and only inside this integration's own folder) |
| 19 | `mqtt_client` used the legacy `asyncio.get_event_loop()` inside a coroutine, and rebuilt a frozenset of bookkeeping field names **for every payload** on a ~2 msg/s/device hot path | `asyncio.get_running_loop()`; the set is a module-level `BOOKKEEPING_FIELDS` constant |
| 20 | Corrupted source text and stale comments: `const.py` held the mojibake comment `# S?c MPPT M?nh Qu?n`, and the retry comment claimed "1s, 2s, 4s" backoff while `RETRY_MAX_ATTEMPTS = 3` only produces 1s then 2s. `.gitignore` listed the Python-cache rules twice | Comment corrected and re-encoded (the trees already ship Vietnamese text elsewhere); comment states the real delays; duplicate block removed |
| 21 | **A failed HTTP poll blanked out entities that MQTT was still feeding.** `CoordinatorEntity.available` is just `last_update_success`, so during a cloud outage every entity reported `unavailable` while `native_value` kept returning live MQTT readings — the values were computed, then discarded by the state machine and the recorder. The interval `number` disappeared too, so the one setting a user might change *because* of an outage could not be changed | `SmartSolarSensor.available` is true when the poll succeeded **or** live MQTT data can feed that entity; the `number` entity is always available (`coordinator.has_live_mqtt_data()`) |
| 22 | **A failing platform setup leaked everything already created.** Home Assistant does not call `async_unload_entry` for an entry whose setup failed (it retries setup), so the coordinator's poll timer + midnight listener, the aiohttp session and the MQTT task survived each attempt — and every retry added another poll timer against the cloud API. A missing `mode` reached that path as a bare `KeyError` from inside sensor.py, and HA's own `async_forward_entry_setups` does **not** roll back the platforms that already succeeded | `mode` is validated up front; the platform forward is wrapped, unloads the partially set-up platforms and runs a shared `_async_teardown()`; `async_unload_entry` also unloads platforms **before** tearing anything down, so a refused unload no longer leaves a half-dead entry |
| 23 | **Legacy metric names inside MQTT `dataStreams` were silently dropped.** The flat payload format was mapped through `MQTT_FIELD_MAPPING`, but the `dataStreams` branch stored names verbatim — so firmware publishing `charging_power` / `yield_today` / `yield_total` inside `dataStreams` had every one of those values filed under a name no sensor reads. A non-string stream name also raised inside the dict assignment | The dataStreams branch applies the same mapping (a no-op for REST-named streams) and skips non-string names |
| 24 | **Three declared tool versions could not run this repository's own gate.** `ruff>=0.4` (dev extra *and* ci.yml) cannot parse `target-version = "py314"` at all — it exits 2 with a TOML parse error — and predates PEP 758; `mypy>=1.9` reports 5 errors on the very sources `mypy 2.x` accepts; and `.pre-commit-config.yaml` pinned `ruff-pre-commit` at `v0.4.0`, so **every commit failed the hook** with exit 2. `.pre-commit-config.yaml` is version-checked by a test now | Floors raised to the verified toolchain (`ruff>=0.16`, `mypy>=2.3`, `pytest-asyncio>=1.0` for the 1.x-only ini options), pre-commit rev bumped to `v0.16.9`, and ci.yml installs `.[test,dev]` so the floors live in pyproject.toml only — pinned by `TestToolingFloors` |
| 25 | **Device mode accepted several chipset ids and published the wrong device's data.** Only `chipset_ids[0]` is ever read (the API call, the sensor prefix, the daily-stats key), so extra ids were silently ignored — but they still passed the MQTT "is this ours?" guard, and device mode merges every accepted device into one `lastMessage.dataStreams`. The second charger's live readings therefore appeared on the first charger's sensors | The config flow refuses more than one id in device mode (`single_chipset_id_required`, translated in all three languages) **and** `_is_tracked_device()` is mode-aware, so an entry that already carries stray ids cannot show wrong data either |
| 26 | **`device_types` was dead entry data.** `async_step_project_devices` wrote it into every such entry, but nothing ever read it, and it duplicated `device_type` — so project-by-devices entries had a different shape from every other flow's, contravening the documented config-key contract | Removed; a test now pins the entry-data keys to the documented set |
| 27 | **`async_step_reauth` did not validate blank fields**, unlike `async_step_user`. Blanks were sent to the API, which reported `invalid_credentials` — or `cannot_connect` when the API happened to be down, hiding the real problem behind a connectivity error | Same blank-field checks as every other entry point (`username_required` / `password_required`), before any API call |

Round 4 also audited the *tests*: two of them (`test_successful_device_entry`,
`test_device_chipset_ids_unique_id_includes_device_type`) asserted the buggy
device-mode-multi-id behaviour and were corrected, which is how the check that
"a test locks in a bug" was found in round 2 as well.

**Rounds 5-6 (saturation pass) found no further code bugs.** Those rounds
checked, and cleared, the remaining surface:

- **No Home Assistant warnings at all** during a real setup in both modes (every
  entity state was written and logged first): no `state_class`/`device_class`
  conflict, no unit mismatch, no name/`has_entity_name` complaint.
- **A systematic sweep for unsafe conversions** (`float()`/`int()`/`round()`, and
  every loop over cloud/MQTT data) — no remaining unguarded conversion.
- **No `TODO`/`FIXME`/`HACK` markers**, and every remaining `smartsolar_mppt`
  string is deliberate (legacy-folder detection, live entity-id prefix).
- **The complete audit diff was re-read** for logical errors in the fixes
  themselves; none found. Two things were considered and left alone as
  deliberate: `_is_tracked_device()`/`sensor.py` iterate `chipset_ids` without
  `as_list()` on purpose — a corrupt scalar now produces a clean logged setup
  failure plus rollback, whereas silently coercing it would create an integration
  with no entities at all; and `hass.data[DOMAIN]` in `async_unload_entry` is not
  `.get()`, because Home Assistant only calls unload for an entry that was
  loaded, which implies `async_setup` ran.
- **Test isolation and ordering**: every test file passes in its own process, and
  a different file order passes too — no cross-test state leakage.
- **Docs audited as user-facing behaviour**: the README test badge was stale
  (366), its changelog had no v2.0.1 entry, and two historical bullets claimed
  things that were never true (`allow_multiple_instances` is not a Home Assistant
  attribute; the sensors do **not** restore a stale value). Fixed, and
  `KNOWLEDGE.md`'s version banner was updated.

Also: `helpers.coerce_float()` now backs every numeric conversion in
`sensor.py` (the manual `float()` + `math.isfinite` pair is gone, so the
`import math` went with it); `__init__.py` type-checks `mqttConnection` before
calling `.get()` on it (a non-mapping used to surface as a generic "MQTT setup
failed"); the docs' claim that a late-discovered device "gets entities" was
wrong — **no entities are created after setup** (deliberate: per-device sensors
are numbered from the sorted GUID order, so a new device with a lower GUID would
renumber existing entity_ids and break dashboards).

Not changed, deliberately: the daily-stats average is an unweighted mean over
samples (MQTT publishes ~2 Hz and the poll adds one more), so `avg_power_today`
is a sample mean rather than a time-weighted one; and `diagnostics` still reports
the account `username` — there is an explicit test asserting that, since the
username is what makes a diagnostics dump traceable to an account, while the
password and token are redacted.

## v2.0.0 — Domain Rename + Audit Fixes

`smartsolar_mppt` → **`smartsolar_ha`** (folder, `manifest.domain`,
`const.DOMAIN`, imports, deploy/verify paths, docs). HA resolves an integration
as `custom_components/<domain>/manifest.json` and restricts the domain to
lowercase letters and underscores, so a hyphenated name such as `smartsolar-ha`
is not a valid *domain*, and renaming without changing the domain would make HA
fail to find the integration. (The GitHub repository name is unrelated — it
happens to be `smartsolar_ha` too, but HA never reads it.) Existing config
entries must be re-added; entity names were left alone so entity_id / dashboards
/ statistics survive. Tests: 261 → 366.

| # | Bug | Fix |
|---|-----|-----|
| 1 | `"deviceLogs": null` from the API **failed the whole poll** (`UpdateFailed: object of type 'NoneType' has no len()`) — the `len()` sat in a debug statement, and debug arguments are evaluated even when debug logging is off | Shared `helpers.device_logs()` / `as_list()` used by coordinator, sensors and diagnostics |
| 2 | **NaN/Infinity reached entity states.** `json.loads` accepts bare `NaN`/`Infinity`, NaN survives every `> max_value` check, and a NaN state poisons that sensor's long-term statistics | `coerce_float()` rejects non-finite values; `_convert_stream_value()` checks `math.isfinite` |
| 3 | A **server-rejected token was cached forever** — 401 did not invalidate it, and the ~30-day expiry kept `refresh_token_if_needed()` from re-authenticating, so every poll failed until HA restarted | `_authed_get()` clears token + expiry on 401 so the next call logs in again |
| 4 | A **non-object JSON body** (list, HTML error page) escaped as `AttributeError` / `JSONDecodeError` and was unclassified | `_json_object()` normalizes both into `SmartSolarAPIError` |
| 5 | **408/429 were treated as permanent failures** and never retried | Added to `RETRYABLE_STATUSES`; 4xx client errors still fail fast |
| 6 | Per-sensor `WARNING` on every poll (plus 1 Hz per MQTT message) when the cloud returned no device logs → log flood | Downgraded to `DEBUG` |
| 7 | MQTT `null` fields were written into `dataStreams` as the string `"None"`, shadowing the real REST value | `_mqtt_to_data_stream()` drops `None` values |
| 8 | `SmartSolarMQTTClient.connected` stayed `True` after `stop()` / a finished message loop → diagnostics reported a live connection that did not exist | Flag cleared in `stop()` and on loop exit |
| 9 | The `refresh_token` service accepted a **missing `entry_id`** and silently did nothing (contradicting `services.yaml`) | `vol.Required("entry_id")` + `ServiceValidationError` for an unknown entry |
| 10 | `allow_multiple_instances = True` in the config flow is **not a Home Assistant attribute** (verified against `config_entries.py` in 2026.9.2, re-checked in 2026.9.4) — dead, misleading code | Removed; multiple entries are allowed because the manifest omits `single_config_entry` |
| 11 | `verify_live.py` **crashed with a traceback** (instead of reporting FAIL) whenever a state was `unknown`/`unavailable`, and on a missing `HA_TOKEN` | `as_float()` helper, plus explicit messages for a missing token / unreachable instance |
| 12 | The local deploy gate linted **fewer files than CI** (`upload_to_ha.py` only, so `deploy_to_ha.py`/`verify_live.py` were unchecked) | One shared `SOURCES` list mirrored in `ci.yml` |
| 13 | Test fixtures handed out **shallow copies** of the recorded payloads while the coordinator merges MQTT data in place → cross-test contamination (two tests only passed because they compared against an object the code had already mutated) | `deepcopy` in `conftest.py` and at every mutation site; `TestFixtureIsolation` in `test_coordinator.py` |

Also fixed: `datetime.now()` → `dt_util.now()` for daily-stats minute buckets
(HA-local time, consistent with the midnight reset listener); `pyproject.toml`
now states the real Python floor (`>=3.14.2`, matching HA 2026.x) and
`ruff target-version = "py314"` (which is why `except A, B:` appears — PEP 758);
the inner `custom_components/*/hacs.json` was deleted (HACS only reads the
repository-root `hacs.json`, and that copy disagreed with it).

## v1.5.1 — Audit Fixes (2026-09-27)

Full audit: 12 real bugs fixed, ruff + mypy clean for the first time, tests
raised from 121 to 261. `mypy` used to be run with `|| true` in CI, hiding 29
type errors; it is now a hard gate.

| # | Bug | Fix |
|---|-----|-----|
| 1 | **HA was running a stale build** (1.3.0: no stats sensors, `sw_version` 1.3.0) while the repo had newer code | Deployed the current tree; version bumped to 1.5.1 across manifest/pyproject/`const.VERSION` |
| 2 | Project battery voltage could be **summed** (26.6 + 26.4 = 53 V) | Per-sensor `AGGREGATION`; voltage/temperature average |
| 3 | Synthesis `status` was **always None** — status was mapped to text before aggregation | Aggregate the numeric code, map to text afterwards |
| 4 | `DataUpdateCoordinator.async_shutdown` is a **coroutine** and was not awaited on unload → poll timer + midnight listener leaked on every reload | `await coordinator.async_shutdown()` |
| 5 | `_request_with_retry` was **dead code** — no API call used it, so the documented retry/backoff never ran | All GETs go through `_authed_get` → `_request_with_retry` |
| 6 | API could return a **naive** token expiry → `TypeError` on compare, killing token refresh | `_parse_expiration()` always returns a tz-aware datetime |
| 7 | MQTT messages from **any** SmartSolar customer could be injected into our deviceLogs (shared broker) | `_is_tracked_device()` guard; `+/#` never subscribed, wildcard kept per-device |
| 8 | Malformed `deviceLogs`/`dataStreams` entries raised `AttributeError`/`KeyError` inside the MQTT merge | Every element type-checked; `_merge_streams` skips junk |
| 9 | Per-device WiFi sensor read only `dataStreams`, but REST reports `signalQuality` at the **deviceLog top level** | `_device_log_value()` checks dataStreams then the deviceLog field |
| 10 | Empty `dataStreams: []` payload silently **dropped every other field** | An empty list is treated as "absent" and the flat format is used |
| 11 | `today_kwh` declared `state_class: measurement` with `device_class: energy` → HA logged a warning per entity and built **no statistics** | `total_increasing` (the device's midnight reset is a meter cycle) |
| 12 | `UpdateIntervalNumber` claimed `RestoreEntity` in docs but did not inherit it; out-of-range values were accepted | Inherits `RestoreEntity`, restores on add, rejects values outside 1–30 |

Also fixed: PV1/PV2 labels are pinned to the **sorted GUID order** (the server's
`deviceLogs` order is not stable, which used to shuffle entity_ids and break
dashboards); `config_flow` closes the cached API client on every terminal path
(success, error, and the duplicate-entry abort) and rebuilds it whenever the
submitted credentials change, so a corrected retry never reuses a stale session;
`async_migrate_entry` refuses a newer entry version instead of pretending success;
`diagnostics.py` redacts secrets and no longer touches private coordinator
attributes; logger names moved to `const.py` so noisy sub-loggers can be silenced.

> **Known, correct limitation:** the 40A charger (GUID `14756976`) never reports
> WiFi signal — the live API returns `signalQuality: null` for it and its
> firmware publishes the older `updateDeviceLog` MQTT format without the field.
> `sensor.…_pv2_wifi_signal` is therefore legitimately `unknown`.

## Development Guidelines

### Running Tests

```bash
py -3.14 -m venv .venv                       # Home Assistant 2026.x needs Python >= 3.14.2
.venv/Scripts/python -m pip install -e ".[test,dev,deploy]"
.venv/Scripts/python -m pytest tests/ --cov=custom_components/
.venv/Scripts/ruff check custom_components/ tests/ upload_to_ha.py deploy_to_ha.py verify_live.py
.venv/Scripts/ruff format --check custom_components/ tests/ upload_to_ha.py deploy_to_ha.py verify_live.py
.venv/Scripts/python -m mypy custom_components/
```

> The `deploy` extra (`paramiko`) is only needed by the SSH scripts. It is a
> separate extra because CI and the test suite never touch it — but a *fresh*
> venv installed with only `.[test,dev]` makes `python deploy_to_ha.py` die with
> `ModuleNotFoundError: No module named 'paramiko'`, which is how that was found.
> `tests/test_packaging.py` asserts the extra is declared.

> The ruff file list is duplicated in `deploy_to_ha.py:SOURCES` and
> `.github/workflows/ci.yml`; keep the three in sync (the local gate used to be
> weaker than CI).

`tests/test_e2e.py` runs the real `async_setup_entry` / `async_unload_entry`
against a real `HomeAssistant` core instance. It deliberately does **not** use
`pytest-homeassistant-custom-component`: that package imports the POSIX-only
`fcntl` module and cannot load on Windows. `tests/conftest.py` does not need the
HA test harness either.

### HA Connection
- URL: `http://192.168.10.15:8123`
- SSH: `vokupt@192.168.10.15` — password via `HA_PASS` env var
- Long-lived token available

### Code Style Targets
- Python **3.14.2+** (required by Home Assistant 2026.x), HA **2026.9+**
- Dependencies: aiohttp >= 3.8.0, aiomqtt >= 2.0
- Use `__slots__` for memory efficiency
- Use `CoordinatorEntity` with `RestoreEntity` for all entities
- `always_update=False` with value-change check
- Shared helpers in `helpers.py` (pure) and `const.py` (metadata)
- Pass `config_entry=` to `DataUpdateCoordinator` — HA 2026 raises a usage
  report when a coordinator relies on the ContextVar

### Key Naming Conventions
- Entity ID: `sensor.smartsolar_mppt_{prefix}_{type}` (e.g., `sensor.smartsolar_mppt_p_123_pv_voltage`)
- Unique ID: `{entry_id}_{prefix}_{sensor_type}`
- Config keys: `username`, `password`, `mode`, `device_type`, `chipset_ids`, `project_id`, `update_interval`
- PV1/PV2 order = GUIDs sorted **numerically** (`547611` → PV1, `14756976` → PV2)

### Deploying to HA

`deploy_to_ha.py` is the supported path. It refuses to ship unless lint, format,
mypy and the full test suite pass, archives what is currently deployed to
`_local_archive/deployed/`, uploads, clears `__pycache__`, restarts the container,
waits for the REST API to answer **and then for this integration's config entry to
report `loaded`**, so `verify_live.py` can be chained directly to it:

```bash
cd d:/code/smartsolar_ha
.venv/Scripts/python deploy_to_ha.py               # full gated deploy
.venv/Scripts/python deploy_to_ha.py --skip-checks # emergency re-push
.venv/Scripts/python verify_live.py                # assert the live entities are right
```

> ⚠️ **Why the extra wait:** Home Assistant answers on `/api/config` as soon as
> its HTTP component is up, *before* the integration platforms are added. The
> deploy used to return at that point, so a verification run chained immediately
> after it found **zero** entities and reported every check as missing — observed
> live on 2026-09-28 (0 entities at once, 38 five seconds later). `restart_ha()`
> now also polls `/api/config/config_entries/entry` until the folder-named domain
> reports `loaded`, and refuses the deploy when the entry stays in
> `setup_retry`/`setup_error`. Three outcomes are kept apart: a listing that was
> *read* and does not mention the domain is reported and the deploy continues (a
> fresh install, or a domain rename, has nothing to verify); a listing that could
> **not** be read (HTTP error, timeout, non-list body) is neither absence nor
> failure, so it keeps waiting and then fails the deploy — treating it as absence
> would report success without ever having seen `loaded`.

> ⚠️ **Changing the domain breaks the deployed config entry.** Home Assistant
> resolves an entry by its `domain`, so an entry stored for `smartsolar_mppt`
> cannot load once the integration is `smartsolar_ha` — it logs
> `Integration 'smartsolar_mppt' not found` and every entity goes away.
> `deploy_to_ha.py` detects a leftover `smartsolar_mppt/` folder and warns about
> it, but it does **not** migrate the entry.

> ✅ **Migrate the entry instead of re-adding it** (validated live on 2026-09-28
> for `smartsolar_mppt` → `smartsolar_ha`, 37 entities, no entity_id or
> statistics loss):
>
> 1. With HA **running**, back up `.storage` on the host:
>    `sudo cp /homeassistant/.storage/core.{config_entries,entity_registry,device_registry} /somewhere/`
>    and tar the currently deployed integration folder.
> 2. `sudo docker stop homeassistant` — HA rewrites `.storage` on shutdown, so
>    editing while it runs is silently discarded.
> 3. In `.storage`, rewrite the domain in three places, then write the files back
>    as **UTF-8 without BOM**:
>    * `core.config_entries` → the entry's `"domain"`
>    * `core.entity_registry` → every entity's `"platform"` (one per sensor)
>    * `core.device_registry` → the device's `"identifiers"` pair
> 4. Upload the new tree, delete the old `custom_components/<old_domain>/`, then
>    `sudo docker start homeassistant`.
>
> Because the **entry_id is unchanged**, every entity's unique_id is unchanged
> too, so HA re-binds the same registry rows and the same entity_ids — dashboards
> and long-term statistics keep working and no credential is re-entered. Deleting
> the entry and re-adding it instead produces a new entry_id, hence new
> unique_ids, hence `_2`-suffixed entity_ids and orphaned statistics.
>
> Notes from doing it for real: HAOS's supervisor can restart the container on
> its own after a `docker stop`, so confirm the folder/`.storage` state and do a
> final clean restart before trusting the result; and `configuration.yaml`'s
> `logger.logs` still named the old domain, which silently hid the new
> integration's INFO lines until it was updated (this can be applied without a
> restart via the `logger.set_level` service).

> `clear_entities.ps1` is the opposite tool (it *deletes* both domains' entities
> and devices from the registries, for a clean re-add); run it only with HA
> **stopped**, since it refuses to run while HA answers on its API.

> `verify_live.py` needs `SMARTSOLAR_USER` / `SMARTSOLAR_PASS` in `.env` for the
> per-device WiFi check: it asks the cloud which devices report a `signalQuality`,
> because 'unknown' is only correct for a device whose payload omits it. Without
> those two keys that check reports `SKIP` instead of guessing.

`upload_to_ha.py` remains as a dependency-light uploader (no test gate).

HA runs the config-entry `data` from disk, so changing `update_interval` in the
number entity persists through `config_entries.async_update_entry`; the value is
re-read on the next reload.
