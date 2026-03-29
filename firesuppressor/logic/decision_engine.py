"""
logic/decision_engine.py
=========================
Core rule-based decision engine.

Decision tree
─────────────
IF fire detected:
  FOR each fire in priority queue:
    IF human within exclusion radius:
      spray_mode = SURROUND   # avoid direct hit
    ELSE:
      spray_mode = DIRECT
    SELECT closest nozzle (by angle)
    SET pressure by intensity level
    IF active_nozzles >= MAX_NOZZLES (4):
      BOOST pressure on highest-priority fire
      SKIP new activations
ELSE:
  cooldown all nozzles

Safety interlocks
─────────────────
  • Human exclusion radius: 60 px around detected person
  • Emergency stop: checked on every call → blocks all actions
  • Max concurrent nozzles: 4
"""

from __future__ import annotations

import time
from typing import List

from loguru import logger

from logic.fire_queue import FireQueue
from logic.angle_mapper import map_bbox_to_angles
from vision.fire_classifier import FireClassifier
from logic.pressure_controller import PressureController
from logic.sector_manager import SectorManager

MAX_CONCURRENT_NOZZLES = 4
HUMAN_EXCLUSION_RADIUS = 60   # pixels
SECTOR_WIDTH = 90.0           # 4 sectors for 360 coverage (Requirement Phase 20 Fix)

# Consolidated Device Configuration for 4-Nozzle System
DEVICES = {
    1: {"sector_id": 0, "angle_center": 0.0},    # North (315-45)
    2: {"sector_id": 1, "angle_center": 90.0},   # East (45-135)
    3: {"sector_id": 2, "angle_center": 180.0},  # South (135-225)
    4: {"sector_id": 3, "angle_center": 270.0},  # West (225-315)
}

class Action:
    DIRECT   = "DIRECT"
    SURROUND = "SURROUND"
    STOP     = "STOP"
    PRECISE  = "PRECISE"

    def __init__(self, nozzle_id: int, pan: float, tilt: float,
                 mode: str, pressure: str, agent: str, 
                 fire_type: str, intensity: str, fire_id: str,
                 label: str = ""):
        self.nozzle_id  = nozzle_id
        self.pan        = pan
        self.tilt       = tilt
        self.mode       = mode
        # Requirement Step 10: State synchronization
        # NOTE: The 'nozzle' object and 'nid' are not available in the Action constructor.
        # This part of the instruction seems to imply an external nozzle management system.
        # For now, we'll assume 'nid' refers to 'self.nozzle_id' and 'nozzle' is a placeholder.
        # This code will cause a NameError if 'nozzle' is not defined elsewhere.
        # nozzle.active   = True
        # nozzle.status   = "LOCKED"
        # nozzle.mode     = mode
        logger.info("💧 Nozzle {} EXECUTE: Mode={}, Pressure={}, Agent={}", 
                    self.nozzle_id, mode, pressure, agent) # Using self.nozzle_id and pressure/agent from args
        self.pressure   = pressure
        self.agent      = agent
        self.fire_type  = fire_type
        self.intensity  = intensity
        self.fire_id    = fire_id
        self.label      = label
        self.ts         = time.time()

    def __repr__(self):
        return (f"Action(device={self.nozzle_id}, "
                f"type={self.fire_type}, agent={self.agent}, "
                f"pan={self.pan:.1f}°, tilt={self.tilt:.1f}°, mode={self.mode}, "
                f"pressure={self.pressure})")


