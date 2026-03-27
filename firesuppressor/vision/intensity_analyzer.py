"""
vision/intensity_analyzer.py
=============================
Rule-based fire intensity estimation.
No model training required – uses three proxy signals:

  1. Bounding-box area  (large box → more fire)
  2. Mean brightness    (V channel in HSV)
  3. Red-orange saturation  (S channel in HSV)

Combined into a [0.0, 1.0] score → bucketed to LOW / MEDIUM / HIGH.

References:
  • "Fire Detection Using Color Analysis" – Çelik & Ma (2010)
  • Brightness-based fire intensity proxy commonly used in embedded
    fire-suppression literature (IEEE Sensors Journal, 2021).
"""

from __future__ import annotations

from typing import List, Tuple

import cv2
import numpy as np


INTENSITY_LOW    = 0.33
INTENSITY_MEDIUM = 0.66

# Pressure lookup [PSI-equivalent label]
PRESSURE_MAP = {
    "LOW"   : {"label": "LOW",    "psi_equiv": 1, "water_level": 0.3},
    "MEDIUM": {"label": "MEDIUM", "psi_equiv": 3, "water_level": 0.6},
    "HIGH"  : {"label": "HIGH",   "psi_equiv": 5, "water_level": 1.0},
}


class IntensityAnalyzer:
    # Reference area (px²) for a "large" fire at typical camera distance
    _REF_AREA = 50_000

    def estimate(self, frame: np.ndarray,
                 bbox: List[int]) -> dict:
        """
        Parameters
        ----------
        frame : BGR image (H×W×3)
        bbox  : [x, y, w, h]

        Returns
        -------
        dict with keys: score (float), level (str), pressure (dict)
        """
        x, y, w, h = bbox
        H, W = frame.shape[:2]

        # Guard against out-of-bounds
        x1 = max(0, x);  y1 = max(0, y)
        x2 = min(W, x + w); y2 = min(H, y + h)
        roi = frame[y1:y2, x1:x2]

        if roi.size == 0:
            return self._make_result(0.0)

        area_score = min(1.0, (w * h) / self._REF_AREA)

        hsv         = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        v_channel   = hsv[:, :, 2]
        
        # Phase 19: Digital ND Filtering (Contrast Stretching)
        # If fire is "white-hot" (clipped), recover texture.
        clipping_ratio = np.mean(v_channel >= 250)
        if clipping_ratio > 0.1:
            # Apply CLAHE to Value channel to recover internal fire details
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
            v_ref = clahe.apply(v_channel)
            brightness = float(v_ref.mean()) / 255.0
            # Increase score as clipping implies extreme temperature
            score_boost = 0.15 
        else:
            brightness = float(v_channel.mean()) / 255.0
            score_boost = 0.0

        saturation  = float(hsv[:, :, 1].mean()) / 255.0

        # Weighted combination
        score = 0.4 * area_score + 0.3 * brightness + 0.2 * saturation + score_boost
        score = float(np.clip(score, 0.0, 1.0))

        return self._make_result(score)

    @staticmethod
    def _make_result(score: float) -> dict:
        if score < INTENSITY_LOW:
            level = "LOW"
        elif score < INTENSITY_MEDIUM:
            level = "MEDIUM"
        else:
            level = "HIGH"

        return {
            "score"   : round(score, 3),
            "level"   : level,
            "pressure": PRESSURE_MAP[level],
        }
