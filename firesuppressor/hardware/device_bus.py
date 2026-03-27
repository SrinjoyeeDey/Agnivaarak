"""
hardware/device_bus.py
======================
Transport layer for real hardware integration.

The vision/control stack runs on the edge computer and emits JSON commands.
Those commands can be:
  - simulated/logged locally
  - sent over serial to a microcontroller

This keeps high-level fire logic separate from low-level real-time actuation.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict

from loguru import logger


class DeviceBus:
    def __init__(
        self,
        enabled: bool = False,
        transport: str | None = None,
        serial_port: str | None = None,
        baudrate: int | None = None,
    ):
        self._enabled = enabled
        self._transport = (transport or os.getenv("DEVICE_BUS_TRANSPORT", "noop")).strip().lower()
        self._serial_port = serial_port or os.getenv("DEVICE_BUS_SERIAL_PORT", "").strip()
        self._baudrate = baudrate or int(os.getenv("DEVICE_BUS_BAUDRATE", "115200"))
        self._serial = None
        self._lock = threading.Lock()

        if self._enabled:
            self._connect()

    def _connect(self):
        if self._transport != "serial":
            logger.info("DeviceBus transport={} (no external controller)", self._transport)
            return

        if not self._serial_port:
            logger.warning("DeviceBus serial transport requested but no serial port configured")
            return

        try:
            import serial  # type: ignore

            self._serial = serial.Serial(self._serial_port, self._baudrate, timeout=0.2)
            logger.success("DeviceBus serial connected on {} @ {}", self._serial_port, self._baudrate)
        except Exception as exc:
            logger.error("DeviceBus serial connection failed: {}", exc)
            self._serial = None

    def emit(self, command_type: str, payload: Dict[str, Any]) -> bool:
        message = {
            "ts": round(time.time(), 3),
            "type": command_type,
            "payload": payload,
        }
        encoded = json.dumps(message, separators=(",", ":"))

        if not self._enabled or self._transport in ("noop", "log"):
            logger.debug("DeviceBus {} => {}", command_type, encoded)
            return True

        if self._transport == "serial":
            return self._emit_serial(encoded)

        logger.warning("Unknown DeviceBus transport={} - dropping command", self._transport)
        return False

    def _emit_serial(self, encoded: str) -> bool:
        if self._serial is None:
            logger.warning("DeviceBus serial not connected - dropping command")
            return False

        try:
            with self._lock:
                self._serial.write((encoded + "\n").encode("utf-8"))
                self._serial.flush()
            return True
        except Exception as exc:
            logger.error("DeviceBus serial write failed: {}", exc)
            return False

    def close(self):
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
