import os
import cv2
import time
import datetime
import numpy as np
from loguru import logger

class EmergencyNotifier:
    """
    Phase 12: Simulates sending an SMS/API call to local fire departments
    when a fire condition exceeds the 10.0s 'Out of Control' age limit.
    """
    def __init__(self, snapshot_dir: str = "emergency_snapshots"):
        self.snapshot_dir = snapshot_dir
        self.last_dispatch = 0.0
        if not os.path.exists(self.snapshot_dir):
            os.makedirs(self.snapshot_dir)

    def trigger_dispatch(self, fire_info: dict, frame: np.ndarray, zone: str):
        """
        Triggers the escalation protocol. Limits to roughly 1 dispatch
        per 30 seconds to avoid spamming.
        """
        now = time.time()
        if now - self.last_dispatch < 30:
            return None  # Already dispatched recently
            
        self.last_dispatch = now
        
        # 1. Take snapshot
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_base = f"escalation_{timestamp}.jpg"
        filename  = os.path.join(self.snapshot_dir, filename_base)
        
        if frame is not None:
            # Draw a simple warning graphic on the snapshot before saving
            snap = frame.copy()
            cv2.putText(snap, "EMERGENCY OUT OF CONTROL", (20, 40), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            cv2.imwrite(filename, snap)
            
        # 2. Simulate the API Call / Terminal Flashing Alert
        logger.error("🚨 🚨 🚨 EMERGENCY ESCALATION PROTOCOL 🚨 🚨 🚨")
        logger.error("DIALING LOCAL FIRE DEPARTMENT (+1-911)...")
        logger.error("Message: Out of Control {} Fire in Zone {}", fire_info.get("fire_type", "Unknown").upper(), zone)
        logger.error("Confidence: {} | Snapshot saved to: {}", fire_info.get("confidence", 0), filename)
        logger.error("🚨 ────────────────────────────────────────── 🚨")
        
        return filename_base
