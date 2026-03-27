
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from logic.decision_engine import DecisionEngine, Action
from logic.fire_queue import FireQueue, FireTarget
import time

def test_blue_fire_activation():
    print("\n--- Repro: Blue Fire Activation Test ---")
    queue = FireQueue()
    engine = DecisionEngine(queue)
    
    # 1. Manually create a FireTarget object to ensure all attributes exist
    fire_id = "blue_test_1"
    detection = {
        "bbox": [100, 100, 50, 50],
        "confidence": 0.9,
        "is_blue": True,
        "fire_type": "b",
        "label": "BIO-GAS (B)"
    }
    target = FireTarget(detection)
    target.id = fire_id
    target.first_seen = time.time() - 10.0 # Confirmed
    target.last_seen = time.time()
    target.angle = 0.0
    target.label_history.clear()
    target.label_history.extend(["BIO-GAS (B)"] * 10)
    target.intensity = {"level": "MEDIUM", "score": 0.5}
    target.hits = 100
    target.misses = 0
    
    # Inject into queue
    queue._targets[fire_id] = target
    
    print(f"Target Confirmed: {target.is_confirmed}")
    print(f"Target Stable Type: {target.stable_type}")
    print(f"Target Stable Label: {target.stable_label}")

    # 3. Run Decision Engine
    detections = [detection]
    
    try:
        actions = engine.decide(detections, [], 640, 480, current_angle=0.0)
        print(f"Actions Generated: {len(actions)}")
        for a in actions:
            print(f"✅ Action: Device {a.nozzle_id}, Mode {a.mode}, Target Pan {a.pan:.1f}")
            # Check event building
            event = engine.build_enhanced_event(a, target.to_dict())
            print(f"✅ Event built: {event['status']}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise e

if __name__ == "__main__":
    test_blue_fire_activation()
