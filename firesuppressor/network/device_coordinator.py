"""
network/device_coordinator.py
==============================
Handles multi-device coordination via MQTT.

Logic:
  • If local node has > MAX_LOCAL_FIRES active targets → publishes
    assist_request to global topic.
  • Other nodes listen for assist_request and take over if they
    have spare nozzle capacity.
  • Emergency stop from ANY node propagates to ALL nodes instantly.
"""

from __future__ import annotations

import time
from loguru import logger

MAX_LOCAL_FIRES = 4


class DeviceCoordinator:
    def __init__(self, mqtt, nozzle_ctrl, node_id: int = 1):
        self._mqtt        = mqtt
        self._nozzle      = nozzle_ctrl
        self._node_id     = node_id
        self._peers: dict = {}   # node_id → last_status

        # Subscribe to peer events
        mqtt.subscribe(
            f"firesuppressor/+/fire_event",
            self._on_peer_fire_event)
        mqtt.subscribe(
            "firesuppressor/global/assist_request",
            self._on_assist_request)
        mqtt.subscribe(
            "firesuppressor/global/emergency_stop",
            self._on_global_estop)

    def broadcast_fire_event(self, fires: list, angle: float):
        if not fires:
            return
        top  = fires[0]
        intv = (top.get("intensity") or {})
        self._mqtt.publish_fire_event(
            fires      = fires,
            angle      = angle,
            nozzle_id  = 0,
            level      = intv.get("level", "MEDIUM"),
            intensity  = intv.get("score", 0.5))

        if len(fires) > MAX_LOCAL_FIRES:
            logger.warning("Node {} overloaded ({} fires) – requesting assist",
                           self._node_id, len(fires))
            self._mqtt.publish_assist_request(len(fires))

    # ── Incoming callbacks ────────────────────────────────
    def _on_peer_fire_event(self, topic: str, payload: dict):
        peer_id = payload.get("device")
        if peer_id == self._node_id:
            return   # own event
        self._peers[peer_id] = {"ts": time.time(), "fires": payload.get("fires", [])}
        logger.info("📡 Node {} reports {} fire(s) at {:.1f}°",
                    peer_id,
                    len(payload.get("fires", [])),
                    payload.get("fire_angle", 0))

    def _on_assist_request(self, topic: str, payload: dict):
        requesting = payload.get("requesting_node")
        if requesting == self._node_id:
            return
        active_local = sum(
            1 for n in self._nozzle.status() if n["active"])
        if active_local < 3:
            logger.info(
                "📡 Assisting Node {} (we have {} spare nozzles)",
                requesting, 4 - active_local)
            # In a real system: coordinate target handoff via MQTT
        else:
            logger.info("📡 Cannot assist Node {} – we are also at capacity",
                        requesting)

    def _on_global_estop(self, topic: str, payload: dict):
        logger.critical("⛔ Global emergency stop from MQTT!")
        self._nozzle.emergency_stop()
