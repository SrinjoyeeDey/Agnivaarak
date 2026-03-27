import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from logic.fire_queue import FireQueue

def test_vision():
    print("--- STANDALONE VISION TEST ---")
    queue = FireQueue()
    
    # 1. Duo-Stage Confidence (New)
    print("Testing Duo-Stage (New)...")
    queue.update([{"bbox": [50, 50, 10, 10], "confidence": 0.5, "id": "weak"}])
    assert len(queue._targets) == 0, f"Expected 0 targets, got {len(queue._targets)}"
    
    queue.update([{"bbox": [50, 50, 10, 10], "confidence": 0.7, "id": "strong"}])
    assert len(queue._targets) == 1, f"Expected 1 target, got {len(queue._targets)}"
    
    # 2. Duo-Stage Confidence (Existing)
    print("Testing Duo-Stage (Existing)...")
    queue.update([{"bbox": [52, 52, 10, 10], "confidence": 0.3, "id": "strong"}])
    assert len(queue._targets) == 1, "Target should be kept at 0.3"
    
    queue.update([{"bbox": [52, 52, 10, 10], "confidence": 0.2, "id": "strong"}])
    # FireQueue.update doesn't delete immediately if just below threshold, 
    # but matched_ids check. Wait, my logic: 
    # if matched: if conf >= 0.25: matched.update(det); matched_ids.add(matched.id)
    # If conf=0.2, it won't be in matched_ids, misses will increment.
    target = queue._targets[list(queue._targets.keys())[0]]
    assert target.misses == 1, "Should have incremented misses for low confidence"
    
    # 3. Smoke Priority Attribute
    print("Testing Smoke Attribute...")
    queue.update([{"bbox": [200, 200, 50, 50], "confidence": 0.8, "id": "smoke_fire", "has_smoke": True}])
    smoke_target = list(queue._targets.values())[-1]
    assert smoke_target.has_smoke is True, "has_smoke attribute lost"
    
    print("--- VISION TEST SUCCESS ---")

if __name__ == "__main__":
    test_vision()
