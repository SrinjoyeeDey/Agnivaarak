#!/usr/bin/env python3
"""
FireSuppressor – Main Entry Point
==================================
Wires together the vision pipeline, decision engine,
hardware abstraction, MQTT networking, and FastAPI backend.

Usage:
    python main.py --demo             # full simulation, no camera
    python main.py --camera 0         # webcam index 0
    python main.py --video fire.mp4   # video file
    python main.py --api-only         # just start the REST server

⚠️  SAFETY NOTE: All actuator calls in this file are SIMULATED.
    No real pumps or servos are activated unless --real-hardware
    flag is set AND GPIO libraries are installed.
"""

import argparse
import asyncio
import os
import signal
import sys
import threading
import time
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# ── Internal imports ──────────────────────────────────────
from vision.capture import FrameSource
from vision.fire_detector import FireDetector
from vision.human_detector import HumanDetector
from vision.intensity_analyzer import IntensityAnalyzer
from logic.decision_engine import DecisionEngine
from logic.fire_queue import FireQueue
from hardware.device_bus import DeviceBus
from hardware.nozzle_controller import NozzleController
from hardware.camera_controller import CameraController
from network.mqtt_client import MQTTClient
from network.device_coordinator import DeviceCoordinator
from network.emergency_notifier import EmergencyNotifier
from backend.app import create_app

console = Console()

