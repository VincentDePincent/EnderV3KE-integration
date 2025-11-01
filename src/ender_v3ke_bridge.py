import asyncio
import json
import logging
import os
import time
from typing import Optional

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
MQTT_BROKER       = os.getenv("MQTT_BROKER", "192.168.1.100")
MQTT_PORT         = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC        = os.getenv("MQTT_TOPIC", "home/3dprinter/status")
MQTT_USER         = os.getenv("MQTT_USER")
MQTT_PASS         = os.getenv("MQTT_PASS")
MQTT_USE_TLS      = os.getenv("MQTT_USE_TLS", "false").lower() in {"1", "true", "yes"}
MQTT_TLS_INSECURE = os.getenv("MQTT_TLS_INSECURE", "false").lower() in {"1", "true", "yes"}
WS_URL            = os.getenv("PRINTER_WS_URL", "ws://192.168.1.53:9999/")
PUBLISH_INTERVAL  = float(os.getenv("PUBLISH_INTERVAL", 2))
IMAGE_URL         = "http://192.168.1.53/downloads/original/current_print_image.png"
LOCAL_IMAGE_PATH  = "/srv/HA/config/www/images/3dprint.png"
TMP_IMAGE_PATH    = LOCAL_IMAGE_PATH + ".tmp"
EXPOSED_IMAGE_PATH = "/local/images/3dprint.png"

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


def require_secret(value: Optional[str], name: str) -> str:
    if value:
        return value
    logging.critical("Missing required secret %s. Populate it via environment variables or .env.", name)
    raise SystemExit(1)


MQTT_USER = require_secret(MQTT_USER, "MQTT_USER")
MQTT_PASS = require_secret(MQTT_PASS, "MQTT_PASS")

if PUBLISH_INTERVAL <= 0:
    logging.warning("PUBLISH_INTERVAL must be positive. Falling back to 2 seconds.")
    PUBLISH_INTERVAL = 2

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
mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
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
    """Download the printer snapshot and write it atomically."""
    try:
        resp = requests.get(IMAGE_URL, timeout=5)
        if resp.status_code == 200:
            with open(TMP_IMAGE_PATH, "wb") as f:
                f.write(resp.content)
            os.replace(TMP_IMAGE_PATH, LOCAL_IMAGE_PATH)
            logging.info("Image downloaded and saved.")
        else:
            logging.warning(f"Image request returned HTTP {resp.status_code}")
    except PermissionError:
        logging.warning("Permission denied writing image file. Check folder ownership.")
    except Exception as e:
        logging.warning(f"Error downloading image: {e}")

def extract_data(data: dict) -> dict:
    """
    Merge incoming data into cached_state, detect new print jobs,
    download image once per job, and build the MQTT payload.
    """
    global current_filename

    # Merge
    cached_state.update(data)

    # If a job just finished (progress back to zero), clear filename so next job triggers download
    if data.get("printProgress") == 0:
        current_filename = None

    # Get base filename
    filename = os.path.basename(cached_state.get("printFileName", ""))

    # On new job start, grab image once
    if filename and filename != current_filename:
        current_filename = filename
        download_image()

    # Build payload
    return {
        "progress":     cached_state.get("printProgress"),
        "layer":        cached_state.get("layer"),
        "total_layers": cached_state.get("TotalLayer"),
        "elapsed":      cached_state.get("printJobTime"),
        "remaining":    cached_state.get("printLeftTime"),
        "filename":     filename,
        "nozzle_temp":  float(cached_state.get("nozzleTemp", 0)),
        "bed_temp":     float(cached_state.get("bedTemp0", 0)),
        "used_filament":cached_state.get("usedMaterialLength"),
        "image_url":    EXPOSED_IMAGE_PATH
    }

def has_meaningful_change(new: dict, old: dict) -> bool:
    return new != old

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
