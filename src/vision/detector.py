from __future__ import annotations

import cv2
import numpy as np


class PersonDetector:
    """HOG-based person detector.

    Runs detection on a downscaled copy for speed, then maps
    bounding boxes back to the original resolution.
    """

    def __init__(self, detection_scale: float = 0.5):
        self._scale = max(0.1, min(1.0, detection_scale))
        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, frame: np.ndarray) -> list[dict]:
        """Return list of dicts: {x, y, w, h, confidence} in original pixel coords."""
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (int(w * self._scale), int(h * self._scale)))

        boxes, weights = self._hog.detectMultiScale(
            small,
            winStride=(8, 8),
            padding=(4, 4),
            scale=1.05,
        )

        results: list[dict] = []
        if len(boxes) == 0:
            return results

        inv = 1.0 / self._scale
        for i, (bx, by, bw, bh) in enumerate(boxes):
            conf = float(weights[i]) if i < len(weights) else 1.0
            results.append(
                {
                    "x": int(bx * inv),
                    "y": int(by * inv),
                    "w": int(bw * inv),
                    "h": int(bh * inv),
                    "confidence": conf,
                }
            )
        return results
