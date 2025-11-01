# Ender V3KE MQTT Bridge Security Review

## Summary
This document reviews the `src/ender_v3ke_bridge.py` script that streams printer telemetry from the Ender V3KE WebSocket API and republishes it over MQTT. The assessment highlights security weaknesses, stability issues, and operational risks.

## Findings

### 1. Hard-coded default MQTT credentials
The script ships with a default MQTT password (`Dehol416!`) that is loaded even when the caller does not explicitly provide credentials via environment variables.【F:src/ender_v3ke_bridge.py†L12-L16】 Anyone who obtains the source can authenticate to the MQTT broker if the defaults are left unchanged, and secrets stored in the codebase often leak through version control or backups.

*Mitigation:* Require credentials to be provided at runtime (e.g., raise if the variables are unset) or load them from a secrets manager. Avoid storing real passwords in source control.

### 2. Unencrypted control channels
The WebSocket and HTTP endpoints default to `ws://` and `http://` URLs on the printer’s LAN.【F:src/ender_v3ke_bridge.py†L17-L19】 These transports provide no confidentiality or integrity guarantees, allowing attackers on the same network segment to intercept or tamper with telemetry. MQTT is likewise configured without TLS, making the broker connection susceptible to credential theft and message injection.

*Mitigation:* Prefer TLS-enabled endpoints (`wss://`, `https://`, and MQTT over TLS), and validate certificates. If the printer does not support TLS, place the integration on a segregated network and use a VPN or SSH tunnel to protect traffic in transit.

### 3. Insufficient validation of WebSocket payloads
Incoming WebSocket messages are merged directly into the cached state without schema validation.【F:src/ender_v3ke_bridge.py†L74-L89】 If the printer emits unexpected types (e.g., `null` for `nozzleTemp`), `float()` conversion raises a `TypeError`, bubbles up to the outer loop, and forces a reconnect cycle. Malformed data could therefore cause a denial of service.

*Mitigation:* Validate and sanitize the payload (type-check numeric fields, clamp ranges, supply defaults). Wrap conversions in `try/except` to isolate failures to individual fields instead of tearing down the WebSocket session.

### 4. Lack of bounds on downloaded snapshot
The `download_image` helper retrieves a snapshot over HTTP and writes it directly to disk without constraining size or verifying content type.【F:src/ender_v3ke_bridge.py†L54-L70】 A compromised printer or MitM attacker could respond with an arbitrarily large payload, exhausting disk space, or supply non-image data.

*Mitigation:* Stream the response with a maximum size, validate headers, and consider writing to a sandboxed directory with restricted permissions.

### 5. Weak change-detection logic
The MQTT publishing guard only compares the new payload with the last one for strict equality.【F:src/ender_v3ke_bridge.py†L103-L111】 Floating-point noise (e.g., repeated temperature values with negligible variation) will cause frequent publishes, while nested structures would not be compared deeply if introduced later.

*Mitigation:* Apply a tolerance when comparing numeric fields, and consider ignoring fields that can jitter rapidly.

### 6. Retry backoff disclosure
When the WebSocket connection fails, the script logs the exception but retains the default credential values in memory and continues retrying indefinitely.【F:src/ender_v3ke_bridge.py†L112-L127】 Repeated retries can create noisy logs and may hammer the printer.

*Mitigation:* Cap the total retries, add jitter to backoff, and differentiate between authentication/authorization failures and transient network issues.

## Recommendations
1. Remove secrets from source control and document secure configuration requirements.
2. Add input validation and error handling for all network-provided values.
3. Protect all transport channels with TLS or network isolation.
4. Harden the snapshot downloader with size limits and content verification.
5. Improve publish throttling to account for sensor jitter and to avoid unnecessary MQTT traffic.

