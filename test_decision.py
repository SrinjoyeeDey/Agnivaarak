import sys
import os
sys.path.insert(0, os.path.abspath('firesuppressor'))

from loguru import logger
logger.remove()

from logic.decision_engine import DecisionEngine
from logic.fire_queue import FireQueue

q = FireQueue()
de = DecisionEngine(q)

fires = [{'bbox': [100, 100, 50, 50], 'confidence': 0.8, 'is_blue': False, 'class_name': 'fire', 'fire_type': 'a', 'label': 'A', 'intensity': {'score': 0.9, 'level': 'HIGH', 'pressure': {}}}]

print("Calling _queue.update()...")
try:
    q.update(fires)
    targets = q.top(4)
    print("TARGETS AFTER 1 UPDATE:", targets)
    
    import time
    time.sleep(0.6)  # Force duration > 0.5s for is_confirmed
    q.update(fires)  # hits=2, misses=0. consistency=1.0. duration>0.5
    
    targets = q.top(4)
    print("TARGETS AFTER 2 UPDATES (0.6s later):", len(targets))
    
    actions = de.decide(fires, [], 640, 480, 0.0)
    print("ACTIONS:", actions)
except Exception as e:
    import traceback
    traceback.print_exc()