# ── Node configuration ────────────────────────────────────
NODE_ID   = int(os.getenv("NODE_ID",   "1"))
ZONE      = os.getenv("ZONE",          "NORTH")
MQTT_HOST = os.getenv("MQTT_HOST",     "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DEMO_MODE = os.getenv("DEMO_MODE",     "0") == "1"


# ─────────────────────────────────────────────────────────
def print_banner():
    banner = Text()
    banner.append("[FIRE] FireSuppressor v1.0\n", style="bold red")
    banner.append(f"   Node: {NODE_ID}  Zone: {ZONE}  Demo: {DEMO_MODE}\n",
                  style="yellow")
    banner.append("   ! SIMULATION MODE - no real hardware activated\n",
                  style="bold white")
    console.print(Panel(banner, border_style="red"))


# ─────────────────────────────────────────────────────────
class FireSuppressionSystem:
    """
    Top-level orchestrator.
    Runs the detection loop in a background thread while the
    FastAPI server handles REST / WebSocket requests.
    """

    def __init__(self, args):
        self.args      = args
        self._running  = False

        # ── Vision pipeline ──────────────────────────────
        self.frame_src        = FrameSource(args)
        self.fire_detector    = FireDetector(
            model_path=None,
            confidence=0.45)
        self.human_detector   = HumanDetector(
            model_path=None,
            confidence=0.50)
        self.intensity_analyzer = IntensityAnalyzer()

        # ── Logic ────────────────────────────────────────
        self.fire_queue  = FireQueue(max_targets=4)
        self.decision    = DecisionEngine(
            fire_queue=self.fire_queue,
            node_id=NODE_ID)

        # ── Hardware (always simulated unless real flag) ──
        real_hw = getattr(args, "real_hardware", False)
        self.device_bus = DeviceBus(enabled=real_hw)
        self.nozzle_ctrl  = NozzleController(
            simulated=not real_hw, num_nozzles=4, device_bus=self.device_bus)
        self.camera_ctrl  = CameraController(
            simulated=not real_hw, device_bus=self.device_bus)
        
        logger.info("🚀 SYSTEM VERSION: 2026.03.27-v21 (4-Nozzle / Expert Classification)")

        # ── Networking ───────────────────────────────────
        self.mqtt        = MQTTClient(host=MQTT_HOST, port=MQTT_PORT, node_id=NODE_ID)
        self.emergency   = EmergencyNotifier(snapshot_dir="emergency_snapshots")
        self.coordinator = DeviceCoordinator(mqtt=self.mqtt, nozzle_ctrl=self.nozzle_ctrl, node_id=NODE_ID)
        self.coord  = DeviceCoordinator(
            mqtt=self.mqtt,
            nozzle_ctrl=self.nozzle_ctrl,
            node_id=NODE_ID)

        # ── Backend state (shared with FastAPI) ──────────
        self.state  = {
            "node_id"      : NODE_ID,
            "zone"         : ZONE,
            "fire_detected": False,
            "fires"        : [],
            "humans"       : [],
            "nozzles"      : self.nozzle_ctrl.status(),
            "alerts"       : [],
            "camera_angle" : 0,
            "emergency_stop": False,
            "temperature"  : 24.5,
            "humidity"     : 45.0,
            "system_pressure": 0.0,
        }

        # FastAPI app (shares state dict by reference)
        self.app = create_app(
            state=self.state,
            nozzle_ctrl=self.nozzle_ctrl,
            decision=self.decision)

    # ── Detection loop ────────────────────────────────────
    def _detection_loop(self):
        logger.info("Detection loop started on Node {}", NODE_ID)
        frame_count = 0

        for frame, meta in self.frame_src.frames():
            if not self._running:
                break
            if self.state["emergency_stop"]:
                logger.warning("! EMERGENCY STOP ACTIVE - detection paused")
                self.nozzle_ctrl.emergency_stop()
                time.sleep(0.5)
                continue

            frame_count += 1

            # 1) Fire detection
            fire_boxes = self.fire_detector.detect(frame)

            # 2) Human detection
            human_boxes = self.human_detector.detect(frame)

            # 3) Intensity & Classification (Requirement Step 2)
            h, w = frame.shape[:2]
            current_angle = self.camera_ctrl.current_angle()
            for fb in fire_boxes:
                fb["intensity"] = self.intensity_analyzer.estimate(frame, fb["bbox"])
                classification = self.decision._classifier.classify(fb, frame, frame_height=h)
                fb["fire_type"] = classification["fire_type"]
                fb["label"]     = classification.get("label", "NORMAL (A)")
                
                # Restore angle for dashboard compatibility (Requirement Phase 15)
                from logic.angle_mapper import map_bbox_to_angles
                pan, _ = map_bbox_to_angles(fb["bbox"], frame.shape[1], frame.shape[0], 
                                            base_pan=current_angle)
                fb["angle"] = pan

            # 5) Decision engine runs unconditionally to allow queue to prune stale targets (Phase 9)
            confirmed_fires = self.decision._queue.all()
            
            if fire_boxes:
                logger.debug("🔥 Vision: Detected {} potential fire(s)", len(fire_boxes))
            
            h, w = frame.shape[:2]
            actions = self.decision.decide(fire_boxes, human_boxes, w, h, 
                                          current_angle=current_angle)

            if actions:
                self.camera_ctrl.point_at(actions[0].pan)
                self.camera_ctrl.set_tilt(actions[0].tilt)
            else:
                self.camera_ctrl.resume_scan()
            
            active_ids = []
            for action in actions:
                self.nozzle_ctrl.execute(action)
                active_ids.append(action.nozzle_id)
                
                target_fire = next((f for f in confirmed_fires if f.get("id") == action.fire_id), None)
                if target_fire:
                    enhanced_event = self.decision.build_enhanced_event(action, target_fire)
                    self.mqtt.publish_enhanced_event(enhanced_event)
            
            # Phase 8: Explicitly clear unassigned nozzles
            self.nozzle_ctrl.deactivate_others(active_ids)

            # 8) Append alerts ONLY for active detections this frame
            if fire_boxes:
                for fb in fire_boxes:
                    alert = {
                        "ts": time.time(), "node": NODE_ID, "zone": ZONE,
                        "intensity": fb["intensity"], "angle": fb.get("angle", 0)
                    }
                    self.state["alerts"] = (self.state["alerts"] + [alert])[-50:]
            else:
                # No new fire pixels detected -> ensure cooldown triggers for devices not governed by ghost logic
                self.nozzle_ctrl.cooldown()

            # 4) Update shared state (Every frame)
            try:
                # Phase 12: Emergency Escalation Check
                # Use a local flag instead of modifying global state immediately to avoid fluttering
                was_dispatched = self.state.get("emergency_dispatched", False)
                
                # Auto-clear emergency state if the fire is fully suppressed
                if not confirmed_fires:
                    self.state["emergency_dispatched"] = False
                    self.state.pop("emergency_snapshot_url", None)
                    
                for fire in confirmed_fires:
                    if fire.get("age", 0) > 30.0:  # Wait 30s to allow extinguisher to work
                        dispatched = self.emergency.trigger_dispatch(fire, frame, str(ZONE))
                        if dispatched:
                            self.state["emergency_dispatched"] = True
                            self.state["emergency_snapshot_url"] = f"http://localhost:8000/snapshots/{dispatched}"

                # Phase 12: Physical Hardware Alarm
                if confirmed_fires:
                    self.nozzle_ctrl.trigger_alarm()
                else:
                    self.nozzle_ctrl.stop_alarm()

                self.state.update({
                    "fire_detected" : len(confirmed_fires) > 0,
                    "fires"         : confirmed_fires,
                    "humans"        : human_boxes,
                    "camera_angle"  : self.camera_ctrl.current_angle(),
                    "nozzles"       : self.nozzle_ctrl.status(),
                    "emergency_dispatched": self.state.get("emergency_dispatched", False),
                    "emergency_snapshot_url": self.state.get("emergency_snapshot_url", None),
                    "temperature"   : round(self.state["temperature"], 2),
                    "humidity"      : round(self.state["humidity"], 2),
                    "system_pressure": round(self.state["system_pressure"], 2),
                })

                # --- Intensity-Aware Simulation Physics ---
                active_nozzles = [n for n in (self.state.get("nozzles") or []) if n.get("active")]
                if active_nozzles:
                    # Target pressure based on highest active nozzle level
                    p_map = {"HIGH": 110.0, "MEDIUM": 75.0, "LOW": 40.0}
                    target_p = max(p_map.get(n.get("pressure"), 0.0) for n in active_nozzles)
                    
                    # Smoothed transition to target
                    if self.state["system_pressure"] < target_p:
                        self.state["system_pressure"] = min(target_p, self.state["system_pressure"] + 6.0)
                    else:
                        self.state["system_pressure"] = max(target_p, self.state["system_pressure"] - 4.0)
                                        
                    self.state["humidity"] = min(90.0, self.state["humidity"] + 0.3)
                    self.state["temperature"] = max(24.5, self.state["temperature"] - 0.08) # Actively cooling
                else:
                    # No active suppression
                    target_p = 0.0
                    self.state["system_pressure"] = max(target_p, self.state["system_pressure"] - 5.0)
                    self.state["humidity"] = max(45.0, self.state["humidity"] - 0.1)
                    
                    if confirmed_fires:
                        self.state["temperature"] += 0.15 # Uncontrolled heating
                    else:
                        self.state["temperature"] = max(24.5, self.state["temperature"] - 0.05) # Natural ambient cooling
            except Exception as e:
                logger.error("State update error: {}", e)

            self.state["nozzles"] = self.nozzle_ctrl.status()

            # Throttle to ~10 FPS in demo, 30 FPS otherwise
            time.sleep(0.1 if DEMO_MODE else 0.033)

        logger.info("Detection loop ended after {} frames", frame_count)

    # ── Public API ────────────────────────────────────────
    def start(self):
        self._running = True
        self.frame_src.start()
        self.mqtt.connect()

        # Detection loop runs in daemon thread
        self._loop_thread = threading.Thread(
            target=self._detection_loop,
            name="DetectionLoop",
            daemon=True)
        self._loop_thread.start()
        logger.success("FireSuppressor Node {} online OK", NODE_ID)

    def stop(self):
        logger.warning("Shutting down Node {}...", NODE_ID)
        self._running = False
        self.nozzle_ctrl.emergency_stop()
        self.camera_ctrl.resume_scan()
        self.frame_src.stop()
        self.mqtt.disconnect()
        self.device_bus.close()
        logger.info("Node {} offline.", NODE_ID)


# ─────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="FireSuppressor Node")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--demo",   action="store_true",
                     help="Synthetic demo (no camera required)")
    src.add_argument("--camera", type=int, default=None,
                     help="Webcam device index (e.g. 0)")
    src.add_argument("--video",  type=str, default=None,
                     help="Path to video file")
    p.add_argument("--api-only", action="store_true",
                   help="Start REST API without detection loop")
    p.add_argument("--port",     type=int, default=8000,
                   help="FastAPI port (default 8000)")
    p.add_argument("--real-hardware", action="store_true",
                   help="⚠️  Enable real GPIO/serial actuators")
    return p.parse_args()


# ─────────────────────────────────────────────────────────
async def main_async(args):
    import uvicorn

    system = FireSuppressionSystem(args)

    # Graceful shutdown (signal handlers not supported on Windows ProactorLoop)
    try:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, system.stop)
    except NotImplementedError:
        logger.warning("Signal handlers not supported on this platform - use Ctrl+C to stop")

    if not args.api_only:
        system.start()

    config = uvicorn.Config(
        app=system.app,
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
        reload=False)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    print_banner()
    args = parse_args()

    # Default to demo if nothing specified
    if not args.demo and args.camera is None and args.video is None:
        args.demo = True

    logger.remove()
    logger.add(sys.stderr, level="DEBUG",
               format="<green>{time:HH:mm:ss}</green> | "
                      "<level>{level: <8}</level> | "
                      "<cyan>{name}</cyan> – {message}")

    asyncio.run(main_async(args))
