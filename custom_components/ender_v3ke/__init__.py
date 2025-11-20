"""Ender V3KE Home Assistant integration."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from typing import Any

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.components import mqtt

from .const import (
    CONF_ENABLE_MQTT,
    CONF_EXPOSED_IMAGE_PATH,
    CONF_LOCAL_IMAGE_PATH,
    CONF_MAX_IMAGE_BYTES,
    CONF_MQTT_TOPIC,
    CONF_PUBLISH_INTERVAL,
    CONF_SNAPSHOT_URL,
    CONF_WS_URL,
    DEFAULT_EXPOSED_IMAGE_PATH,
    DEFAULT_LOCAL_IMAGE_PATH,
    DEFAULT_MAX_IMAGE_BYTES,
    DEFAULT_MQTT_TOPIC,
    DEFAULT_PUBLISH_INTERVAL,
    DOMAIN,
    IMAGE_ALLOWED_CONTENT_TYPES,
    IMAGE_CHUNK_BYTES,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration from YAML (not supported)."""
    return True


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        result = str(value)
    except Exception:  # noqa: BLE001 - defensive conversion
        return default
    return result


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        try:
            result = float(str(value).strip())
        except (TypeError, ValueError):
            return default
    if math.isnan(result) or math.isinf(result):
        return default
    return result


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return default
        return int(value)
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


class EnderStateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator backing the Ender V3KE sensors."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Ender V3KE state",
            update_method=self._async_empty_update,
        )

    async def _async_empty_update(self) -> dict[str, Any]:
        return self.data or {}


