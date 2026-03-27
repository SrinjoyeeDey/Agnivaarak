import sys
import time
from pathlib import Path

import numpy as np

sys.path.append(str(Path(__file__).parent.parent))

from logic.decision_engine import DecisionEngine, Action
from logic.fire_queue import FireQueue
from vision.fire_classifier import FireClassifier


def make_blue_frame():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[120:220, 180:260] = (255, 120, 40)
    return frame


def make_orange_frame():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[120:280, 220:320] = (20, 140, 255)
    return frame


def make_electrical_frame():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[360:430, 280:335] = (40, 180, 255)
    return frame


def make_white_hot_orange_frame():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[130:260, 220:330] = (80, 210, 255)
    frame[170:220, 245:305] = (180, 240, 255)
    return frame


def test_blue_flame_roi_classifies_as_gas():
    classifier = FireClassifier()
    frame = make_blue_frame()

    result = classifier.classify(
        {
            "bbox": [180, 120, 80, 100],
            "is_blue": True,
            "intensity": {"score": 0.55, "level": "MEDIUM"},
        },
        frame=frame,
        frame_height=480,
    )

    assert result["fire_type"] == "b"
    assert result["label"] == "CLASS B (GAS)"


def test_normal_orange_fire_stays_class_a():
    classifier = FireClassifier()
    frame = make_orange_frame()

    result = classifier.classify(
        {
            "bbox": [220, 120, 100, 160],
            "intensity": {"score": 0.72, "level": "HIGH"},
        },
        frame=frame,
        frame_height=480,
    )

    assert result["fire_type"] == "a"
    assert result["label"] == "CLASS A (SOLID)"


def test_low_mounted_compact_fire_classifies_as_electrical():
    classifier = FireClassifier()
    frame = make_electrical_frame()

    result = classifier.classify(
        {
            "bbox": [280, 360, 55, 70],
            "intensity": {"score": 0.62, "level": "MEDIUM"},
        },
        frame=frame,
        frame_height=480,
    )

    assert result["fire_type"] == "c"
    assert result["label"] == "CLASS C (ELEC)"


def test_bright_orange_flame_is_not_metal():
    classifier = FireClassifier()
    frame = make_white_hot_orange_frame()

    result = classifier.classify(
        {
            "bbox": [220, 130, 110, 130],
            "intensity": {"score": 0.86, "level": "HIGH"},
        },
        frame=frame,
        frame_height=480,
    )

    assert result["fire_type"] != "d"
    assert result["label"] == "CLASS A (SOLID)"


def test_queue_preserves_blue_fire_type_consensus():
    queue = FireQueue()
    blue_detection = {
        "bbox": [180, 120, 80, 100],
        "confidence": 0.9,
        "is_blue": True,
        "fire_type": "b",
        "label": "CLASS B (GAS)",
        "intensity": {"score": 0.55, "level": "MEDIUM"},
    }

    queue.update([blue_detection])
    target = next(iter(queue._targets.values()))
    target.first_seen = time.time() - 1.0

    queue.update(
        [
            {
                **blue_detection,
                "is_blue": True,
                "fire_type": "a",
                "label": "CLASS A (SOLID)",
            }
        ]
    )

    fire = queue.top(1)[0]
    assert fire["fire_type"] == "b"


def test_decision_engine_uses_gas_suppression_for_blue_fire():
    queue = FireQueue()
    engine = DecisionEngine(queue)

    detection = {
        "bbox": [180, 120, 80, 100],
        "confidence": 0.9,
        "is_blue": True,
        "fire_type": "b",
        "label": "CLASS B (GAS)",
        "intensity": {"score": 0.55, "level": "MEDIUM"},
    }

    queue.update([detection])
    target = next(iter(queue._targets.values()))
    target.first_seen = time.time() - 1.0
    target.hits = 20
    target.misses = 0

    actions = engine.decide([detection], [], 640, 480, current_angle=0.0)

    assert len(actions) == 1
    assert actions[0].mode == Action.SURROUND
    assert actions[0].agent == "FOAM/CO2"
    assert actions[0].fire_type == "b"
