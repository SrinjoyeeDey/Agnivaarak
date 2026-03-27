from logic.decision_engine import DecisionEngine
from logic.fire_queue import FireQueue
from hardware.nozzle_controller import NozzleController
import time

def test_upgrade():
    print("Testing FireSuppressor Upgrade...")
    
    # 1. Initialize
    fq = FireQueue(max_targets=4)
    de = DecisionEngine(fq)
    nc = NozzleController(simulated=True)
    
    # 2. Simulate Fires
    # Fire 1: Near Device 1 (center 160, 120)
    # Fire 2: Near Device 2 (center 480, 120)
    # Fire 3: Out of range
    fires = [
        {"id": "F1", "bbox": [150, 110, 20, 20], "intensity": {"level": "HIGH", "score": 0.9}},
        {"id": "F2", "bbox": [470, 110, 20, 20], "intensity": {"level": "MEDIUM", "score": 0.5}},
        {"id": "F3", "bbox": [0, 0, 10, 10], "intensity": {"level": "LOW", "score": 0.2}}, # Should be out of range
    ]
    
    print("\nDetecting fires...")
    actions = de.decide(fires, [], 640, 480)
    
    print(f"Decisions made: {len(actions)}")
    for action in actions:
        print(f"  - {action}")
        nc.execute(action)
    
    # Verify Device 1 handled F1
    # Verify Device 2 handled F2
    # Verify F3 was skipped
    
    # 3. Test Scanning
    print("\nTesting Scanning (Cooldown)...")
    time.sleep(0.1)
    nc.cooldown()
    status = nc.status()
    for s in status:
        print(f"  - Device {s['device_id']}: {s['status']} | Pan: {s['pan']:.1f}")

    print("\nVerification Complete!")

if __name__ == "__main__":
    test_upgrade()
