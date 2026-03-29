import sys
import os
import time
from loguru import logger
logger.remove()

# Add project root to sys.path
sys.path.insert(0, os.path.abspath('firesuppressor'))

from firesuppressor.logic.fire_queue import FireQueue
from firesuppressor.logic.decision_engine import DecisionEngine
from firesuppressor.hardware.nozzle_controller import NozzleController
from firesuppressor.hardware.device_bus import DeviceBus

def test_background_scanning():
    bus = DeviceBus(enabled=False)
    q = FireQueue(max_targets=4)
    de = DecisionEngine(q)
    nc = NozzleController(simulated=True, num_nozzles=4, device_bus=bus)

    # Initial state: Nozzle 1-4 should be SCANNING
    status = nc.status()
    print(f"Initial Nozzle 1 Pan: {status[0]['pan']}")
    prev_pan = status[0]['pan']

    # Detected Fire (will be assigned to Nozzle 1 or 2 based on angle)
    # Fire at 0 degrees -> Nozzle 1
    fires = [{'bbox': [300, 200, 40, 40], 'confidence': 0.8, 'is_blue': False, 'intensity': {'level': 'MEDIUM'}}]
    
    print("\n--- Simulating Fire Detection (Target Nozzle 1) ---")
    q.update(fires)
    time.sleep(0.6) # Confirm fire
    q.update(fires)
    
    actions = de.decide(fires, [], 640, 480, 0.0)
    print(f"Generated {len(actions)} actions.")
    
    for a in actions:
        nc.execute(a)
    
    # Nozzle 1 should now be LOCKED
    status = nc.status()
    print(f"Nozzle 1 Status: {status[0]['status']}, Pan: {status[0]['pan']}")
    print(f"Nozzle 2 Status: {status[1]['status']}, Pan: {status[1]['pan']}")
    
    # Run cooldown (background scan)
    print("\n--- Running Cooldown (Background Scan) ---")
    nc.cooldown()
    
    new_status = nc.status()
    print(f"Nozzle 1 State after Cooldown: {new_status[0]['status']}, Pan: {new_status[0]['pan']} (Should be same)")
    print(f"Nozzle 2 State after Cooldown: {new_status[1]['status']}, Pan: {new_status[1]['pan']} (Should have moved!)")

    if new_status[1]['pan'] != status[1]['pan']:
        print("\n✅ SUCCESS: Nozzle 2 moved while Nozzle 1 was busy!")
    else:
        print("\n❌ FAILURE: Nozzle 2 stayed stationary.")

if __name__ == "__main__":
    test_background_scanning()
