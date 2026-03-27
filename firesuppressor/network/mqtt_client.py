"""
network/mqtt_client.py
=======================
Thin wrapper around paho-mqtt for fire event messaging.

Topic Schema
────────────
firesuppressor/{node_id}/fire_event     ← fire detected (published)
firesuppressor/{node_id}/status         ← periodic heartbeat
firesuppressor/global/emergency_stop    ← broadcast e-stop
firesuppressor/global/assist_request    ← ask other nodes for help

Example fire_event message
──────────────────────────
{
  "device"     : 1,
  "zone"       : "NORTH",
  "ts"         : 1710000000.123,
  "fire_angle" : 45.0,
  "intensity"  : 0.78,
  "level"      : "HIGH",
  "nozzle_id"  : 2,
  "fires"      : [
    {"id": "abc12345", "bbox": [100, 80, 90, 110],
     "angle": 45.0, "level": "HIGH", "confidence": 0.92}
  ]
}

Example assist_request message
────────────────────────────────
{
  "requesting_node" : 1,
  "overloaded"      : true,
  "active_fires"    : 5,
  "ts"              : 1710000005.0
}
"""

from __future__ import annotations

import json
import threading
import time
from typing import Callable, Dict

from loguru import logger

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    logger.warning("paho-mqtt not installed → MQTT disabled")


class MQTTClient:
    BASE_TOPIC = "firesuppressor"

    def __init__(self, host: str = "localhost", port: int = 1883,
                 node_id: int = 1, keepalive: int = 60):
        self._host      = host
        self._port      = port
        self._node_id   = node_id
        self._keepalive = keepalive
        self._client    = None
        self._handlers: Dict[str, Callable] = {}
        self._connected = False

    def connect(self):
        if not MQTT_AVAILABLE:
            logger.warning("MQTT unavailable – running in isolated mode")
            return
        try:
            self._client = mqtt.Client(
                client_id=f"firesuppressor_node_{self._node_id}",
                clean_session=True)
            self._client.on_connect    = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_message    = self._on_message

            logger.info("📡 MQTT: Connecting to {}:{}...", self._host, self._port)
            self._client.connect(self._host, self._port, self._keepalive)
            self._client.loop_start()
        except Exception as exc:
            logger.error("❌ MQTT: Connect failed: {} – will retry", exc)

    def disconnect(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()

    # ── Callbacks ─────────────────────────────────────────
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            logger.success("✅ MQTT: Connected successfully to {}:{}", self._host, self._port)
            client.subscribe(f"{self.BASE_TOPIC}/global/#")
            client.subscribe(f"{self.BASE_TOPIC}/+/fire_event")
        else:
            logger.error("❌ MQTT: Connection refused (rc={})", rc)

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        if rc != 0:
            logger.warning("⚠️ MQTT: Unexpectedly disconnected (rc={}) - auto-reconnecting", rc)
        else:
            logger.info("📡 MQTT: Disconnected.")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            topic   = msg.topic
            logger.debug("MQTT ← {} : {}", topic, payload)
            handler = self._handlers.get(topic)
            if handler:
                handler(topic, payload)
        except Exception as exc:
            logger.error("MQTT message parse error: {}", exc)

    # ── Publish helpers (Enhanced) ────────────────────────
    def publish_enhanced_event(self, event: dict):
        """Standardized industrial fire event."""
        device_id = event.get("device_id", self._node_id)
        topic = f"{self.BASE_TOPIC}/device/{device_id}/status"
        self._publish(topic, event)

    def publish_emergency_stop(self):
        payload = {"issued_by": self._node_id, "timestamp": time.time()}
        self._publish(f"{self.BASE_TOPIC}/global/emergency_stop", payload)

    def subscribe(self, topic: str, handler: Callable):
        self._handlers[topic] = handler
        if self._client and self._connected:
            self._client.subscribe(topic)

    def _publish(self, topic: str, payload: dict):
        if not self._client or not self._connected:
            return
        try:
            self._client.publish(topic, json.dumps(payload), qos=1)
            logger.debug("MQTT → Published to {}", topic)
        except Exception as exc:
            logger.error("MQTT publish failed: {}", exc)
