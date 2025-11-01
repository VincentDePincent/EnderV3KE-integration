import asyncio
import json
import logging
import math
import os
import time
from typing import Any, Dict

import requests
import websockets
import paho.mqtt.client as mqtt


def load_env_file(filepath: str = ".env") -> None:
    """Populate os.environ with key=value pairs from a simple .env file."""
    if not os.path.exists(filepath):
        return

    try:
        with open(filepath, "r", encoding="utf-8") as env_file:
            for line in env_file:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                key = key.strip()
                if not key or key in os.environ:
                    continue
                os.environ[key] = value.strip().strip('"').strip("'")
    except OSError as exc:
        raise RuntimeError(f"Unable to read environment file {filepath}: {exc}") from exc


load_env_file()

# Configuration (can also be set via environment variables)
MQTT_BROKER       = os.getenv("MQTT_BROKER", "[your mqtt broker]")
MQTT_PORT         = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC        = os.getenv("MQTT_TOPIC", "[mqtt topic]")
MQTT_USER         = os.getenv("MQTT_USER")
MQTT_PASS         = os.getenv("MQTT_PASS")
MQTT_USE_TLS      = os.getenv("MQTT_USE_TLS", "false").lower() in {"1", "true", "yes"}
MQTT_TLS_INSECURE = os.getenv("MQTT_TLS_INSECURE", "false").lower() in {"1", "true", "yes"}
WS_URL            = os.getenv("PRINTER_WS_URL", "ws://[your ws-url]/")
PUBLISH_INTERVAL  = float(os.getenv("PUBLISH_INTERVAL", 2))
IMAGE_URL         = os.getenv(
    "PRINTER_SNAPSHOT_URL",
    "http://[your printer snapshot url]/downloads/original/current_print_image.png",
)
LOCAL_IMAGE_PATH  = os.getenv("LOCAL_IMAGE_PATH", "public/images/3dprint.png")
TMP_IMAGE_PATH    = LOCAL_IMAGE_PATH + ".tmp"
EXPOSED_IMAGE_PATH = os.getenv("EXPOSED_IMAGE_PATH", "/local/images/3dprint.png")
MAX_IMAGE_BYTES   = int(os.getenv("MAX_IMAGE_BYTES", 5 * 1024 * 1024))
IMAGE_ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg"}
IMAGE_CHUNK_BYTES = 64 * 1024

# Ensure the HA images folder exists
os.makedirs(os.path.dirname(LOCAL_IMAGE_PATH), exist_ok=True)

