"""
vision/capture.py
==================
Unified frame source:
  • Real webcam  (--camera N)
  • Video file   (--video path)
  • Demo mode    (--demo)  – synthetic frames with injected fire/smoke regions

In demo mode no camera hardware is required.
"""

import time
from typing import Generator, Tuple

import cv2
import numpy as np
from loguru import logger


FrameMeta = dict   # {"source": str, "ts": float, "frame_id": int}


class FrameSource:
    def __init__(self, args):
        self._args   = args
        self._cap    = None
        self._demo   = getattr(args, "demo",   False)
        self._camera = getattr(args, "camera", None)
        self._video  = getattr(args, "video",  None)
        self._frame_id = 0

    def start(self):
        if self._demo:
            return   # no hardware needed
        
        src = self._camera if self._camera is not None else self._video
        if src is None:
            raise ValueError("No video source provided (demo, camera, or video)")

        # On Windows, try CAP_DSHOW for webcams if default fails
        backends = [None, cv2.CAP_DSHOW] if isinstance(src, int) else [None]
        
        for backend in backends:
            try:
                if backend is not None:
                    self._cap = cv2.VideoCapture(src, backend)
                else:
                    self._cap = cv2.VideoCapture(src)
                
                if self._cap.isOpened():
                    logger.success(f"Opened video source {src} with backend {'DSHOW' if backend else 'Default'}")
                    return
            except Exception as e:
                logger.warning(f"Failed to open source {src} with backend {backend}: {e}")

        raise RuntimeError(f"Cannot open video source: {src}. Please ensure your camera is connected and not in use by another app.")

    def stop(self):
        if self._cap:
            self._cap.release()

    def frames(self) -> Generator[Tuple[np.ndarray, FrameMeta], None, None]:
        if self._demo:
            yield from self._synthetic_frames()
        else:
            yield from self._real_frames()

    # ── Real frames ───────────────────────────────────────
    def _real_frames(self):
        while True:
            ret, frame = self._cap.read()
            if not ret:
                # Loop video file
                if self._video:
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                break
            self._frame_id += 1
            meta = {"source": str(self._camera or self._video),
                    "ts": time.time(), "frame_id": self._frame_id}
            yield frame, meta

    # ── Synthetic demo frames ────────────────────────────
    def _synthetic_frames(self):
        """
        Generates 640×480 frames with animated fire rectangles and
        human silhouettes to exercise the full pipeline without a camera.

        Fire position cycles around the frame; a "human" blob appears
        every 5 s.
        """
        W, H = 640, 480
        angle   = 0.0    # camera sweep angle
        t_start = time.time()

        while True:
            frame = np.zeros((H, W, 3), dtype=np.uint8)

            # Background: dark room
            frame[:] = (20, 20, 30)

            t = time.time() - t_start

            # ── Animated fire blob ────────────────────────
            fire_cx = int(W * 0.2 + W * 0.6 * abs(np.sin(t * 0.3)))
            fire_cy = int(H * 0.3 + H * 0.2 * abs(np.cos(t * 0.4)))
            fire_w  = int(60 + 30 * abs(np.sin(t * 0.8)))
            fire_h  = int(80 + 20 * abs(np.cos(t * 0.7)))

            x1 = max(0, fire_cx - fire_w // 2)
            y1 = max(0, fire_cy - fire_h // 2)
            x2 = min(W, fire_cx + fire_w // 2)
            y2 = min(H, fire_cy + fire_h // 2)

            # Draw orange-red fire rectangle
            frame[y1:y2, x1:x2] = self._fire_texture(y2 - y1, x2 - x1, t)

            # ── Second smaller fire every 8 s ─────────────
            if int(t) % 8 < 4:
                fx2, fy2 = int(W * 0.75), int(H * 0.6)
                fw2, fh2 = 40, 50
                frame[fy2:fy2+fh2, fx2:fx2+fw2] = \
                    self._fire_texture(fh2, fw2, t + 1.5)

            # ── Human silhouette every 5 s ────────────────
            if int(t) % 5 < 2:
                hx = int(W * 0.55)
                hy = int(H * 0.35)
                hw, hh = 30, 80
                frame[hy:hy+hh, hx:hx+hw] = (180, 120, 90)

            # ── Simulate camera rotation ───────────────────
            angle = (angle + 0.5) % 360

            self._frame_id += 1
            meta = {"source": "demo", "ts": time.time(),
                    "frame_id": self._frame_id, "camera_angle": angle}
            yield frame, meta
            time.sleep(0.1)   # 10 FPS demo

    @staticmethod
    def _fire_texture(h: int, w: int, t: float) -> np.ndarray:
        """Simple orange-red noise resembling fire."""
        noise = np.random.randint(0, 40, (h, w, 3), dtype=np.uint8)
        base  = np.zeros((h, w, 3), dtype=np.uint8)
        # BGR: orange-red
        base[:, :, 2] = np.clip(200 + noise[:, :, 0], 0, 255)  # R
        base[:, :, 1] = np.clip(80  + noise[:, :, 1], 0, 180)  # G
        base[:, :, 0] = np.clip(10  + noise[:, :, 2], 0, 50)   # B
        return base
