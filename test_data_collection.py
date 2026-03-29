import sys
import os
import shutil
from pathlib import Path
from loguru import logger
logger.remove()

# Add project root to sys.path
sys.path.insert(0, os.path.abspath('firesuppressor'))

from firesuppressor.vision.fire_detector import FireDetector
import numpy as np

def test_data_collection():
    # Setup test dir
    test_collected = Path("data/collected")
    if test_collected.exists():
        shutil.rmtree(test_collected)
    
    detector = FireDetector(collect_data=True)
    
    # Create fake frame
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Simulate a "fire" detection
    detections = [{
        "bbox": [100, 100, 50, 50],
        "confidence": 0.9,
        "class_name": "fire",
        "is_blue": False
    }]
    
    print("Saving test sample...")
    detector._save_training_sample(frame, detections)
    
    # Verify files
    imgs = list((test_collected / "images").glob("*.jpg"))
    lbls = list((test_collected / "labels").glob("*.txt"))
    
    print(f"Found {len(imgs)} images and {len(lbls)} label files.")
    
    if len(imgs) == 1 and len(lbls) == 1:
        # Check label content
        with open(lbls[0], "r") as f:
            content = f.read().strip()
            print(f"Label Content: {content}")
            # Format: class_id x_center y_center width height
            # 100, 100, 50, 50 in 640, 480
            # x_center = (100 + 25) / 640 = 0.195312
            # y_center = (100 + 25) / 480 = 0.260417
            # width = 50 / 640 = 0.078125
            # height = 50 / 480 = 0.104167
            if content.startswith("0 0.195312 0.260417"):
                print("✅ Label format is correct!")
            else:
                print("❌ Label format mismatch.")
    else:
        print("❌ Files not found.")

if __name__ == "__main__":
    test_data_collection()
