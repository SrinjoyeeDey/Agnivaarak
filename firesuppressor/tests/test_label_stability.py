import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from logic.fire_queue import FireQueue
import time

def test_label_stability():
    print("--- TESTING LABEL STABILITY (VOTING) ---")
    queue = FireQueue()
    
    # 1. Initial detection: CLASS A
    det_a = {"bbox": [100, 100, 50, 50], "confidence": 0.8, "id": "target_1", "label": "CLASS A (SOLID)", "fire_type": "a"}
    queue.update([det_a])
    target = list(queue._targets.values())[0]
    print(f"Initial Label: {target.to_dict()['label']}")
    assert target.to_dict()['label'] == "CLASS A (SOLID)"

    # 2. Simulate fluctuation: 2 frames of CLASS B (should not flip yet)
    det_b = det_a.copy()
    det_b["label"] = "CLASS B (LIQUID)"
    det_b["fire_type"] = "b"
    
    for _ in range(2):
        queue.update([det_b])
    
    print(f"Label after 2 fluctuations: {target.to_dict()['label']}")
    assert target.to_dict()['label'] == "CLASS A (SOLID)", "Label flipped too early!"

    # 3. Simulate persistence: 10 frames of CLASS B (should eventually flip)
    for _ in range(10):
        queue.update([det_b])
    
    print(f"Label after 12 total frames of B: {target.to_dict()['label']}")
    assert target.to_dict()['label'] == "CLASS B (LIQUID)", "Label failed to flip after majority"

    print("--- STABILITY TEST SUCCESS ---")

if __name__ == "__main__":
    test_label_stability()
