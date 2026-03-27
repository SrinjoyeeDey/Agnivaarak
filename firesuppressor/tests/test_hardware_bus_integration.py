import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from hardware.camera_controller import CameraController
from hardware.nozzle_controller import NozzleController


class RecordingBus:
    def __init__(self):
        self.messages = []

    def emit(self, command_type, payload):
        self.messages.append((command_type, payload))
        return True

    def close(self):
        return None


class DummyAction:
    def __init__(self):
        self.nozzle_id = 1
        self.pressure = "HIGH"
        self.mode = "DIRECT"
        self.pan = 42.0
        self.tilt = 21.0
        self.agent = "WATER"
        self.fire_type = "a"
        self.intensity = "HIGH"
        self.label = "CLASS A (SOLID)"


def test_camera_controller_emits_point_and_scan_commands():
    bus = RecordingBus()
    camera = CameraController(simulated=True, device_bus=bus)

    camera.point_at(120.0)
    camera.set_tilt(15.0)
    camera.resume_scan()

    command_types = [msg[0] for msg in bus.messages]
    assert command_types == ["camera_command", "camera_command", "camera_command"]
    assert bus.messages[0][1]["command"] == "point"
    assert bus.messages[1][1]["command"] == "tilt"
    assert bus.messages[2][1]["command"] == "resume_scan"


def test_nozzle_controller_emits_nozzle_alarm_and_estop_commands():
    bus = RecordingBus()
    ctrl = NozzleController(simulated=True, device_bus=bus)

    ctrl.execute(DummyAction())
    ctrl.trigger_alarm()
    ctrl.emergency_stop()

    command_types = [msg[0] for msg in bus.messages]
    assert "nozzle_command" in command_types
    assert "alarm_command" in command_types
    assert "emergency_stop" in command_types