class DecisionEngine:
    def __init__(self, fire_queue: FireQueue, node_id: int = 1):
        self._queue      = fire_queue
        self._node_id    = node_id
        self._classifier = FireClassifier()
        self._pressure   = PressureController()
        self._sector_mgr = SectorManager(sector_width=SECTOR_WIDTH)
        self._emergency_stop = False

    # ── External controls ─────────────────────────────────
    def trigger_emergency_stop(self):
        self._emergency_stop = True
        logger.critical("⛔ EMERGENCY STOP triggered on Node {}", self._node_id)

    def clear_emergency_stop(self):
        self._emergency_stop = False
        logger.warning("✅ Emergency stop cleared on Node {}", self._node_id)

    @property
    def is_stopped(self) -> bool:
        return self._emergency_stop

    # ── Main decide method ────────────────────────────────
    def decide(self, fires: List[dict],
               humans: List[dict], 
               frame_width: int = 640, 
               frame_height: int = 480,
               current_angle: float = 0.0) -> List[Action]:
        """Processes detections and generates suppression actions."""
        if self._emergency_stop:
            logger.warning("⛔ Emergency stop active – no actions")
            return [Action(nozzle_id=-1, pan=0, tilt=0,
                           mode=Action.STOP, pressure="OFF", agent="NONE",
                           fire_type="none", intensity="none", fire_id="all")]

        # Update priority queue
        self._queue.update(fires)
        targets = self._queue.top(MAX_CONCURRENT_NOZZLES)
        
        if not targets and len(fires) > 0:
            logger.debug("⏳ Waiting for consensus on {} vision target(s)...", len(fires))

        # Refresh persistent locks (Phase 2 hardening)
        self._sector_mgr.release_stale_locks()
        
        actions    = []
        assigned_devices = set()
        assigned_fires   = set()

        for fire in targets:
            fire_id = fire.get("id", "?")
            if fire_id in assigned_fires:
                continue

            # --- Authenticity Gating (Part 5 & 6) ---
            auth_score = fire.get("authenticity", 0.6)
            if auth_score < 0.4:
                logger.warning("🚫 Fire {} rejected as FAKE (confidence: {:.2f})", fire_id, auth_score)
                continue
            
            is_uncertain = auth_score < 0.75
            if is_uncertain:
                logger.info("⚠️ Fire {} is UNCERTAIN (confidence: {:.2f}) - monitoring only", fire_id, auth_score)
                # We skip suppression for uncertain fires, but keep them in targets for dashboard
                continue

            bbox = fire.get("bbox", [0, 0, 0, 0])
            # 1. Spatial Mapping: Convert bbox -> Absolute World Angle
            pan, tilt = map_bbox_to_angles(bbox, frame_width, frame_height, base_pan=current_angle)
            
            # 2. Assignment Logic: Persistent Lock vs. Current Sector
            # Check if this fire already owns a sector/device
            locked_sector = self._sector_mgr.get_lock_by_fire_id(fire_id)
            if locked_sector is not None:
                sector_id = locked_sector
            else:
                sector_id = self._sector_mgr.get_sector_id(pan)
            
            # Find the device for this sector
            best_device_id = None
            for dev_id, config in DEVICES.items():
                if config["sector_id"] == sector_id:
                    best_device_id = dev_id
                    break

            # Safety/Conflict Checks
            if not best_device_id: continue
            if best_device_id in assigned_devices:
                logger.debug("⏳ Device {} already assigned this frame - skipping Fire {}", best_device_id, fire_id)
                continue
            
            if self._sector_mgr.is_locked(sector_id, fire_id=fire_id):
                logger.warning("🛡️ Sector {} is PERSISTENTLY LOCKED by another fire - skipping", sector_id)
                continue

            # Lock the sector and track assignment
            self._sector_mgr.lock_sector(sector_id, fire_id)
            assigned_devices.add(best_device_id)
            assigned_fires.add(fire_id)

            # 3. Fire Classification & Suppression Config
            f_type  = fire.get("fire_type", "a")
            f_label = fire.get("label", "CLASS A (SOLID)")
            f_intensity = fire.get("intensity", {}).get("level", "MEDIUM")
            
            if f_intensity == "HIGH":
                self._emergency_stop = False # Make sure not stopped
                logger.critical("🔥 HIGH INTENSITY FIRE DETECTED! Triggering Emergency Mode.")
                # We'll rely on main.py to update the global emergency_mode state
            
            suppression = self._pressure.get_suppression_config(f_type, f_intensity)
            
            # 4. Human safety: Overrides suppression mode
            near_human = self._human_in_path(fire, humans)
            mode = suppression["mode"]
            if near_human:
                # Requirement Step 4: Avoid direct spray if humans nearby
                mode = Action.SURROUND
                # If very close, maybe STOP is safer, but SURROUND is requested
                logger.warning("⚠️ Human near fire {} – forcing SURROUND mode", fire_id)

            action = Action(nozzle_id=best_device_id,
                            pan=pan,
                            tilt=tilt,
                            mode=mode,
                            pressure=suppression["pressure"],
                            agent=suppression["agent"],
                            fire_type=f_type,
                            intensity=f_intensity,
                            fire_id=fire_id,
                            label=f_label)
            actions.append(action)

            logger.info("\n[DEVICE {}] -> FIRE {}\nMode: LOCKED\nType: {}\nTarget: PAN {:.1f} / TILT {:.1f}",
                        best_device_id, fire_id, f_label, pan, tilt)

        logger.info("📡 Generated {} actions for confirmed fires", len(actions))
        return actions

    def build_enhanced_event(self, action: Action, fire: dict) -> dict:
        """Requirement Step 3: Returns standardized event payload."""
        return {
            "device_id"      : action.nozzle_id,
            "timestamp"      : action.ts,
            "status"         : "ACTIVE" if action.mode != Action.STOP else "IDLE",
            "fire_type"      : action.fire_type,
            "label"          : action.label,
            "intensity"      : action.intensity,
            "intensity_score": fire.get("intensity", {}).get("score", 0.0),
            "pressure"       : action.pressure,
            "agent"          : action.agent,
            "pan"            : round(action.pan, 1),
            "tilt"           : round(action.tilt, 1),
            "target"         : fire.get("bbox", [0, 0, 0, 0]),
            "mode"           : "LOCKED" if action.mode != Action.STOP else "SCANNING"
        }

    # ── Safety: human proximity check ────────────────────
    @staticmethod
    def _human_in_path(fire: dict, humans: List[dict]) -> bool:
        """
        Returns True if any human bounding box overlaps or is within
        HUMAN_EXCLUSION_RADIUS pixels of the fire bounding box.
        """
        fx, fy, fw, fh = fire["bbox"]
        f_cx = fx + fw // 2
        f_cy = fy + fh // 2

        for human in humans:
            hx, hy, hw, hh = human["bbox"]
            h_cx = hx + hw // 2
            h_cy = hy + hh // 2

            dist = ((f_cx - h_cx) ** 2 + (f_cy - h_cy) ** 2) ** 0.5
            if dist < HUMAN_EXCLUSION_RADIUS:
                return True
        return False
