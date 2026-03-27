"""
hardware/camera_controller.py
=============================
Pan-tilt camera controller with simulation, PCA9685 support, and external bus commands.
"""

from __future__ import annotations

import time

from loguru import logger

from hardware.device_bus import DeviceBus

PAN_PWM_MIN = 150
PAN_PWM_MAX = 600
TILT_PWM_MIN = 200
TILT_PWM_MAX = 450

SWEEP_SPEED = 1.0


class CameraController:
    def __init__(self, simulated: bool = True, device_bus: DeviceBus | None = None):
        self._simulated = simulated
        self._pan_angle = 0.0
        self._tilt_angle = 0.0
        self._pca = None
        self._sweep_active = True
        self._device_bus = device_bus or DeviceBus(enabled=False)

        if not simulated:
            self._init_pca9685()

    def _init_pca9685(self):
        try:
            from adafruit_pca9685 import PCA9685
            import board
            import busio

            i2c = busio.I2C(board.SCL, board.SDA)
            self._pca = PCA9685(i2c)
            self._pca.frequency = 50
            logger.success("PCA9685 PWM driver initialised at 0x40")
        except Exception as exc:
            logger.error("PCA9685 init failed: {} -> simulation", exc)
            self._simulated = True

    def tick(self):
        if self._simulated and self._sweep_active:
            self._pan_angle = (self._pan_angle + SWEEP_SPEED) % 360
            if int(self._pan_angle) % 30 == 0:
                logger.debug("Camera at {:.0f} deg", self._pan_angle)
                print(f"  Camera at angle {self._pan_angle:.0f} deg")
                self._emit_camera_state("scan")

    def current_angle(self) -> float:
        self.tick()
        return round(self._pan_angle, 1)

    def point_at(self, angle: float):
        self._sweep_active = False
        self._pan_angle = angle % 360
        logger.info("Camera -> {:.1f} deg", self._pan_angle)
        if not self._simulated and self._pca:
            pwm = self._angle_to_pwm(self._pan_angle, PAN_PWM_MIN, PAN_PWM_MAX, 0, 360)
            self._pca.channels[0].duty_cycle = self._pwm_to_duty(pwm)
        self._emit_camera_state("point")

    def set_tilt(self, angle: float):
        self._tilt_angle = max(-30.0, min(90.0, angle))
        if not self._simulated and self._pca:
            pwm = self._angle_to_pwm(self._tilt_angle, TILT_PWM_MIN, TILT_PWM_MAX, -30, 90)
            self._pca.channels[1].duty_cycle = self._pwm_to_duty(pwm)
        self._emit_camera_state("tilt")

    def resume_scan(self):
        self._sweep_active = True
        self._emit_camera_state("resume_scan")

    def pixel_to_angle(self, pixel_x: int, frame_width: int, fov_deg: float = 90.0) -> float:
        norm = (pixel_x / frame_width) - 0.5
        offset = norm * fov_deg
        abs_angle = (self._pan_angle + offset) % 360
        return round(abs_angle, 1)

    def angle_to_pixel(self, target_angle: float, frame_width: int, fov_deg: float = 90.0) -> int:
        offset = target_angle - self._pan_angle
        while offset > 180:
            offset -= 360
        while offset < -180:
            offset += 360
        norm = offset / fov_deg
        pixel_x = int((norm + 0.5) * frame_width)
        return max(0, min(frame_width - 1, pixel_x))

    @staticmethod
    def _angle_to_pwm(angle, pwm_min, pwm_max, angle_min, angle_max) -> int:
        ratio = (angle - angle_min) / (angle_max - angle_min)
        return int(pwm_min + ratio * (pwm_max - pwm_min))

    @staticmethod
    def _pwm_to_duty(pwm_val: int) -> int:
        return int(pwm_val / 4096 * 65535)

    def calibrate(self):
        if self._simulated:
            print("Cannot calibrate in simulation mode. Use --real-hardware.")
            return
        cal = {}
        for angle in (0, 90, 180, 270):
            input(f"Position camera to {angle} deg and press Enter...")
            cal[angle] = {"pwm": None, "note": "manual"}
        import json
        import pathlib

        pathlib.Path("docs/servo_calibration.json").write_text(json.dumps(cal, indent=2))
        print("Calibration saved to docs/servo_calibration.json")

    def _emit_camera_state(self, command: str):
        self._device_bus.emit(
            "camera_command",
            {
                "command": command,
                "pan": round(self._pan_angle, 1),
                "tilt": round(self._tilt_angle, 1),
                "sweep_active": self._sweep_active,
            },
        )


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--calibrate", action="store_true")
    p.add_argument("--real-hardware", action="store_true")
    args = p.parse_args()
    ctrl = CameraController(simulated=not args.real_hardware)
    if args.calibrate:
        ctrl.calibrate()
    else:
        for _ in range(20):
            angle = ctrl.current_angle()
            print(f"Camera @ {angle:.1f} deg")
            time.sleep(0.1)
