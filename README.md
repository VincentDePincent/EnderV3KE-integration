# EnderV3KE-integration
A simple, fully local HA integration that uses the web-interface of your Ender V3KE to display print statistics in Home Assistant. For best results, create a `.env` file next to the script that supplies your broker host/topic details (e.g. `MQTT_BROKER=[your mqtt broker]`, `MQTT_TOPIC=[mqtt topic]`), optional credentials (`MQTT_USER`, `MQTT_PASS`), and enables TLS (`MQTT_USE_TLS=true`); while the bridge can connect without them, leaving authentication or encryption disabled is discouraged on any shared network.

The bridge now bounds its snapshot downloads and validates WebSocket payloads before publishing them. You can further tune behaviour by setting optional variables such as `PRINTER_WS_URL=ws://[your ws-url]/`, `PRINTER_SNAPSHOT_URL`, `LOCAL_IMAGE_PATH`, `MAX_IMAGE_BYTES` (defaults to 5 MiB), or `PUBLISH_INTERVAL` inside the same `.env` file to balance resource use with update frequency.

After writing the file, keep it private (e.g. `chmod 600 .env`) and avoid committing it—this repository's `.gitignore` already excludes `.env`, so your secrets stay out of version control. You can add any additional overrides (broker host/port, TLS flags) in the same file, and the script will read them automatically on startup.

## Home Assistant MQTT discovery examples
The bridge publishes a single JSON document to your chosen `MQTT_TOPIC`. Home Assistant can auto-create sensors for each field by subscribing to retained discovery payloads. The examples below assume your status updates live at `ender_v3ke/status` and demonstrate the retained `mosquitto_pub` command you would run once per sensor (replace `-h`/`-u`/`-P` as needed). Each payload references the same `device` block so Home Assistant groups the entities together.

Each sensor uses the same `device` definition but a different discovery topic and value template. Publish each retained payload once (per broker) so Home Assistant can recreate the entities after every restart.

#### Progress sensor
```bash
mosquitto_pub -h broker.example.net -t homeassistant/sensor/ender_v3ke_progress/config -r -m '{
  "name": "Ender V3KE Progress",
  "unique_id": "ender_v3ke_progress",
  "state_topic": "ender_v3ke/status",
  "unit_of_measurement": "%",
  "state_class": "measurement",
  "value_template": "{{ value_json.progress }}",
  "device": {
    "identifiers": ["ender_v3ke_bridge"],
    "manufacturer": "Creality",
    "model": "Ender V3 KE",
    "name": "Ender V3KE Bridge"
  }
}'
```

#### Current layer sensor
```bash
mosquitto_pub -h broker.example.net -t homeassistant/sensor/ender_v3ke_layer/config -r -m '{
  "name": "Ender V3KE Layer",
  "unique_id": "ender_v3ke_layer",
  "state_topic": "ender_v3ke/status",
  "state_class": "measurement",
  "value_template": "{{ value_json.layer }}",
  "device": {
    "identifiers": ["ender_v3ke_bridge"],
    "manufacturer": "Creality",
    "model": "Ender V3 KE",
    "name": "Ender V3KE Bridge"
  }
}'
```

#### Total layers sensor
```bash
mosquitto_pub -h broker.example.net -t homeassistant/sensor/ender_v3ke_total_layers/config -r -m '{
  "name": "Ender V3KE Total Layers",
  "unique_id": "ender_v3ke_total_layers",
  "state_topic": "ender_v3ke/status",
  "state_class": "measurement",
  "value_template": "{{ value_json.total_layers }}",
  "device": {
    "identifiers": ["ender_v3ke_bridge"],
    "manufacturer": "Creality",
    "model": "Ender V3 KE",
    "name": "Ender V3KE Bridge"
  }
}'
```

#### Elapsed time sensor
```bash
mosquitto_pub -h broker.example.net -t homeassistant/sensor/ender_v3ke_elapsed/config -r -m '{
  "name": "Ender V3KE Elapsed",
  "unique_id": "ender_v3ke_elapsed",
  "state_topic": "ender_v3ke/status",
  "unit_of_measurement": "s",
  "state_class": "total_increasing",
  "value_template": "{{ value_json.elapsed }}",
  "device": {
    "identifiers": ["ender_v3ke_bridge"],
    "manufacturer": "Creality",
    "model": "Ender V3 KE",
    "name": "Ender V3KE Bridge"
  }
}'
```

