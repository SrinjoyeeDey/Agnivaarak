"""
hardware/nozzle_controller.py
=============================
Nozzle controller with simulated and hardware-backed actuation.

Pressure control supports two hardware modes:
  1. Relay-only fallback: pump is on/off, no variable throw modulation.
  2. PWM pressure channel: variable duty cycle controls pump/valve throw.
"""

from __future__ import annotations

import os
import time
from typing import Dict, List

from loguru import logger

from hardware.device_bus import DeviceBus

# GPIO pin map: nozzle_id -> (solenoid_pin, pump_relay_pin)
NOZZLE_PINS: Dict[int, tuple[int, int]] = {
    1: (17, 27),
    2: (22, 23),
    3: (24, 25),
    4: (5, 6),
}
ALARM_PIN = 18

# Optional PWM-capable pressure control pins.
# Configure with env vars PRESSURE_PWM_PIN_1 .. PRESSURE_PWM_PIN_4.
PRESSURE_PWM_PINS: Dict[int, int] = {
    nozzle_id: int(value)
    for nozzle_id in NOZZLE_PINS
    for value in [os.getenv(f"PRESSURE_PWM_PIN_{nozzle_id}", "").strip()]
    if value
}

PRESSURE_DUTY: Dict[str, int] = {
    "OFF": 0,
    "LOW": 30,
    "MEDIUM": 60,
    "HIGH": 85,
    "MAX": 100,
}

PWM_FREQUENCY_HZ = 200
COOLDOWN_DELAY = 2.0


class NozzleState:
    def __init__(self, nozzle_id: int):
        self.id = nozzle_id
        self.active = False
        self.mode = "OFF"
        self.pressure = "OFF"
        self.agent = "NONE"
        self.pan = 90.0
        self.tilt = 45.0
        self.last_activated = 0.0
        self.status = "IDLE"
        self.fire_type = None
        self.label = None
        self.intensity = None
        self.pressure_duty = 0
        self._scan_angle = 0.0

    def to_dict(self) -> dict:
        return {
            "device_id": self.id,
            "pan": self.pan,
            "tilt": self.tilt,
            "status": self.status,
            "active": self.active,
            "mode": self.mode,
            "pressure": self.pressure,
            "pressure_duty": self.pressure_duty,
            "agent": self.agent,
            "fire_type": self.fire_type,
            "label": self.label,
            "intensity": self.intensity,
        }


