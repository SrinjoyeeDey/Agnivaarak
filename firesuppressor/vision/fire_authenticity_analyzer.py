import cv2
import numpy as np
from collections import deque
from loguru import logger

class FireAuthenticityAnalyzer:
    """
    Analyzes temporal and sensor signatures of a fire target to verify its authenticity.
    Distinguishes between real physical fire and 'fake' samples (screens, images, etc.).
    """
    
    def __init__(self, history_len=30, simulate_fake=False, simulate_real=False):
        self.history_len = history_len
        self.simulate_fake = simulate_fake
        self.simulate_real = simulate_real
        # Key: fire_id, Value: dict of histories
        self.histories = {}
        
    def update(self, fire_id: str, frame: np.ndarray, bbox: list, 
               temperature: float, infrared: float, distance_factor: float = 1.0):
        """
        Updates the history for a specific fire target and computes an authenticity score.
        bbox: [x, y, w, h]
        """
        if fire_id not in self.histories:
            self.histories[fire_id] = {
                "intensity": deque(maxlen=self.history_len),
                "bbox_area": deque(maxlen=self.history_len),
                "aspect_ratio": deque(maxlen=self.history_len),
                "temp": deque(maxlen=60), # Longer history for temp trends
                "ir":   deque(maxlen=60),
                "optical_flow": deque(maxlen=self.history_len)
            }
            
        h, w = frame.shape[:2]
        x, y, bw, bh = bbox
        # Safety crop
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(w, x+bw), min(h, y+bh)
        
        if x2 <= x1 or y2 <= y1:
            return 0.5 # Default uncertain
            
        roi = frame[y1:y2, x1:x2]
        gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        
        # 1. Intensity Scaling (Flicker)
        mean_intensity = cv2.mean(gray_roi)[0]
        self.histories[fire_id]["intensity"].append(mean_intensity)
        
        # 2. Bbox Dynamics
        self.histories[fire_id]["bbox_area"].append(bw * bh)
        self.histories[fire_id]["aspect_ratio"].append(bw / bh if bh > 0 else 1.0)
        
        # 3. Sensor Delta
        self.histories[fire_id]["temp"].append(temperature)
        self.histories[fire_id]["ir"].append(infrared)
        
        # 4. Optical Flow (Simplified)
        # We only compute flow if we have a previous frame for this target
        # For simplicity in this modular design, we'll store the gray_roi
        prev_roi = self.histories[fire_id].get("prev_gray_roi")
        flow_mag = 0.0
        if prev_roi is not None and prev_roi.shape == gray_roi.shape:
            # Dense flow is expensive, let's use a simpler diff-based motion metric 
            # as a proxy unless robust flow is strictly needed.
            # Actually, let's use Farneback on a small resize for better accuracy.
            small_roi = cv2.resize(gray_roi, (32, 32))
            small_prev = cv2.resize(prev_roi, (32, 32))
            flow = cv2.calcOpticalFlowFarneback(small_prev, small_roi, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            flow_mag = np.mean(np.sqrt(flow[..., 0]**2 + flow[..., 1]**2))
            
        self.histories[fire_id]["optical_flow"].append(flow_mag)
        self.histories[fire_id]["prev_gray_roi"] = gray_roi
        
        return self._calculate_score(fire_id, distance_factor)

    def _calculate_score(self, fire_id: str, distance_factor: float) -> float:
        """
        Combines temporal, sensor, and context signals into a single score [0, 1].
        """
        if self.simulate_fake: return 0.15 # Strong 'Fake'
        if self.simulate_real: return 0.98 # Strong 'Real'
        
        hist = self.histories[fire_id]
        if len(hist["intensity"]) < 5:
            return 0.6 # Initial default (wait for data)
            
        # 1. Temporal Flicker Score (Real fire flickers significantly)
        # Intensity variance
        flicker_score = np.std(hist["intensity"]) / (np.mean(hist["intensity"]) + 1e-6)
        flicker_score = np.clip(flicker_score * 5.0, 0, 1.0) # Tune multiplier
        
        # 2. Motion Score (Internal turbulence)
        # Real fire has high erratic internal motion
        avg_flow = np.mean(hist["optical_flow"]) if hist["optical_flow"] else 0
        motion_score = np.clip(avg_flow / 2.0, 0, 1.0)
        
        # 3. Shape Variation (Real fire changes shape constantly)
        shape_score = np.std(hist["aspect_ratio"]) * 10.0
        shape_score = np.clip(shape_score, 0, 1.0)
        
        # 4. Sensor Fusion Score (Adaptive to distance)
        # Check for rising trend
        temp_delta = (hist["temp"][-1] - hist["temp"][0]) if len(hist["temp"]) > 10 else 0
        ir_delta   = (hist["ir"][-1] - hist["ir"][0]) if len(hist["ir"]) > 10 else 0
        
        # Adaptive: Small bbox (far) needs less sensor confirmation
        sensor_score = 0.5 # neutral
        if ir_delta > 5.0: sensor_score += 0.25
        if temp_delta > 0.5: sensor_score += 0.25
        
        # Apply distance correction
        # If fire is far (distance_factor is high), we trust sensor less and vision more
        temporal_combined = (flicker_score * 0.4 + motion_score * 0.4 + shape_score * 0.2)
        
        # Weighting: Far = Vision(0.7)+Sensor(0.3), Near = Vision(0.4)+Sensor(0.6)
        vision_weight = np.clip(0.4 + (distance_factor * 0.3), 0.4, 0.8)
        sensor_weight = 1.0 - vision_weight
        
        final_score = (temporal_combined * vision_weight) + (sensor_score * sensor_weight)
        
        # Hard Filter: Static Rectangular Screens
        # If very low shape variation AND very low flicker -> FAKE
        if shape_score < 0.05 and flicker_score < 0.1:
            final_score *= 0.3
            
        return np.clip(final_score, 0, 1.0)

    def cleanup(self, active_ids: list):
        """Removes histories for fires no longer in the queue."""
        to_remove = [fid for fid in self.histories if fid not in active_ids]
        for fid in to_remove:
            del self.histories[fid]