#### Remaining time sensor
```bash
mosquitto_pub -h broker.example.net -t homeassistant/sensor/ender_v3ke_remaining/config -r -m '{
  "name": "Ender V3KE Remaining",
  "unique_id": "ender_v3ke_remaining",
  "state_topic": "ender_v3ke/status",
  "unit_of_measurement": "s",
  "state_class": "measurement",
  "value_template": "{{ value_json.remaining }}",
  "device": {
    "identifiers": ["ender_v3ke_bridge"],
    "manufacturer": "Creality",
    "model": "Ender V3 KE",
    "name": "Ender V3KE Bridge"
  }
}'
```

#### Nozzle temperature sensor
```bash
mosquitto_pub -h broker.example.net -t homeassistant/sensor/ender_v3ke_nozzle_temp/config -r -m '{
  "name": "Ender V3KE Nozzle",
  "unique_id": "ender_v3ke_nozzle",
  "state_topic": "ender_v3ke/status",
  "unit_of_measurement": "°C",
  "state_class": "measurement",
  "device_class": "temperature",
  "value_template": "{{ value_json.nozzle_temp }}",
  "device": {
    "identifiers": ["ender_v3ke_bridge"],
    "manufacturer": "Creality",
    "model": "Ender V3 KE",
    "name": "Ender V3KE Bridge"
  }
}'
```

#### Bed temperature sensor
```bash
mosquitto_pub -h broker.example.net -t homeassistant/sensor/ender_v3ke_bed_temp/config -r -m '{
  "name": "Ender V3KE Bed",
  "unique_id": "ender_v3ke_bed",
  "state_topic": "ender_v3ke/status",
  "unit_of_measurement": "°C",
  "state_class": "measurement",
  "device_class": "temperature",
  "value_template": "{{ value_json.bed_temp }}",
  "device": {
    "identifiers": ["ender_v3ke_bridge"],
    "manufacturer": "Creality",
    "model": "Ender V3 KE",
    "name": "Ender V3KE Bridge"
  }
}'
```

#### Filament usage sensor
```bash
mosquitto_pub -h broker.example.net -t homeassistant/sensor/ender_v3ke_used_filament/config -r -m '{
  "name": "Ender V3KE Filament Used",
  "unique_id": "ender_v3ke_filament",
  "state_topic": "ender_v3ke/status",
  "unit_of_measurement": "mm",
  "state_class": "total_increasing",
  "value_template": "{{ value_json.used_filament }}",
  "device": {
    "identifiers": ["ender_v3ke_bridge"],
    "manufacturer": "Creality",
    "model": "Ender V3 KE",
    "name": "Ender V3KE Bridge"
  }
}'
```

#### Current job name sensor
```bash
mosquitto_pub -h broker.example.net -t homeassistant/sensor/ender_v3ke_filename/config -r -m '{
  "name": "Ender V3KE Job Name",
  "unique_id": "ender_v3ke_filename",
  "state_topic": "ender_v3ke/status",
  "icon": "mdi:file",
  "value_template": "{{ value_json.filename }}",
  "device": {
    "identifiers": ["ender_v3ke_bridge"],
    "manufacturer": "Creality",
    "model": "Ender V3 KE",
    "name": "Ender V3KE Bridge"
  }
}'
```

#### Snapshot path sensor
```bash
mosquitto_pub -h broker.example.net -t homeassistant/sensor/ender_v3ke_image/config -r -m '{
  "name": "Ender V3KE Snapshot Path",
  "unique_id": "ender_v3ke_image",
  "state_topic": "ender_v3ke/status",
  "icon": "mdi:image",
  "entity_category": "diagnostic",
  "value_template": "{{ value_json.image_url }}",
  "device": {
    "identifiers": ["ender_v3ke_bridge"],
    "manufacturer": "Creality",
    "model": "Ender V3 KE",
    "name": "Ender V3KE Bridge"
  }
}'
```

### Placeholder template
When customising the discovery payloads for your own environment, substitute your topic, identifiers, and friendly names. The template below shows the structure Home Assistant expects—replace every bracketed value (including the brackets) before publishing the retained message.

```json
{
  "name": "[friendly sensor name]",
  "unique_id": "[stable-unique-id]",
  "state_topic": "[your mqtt topic]",
  "value_template": "{{ value_json.[field name] }}",
  "unit_of_measurement": "[unit, if applicable]",
  "state_class": "[measurement|total_increasing]",
  "device_class": "[home assistant device class, if any]",
  "icon": "[mdi icon, optional]",
  "entity_category": "[diagnostic|config, optional]",
  "device": {
    "identifiers": ["[shared device identifier]"],
    "manufacturer": "[printer manufacturer]",
    "model": "[printer model]",
    "name": "[device name as it should appear in Home Assistant]"
  }
}
```

Always publish discovery payloads with the retain flag so they survive restarts (`mosquitto_pub -r ...`), and re-run the command whenever you change the configuration.
