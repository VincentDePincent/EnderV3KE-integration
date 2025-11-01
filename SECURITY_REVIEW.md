# Ender V3KE MQTT Bridge Security Review

## Summary
This update reassesses the `src/ender_v3ke_bridge.py` bridge after the latest hardening changes. The script now validates WebSocket payloads, bounds snapshot downloads, and debounces noisy MQTT updates while keeping MQTT authentication and TLS optional. These guardrails reduce the likelihood of malformed printer data crashing the bridge or overwhelming Home Assistant, but plaintext defaults and printer-facing links continue to dominate the remaining risk.

## Findings

### 1. Insecure-by-default MQTT posture
The bridge still permits anonymous, plaintext MQTT connections whenever credentials or TLS flags are absent, logging only a warning before proceeding.【F:src/ender_v3ke_bridge.py†L38-L111】 A misconfigured `.env` (or none at all) therefore yields unauthenticated broker access and cleartext telemetry—conditions an attacker can silently exploit on a shared LAN.

*Mitigation:* Require explicit opt-in for anonymous or non-TLS connections (e.g., fail fast unless `MQTT_ALLOW_INSECURE=true` is set) so administrators cannot accidentally deploy the integration with insecure defaults.

### 2. Unprotected printer transports
Printer resources are still contacted over unencrypted channels: the WebSocket defaults to `ws://` and the snapshot downloader uses `http://` without integrity checks.【F:src/ender_v3ke_bridge.py†L46-L55】【F:src/ender_v3ke_bridge.py†L119-L166】 Attackers on the same network segment can sniff or tamper with printer traffic, inject malicious JSON, or replace the snapshot payload. MQTT TLS does not shield these printer-facing requests.

*Mitigation:* Prefer `wss://`/`https://` endpoints if the printer firmware supports them, or isolate the printer inside a secured segment (VLAN, VPN tunnel, or dedicated IoT SSID) so untrusted devices cannot observe or modify traffic.

### 3. Residual snapshot trust gap
Snapshot downloads now stream in bounded chunks, validate MIME types, and cap the total size before atomically replacing the published file.【F:src/ender_v3ke_bridge.py†L119-L166】 These limits blunt the impact of giant payloads but still trust the printer to supply honest content. An on-path attacker can return a spoofed yet small image (or a mislabeled binary) that downstream consumers might render without additional validation.

*Mitigation:* Add stronger content validation—such as verifying magic numbers for accepted formats, scanning with `imghdr`, or serving the file from a quarantined directory—to prevent doctored media from reaching dashboards.

## Recommendations
1. Fail closed unless an operator explicitly acknowledges insecure MQTT/TLS modes.
2. Harden printer communications with TLS, segmentation, or authenticated tunnels.
3. Verify snapshot content beyond headers (magic numbers, basic decoding) before exposing it to Home Assistant.

## Operational Opportunities
- **Asynchronous downloads:** Offload `download_image()` to an executor or asynchronous HTTP client so the WebSocket consumer never stalls while fetching snapshots.
- **Configurable tolerances:** Expose the change-detection thresholds (`progress`, temperatures, etc.) via environment variables to let operators fine-tune chatter versus responsiveness without editing source.
- **Persistent metrics:** Emit lightweight counters (e.g., via Prometheus or MQTT) for reconnects, dropped payloads, and image rejections to simplify monitoring and troubleshooting.
