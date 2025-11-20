"""Constants for the Ender V3KE integration."""

from __future__ import annotations

DOMAIN = "ender_v3ke"

CONF_WS_URL = "ws_url"
CONF_MQTT_TOPIC = "mqtt_topic"
CONF_SNAPSHOT_URL = "snapshot_url"
CONF_LOCAL_IMAGE_PATH = "local_image_path"
CONF_EXPOSED_IMAGE_PATH = "exposed_image_path"
CONF_PUBLISH_INTERVAL = "publish_interval"
CONF_MAX_IMAGE_BYTES = "max_image_bytes"
CONF_ENABLE_MQTT = "enable_mqtt"

DEFAULT_WS_URL = "ws://[your ws-url]/"
DEFAULT_SNAPSHOT_URL = (
    "http://[your printer snapshot url]/downloads/original/current_print_image.png"
)
DEFAULT_MQTT_TOPIC = "ender_v3ke/status"
DEFAULT_PUBLISH_INTERVAL = 2.0
DEFAULT_MAX_IMAGE_BYTES = 5 * 1024 * 1024
DEFAULT_LOCAL_IMAGE_PATH = "www/ender_v3ke/print.png"
DEFAULT_EXPOSED_IMAGE_PATH = "/local/ender_v3ke/print.png"

IMAGE_ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg"}
IMAGE_CHUNK_BYTES = 64 * 1024