class EnderBridge:
    """Manage the printer WebSocket connection and MQTT publishing."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: EnderStateCoordinator,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._cached_state: dict[str, Any] = {}
        self._last_sent_state: dict[str, Any] = {}
        self._last_sent_time: float = 0
        self._current_filename: str | None = None
        self._session = async_get_clientsession(hass)

    @property
    def mqtt_topic(self) -> str:
        return self.entry.data.get(CONF_MQTT_TOPIC, DEFAULT_MQTT_TOPIC)

    @property
    def publish_interval(self) -> float:
        interval = _safe_float(
            self.entry.data.get(CONF_PUBLISH_INTERVAL, DEFAULT_PUBLISH_INTERVAL),
            DEFAULT_PUBLISH_INTERVAL,
        )
        return interval if interval > 0 else DEFAULT_PUBLISH_INTERVAL

    @property
    def snapshot_url(self) -> str:
        return self.entry.data.get(CONF_SNAPSHOT_URL) or self.entry.options.get(
            CONF_SNAPSHOT_URL, ""
        )

    @property
    def ws_url(self) -> str:
        return self.entry.data.get(CONF_WS_URL, "")

    @property
    def local_image_path(self) -> str:
        return self.entry.data.get(CONF_LOCAL_IMAGE_PATH, DEFAULT_LOCAL_IMAGE_PATH)

    @property
    def exposed_image_path(self) -> str:
        return self.entry.data.get(
            CONF_EXPOSED_IMAGE_PATH, DEFAULT_EXPOSED_IMAGE_PATH
        )

    @property
    def max_image_bytes(self) -> int:
        size = _safe_int(
            self.entry.data.get(CONF_MAX_IMAGE_BYTES, DEFAULT_MAX_IMAGE_BYTES),
            DEFAULT_MAX_IMAGE_BYTES,
        )
        return size if size > 0 else DEFAULT_MAX_IMAGE_BYTES

    @property
    def mqtt_enabled(self) -> bool:
        return bool(self.entry.data.get(CONF_ENABLE_MQTT, True))

    async def async_start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def async_stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        backoff = 1
        while not self._stop_event.is_set():
            try:
                import websockets

                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=20,
                    max_size=2**20,
                ) as ws:
                    _LOGGER.info("WebSocket connected to %s", self.ws_url)
                    backoff = 1
                    async for msg in ws:
                        if self._stop_event.is_set():
                            break
                        await self._handle_message(msg)
            except asyncio.CancelledError:
                break
            except Exception as err:  # noqa: BLE001 - log unexpected errors
                _LOGGER.error("WebSocket error: %s", err)
            if self._stop_event.is_set():
                break
            _LOGGER.info("Reconnecting in %ss…", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    async def _handle_message(self, msg: str) -> None:
        try:
            data = json.loads(msg)
        except json.JSONDecodeError:
            _LOGGER.debug("Ignoring non-JSON message: %s", msg)
            return
        if not isinstance(data, dict):
            _LOGGER.debug("Ignoring non-dict message: %s", data)
            return

        payload = await self._extract_data(data)
        now = time.monotonic()
        if self._has_meaningful_change(payload, self._last_sent_state):
            if self.mqtt_enabled:
                await self._async_publish(payload)
            self._last_sent_state = payload.copy()
            self._last_sent_time = now
            self.coordinator.async_set_updated_data(payload)
        elif (now - self._last_sent_time) >= self.publish_interval:
            # Periodic refresh for entities even without major changes.
            self._last_sent_time = now
            self.coordinator.async_set_updated_data(payload)

    async def _async_publish(self, payload: dict[str, Any]) -> None:
        if mqtt.DOMAIN not in self.hass.config.components:
            _LOGGER.debug("MQTT integration not loaded; skipping publish")
            return
        try:
            await mqtt.async_publish(self.hass, self.mqtt_topic, json.dumps(payload))
            _LOGGER.info("Published MQTT payload to %s", self.mqtt_topic)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("Failed to publish MQTT payload: %s", exc)

    def _sanitise_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        progress = _clamp(_safe_float(state.get("printProgress"), 0.0), 0.0, 100.0)
        layer = _safe_int(state.get("layer"), 0)
        total_layers = max(layer, _safe_int(state.get("TotalLayer"), 0))
        elapsed = max(0, _safe_int(state.get("printJobTime"), 0))
        remaining = max(0, _safe_int(state.get("printLeftTime"), 0))
        nozzle_temp = _safe_float(state.get("nozzleTemp"), 0.0)
        bed_temp = _safe_float(state.get("bedTemp0"), 0.0)
        used_filament = max(0, _safe_int(state.get("usedMaterialLength"), 0))
        filename = os.path.basename(_safe_str(state.get("printFileName", "")))

        return {
            "progress": progress,
            "layer": layer,
            "total_layers": total_layers,
            "elapsed": elapsed,
            "remaining": remaining,
            "filename": filename,
            "nozzle_temp": nozzle_temp,
            "bed_temp": bed_temp,
            "used_filament": used_filament,
            "image_url": self.exposed_image_path,
        }

    async def _extract_data(self, data: dict[str, Any]) -> dict[str, Any]:
        for key in (
            "printProgress",
            "layer",
            "TotalLayer",
            "printJobTime",
            "printLeftTime",
            "printFileName",
            "nozzleTemp",
            "bedTemp0",
            "usedMaterialLength",
        ):
            if key in data:
                self._cached_state[key] = data[key]

        if _safe_float(data.get("printProgress"), 1.0) == 0:
            self._current_filename = None

        filename = os.path.basename(_safe_str(self._cached_state.get("printFileName", "")))
        if filename and filename != self._current_filename:
            self._current_filename = filename
            await self._async_download_image()

        return self._sanitise_payload(self._cached_state)

    async def _async_download_image(self) -> None:
        if not self.snapshot_url:
            return
        target_path = self.hass.config.path(self.local_image_path)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        tmp_path = f"{target_path}.tmp"

        try:
            async with self._session.get(
                self.snapshot_url,
                timeout=5,
                headers={"Accept": "image/*"},
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("Image request returned HTTP %s", resp.status)
                    return
                content_type = resp.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type and content_type not in IMAGE_ALLOWED_CONTENT_TYPES:
                    _LOGGER.warning("Unexpected image Content-Type '%s'; aborting download.", content_type or "<missing>")
                    return

                bytes_written = 0
                over_limit = False
                with open(tmp_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(IMAGE_CHUNK_BYTES):
                        if not chunk:
                            continue
                        bytes_written += len(chunk)
                        if bytes_written > self.max_image_bytes:
                            _LOGGER.warning(
                                "Image exceeded %s bytes; discarding partial download.",
                                self.max_image_bytes,
                            )
                            over_limit = True
                            break
                        f.write(chunk)

                if over_limit:
                    os.remove(tmp_path)
                    return

                os.replace(tmp_path, target_path)
                _LOGGER.info("Image downloaded and saved (%s bytes).", bytes_written)
        except FileNotFoundError:
            _LOGGER.warning("Local image path directory missing: %s", target_path)
        except PermissionError:
            _LOGGER.warning("Permission denied writing image file: %s", target_path)
        except (asyncio.TimeoutError, ClientError) as exc:
            _LOGGER.warning("Error downloading image: %s", exc)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("Unexpected error downloading image: %s", exc)

    def _has_meaningful_change(self, new: dict[str, Any], old: dict[str, Any]) -> bool:
        if not old:
            return True

        numeric_tolerances = {
            "progress": 0.5,
            "nozzle_temp": 0.5,
            "bed_temp": 0.5,
            "elapsed": 1,
            "remaining": 1,
            "used_filament": 1,
            "layer": 1,
            "total_layers": 1,
        }

        for key, value in new.items():
            if key not in old:
                return True
            other = old[key]
            if isinstance(value, (int, float)) and isinstance(other, (int, float)):
                tolerance = numeric_tolerances.get(key, 0)
                if abs(float(value) - float(other)) > tolerance:
                    return True
            elif value != other:
                return True

        for key in old:
            if key not in new:
                return True

        return False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    coordinator = EnderStateCoordinator(hass)
    bridge = EnderBridge(hass, entry, coordinator)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "bridge": bridge,
    }

    try:
        await bridge.async_start()
    except Exception as exc:  # noqa: BLE001
        raise ConfigEntryNotReady(f"Failed to start Ender V3KE bridge: {exc}") from exc

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if data and isinstance(data.get("bridge"), EnderBridge):
        await data["bridge"].async_stop()
    return unload_ok
