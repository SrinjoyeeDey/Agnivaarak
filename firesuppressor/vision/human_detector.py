"""
vision/human_detector.py
=========================
Detects people using YOLOv8n pre-trained on COCO.
Only the "person" class (index 0) is retained.

Model: Ultralytics YOLOv8n (COCO)
  HF page: https://huggingface.co/Ultralytics/assets
  Parameters: 3.2 M  | mAP50-95 person: 0.55 | ~28 FPS CPU (640px)
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import cv2
import numpy as np
from loguru import logger


HumanResult = dict   # bbox, confidence


class HumanDetector:
    _PERSON_CLASS = 0  # COCO class index for "person"

    def __init__(self, model_path: str = None,
                 confidence: float = 0.50):
        self.confidence  = confidence
        if model_path is None:
            # Default to weights folder relative to this file
            self._model_path = Path(__file__).parent.parent / "models" / "weights" / "yolov8n.pt"
        else:
            self._model_path = Path(model_path)
        self._model      = None
        self._using_yolo = False
        self._load_model()

    def _load_model(self):
        if not self._model_path.exists() or \
                self._model_path.read_bytes() == b"PLACEHOLDER":
            logger.warning("YOLOv8n weights missing → human detection disabled")
            return
        try:
            from ultralytics import YOLO
            self._model      = YOLO(str(self._model_path))
            self._using_yolo = True
            logger.success("HumanDetector: YOLOv8n COCO loaded")
        except Exception as exc:
            logger.error("Failed to load human YOLO: {}", exc)

    def detect(self, frame: np.ndarray) -> List[HumanResult]:
        if not self._using_yolo:
            return []   # safe default: assume no humans in fallback mode
        return self._detect_yolo(frame)

    def _detect_yolo(self, frame: np.ndarray) -> List[HumanResult]:
        results = self._model.predict(
            frame,
            conf=self.confidence,
            classes=[self._PERSON_CLASS],
            verbose=False)[0]

        humans = []
        for box in results.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            humans.append({
                "bbox"      : [x1, y1, x2 - x1, y2 - y1],
                "confidence": float(box.conf[0]),
            })
        return humans
