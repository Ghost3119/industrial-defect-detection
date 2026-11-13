"""Shared full-frame preprocessing for stamped-part classification (OpenCV BGR)."""
import cv2
import numpy as np

NAMES = ("falta_embutido_material", "ok", "ruptura_deformacion")
REVIEW_THRESHOLD = 0.90


def square_frame(frame, size=224):
    height, width = frame.shape[:2]
    ratio = size / max(height, width)
    w, h = max(1, round(width * ratio)), max(1, round(height * ratio))
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    x, y = (size - w) // 2, (size - h) // 2
    canvas[y:y+h, x:x+w] = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
    return canvas
