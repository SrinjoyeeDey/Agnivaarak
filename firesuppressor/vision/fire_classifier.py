"""
vision/fire_classifier.py
=========================
Industrial rule-based fire classification.
"""

import cv2
import numpy as np
from loguru import logger


class FireClassifier:
    def __init__(self, model_path: str = None):
        self._model_path = model_path
        self._using_ml = False

    def classify(self, fire_data: dict, frame: np.ndarray = None, frame_height: int = 480) -> dict:
        """
        Fire class selection priority:
          1. Class D for white-hot metal signatures.
          2. Class B gas when blue flame evidence is present.
          3. Class B liquid for large, intense spills.
          4. Class C for compact low-mounted electrical fires.
          5. Class A fallback.
        """
        bbox = fire_data.get("bbox", [0, 0, 0, 0])
        x, y, w, h = map(int, bbox)
        detector_blue_flag = bool(fire_data.get("is_blue", False))

        roi_available = self._extract_roi(frame, x, y, w, h) is not None
        blue_metrics = self._analyze_blue_signature(frame, x, y, w, h)
        blue_classification = self._decide_blue_class(detector_blue_flag, blue_metrics, roi_available)

        intensity_info = fire_data.get("intensity") or {}
        score = intensity_info.get("score", 0.5)
        area = w * h
        aspect_ratio = (w / max(h, 1)) if h > 0 else 1.0
        bottom_edge = y + h
        near_floor = bottom_edge >= frame_height * 0.72
        compact_source = area <= 18000 and 0.25 <= aspect_ratio <= 4.0
        spreading_pool_shape = area >= 12000 and aspect_ratio >= 1.2 and bottom_edge >= frame_height * 0.45
        is_metal = self._detect_metal_signature(frame, x, y, w, h)

        fire_type = "CLASS A (SOLID)"
        confidence = 0.70

        if is_metal:
            fire_type = "CLASS D (METAL)"
            confidence = 0.95
        elif blue_classification:
            fire_type = "CLASS B (GAS)"
            confidence = blue_classification["confidence"]
        elif near_floor and compact_source and score <= 0.9:
            fire_type = "CLASS C (ELEC)"
            confidence = 0.80 if score >= 0.45 else 0.74
        elif spreading_pool_shape and score > 0.78:
            fire_type = "CLASS B (LIQUID)"
            confidence = 0.85

        logger.debug(
            "CLASSIFICATION: Result={} | detector_blue={} | blue_ratio={:.3f} | core_blue_ratio={:.3f} | area={} | aspect={:.2f} | bottom_edge={}",
            fire_type,
            detector_blue_flag,
            blue_metrics["blue_ratio"],
            blue_metrics["core_blue_ratio"],
            area,
            aspect_ratio,
            bottom_edge,
        )

        return {
            "fire_type": fire_type.split(" ")[1].lower(),
            "label": fire_type,
            "confidence": confidence,
        }

    @staticmethod
    def _extract_roi(frame: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray | None:
        if frame is None or w <= 0 or h <= 0:
            return None
        roi = frame[max(0, y):min(frame.shape[0], y + h), max(0, x):min(frame.shape[1], x + w)]
        return roi if roi.size > 0 else None

    def _analyze_blue_signature(self, frame: np.ndarray, x: int, y: int, w: int, h: int) -> dict:
        roi = self._extract_roi(frame, x, y, w, h)
        if roi is None:
            return {
                "blue_ratio": 0.0,
                "core_blue_ratio": 0.0,
                "blue_dominance": 0.0,
                "v_std": 0.0,
                "mean_saturation": 0.0,
                "mean_brightness": 0.0,
            }

        try:
            hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            h_channel = hsv_roi[:, :, 0]
            s_channel = hsv_roi[:, :, 1]
            v_channel = hsv_roi[:, :, 2]

            blue_mask = (
                (h_channel >= 85) & (h_channel <= 140) &
                (s_channel >= 70) & (v_channel >= 65)
            )
            core_blue_mask = (
                (h_channel >= 95) & (h_channel <= 130) &
                (s_channel >= 100) & (v_channel >= 90)
            )

            roi_float = roi.astype(np.float32)
            blue_ratio = float(np.mean(blue_mask))
            core_blue_ratio = float(np.mean(core_blue_mask))
            blue_dominance = float(np.mean(roi_float[:, :, 0] - np.maximum(roi_float[:, :, 1], roi_float[:, :, 2])))
            v_std = float(np.std(v_channel[blue_mask])) if np.any(blue_mask) else 0.0
            mean_saturation = float(np.mean(s_channel))
            mean_brightness = float(np.mean(v_channel))

            return {
                "blue_ratio": blue_ratio,
                "core_blue_ratio": core_blue_ratio,
                "blue_dominance": blue_dominance,
                "v_std": v_std,
                "mean_saturation": mean_saturation,
                "mean_brightness": mean_brightness,
            }
        except Exception as exc:
            logger.error("Blue signature analysis failed: {}", exc)
            return {
                "blue_ratio": 0.0,
                "core_blue_ratio": 0.0,
                "blue_dominance": 0.0,
                "v_std": 0.0,
                "mean_saturation": 0.0,
                "mean_brightness": 0.0,
            }

    @staticmethod
    def _decide_blue_class(detector_blue_flag: bool, metrics: dict, roi_available: bool) -> dict | None:
        blue_ratio = metrics["blue_ratio"]
        core_blue_ratio = metrics["core_blue_ratio"]
        blue_dominance = metrics["blue_dominance"]
        v_std = metrics["v_std"]

        strong_roi_blue = (
            blue_ratio >= 0.14 and
            core_blue_ratio >= 0.06 and
            blue_dominance >= 8.0
        )
        supported_detector_blue = (
            detector_blue_flag and
            blue_ratio >= 0.08 and
            core_blue_ratio >= 0.03 and
            blue_dominance >= 4.0
        )

        if strong_roi_blue:
            return {"confidence": 0.94}
        if supported_detector_blue:
            return {"confidence": 0.88 if v_std >= 6.0 else 0.84}
        if detector_blue_flag and not roi_available:
            return {"confidence": 0.80}
        return None

    def _detect_metal_signature(self, frame: np.ndarray, x: int, y: int, w: int, h: int) -> bool:
        roi = self._extract_roi(frame, x, y, w, h)
        if roi is None:
            return False
        try:
            hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            saturation = hsv_roi[:, :, 1]
            brightness = hsv_roi[:, :, 2]

            white_hot_mask = (gray_roi >= 250) & (brightness >= 245) & (saturation <= 60)
            white_ratio = float(np.mean(white_hot_mask))
            low_chroma_ratio = float(np.mean(saturation <= 50))

            return white_ratio >= 0.18 and low_chroma_ratio >= 0.25
        except Exception:
            return False