# Setup logging
LOG_FILE = os.getenv("LOG_FILE", "v3kepull.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)


if PUBLISH_INTERVAL <= 0:
    logging.warning("PUBLISH_INTERVAL must be positive. Falling back to 2 seconds.")
    PUBLISH_INTERVAL = 2

if MAX_IMAGE_BYTES <= 0:
    logging.warning("MAX_IMAGE_BYTES must be positive. Falling back to 5 MiB.")
    MAX_IMAGE_BYTES = 5 * 1024 * 1024

# MQTT callbacks
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info("Connected to MQTT broker.")
    else:
        logging.error(f"Failed to connect to MQTT broker, return code {rc}")

def on_disconnect(client, userdata, rc):
    logging.warning(f"Disconnected from MQTT broker (rc={rc}), will attempt to reconnect.")

# Initialize MQTT client
mqtt_client = mqtt.Client()
if MQTT_USER and MQTT_PASS:
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
elif MQTT_USER or MQTT_PASS:
    logging.warning("Both MQTT_USER and MQTT_PASS are required for authenticated connections; proceeding without auth.")
else:
    logging.warning("No MQTT credentials supplied; connecting without authentication.")
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect

if MQTT_USE_TLS:
    mqtt_client.tls_set()
    if MQTT_TLS_INSECURE:
        mqtt_client.tls_insecure_set(True)
try:
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    mqtt_client.loop_start()
except Exception as e:
    logging.error(f"Initial MQTT connection failed: {e}")

# State caches
cached_state    = {}
last_sent_state = {}
last_sent_time  = time.monotonic() - PUBLISH_INTERVAL
current_filename = None

def download_image():
    """Download the printer snapshot safely and write it atomically."""
    try:
        resp = requests.get(
            IMAGE_URL,
            timeout=5,
            stream=True,
            headers={"Accept": "image/*"},
        )
        with resp:
            if resp.status_code != 200:
                logging.warning(f"Image request returned HTTP {resp.status_code}")
                return

            content_type = resp.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type and content_type not in IMAGE_ALLOWED_CONTENT_TYPES:
                logging.warning(
                    "Unexpected image Content-Type '%s'; aborting download.",
                    content_type or "<missing>",
                )
                return

            bytes_written = 0
            over_limit = False
            with open(TMP_IMAGE_PATH, "wb") as f:
                for chunk in resp.iter_content(chunk_size=IMAGE_CHUNK_BYTES):
                    if not chunk:
                        continue
                    bytes_written += len(chunk)
                    if bytes_written > MAX_IMAGE_BYTES:
                        logging.warning(
                            "Image exceeded %s bytes; discarding partial download.",
                            MAX_IMAGE_BYTES,
                        )
                        over_limit = True
                        break
                    f.write(chunk)

            if over_limit:
                try:
                    os.remove(TMP_IMAGE_PATH)
                except FileNotFoundError:
                    pass
                return

            os.replace(TMP_IMAGE_PATH, LOCAL_IMAGE_PATH)
            logging.info("Image downloaded and saved (%s bytes).", bytes_written)
    except PermissionError:
        logging.warning("Permission denied writing image file. Check folder ownership.")
    except requests.RequestException as exc:
        logging.warning("Error downloading image: %s", exc)
    except Exception as e:
        logging.warning(f"Unexpected error downloading image: {e}")


def safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        result = str(value)
    except Exception:
        return default
    return result


def safe_float(value: Any, default: float = 0.0) -> float:
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


def safe_int(value: Any, default: int = 0) -> int:
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


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def sanitise_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    progress = clamp(safe_float(state.get("printProgress"), 0.0), 0.0, 100.0)
    layer = safe_int(state.get("layer"), 0)
    total_layers = max(layer, safe_int(state.get("TotalLayer"), 0))
    elapsed = max(0, safe_int(state.get("printJobTime"), 0))
    remaining = max(0, safe_int(state.get("printLeftTime"), 0))
    nozzle_temp = safe_float(state.get("nozzleTemp"), 0.0)
    bed_temp = safe_float(state.get("bedTemp0"), 0.0)
    used_filament = max(0, safe_int(state.get("usedMaterialLength"), 0))
    filename = os.path.basename(safe_str(state.get("printFileName", "")))

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
        "image_url": EXPOSED_IMAGE_PATH,
    }

def extract_data(data: dict) -> dict:
    """
    Merge incoming data into cached_state, detect new print jobs,
    download image once per job, and build the MQTT payload.
    """
    global current_filename

    # Merge only the keys we care about
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
            cached_state[key] = data[key]

    # If a job just finished (progress back to zero), clear filename so next job triggers download
    if safe_float(data.get("printProgress"), 1.0) == 0:
        current_filename = None

    # Get base filename
    filename = os.path.basename(safe_str(cached_state.get("printFileName", "")))

    # On new job start, grab image once
    if filename and filename != current_filename:
        current_filename = filename
        download_image()

    return sanitise_payload(cached_state)

def has_meaningful_change(new: dict, old: dict) -> bool:
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
        else:
            if value != other:
                return True

    for key in old:
        if key not in new:
            return True

    return False

async def listen_to_printer():
    global last_sent_state, last_sent_time
    backoff = 1
    while True:
        try:
            async with websockets.connect(
                WS_URL,
                ping_interval=20,
                ping_timeout=20,
                max_size=2 ** 20,
            ) as ws:
                logging.info("WebSocket connected.")
                backoff = 1
                while True:
                    msg = await ws.recv()
                    try:
                        data = json.loads(msg)
                        if not isinstance(data, dict):
                            logging.debug("Ignoring non-dict payload: %s", data)
                            continue
                        full = extract_data(data)

                        now = time.monotonic()
                        if (now - last_sent_time) >= PUBLISH_INTERVAL and has_meaningful_change(full, last_sent_state):
                            mqtt_client.publish(MQTT_TOPIC, json.dumps(full))
                            logging.info(f"Published: {full}")
                            last_sent_state = full.copy()
                            last_sent_time = now
                    except json.JSONDecodeError:
                        logging.warning(f"Received non-JSON WS message: {msg}")
                    except websockets.ConnectionClosedError as wc:
                        logging.warning(f"WebSocket closed: {wc}")
                        break
        except Exception as e:
            logging.error(f"WebSocket error: {e}")
        logging.info(f"Reconnecting in {backoff}s…")
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)

if __name__ == "__main__":
    try:
        asyncio.run(listen_to_printer())
    except KeyboardInterrupt:
        logging.info("Shutting down…")
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
