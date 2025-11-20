# Ender V3KE Home Assistant Integration

A HACS-compatible integration that connects to the Ender V3KE WebSocket feed, sanitises its telemetry, exposes it as Home Assistant sensors, optionally publishes the same payload to an MQTT topic, and saves a bounded printer snapshot to `/local` for dashboards.

## Installation (HACS)
1. In Home Assistant, open **HACS → Integrations → Custom repositories**, add this repo's URL, and choose type **Integration**.
2. Search for **Ender V3KE Home Assistant Integration** in HACS and install it.
3. Restart Home Assistant when prompted.

## Configuration
1. Go to **Settings → Devices & Services → Add Integration** and search for **Ender V3KE**.
2. Supply your printer WebSocket URL (for example `ws://[your ws-url]/`).
3. Choose the MQTT topic to publish telemetry to (default `ender_v3ke/status`) and leave **Publish MQTT telemetry** enabled if you want the bridge to keep emitting the JSON status payload.
4. Optionally override the snapshot URL, local save path (relative to your HA config folder, defaults to `www/ender_v3ke/print.png`), public image path (defaults to `/local/ender_v3ke/print.png`), publish interval, and maximum snapshot size.

All settings are stored in the config entry; no YAML is required. Use Home Assistant's `secrets.yaml` if you need to mask broker credentials used elsewhere—this integration itself does not store passwords.

## Entities
The integration creates sensors for:
- Print progress (%)
- Current layer and total layers
- Elapsed and remaining print time (seconds)
- Nozzle and bed temperatures (°C)
- Used filament length (mm)

Each sensor includes the current filename and public snapshot path as attributes.

## MQTT payload (optional)
When **Publish MQTT telemetry** is enabled and the Home Assistant MQTT integration is loaded, the bridge publishes the same JSON payload it uses for the sensors to the configured topic, e.g.:
```json
{
  "progress": 100,
  "layer": 0,
  "total_layers": 0,
  "elapsed": 0,
  "remaining": 0,
  "filename": "1-Boat.gcode",
  "nozzle_temp": 20.76,
  "bed_temp": 20.11,
  "used_filament": 0,
  "image_url": "/local/ender_v3ke/print.png"
}
```
Use retained Home Assistant MQTT discovery payloads if you want other systems to auto-create entities pointing at this topic.

## Notes and tips
- The integration validates WebSocket payloads and clamps noisy values to avoid entity spam.
- Snapshot downloads enforce a content-type allowlist and a configurable size cap before atomically replacing the on-disk image.
- Keep the `www/ender_v3ke` folder writable by Home Assistant so the snapshot can be saved.
