import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from hardware.nozzle_controller import NozzleController


class DummyAction:
    def __init__(self, nozzle_id=1, pressure="MAX", mode="DIRECT", pan=10.0, tilt=20.0):
        self.nozzle_id = nozzle_id
        self.pressure = pressure
        self.mode = mode
        self.pan = pan
        self.tilt = tilt
        self.agent = "WATER"
        self.fire_type = "a"
        self.intensity = "CRITICAL"
        self.label = "CLASS A (SOLID)"


class FakePWM:
    def __init__(self):
        self.duty = None
        self.stopped = False

    def ChangeDutyCycle(self, duty):
        self.duty = duty

    def stop(self):
        self.stopped = True


class FakeGPIO:
    HIGH = 1
    LOW = 0

    def __init__(self):
        self.outputs = []
        self.cleaned = False

    def output(self, pin, value):
        self.outputs.append((pin, value))

    def cleanup(self):
        self.cleaned = True


def test_pressure_normalization_maps_critical_to_max():
    assert NozzleController._normalize_pressure("CRITICAL") == "MAX"
    assert NozzleController._pressure_to_duty("CRITICAL") == 100


def test_execute_sets_pressure_duty_in_simulation():
    ctrl = NozzleController(simulated=True)
    ctrl.execute(DummyAction(pressure="MAX"))

    status = {n["device_id"]: n for n in ctrl.status()}
    assert status[1]["pressure"] == "MAX"
    assert status[1]["pressure_duty"] == 100


def test_manual_activate_supports_max_pressure():
    ctrl = NozzleController(simulated=True)
    assert ctrl.manual_activate(2, "CRITICAL") is True

    status = {n["device_id"]: n for n in ctrl.status()}
    assert status[2]["pressure"] == "MAX"
    assert status[2]["pressure_duty"] == 100


def test_hardware_actuation_uses_pwm_pressure_channel():
    ctrl = NozzleController(simulated=True)
    ctrl._simulated = False
    ctrl._gpio = FakeGPIO()
    ctrl._pressure_pwm[1] = FakePWM()

    ctrl._actuate_hardware(1, pan=15.0, tilt=25.0, pressure="HIGH")

    assert ctrl._pressure_pwm[1].duty == 85
    assert (17, ctrl._gpio.HIGH) in ctrl._gpio.outputs
    assert (27, ctrl._gpio.HIGH) in ctrl._gpio.outputs


def test_hardware_off_clears_pressure_output():
    ctrl = NozzleController(simulated=True)
    ctrl._simulated = False
    ctrl._gpio = FakeGPIO()
    ctrl._pressure_pwm[1] = FakePWM()

    ctrl._actuate_hardware(1, pan=15.0, tilt=25.0, pressure="OFF")

    assert ctrl._pressure_pwm[1].duty == 0
    assert (17, ctrl._gpio.LOW) in ctrl._gpio.outputs
    assert (27, ctrl._gpio.LOW) in ctrl._gpio.outputs