class NozzleController:
    def __init__(self, simulated: bool = True, num_nozzles: int = 4, device_bus: DeviceBus | None = None):
        self._simulated = simulated
        self._nozzles = {i: NozzleState(i) for i in range(1, num_nozzles + 1)}
        self._gpio = None
        self._pressure_pwm: Dict[int, object] = {}
        self._pressure_pwm_pins = {
            nozzle_id: pin
            for nozzle_id, pin in PRESSURE_PWM_PINS.items()
            if nozzle_id in self._nozzles
        }
        self._device_bus = device_bus or DeviceBus(enabled=False)

        if not simulated:
            self._init_gpio()

    def _init_gpio(self):
        """Real hardware path."""
        try:
            import RPi.GPIO as GPIO

            GPIO.setmode(GPIO.BCM)
            for nid, (solenoid_pin, pump_pin) in NOZZLE_PINS.items():
                if nid not in self._nozzles:
                    continue
                GPIO.setup(solenoid_pin, GPIO.OUT, initial=GPIO.LOW)
                GPIO.setup(pump_pin, GPIO.OUT, initial=GPIO.LOW)

            for nid, pwm_pin in self._pressure_pwm_pins.items():
                GPIO.setup(pwm_pin, GPIO.OUT, initial=GPIO.LOW)
                pwm_channel = GPIO.PWM(pwm_pin, PWM_FREQUENCY_HZ)
                pwm_channel.start(0)
                self._pressure_pwm[nid] = pwm_channel

            GPIO.setup(ALARM_PIN, GPIO.OUT, initial=GPIO.LOW)
            self._gpio = GPIO
            logger.success(
                "GPIO initialised (nozzles={}, pwm_pressure_channels={})",
                len(self._nozzles),
                sorted(self._pressure_pwm.keys()),
            )
        except Exception as exc:
            logger.error("GPIO init failed: {}. Falling back to simulation.", exc)
            self._simulated = True
            self._gpio = None
            self._pressure_pwm.clear()

    def execute(self, action) -> None:
        nid = action.nozzle_id
        pressure = self._normalize_pressure(getattr(action, "pressure", "MEDIUM"))
        mode = getattr(action, "mode", "DIRECT")
        pan = getattr(action, "pan", 90.0)
        tilt = getattr(action, "tilt", 45.0)

        if nid < 0:
            self.emergency_stop()
            return

        nozzle = self._nozzles.get(nid)
        if not nozzle:
            logger.warning("Unknown or invalid nozzle ID: {}", nid)
            return

        f_type = getattr(action, "fire_type", "fire")
        f_agent = getattr(action, "agent", "WATER")
        f_intens = getattr(action, "intensity", pressure)

        nozzle.active = True
        nozzle.status = "LOCKED"
        nozzle.mode = mode
        nozzle.pressure = pressure
        nozzle.pressure_duty = self._pressure_to_duty(pressure)
        nozzle.label = getattr(action, "label", f_type)
        nozzle.agent = f_agent
        nozzle.pan = pan
        nozzle.tilt = tilt
        nozzle.fire_type = f_type
        nozzle.intensity = f_intens
        nozzle.last_activated = time.time()

        logger.info(
            "Nozzle {} EXECUTE: mode={} pressure={} duty={} agent={}",
            nid,
            mode,
            nozzle.pressure,
            nozzle.pressure_duty,
            nozzle.agent,
        )
        logger.info(
            "\n[DEVICE {}]\nMode: LOCKED\nFire Type: {}\nIntensity: {}\nPressure: {}\nDuty: {}%\nAgent: {}\nTarget: PAN {:.1f} / TILT {:.1f}",
            nid,
            str(f_type).upper(),
            str(f_intens).upper(),
            pressure.upper(),
            nozzle.pressure_duty,
            str(f_agent).upper(),
            pan,
            tilt,
        )

        self._log_action(nozzle, mode)

        if not self._simulated:
            self._actuate_hardware(nid, pan, tilt, pressure)
        self._emit_nozzle_command(nozzle)

    def _log_action(self, nozzle: NozzleState, mode: str):
        logger.info(
            "Device_{} moving to PAN:{:.1f} TILT:{:.1f} | Spraying @ {} ({}%)",
            nozzle.id,
            nozzle.pan,
            nozzle.tilt,
            nozzle.pressure,
            nozzle.pressure_duty,
        )
        print(f"  Moving to PAN:{nozzle.pan:.1f} TILT:{nozzle.tilt:.1f}")
        print(f"  Spraying (Mode: {mode}, Pressure: {nozzle.pressure}, Duty: {nozzle.pressure_duty}%)")

    def _actuate_hardware(self, nozzle_id: int, pan: float, tilt: float, pressure: str):
        """Real hardware: solenoid + pump + optional PWM pressure modulation."""
        if not self._gpio or nozzle_id not in NOZZLE_PINS:
            return

        solenoid_pin, pump_pin = NOZZLE_PINS[nozzle_id]
        duty = self._pressure_to_duty(pressure)

        if duty <= 0:
            self._gpio.output(solenoid_pin, self._gpio.LOW)
            self._gpio.output(pump_pin, self._gpio.LOW)
            self._set_pressure_output(nozzle_id, 0)
            return

        self._gpio.output(solenoid_pin, self._gpio.HIGH)
        self._gpio.output(pump_pin, self._gpio.HIGH)
        self._set_pressure_output(nozzle_id, duty)

        # Pan/tilt servos are still controlled by the camera/aim subsystem.
        logger.debug(
            "Hardware actuation: nozzle={} pan={:.1f} tilt={:.1f} pressure={} duty={}%",
            nozzle_id,
            pan,
            tilt,
            pressure,
            duty,
        )

    def _set_pressure_output(self, nozzle_id: int, duty: int):
        pwm_channel = self._pressure_pwm.get(nozzle_id)
        if pwm_channel is not None:
            pwm_channel.ChangeDutyCycle(duty)
            return

        if duty not in (0, 100):
            logger.warning(
                "No PWM pressure channel configured for nozzle {}. Falling back to binary pump control for duty {}%%.",
                nozzle_id,
                duty,
            )

    def _emit_nozzle_command(self, nozzle: NozzleState):
        self._device_bus.emit(
            "nozzle_command",
            {
                "device_id": nozzle.id,
                "status": nozzle.status,
                "mode": nozzle.mode,
                "pan": round(nozzle.pan, 1),
                "tilt": round(nozzle.tilt, 1),
                "pressure": nozzle.pressure,
                "pressure_duty": nozzle.pressure_duty,
                "agent": nozzle.agent,
                "fire_type": nozzle.fire_type,
                "label": nozzle.label,
                "intensity": nozzle.intensity,
                "active": nozzle.active,
            },
        )

    def deactivate_others(self, active_ids: List[int]):
        for nid, nozzle in self._nozzles.items():
            if nid not in active_ids and nozzle.active:
                nozzle.active = False
                nozzle.status = "SCANNING"
                nozzle.mode = "OFF"
                nozzle.pressure = "OFF"
                nozzle.pressure_duty = 0
                logger.debug("Device_{} explicitly deactivated", nid)
                if not self._simulated:
                    self._actuate_hardware(nid, nozzle.pan, nozzle.tilt, "OFF")
                self._emit_nozzle_command(nozzle)

    def trigger_alarm(self):
        if self._simulated:
            logger.error("PHYSICAL ALARM ACTIVATED (Demo Mode)")
        elif self._gpio:
            self._gpio.output(ALARM_PIN, self._gpio.HIGH)
        self._device_bus.emit("alarm_command", {"active": True})

    def stop_alarm(self):
        if not self._simulated and self._gpio:
            self._gpio.output(ALARM_PIN, self._gpio.LOW)
        self._device_bus.emit("alarm_command", {"active": False})

    def cooldown(self):
        now = time.time()
        for nozzle in self._nozzles.values():
            if nozzle.active and (now - nozzle.last_activated) > COOLDOWN_DELAY:
                nozzle.active = False
                nozzle.status = "SCANNING"
                nozzle.mode = "OFF"
                nozzle.pressure = "OFF"
                nozzle.pressure_duty = 0
                logger.debug("Device_{} returned to SCANNING", nozzle.id)
                if not self._simulated:
                    self._actuate_hardware(nozzle.id, nozzle.pan, nozzle.tilt, "OFF")
                self._emit_nozzle_command(nozzle)

            if not nozzle.active:
                nozzle.status = "SCANNING"
                nozzle._scan_angle = (nozzle._scan_angle + 5) % 180
                nozzle.pan = nozzle._scan_angle
                nozzle.tilt = 45.0

    def emergency_stop(self):
        logger.critical("EMERGENCY STOP - shutting all devices")
        for nozzle in self._nozzles.values():
            nozzle.active = False
            nozzle.status = "STOPPED"
            nozzle.mode = "OFF"
            nozzle.pressure = "OFF"
            nozzle.pressure_duty = 0
            if not self._simulated:
                self._actuate_hardware(nozzle.id, nozzle.pan, nozzle.tilt, "OFF")
            self._emit_nozzle_command(nozzle)
        self._device_bus.emit("emergency_stop", {"active": True})
        print("  ALL DEVICES STOPPED")

    def manual_activate(self, nozzle_id: int, pressure: str = "MEDIUM") -> bool:
        if nozzle_id not in self._nozzles:
            return False

        normalized_pressure = self._normalize_pressure(pressure)
        nozzle = self._nozzles[nozzle_id]
        nozzle.active = True
        nozzle.status = "MANUAL"
        nozzle.mode = "MANUAL"
        nozzle.pressure = normalized_pressure
        nozzle.pressure_duty = self._pressure_to_duty(normalized_pressure)
        nozzle.last_activated = time.time()
        logger.info(
            "Manual override: device_{} @ {} ({}%)",
            nozzle_id,
            normalized_pressure,
            nozzle.pressure_duty,
        )

        if not self._simulated:
            self._actuate_hardware(nozzle_id, nozzle.pan, nozzle.tilt, normalized_pressure)
        self._emit_nozzle_command(nozzle)
        return True

    def status(self) -> List[dict]:
        return [n.to_dict() for n in self._nozzles.values()]

    def cleanup(self):
        self.emergency_stop()
        for pwm_channel in self._pressure_pwm.values():
            try:
                pwm_channel.stop()
            except Exception:
                pass
        if not self._simulated and self._gpio:
            try:
                self._gpio.cleanup()
            except Exception:
                pass
        self._device_bus.close()

    @staticmethod
    def _normalize_pressure(pressure: str | None) -> str:
        raw = (pressure or "MEDIUM").strip().upper()
        if raw == "CRITICAL":
            return "MAX"
        return raw if raw in PRESSURE_DUTY else "MEDIUM"

    @staticmethod
    def _pressure_to_duty(pressure: str | None) -> int:
        normalized = NozzleController._normalize_pressure(pressure)
        return PRESSURE_DUTY.get(normalized, PRESSURE_DUTY["MEDIUM"])
