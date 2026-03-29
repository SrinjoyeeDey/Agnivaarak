import sys
import os
sys.path.insert(0, os.path.abspath('firesuppressor'))

from loguru import logger
logger.remove()

from logic.decision_engine import DecisionEngine
from logic.fire_queue import FireQueue
from hardware.nozzle_controller import NozzleController

q = FireQueue()
de = DecisionEngine(q)

fires = [{'bbox': [100, 100, 50, 50], 'confidence': 0.8, 'is_blue': False, 'class_name': 'fire', 'fire_type': 'a', 'label': 'A', 'intensity': {'score': 0.9, 'level': 'HIGH', 'pressure': {}}}]

try:
    q.update(fires)
    import time
    time.sleep(0.6)
    q.update(fires)
    actions = de.decide(fires, [], 640, 480, 0.0)
    print("ACTIONS:", actions)
    
    ctrl = NozzleController(simulated=True, num_nozzles=4)
    ctrl._nozzles[1].pressure = "MEDIUM" # Mock it
    for a in actions:
        print("Executing action:", a.nozzle_id)
        ctrl.execute(a)
    print("DONE executing!")
    
except Exception as e:
    import traceback
    traceback.print_exc()

