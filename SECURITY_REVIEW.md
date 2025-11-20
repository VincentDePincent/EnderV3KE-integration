# Ender V3KE Home Assistant Integration — Security Review

## Summary
The integration now runs as a Home Assistant custom component that streams printer telemetry over WebSocket, sanitises the data, updates sensors, optionally republishes the same payload to an MQTT topic, and saves a bounded snapshot into `/local`. The move into the HA runtime removes hard-coded secrets and shifts MQTT publishing to the built-in MQTT integration, but traffic to the printer still defaults to plaintext `ws://`/`http://`, and snapshot trust remains limited to basic content-type and size checks.

## Findings

### 1. Printer transports remain unencrypted
The config flow defaults to `ws://` for the printer feed and `http://` for snapshots, leaving telemetry and images visible or modifiable to on-path attackers on the LAN. TLS settings are not exposed in the flow, so operators must supply secure URLs manually if their firmware supports them.

*Mitigation:* Prefer `wss://` and `https://` endpoints where available, or isolate the printer on a trusted network segment (e.g., VLAN/VPN) to prevent interception or tampering.

### 2. Snapshot validation is minimal
Snapshots are streamed with a size cap and content-type allowlist before being atomically written to disk, but the integration does not verify image magic numbers or decode the file to ensure it is a valid PNG/JPEG. A malicious on-path actor could return a small, mislabeled payload that front-end consumers might still render.

*Mitigation:* Add lightweight magic-number checks (e.g., `imghdr.what`) or decode-and-re-encode snapshots server-side to ensure the content matches the declared MIME type before exposing it via `/local`.

### 3. MQTT publishing depends on external broker hardening
MQTT telemetry is published through Home Assistant's MQTT integration if it is loaded. The add-on/broker configuration (TLS, credentials, ACLs) remains outside this integration's control; if the broker permits anonymous or plaintext sessions, those messages could be sniffed or injected on shared networks.

*Mitigation:* Enforce authenticated, TLS-protected MQTT in the Home Assistant MQTT integration and restrict topics/ACLs to the expected telemetry path.

## Operational opportunities
- Expose option flow controls for publish interval, tolerances, and snapshot limits so operators can tune chatter versus freshness without reinstalling the integration.
- Consider adding a diagnostics endpoint or logbook events for WebSocket reconnects, dropped payloads, and rejected snapshots to ease troubleshooting.
- If dashboards need the snapshot directly, a dedicated `camera` platform could reuse the downloaded file instead of relying solely on attributes and MQTT payloads.
