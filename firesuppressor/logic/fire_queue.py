"""
logic/fire_queue.py
====================
Priority queue of active fire targets.

Priority order (descending):
  1. HIGH intensity
  2. MEDIUM intensity
  3. LOW intensity
  (within same intensity → longest-unattended first)

Stale fires (not seen for > STALE_TIMEOUT seconds) are removed.
"""

from __future__ import annotations

import time
import uuid
from collections import OrderedDict, deque, Counter
from typing import List

STALE_TIMEOUT = 1.5   # seconds

INTENSITY_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def _normalize_fire_type(fire_type: str | None, label: str | None, is_blue: bool = False) -> str:
    if is_blue:
        return "b"
    raw = (fire_type or "").strip().lower()
    if raw:
        if raw.startswith("class "):
            parts = raw.split()
            if len(parts) > 1 and parts[1]:
                return parts[1][0]
        return raw[0]
    raw_label = (label or "").upper()
    for key in ("A", "B", "C", "D"):
        if f"({key})" in raw_label or f"CLASS {key}" in raw_label:
            return key.lower()
    return "a"


def _canonical_label(fire_type: str, label: str | None) -> str:
    if label:
        return label
    return {
        "a": "CLASS A (SOLID)",
        "b": "CLASS B (GAS)",
        "c": "CLASS C (ELEC)",
        "d": "CLASS D (METAL)",
    }.get(fire_type, "CLASS A (SOLID)")


class FireTarget:
    def __init__(self, detection: dict):
        self.id         = str(uuid.uuid4())[:8]
        self.bbox       = detection["bbox"]
        self.angle      = detection.get("angle", 0.0)
        self.intensity  = detection.get("intensity", {})
        self.confidence = detection.get("confidence", 0.5)
        self.is_blue    = detection.get("is_blue", False)
        self.first_seen = time.time()
        self.last_seen  = time.time()
        self.hits       = 1  # Track frames seen
        self.misses     = 0  # Track frames missed
        self.level      = (self.intensity or {}).get("level", "MEDIUM")
        self.fire_type  = _normalize_fire_type(
            detection.get("fire_type"),
            detection.get("label"),
            self.is_blue,
        )
        self.label      = _canonical_label(self.fire_type, detection.get("label"))
        self.has_smoke  = detection.get("has_smoke", False)
        # Initialize with anchor frames to prevent rapid flip-flopping
        self.label_history = deque([self.label] * 10, maxlen=30)
        self.type_history = deque([self.fire_type] * 10, maxlen=30)
        self.authenticity = 0.6 # Initial default (Uncertain)

    def update(self, detection: dict):
        self.bbox       = detection["bbox"]
        self.angle      = detection.get("angle", self.angle)
        self.intensity  = detection.get("intensity", self.intensity)
        self.confidence = detection.get("confidence", self.confidence)
        self.is_blue    = detection.get("is_blue", self.is_blue)
        self.last_seen  = time.time()
        self.hits      += 1
        self.level      = (self.intensity or {}).get("level", self.level)
        self.fire_type  = _normalize_fire_type(
            detection.get("fire_type", self.fire_type),
            detection.get("label", self.label),
            self.is_blue,
        )
        self.label      = _canonical_label(self.fire_type, detection.get("label", self.label))
        self.has_smoke  = detection.get("has_smoke", self.has_smoke)
        self.label_history.append(self.label)
        self.type_history.append(self.fire_type)

    @property
    def priority(self) -> float:
        rank = INTENSITY_RANK.get(self.level, 2)
        age  = time.time() - self.last_seen
        smoke_bonus = 50 if self.has_smoke else 0
        return rank * 100 + smoke_bonus - age   # higher = more urgent

    @property
    def is_confirmed(self) -> bool:
        """Requirement Phase 6 & Phase 16: Time + Consistency check."""
        duration = time.time() - self.first_seen
        # Accelerated for Demo/Phase 21: 0.5s and 40% consistency
        consistency = self.hits / (self.hits + self.misses) if (self.hits + self.misses) > 0 else 0
        return duration >= 0.5 and consistency >= 0.4

    @property
    def stable_label(self) -> str:
        """Phase 20: Returns the temporal consensus label."""
        if not self.label_history: return self.label
        return Counter(self.label_history).most_common(1)[0][0]

    @property
    def stable_type(self) -> str:
        """Phase 20: Returns the temporal consensus type (a, b, c, d)."""
        if self.is_blue:
            return "b"
        if self.type_history:
            return Counter(self.type_history).most_common(1)[0][0]
        return _normalize_fire_type(self.fire_type, self.label, self.is_blue)

    def to_dict(self) -> dict:
        # Phase 20: Use stable consensus for output
        return {
            "id"        : self.id,
            "bbox"      : self.bbox,
            "angle"     : round(self.angle or 0.0, 1),
            "intensity" : self.intensity,
            "confidence": round(self.confidence, 3),
            "is_blue"   : self.is_blue,
            "level"     : self.level,
            "fire_type" : self.stable_type,
            "label"     : self.stable_label,
            "age"       : round(time.time() - self.first_seen, 1),
            "stability" : round(self.hits / (self.hits + self.misses), 2) if (self.hits+self.misses)>0 else 0,
            "authenticity" : round(getattr(self, "authenticity", 0.6), 2)
        }


