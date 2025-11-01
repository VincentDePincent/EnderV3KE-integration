# EnderV3KE-integration
A simple, fully local HA integration that uses the web-interface of your Ender V3KE to display print statistics in Home Assistant. For best results, create a `.env` file next to the script that supplies your broker credentials (`MQTT_USER`, `MQTT_PASS`) and enables TLS (`MQTT_USE_TLS=true`); while the bridge can connect without them, leaving authentication or encryption disabled is discouraged on any shared network.

The bridge now bounds its snapshot downloads and validates WebSocket payloads before publishing them. You can further tune behaviour by setting optional variables such as `MAX_IMAGE_BYTES` (defaults to 5 MiB) or `PUBLISH_INTERVAL` inside the same `.env` file to balance resource use with update frequency.

After writing the file, keep it private (e.g. `chmod 600 .env`) and avoid committing it—this repository's `.gitignore` already excludes `.env`, so your secrets stay out of version control. You can add any additional overrides (broker host/port, TLS flags) in the same file, and the script will read them automatically on startup.
