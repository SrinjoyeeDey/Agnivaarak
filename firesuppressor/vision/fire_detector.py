"""
vision/fire_detector.py
========================
Fire & smoke detection using YOLOv8 fine-tuned on fire datasets.

Model: keremberke/yolov8s-fire-detection (HF Hub)
  • Classes: 0=fire, 1=smoke
  • mAP50 ~0.87 on Roboflow fire-detection dataset

Falls back to colour-threshold heuristic if weights unavailable
(useful in CI / environments without downloaded weights).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List

import cv2
import numpy as np
from loguru import logger


DetectionResult = dict  # bbox, confidence, class_name, intensity (added later)


from collections import deque

class FireDetector:
    # HSV thresholds for colour-fallback
    _FIRE_LOWER = np.array([0,  80, 120], dtype=np.uint8)
    _FIRE_UPPER = np.array([35, 255, 255], dtype=np.uint8)
    
    # Blue flame thresholds (LPG, Ethanol) - Phase 21 Ultimate (Hue 80-130, S/V 60/60)
    _BLUE_LOWER = np.array([80, 60, 60], dtype=np.uint8)
    _BLUE_UPPER = np.array([140, 255, 255], dtype=np.uint8)

    def __init__(self, model_path: str = None,
                 confidence: float = 0.25,
                 collect_data: bool = False):
        self.confidence  = confidence
        self.collect_data = collect_data
        self.data_dir    = Path("data/collected")
        
        # Priority for model weights: 
        # 1. Newest best training run -> 2. Default provided weights -> 3. Fallback
        best_run_path = Path("runs/detect/fire/weights/best.pt")
        default_path  = Path(__file__).parent.parent / "models" / "weights" / "fire_yolo.pt"
        
        if model_path is not None:
            self._model_path = Path(model_path)
        elif best_run_path.exists():
            self._model_path = best_run_path
            logger.info("🎯 FireDetector: Using NEWEST training weights from {}", best_run_path)
        else:
            self._model_path = default_path
        self._model      = None
        self._using_yolo = False
        self._history    = deque(maxlen=5) # Last 5 frames for flicker test
        
        if self.collect_data:
            (self.data_dir / "images").mkdir(parents=True, exist_ok=True)
            (self.data_dir / "labels").mkdir(parents=True, exist_ok=True)
            
        self._load_model()

    def _load_model(self):
        if not self._model_path.exists() or \
                self._model_path.read_bytes() == b"PLACEHOLDER":
            logger.warning("Fire YOLO weights not found → using colour fallback")
            return
        try:
            from ultralytics import YOLO
            self._model      = YOLO(str(self._model_path))
            self._using_yolo = True
            logger.success("FireDetector: YOLOv8 loaded from {}", self._model_path)
        except Exception as exc:
            logger.error("Failed to load fire YOLO: {} → colour fallback", exc)

    # ── Public API ────────────────────────────────────────
    def detect(self, frame: np.ndarray) -> List[DetectionResult]:
        # 1. Primary detection (YOLO or Orange-Color)
        if self._using_yolo:
            detections = self._detect_yolo(frame)
        else:
            detections = self._detect_colour(frame)
            
        # 2. Check for Blue Flames (Requirement Phase 3)
        blue_flames = self._detect_blue(frame)
        
        # Phase 21: Cross-Correlation
        # If any primary detection overlaps with a blue detection, mark it as blue.
        for det in detections:
            for blue in blue_flames:
                if self._iou(det["bbox"], blue["bbox"]) > 0.3:
                    det["is_blue"] = True
                    # Inherit higher confidence if blue detection is stronger
                    det["confidence"] = max(det["confidence"], blue["confidence"])
                    break
                    
        # Add non-overlapping blue flames as standalone detections
        for blue in blue_flames:
            is_new = True
            for det in detections:
                if self._iou(det["bbox"], blue["bbox"]) > 0.5:
                    is_new = False
                    break
            if is_new:
                detections.append(blue)
        
        if self.collect_data and detections:
            self._save_training_sample(frame, detections)
            
        return detections

    def _save_training_sample(self, frame: np.ndarray, detections: List[DetectionResult]):
        """Saves image and YOLO-format annotations for custom training."""
        import uuid
        sample_id = str(uuid.uuid4())[:8]
        img_path = self.data_dir / "images" / f"sample_{sample_id}.jpg"
        lbl_path = self.data_dir / "labels" / f"sample_{sample_id}.txt"
        
        # Save Image
        cv2.imwrite(str(img_path), frame)
        
        # Save YOLO Labels [class_id x_center y_center width height] (normalized 0-1)
        h, w = frame.shape[:2]
        with open(lbl_path, "w") as f:
            for det in detections:
                bx, by, bw, bh = det["bbox"]
                # Convert to YOLO format
                x_center = (bx + bw / 2) / w
                y_center = (by + bh / 2) / h
                nw = bw / w
                nh = bh / h
                # class_id 0 for fire
                class_id = 0 
                f.write(f"{class_id} {x_center:.6f} {y_center:.6f} {nw:.6f} {nh:.6f}\n")
        
        logger.debug("📸 Saved training sample: {}", sample_id)

    def _detect_blue(self, frame: np.ndarray) -> List[DetectionResult]:
        """Heuristic to catch LPG/Alcohol blue fires with temporal flicker validation."""
        hsv   = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask  = cv2.inRange(hsv, self._BLUE_LOWER, self._BLUE_UPPER)
        
        # 1. Update history for flicker validation (Phase 19)
        self._history.append(mask.copy())
        
        # 2. Refine current mask
        kernel_open  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel_open)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close)
        
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        results = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 800: continue
            
            x, y, w, h = cv2.boundingRect(cnt)
            
            # 3. Temporal Consistency Test: Pixel-wise variance across 5 frames
            if len(self._history) == self._history.maxlen:
                # Extract ROI from all history masks
                roi_history = [m[y:y+h, x:x+w] for m in self._history]
                # Stack and calculate temporal variance per pixel
                stack = np.stack(roi_history, axis=0)
                temp_variance = np.var(stack, axis=0) # Variance across time
                # Average flicker score in active detection area
                active_flicker = np.mean(temp_variance[mask[y:y+h, x:x+w] > 0])
                
                # Confidence-Weighted Flicker Test
                # If YOLO is very sure (>0.7), the flicker requirement is relaxed.
                # If it's a weak detection, we require stronger flicker verification.
                flicker_threshold = 0.25 if self._using_yolo else 0.4
                if active_flicker < flicker_threshold:
                    continue
            
            results.append({
                "bbox"      : [x, y, w, h],
                "confidence": min(0.95, area / 4000),
                "class_name": "fire",
                "is_blue"   : True,
                "intensity" : None,
                "angle"     : None,
            })
        return results

    # ── YOLO path ─────────────────────────────────────────
    def _detect_yolo(self, frame: np.ndarray) -> List[DetectionResult]:
        results = self._model.predict(
            frame, conf=self.confidence, verbose=False)[0]
        
        raw_dets = []
        for box in results.boxes:
            cls_id   = int(box.cls[0])
            cls_name = results.names[cls_id]
            if cls_name not in ("fire", "smoke"): continue
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            raw_dets.append({
                "bbox": [x1, y1, x2 - x1, y2 - y1],
                "conf": float(box.conf[0]),
                "name": cls_name
            })

        # Phase 19: Smoke-Fire Correlation & Unification
        # If fire and smoke overlap, unify them into a single fire detection
        # with high spread priority.
        unified = []
        fire_dets  = [d for d in raw_dets if d["name"] == "fire"]
        smoke_dets = [d for d in raw_dets if d["name"] == "smoke"]
        
        matched_smoke = set()
        for f in fire_dets:
            f_unif = {
                "bbox"      : f["bbox"],
                "confidence": f["conf"],
                "class_name": "fire",
                "has_smoke" : False,
                "intensity" : None,
                "angle"     : None,
            }
            # Check for overlapping smoke
            for i, s in enumerate(smoke_dets):
                if self._iou(f["bbox"], s["bbox"]) > 0.1:
                    f_unif["has_smoke"] = True
                    matched_smoke.add(i)
            unified.append(f_unif)
            
        # Add remaining smoke as potential fire-sources deeper in
        for i, s in enumerate(smoke_dets):
            if i not in matched_smoke:
                unified.append({
                    "bbox"      : s["bbox"],
                    "confidence": s["conf"] * 0.8, # lower conf for smoke-only
                    "class_name": "smoke",
                    "has_smoke" : True,
                    "intensity" : None,
                    "angle"     : None,
                })
        return unified

    @staticmethod
    def _iou(a: List[int], b: List[int]) -> float:
        """Utility for Smoke-Fire Correlation overlap check."""
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        ix = max(ax, bx); iy = max(ay, by)
        ex = min(ax+aw, bx+bw); ey = min(ay+ah, by+bh)
        if ex < ix or ey < iy: return 0.0
        inter = (ex - ix) * (ey - iy)
        union = aw*ah + bw*bh - inter
        return float(inter / union) if union > 0 else 0.0

    # ── Colour-threshold fallback ─────────────────────────
    def _detect_colour(self, frame: np.ndarray) -> List[DetectionResult]:
        """
        Simple HSV-range fire detector.
        Sufficient for demo; not suitable for production outdoors.
        """
        hsv   = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask  = cv2.inRange(hsv, self._FIRE_LOWER, self._FIRE_UPPER)
        # Morphological cleaning
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        mask   = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask   = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel)

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 1200:          # Noise suppression increased to 1200
                continue
            x, y, w, h = cv2.boundingRect(cnt)
            detections.append({
                "bbox"      : [x, y, w, h],
                "confidence": min(0.99, area / 5000),
                "class_name": "fire",
                "intensity" : None,
                "angle"     : None,
            })
        return detections