class FireQueue:
    def __init__(self, max_targets: int = 4):
        self._max      = max_targets
        self._targets: OrderedDict[str, FireTarget] = OrderedDict()

    def update(self, detections: List[dict]):
        """Merge new detections into queue with Duo-Stage Confidence Filtering."""
        now = time.time()

        # Phase 16, 19 & 22: Unified Spatial Clustering for ALL Fires
        # Prevents fragmented bboxes from triggering multiple nozzles
        final_detections = self._cluster_detections(detections, threshold=180.0)

        # 1. Update existing/New
        matched_ids = set()
        for det in final_detections:
            matched = self._find_match(det)
            
            # Duo-Stage thresholding:
            # - Existing fires: keep if conf > 0.25
            # - New fires: accept only if conf > 0.60
            conf = det.get("confidence", 0.0)
            
            if matched:
                if conf >= 0.25:
                    matched.update(det)
                    matched_ids.add(matched.id)
            elif conf >= 0.40 and len(self._targets) < self._max * 2:
                target = FireTarget(det)
                self._targets[target.id] = target
                matched_ids.add(target.id)

        # 2. Track misses / Priority boosting
        for tid, t in self._targets.items():
            if tid not in matched_ids:
                t.misses += 1
            # Boost priority if smoke is visible (Phase 19)
            # This is handled via t.update/init if we add the has_smoke field
            # (already added in fire_detector.py)

        # 3. Remove stale
        stale = [tid for tid, t in self._targets.items()
                 if now - t.last_seen > STALE_TIMEOUT]
        for tid in stale:
            del self._targets[tid]

    def _cluster_detections(self, detections: List[dict], threshold: float) -> List[dict]:
        """
        Groups multiple detection boxes into clusters based on centroid proximity.
        Ensures that fragmented blue flames are treated as single logical objects.
        """
        if not detections:
            return []
            
        data = []
        for d in detections:
            bbox = d["bbox"]
            cx = float(bbox[0]) + float(bbox[2])/2.0
            cy = float(bbox[1]) + float(bbox[3])/2.0
            data.append({"det": d, "center": (cx, cy), "cluster": -1})
            
        cluster_count = 0
        for i in range(len(data)):
            if data[i]["cluster"] != -1: continue
            data[i]["cluster"] = cluster_count
            stack = [i]
            while stack:
                curr = stack.pop()
                for j in range(len(data)):
                    if data[j]["cluster"] != -1: continue
                    dist = ((data[curr]["center"][0] - data[j]["center"][0])**2 + 
                            (data[curr]["center"][1] - data[j]["center"][1])**2)**0.5
                    if dist < threshold:
                        data[j]["cluster"] = cluster_count
                        stack.append(j)
            cluster_count += 1
            
        results = []
        for c in range(cluster_count):
            cluster_items = [d["det"] for d in data if d["cluster"] == c]
            if not cluster_items: continue
            
            # Pick the "best" item in the cluster (highest confidence) to lead
            best_item = max(cluster_items, key=lambda d: d.get("confidence", 0.0))
            
            x1 = min(float(d["bbox"][0]) for d in cluster_items)
            y1 = min(float(d["bbox"][1]) for d in cluster_items)
            x2 = max(float(d["bbox"][0]) + float(d["bbox"][2]) for d in cluster_items)
            y2 = max(float(d["bbox"][1]) + float(d["bbox"][3]) for d in cluster_items)
            
            results.append({
                "bbox": [int(x1), int(y1), int(x2 - x1), int(y2 - y1)],
                "confidence": best_item.get("confidence", 0.5),
                "is_blue": any(d.get("is_blue", False) for d in cluster_items),
                "class_name": best_item.get("class_name", "fire"),
                "fire_type": best_item.get("fire_type", "a"),
                "label": best_item.get("label", "CLASS A (SOLID)"),
                "intensity": best_item.get("intensity"),
                "angle": best_item.get("angle"),
                "has_smoke": any(d.get("has_smoke", False) for d in cluster_items)
            })
        return results

    def top(self, n: int) -> List[dict]:
        """Return top-n highest priority confirmed targets."""
        confirmed = [t for t in self._targets.values() if t.is_confirmed]
        sorted_targets = sorted(
            confirmed,
            key=lambda t: t.priority,
            reverse=True)
        return [t.to_dict() for t in sorted_targets[:n]]

    def all(self) -> List[dict]:
        """Return all confirmed targets."""
        return [t.to_dict() for t in self._targets.values() if t.is_confirmed]

    # ── Enhanced matching ────────────────────────────────
    def _find_match(self, det: dict,
                    iou_threshold: float = 0.15,
                    dist_threshold: float = 200.0) -> FireTarget | None:
        """
        Merge detections using IoU and Center-Distance fallback.
        Very small fires (like matchsticks) often have 0 IoU despite being the same.
        """
        det_bbox = det["bbox"]
        det_cx = det_bbox[0] + det_bbox[2] / 2
        det_cy = det_bbox[1] + det_bbox[3] / 2

        best_score = 0.0
        best_match = None

        for target in self._targets.values():
            # 1. Try IoU
            iou = self._iou(det_bbox, target.bbox)
            
            # 2. Try Center Distance
            t_bbox = target.bbox
            t_cx = t_bbox[0] + t_bbox[2] / 2
            t_cy = t_bbox[1] + t_bbox[3] / 2
            dist = ((det_cx - t_cx)**2 + (det_cy - t_cy)**2)**0.5

            # Match if IoU is high OR centers are very close
            if iou >= iou_threshold:
                if iou > best_score:
                    best_score = iou
                    best_match = target
            elif dist < dist_threshold:
                # Use distance as a secondary match (normalized score)
                dist_score = 1.0 - (dist / dist_threshold)
                if dist_score > best_score:
                    best_score = dist_score
                    best_match = target

        return best_match

    @staticmethod
    def _iou(a: List[int], b: List[int]) -> float:
        ax, ay, aw, ah = a;  bx, by, bw, bh = b
        ix = max(ax, bx); iy = max(ay, by)
        ex = min(ax+aw, bx+bw); ey = min(ay+ah, by+bh)
        if ex < ix or ey < iy:
            return 0.0
        inter = (ex - ix) * (ey - iy)
        union = aw*ah + bw*bh - inter
        return inter / union if union > 0 else 0.0
