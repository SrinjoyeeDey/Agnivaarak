
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from logic.fire_queue import FireTarget
import time

def test_to_dict():
    print("\n--- Testing FireTarget.to_dict ---")
    detection = {
        "bbox": [100, 100, 50, 50],
        "confidence": 0.9,
        "is_blue": True,
        "fire_type": "b",
        "label": "BIO-GAS (B)"
    }
    target = FireTarget(detection)
    
    print(f"Target properties before to_dict:")
    print(f"  id: {target.id}")
    print(f"  bbox: {target.bbox}")
    print(f"  angle: {target.angle}")
    print(f"  confidence: {target.confidence}")
    print(f"  intensity: {target.intensity}")
    
    try:
        d = target.to_dict()
        print("✅ to_dict succeeded")
    except Exception as e:
        print(f"❌ to_dict failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_to_dict()
