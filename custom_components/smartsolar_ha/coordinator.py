"""Data update coordinator for SmartSolar MPPT."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_call_later, async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import SmartSolarAPI, SmartSolarAPIError, SmartSolarInvalidCredentialsError
from .const import (
    CHARGE_POWER_MAX_W,
    COORDINATOR_LOGGER,
    DEFAULT_UPDATE_INTERVAL,
    MODE_DEVICE,
    MQTT_NOTIFY_THROTTLE,
)
from .helpers import coerce_float, device_logs, guid_sort_key, stream_dict

_LOGGER = logging.getLogger(COORDINATOR_LOGGER)


def _format_outage(duration: timedelta) -> str:
    """Render an outage length for the recovery log line (e.g. '2 h 05 min')."""
    total = int(duration.total_seconds())
    if total < 60:
        return f"{total} s"
    minutes, seconds = divmod(total, 60)
    if minutes < 60:
        return f"{minutes} min {seconds:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"


# ── Daily stats tracking ──────────────────────────────────────────────
# The SmartSolar server does NOT store long-term historical data (API only
# returns current month; Prometheus only keeps ~2 months).  HA fills the gap:
#  • total_kwh (total_increasing) → HA long-term statistics → monthly/yearly deltas
#  • utility_meter → daily/monthly/yearly buckets
#  • Stats below → peak/avg/production-hours per day (server doesn't provide)


class SmartSolarDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching data from the SmartSolar API.

    Supports optional MQTT real-time data: when MQTT data is available
    for a device, it is merged into the HTTP response so sensors see
    live values between polling intervals.

    Tracks daily statistics (peak power, avg power, production hours)
    that the SmartSolar server doesn't store long-term.
    """

    __slots__ = (
        "api",
        "entry",
        "discovered_devices",
        "_mqtt_data",
        "_mqtt_client",
        "_daily_stats",
        "_daily_tracker_unsub",
        "_mqtt_notify_unsub",
        "_consecutive_api_failures",
        "_outage_started",
    )

    def __init__(
        self,
        hass: HomeAssistant,
        api: SmartSolarAPI,
        entry: ConfigEntry,
        update_interval: timedelta | None = None,
    ) -> None:
        """Initialize the coordinator."""
        if update_interval is None:
            update_interval = DEFAULT_UPDATE_INTERVAL

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="SmartSolar MPPT",
            update_interval=update_interval,
            always_update=False,
        )
        self.api = api
        self.entry = entry
        self.discovered_devices: set[str] = set()
        self._mqtt_data: dict[str, dict[str, Any]] = {}
        self._mqtt_client: Any = None  # SmartSolarMQTTClient set by __init__.py

        # Daily statistics per device
        # {guid: {peak_power: float, power_sum: float, power_count: int, active_minutes: set}}
        self._daily_stats: dict[str, dict[str, Any]] = {}
        self._daily_tracker_unsub: Callable[[], None] | None = None

        # MQTT-driven listener refresh, throttled to at most one per second.
        # See async_process_mqtt_data() for why this must NOT be
        # async_set_updated_data().
        self._mqtt_notify_unsub: Callable[[], None] | None = None

        # Cloud-outage bookkeeping. A failing poll reports itself through
        # UpdateFailed, which Home Assistant already logs once per transition,
        # so consecutive failures are counted here and only the first one is
        # logged at WARNING: a multi-hour outage used to write an ERROR line
        # every poll (~1,600 lines/hour) of identical text.
        self._consecutive_api_failures = 0
        self._outage_started: datetime | None = None

        # Register midnight-reset listener
        self._daily_tracker_unsub = async_track_time_change(hass, self._reset_daily_stats, hour=0, minute=0, second=0)

    @callback
    def _reset_daily_stats(self, _now: datetime) -> None:
        """Reset daily statistics at midnight."""
        self._daily_stats.clear()
        _LOGGER.debug("Daily stats reset at midnight")

    async def async_shutdown(self) -> None:
        """Stop the poll timer and cancel the midnight and MQTT listeners."""
        await super().async_shutdown()
        if self._daily_tracker_unsub is not None:
            self._daily_tracker_unsub()
            self._daily_tracker_unsub = None
        if self._mqtt_notify_unsub is not None:
            self._mqtt_notify_unsub()
            self._mqtt_notify_unsub = None

    def _init_daily_stats(self, device_guid: str) -> dict[str, Any]:
        """Initialize (or return existing) daily stats for a device."""
        if device_guid not in self._daily_stats:
            self._daily_stats[device_guid] = {
                "peak_power": 0.0,
                "power_sum": 0.0,
                "power_count": 0,
                "active_minutes": set(),  # set of hour:minute strings for active minutes
            }
        return self._daily_stats[device_guid]

    def get_daily_stats(self, device_guid: str) -> dict[str, Any]:
        """Get current daily stats for a device (peak, avg, production hours)."""
        stats = self._daily_stats.get(device_guid, {})
        peak = stats.get("peak_power", 0.0)
        power_sum = stats.get("power_sum", 0.0)
        power_count = stats.get("power_count", 0)
        active_minutes = stats.get("active_minutes", set())

        avg = power_sum / power_count if power_count > 0 else 0.0
        production_hours = len(active_minutes) / 60.0  # minutes → hours

        return {
            "peak_power": round(peak, 1),
            "avg_power": round(avg, 1),
            "production_hours": round(production_hours, 2),
        }

    def _update_daily_stats(self, device_guid: str, charge_power: float | None, now: datetime | None = None) -> None:
        """Update daily tracking with latest charge_power reading."""
        # Normalizes NaN/Infinity (which survive ``<``/``>`` comparisons and
        # would silently become the peak) to None as well.
        charge_power = coerce_float(charge_power)
        if charge_power is None:
            return

        # Validate against the shared ceiling to reject garbage/overflow readings
        max_cp = CHARGE_POWER_MAX_W
        if charge_power < 0 or charge_power > max_cp:
            _LOGGER.debug(
                "Stats: rejecting charge_power=%.1f for %s (valid range 0-%.0f)",
                charge_power,
                device_guid,
                max_cp,
            )
            return

        stats = self._init_daily_stats(device_guid)

        # Peak power
        if charge_power > stats["peak_power"]:
            stats["peak_power"] = charge_power

        # Running average
        stats["power_sum"] += charge_power
        stats["power_count"] += 1

        # Production hours: track each minute where power > 5W
        if charge_power > 5:
            if now is None:
                now = dt_util.now()
            minute_key = f"{now.hour}:{now.minute:02d}"
            stats["active_minutes"].add(minute_key)

    def set_mqtt_client(self, mqtt_client: Any) -> None:
        """Set the MQTT client reference for real-time data merging."""
        self._mqtt_client = mqtt_client

    @property
    def mqtt_client(self) -> Any:
        """Return the MQTT client (or None when real-time updates are off)."""
        return self._mqtt_client

    @property
    def mqtt_cached_device_count(self) -> int:
        """Return how many devices have live MQTT data buffered."""
        return len(self._mqtt_data)

    def has_live_mqtt_data(self, device_guid: str | None = None) -> bool:
        """Return whether buffered MQTT data can feed an entity.

        Entities use this to stay *available* when the HTTP poll fails while MQTT
        keeps delivering: the REST value is stale in that case but the entity's
        ``native_value`` is still a live reading, and reporting ``unavailable``
        would throw away the very data the real-time path exists to provide (and
        punch a hole in the recorder/statistics).

        ``device_guid=None`` asks about the whole entry, which is what the
        project synthesis sensors need.
        """
        if self.data is None:
            # No poll has ever succeeded, so MQTT data has not been merged into
            # anything an entity can read yet.
            return False
        if device_guid is None:
            return bool(self._mqtt_data)
        return str(device_guid) in self._mqtt_data

    async def async_process_mqtt_data(self, device_guid: str, data: dict[str, Any]) -> None:
        """Process incoming MQTT data for a device.

        Merges the payload into ``self.data`` and wakes the entities so
        sensors reflect real-time values between HTTP polls.

        Entities are notified via ``async_update_listeners``, NOT via
        ``async_set_updated_data``. The latter also calls
        ``_async_unsub_refresh()`` + ``_schedule_refresh()``, so every MQTT
        message cancels and restarts the poll timer. These devices publish
        roughly twice a second while ``update_interval`` defaults to 5s, so
        the timer never fires: ``_async_update_data`` stops running entirely,
        token refresh stops, and recorder writes climb to ~2 per second per
        sensor. Calling the listeners directly leaves the poll timer alone.
        """
        # Only merge for devices this config entry actually tracks. The broker
        # is shared by every SmartSolar customer, so a message from a foreign
        # device must never populate our cache or daily-stats map, nor be
        # injected into our deviceLogs.
        if not self._is_tracked_device(device_guid):
            return

        self._mqtt_data[device_guid] = data

        # Update daily stats from MQTT data
        if (charge_power := coerce_float(data.get("charge_power"))) is not None:
            self._update_daily_stats(device_guid, charge_power)

        if self.data is None:
            return

        # Patch the payload in-place, then notify at most once per second so a
        # burst of messages coalesces into a single round of entity updates.
        self._merge_mqtt_into_data(self.data, device_guid, data)
        self._schedule_mqtt_notify()

    def _is_tracked_device(self, device_guid: str) -> bool:
        """Return whether a device GUID belongs to this config entry."""
        guid = str(device_guid)
        if guid in self.discovered_devices:
            return True
        chipset_ids = [str(cid) for cid in (self.entry.data.get("chipset_ids") or [])]
        if self.entry.data.get("mode") == MODE_DEVICE:
            # Device mode has entities for exactly one device, and it merges every
            # accepted device into a single ``lastMessage.dataStreams``. Accepting
            # a stray extra chipset id therefore published *that* device's readings
            # on this device's sensors. The config flow now refuses multiple ids;
            # this keeps an entry that already has them from showing wrong data.
            return bool(chipset_ids) and guid == chipset_ids[0]
        return guid in set(chipset_ids)

    @staticmethod
    def device_guids(data: dict[str, Any]) -> list[str]:
        """Return the device GUIDs of a project response in a STABLE order.

        The server does not guarantee the order of ``deviceLogs``, and the
        PV1/PV2 entity names (and therefore the entity_ids and every dashboard
        reference) are derived from that order. Sorting by the numeric value of
        the GUID keeps the labels stable across restarts and re-polls.
        """
        guids = {str(log["deviceGuid"]) for log in device_logs(data) if isinstance(log, dict) and log.get("deviceGuid")}
        return sorted(guids, key=guid_sort_key)

    @callback
    def _schedule_mqtt_notify(self) -> None:
        """Notify entities of MQTT data, rate-limited to 1Hz.

        Values are merged into ``self.data`` on every message; only the
        listener refresh is throttled, so nothing is lost — the next allowed
        refresh publishes the newest merged values.
        """
        if self._mqtt_notify_unsub is not None:
            return
        self.async_update_listeners()
        self._mqtt_notify_unsub = async_call_later(self.hass, MQTT_NOTIFY_THROTTLE, self._async_mqtt_notify_done)

    @callback
    def _async_mqtt_notify_done(self, _now: datetime) -> None:
        """Release the 1Hz gate so the next MQTT message can notify."""
        self._mqtt_notify_unsub = None

    def _mqtt_to_data_stream(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Convert flat MQTT data dict to dataStreams list format.

        ``None`` values are dropped: some firmware publishes
        ``signalQuality: null``, and ``str(None)`` would inject the literal
        string ``"None"`` into ``dataStreams``, where it shadows the real REST
        value with an unparseable one.
        """
        return [{"name": key, "value": str(value)} for key, value in data.items() if value is not None]

    def _merge_mqtt_into_data(
        self,
        api_data: dict[str, Any],
        device_guid: str,
        mqtt_data: dict[str, Any],
    ) -> None:
        """Merge MQTT data into API response data in-place."""
        mqtt_streams = self._mqtt_to_data_stream(mqtt_data)

        mode = api_data.get("_mode", self.entry.data.get("mode"))

        if mode == MODE_DEVICE:
            # Device mode: update lastMessage.dataStreams
            last_msg = api_data.setdefault("lastMessage", {})
            if not isinstance(last_msg, dict):
                last_msg = {}
                api_data["lastMessage"] = last_msg
            existing = last_msg.get("dataStreams", [])
            last_msg["dataStreams"] = self._merge_streams(existing, mqtt_streams)
        else:
            # Project mode: update deviceLogs for the matching device
            device_logs = api_data.get("deviceLogs")
            if not isinstance(device_logs, list):
                device_logs = []
                api_data["deviceLogs"] = device_logs

            for device_log in device_logs:
                if not isinstance(device_log, dict):
                    continue
                if str(device_log.get("deviceGuid")) == str(device_guid):
                    device_log["dataStreams"] = self._merge_streams(device_log.get("dataStreams", []), mqtt_streams)
                    return

            # New device — add a deviceLog entry from MQTT data
            device_logs.append(
                {
                    "deviceGuid": device_guid,
                    "dataStreams": mqtt_streams,
                }
            )
            _LOGGER.info(
                "MQTT discovered new device %s not yet in API response",
                device_guid,
            )

    @staticmethod
    def _merge_streams(
        existing: Any,
        incoming: Any,
    ) -> list[dict[str, Any]]:
        """Merge incoming dataStreams into existing, overwriting by name.

        Malformed entries (missing ``name``, or a stream that is not a mapping)
        are skipped instead of raising — MQTT payloads come from third-party
        firmware and must never be able to break a poll cycle.
        """
        if not isinstance(existing, list):
            existing = []
        if not isinstance(incoming, list):
            incoming = []
        merged: dict[str, dict[str, Any]] = {}
        for stream in existing:
            if isinstance(stream, dict) and stream.get("name") is not None:
                merged[stream["name"]] = stream
        for stream in incoming:
            if isinstance(stream, dict) and stream.get("name") is not None:
                merged[stream["name"]] = stream
        return list(merged.values())

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""
        try:
            # Get configuration from entry with validation
            device_type = self.entry.data.get("device_type")
            chipset_ids = self.entry.data.get("chipset_ids")
            mode = self.entry.data.get("mode")
            project_id = self.entry.data.get("project_id")

            # Validate required fields
            if not device_type:
                raise UpdateFailed("Missing device_type in configuration")
            if not mode:
                raise UpdateFailed("Missing mode in configuration")
            if not project_id and not chipset_ids:
                raise UpdateFailed("Missing both project_id and chipset_ids in configuration")

            _LOGGER.debug(
                "SmartSolar API Update - Interval: %s, Mode: %s",
                self.update_interval,
                mode,
            )

            # Fetch metrics from API
            if project_id:
                # Use project ID for project mode
                data = await self.api.get_project_metrics(project_id)
            else:
                # Use existing logic for device mode or device IDs project mode
                if not chipset_ids:
                    raise UpdateFailed("No chipset_ids or project_id found in configuration")

                data = await self.api.get_metrics(
                    device_type=device_type,
                    chipset_ids=chipset_ids,
                    mode=mode,
                )

            # Log summary only — avoid logging full response with potentially sensitive data
            _LOGGER.debug(
                "API response: mode=%s, keys=%s, device_count=%s",
                data.get("_mode"),
                list(data.keys()),
                len(device_logs(data)),
            )

            # Track discovered devices for project mode
            if mode == "project" and "deviceLogs" in data:
                current_devices = set(self.device_guids(data))
                new_devices = current_devices - self.discovered_devices
                if new_devices:
                    _LOGGER.info("New devices discovered: %s", sorted(new_devices))
                # REPLACE, do not union. This set is the "does this device belong
                # to us?" guard for a broker shared with every SmartSolar
                # customer, and it is also what lets a cached MQTT payload be
                # merged back into the response. Growing it forever meant a
                # device removed from the project kept being accepted, so its
                # last MQTT values re-created a phantom deviceLogs entry (and
                # were summed into the project totals) on every poll, forever.
                self.discovered_devices = current_devices

            # Add metadata to the data
            data["_mode"] = mode
            data["_device_type"] = device_type
            data["_chipset_ids"] = chipset_ids

            # Merge any MQTT real-time data into the HTTP response, but only
            # for devices this entry tracks (see _is_tracked_device).
            for guid, mqtt_data in self._mqtt_data.items():
                if self._is_tracked_device(guid):
                    self._merge_mqtt_into_data(data, guid, mqtt_data)

            # Update daily stats from API data (both device and project modes)
            now = dt_util.now()
            if mode == MODE_DEVICE:
                # Device mode: extract charge_power from lastMessage.dataStreams
                last_msg = data.get("lastMessage", {})
                if not isinstance(last_msg, dict):
                    last_msg = {}
                charge_power = coerce_float(stream_dict(last_msg.get("dataStreams")).get("charge_power"))
                if charge_power is not None:
                    device_guid = chipset_ids[0] if chipset_ids else "unknown"
                    self._update_daily_stats(device_guid, charge_power, now)
            else:
                # Project mode: extract charge_power from each deviceLog
                for device_log in device_logs(data):
                    if not isinstance(device_log, dict):
                        continue
                    guid = str(device_log.get("deviceGuid", ""))
                    if not guid:
                        continue
                    charge_power = coerce_float(stream_dict(device_log.get("dataStreams")).get("charge_power"))
                    if charge_power is not None:
                        self._update_daily_stats(guid, charge_power, now)

            if self._consecutive_api_failures:
                outage = dt_util.now() - self._outage_started if self._outage_started else None
                _LOGGER.info(
                    "SmartSolar cloud reachable again after %d failed poll(s)%s",
                    self._consecutive_api_failures,
                    f" ({_format_outage(outage)})" if outage is not None else "",
                )
                self._consecutive_api_failures = 0
                self._outage_started = None

            _LOGGER.debug("SmartSolar API Update Complete")
            return data

        except SmartSolarInvalidCredentialsError as err:
            # A wrong password is not an outage and no retry can fix it, so this
            # is the one failure we hand to Home Assistant instead of counting
            # it: DataUpdateCoordinator logs it once and calls
            # async_start_reauth_if_available(), which is what asks the user for
            # new credentials. Nothing is logged here — HA already did, and a
            # second line per poll would be the noise v2.0.5 removed.
            #
            # Note the narrower type: a *rejected token* stays a plain
            # SmartSolarAuthenticationError below, because the next poll logs in
            # again and forcing a reauth for it would ask the user to re-enter
            # credentials that are perfectly good.
            raise ConfigEntryAuthFailed(f"SmartSolar rejected the stored credentials: {err}") from err
        except SmartSolarAPIError as err:
            self._consecutive_api_failures += 1
            if self._consecutive_api_failures == 1:
                self._outage_started = dt_util.now()
                _LOGGER.warning(
                    "SmartSolar cloud request failed (%s); retrying every %s in the background",
                    err,
                    self.update_interval,
                )
            else:
                _LOGGER.debug(
                    "SmartSolar cloud still failing (poll %d): %s",
                    self._consecutive_api_failures,
                    err,
                )
            raise UpdateFailed(f"SmartSolar API error: {err}") from err
        except (ValueError, TypeError, KeyError) as err:
            _LOGGER.error("Data processing error: %s", err, exc_info=True)
            raise UpdateFailed(f"Data processing error: {err}") from err
