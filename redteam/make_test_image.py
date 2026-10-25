"""Generate a benign, valid test JPEG used by the evidence/retest scripts.

Run inside the lab container (has numpy + cv2). Writes a 300x300 color JPEG.
"""
import numpy as np
import cv2
import os

out = os.environ.get("OUT", "/app/_fixtures/valid.jpg")
os.makedirs(os.path.dirname(out), exist_ok=True)

# A simple deterministic gradient image (not a real face; models are mocked).
img = np.zeros((300, 300, 3), dtype=np.uint8)
img[:, :, 0] = np.tile(np.linspace(0, 255, 300, dtype=np.uint8), (300, 1))
img[:, :, 1] = np.tile(np.linspace(0, 255, 300, dtype=np.uint8), (300, 1)).T
img[:, :, 2] = 128
cv2.imwrite(out, img)
print(f"wrote {out} ({os.path.getsize(out)} bytes)")
