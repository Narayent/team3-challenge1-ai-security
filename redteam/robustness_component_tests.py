"""Robustness tests for the original code (Part 1 questions).

At runtime the stream-ordering bug crashes every request at the first model
call, which hides the other bugs, so we call the original functions directly to
show each one: Q1 corrupt input, Q2 wrong tensor shape, Q3 knife not flagged,
plus the ordering crash itself. Q4 (the 0.15 threshold) is argued in the report.
Run inside the container - needs numpy, cv2 and the mock models.
"""
import numpy as np
import cv2

# Import the exact functions/objects the app uses. lab_access_api.py opens
# "./models/*.pkl" relative to CWD, so chdir into the original/ app dir first.
import sys, os
ORIG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "original"))
os.chdir(ORIG)
sys.path.insert(0, ORIG)
from mock_models import MockFaceRecognitionModel, MockObjectDetectionModel  # noqa
from lab_access_api import preprocess_image  # noqa  (imports app module)

face_model = MockFaceRecognitionModel()
object_model = MockObjectDetectionModel()

line = lambda: print("-" * 68)


def q1_corrupt_input():
    print("Q1  Corrupted / non-image upload -> imdecode None -> predict crash")
    corrupt = b"This is a .txt file, not an image."
    img = preprocess_image(corrupt)
    print(f"    preprocess_image(corrupt bytes) -> {img!r}  (expected: None)")
    try:
        face_model.predict(img)
        print("    predict(None) -> NO ERROR  (unexpected)")
    except Exception as e:
        print(f"    face_model.predict(None) -> {type(e).__name__}: {e}")
    line()


def q2_shape_mismatch():
    print("Q2  Missing resize/normalize -> wrong shape -> model ValueError")
    # A *valid* decoded image: shape is (H, W, 3), NOT (1,224,224,3).
    real = np.zeros((300, 300, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", real)
    img = preprocess_image(buf.tobytes())
    print(f"    decoded image shape = {None if img is None else img.shape}")
    try:
        face_model.predict(img)
        print("    predict(decoded) -> NO ERROR (unexpected)")
    except Exception as e:
        print(f"    face_model.predict(decoded) -> {type(e).__name__}: {e}")
    line()


def q3_weapon_label_miss():
    print("Q3  Weapon-detection logic never fires for a real 'knife'")
    valid_tensor = np.zeros((1, 224, 224, 3), dtype=np.uint8)
    preds = object_model.predict(valid_tensor)
    print(f"    object_model output = {preds}")
    # Replicate the EXACT vulnerable decision loop from lab_access_api.py:
    has_danger = False
    for obj in preds:
        if obj['label'] == 'weapon' and obj['confidence'] > 0.15:
            has_danger = True
            break
    print(f"    vulnerable loop (label=='weapon') -> has_danger = {has_danger}")
    knife = [o for o in preds if o['label'] == 'knife']
    print(f"    reality: a knife is present at conf={knife[0]['confidence']} but")
    print(f"    the code checks label=='weapon' only -> DANGER MISSED, access not blocked.")
    line()


def ordering_root_cause():
    print("ROOT CAUSE of live 500s: file.save() consumes the stream, so a later")
    print("file.read() returns b'' -> np.frombuffer(b'') -> cv2.imdecode(empty).")
    empty = b""
    try:
        img = preprocess_image(empty)
        print(f"    preprocess_image(b'') -> {img!r}")
    except Exception as e:
        print(f"    preprocess_image(b'') -> {type(e).__name__}: "
              f"{str(e).splitlines()[0]}")
        print("    => this is the exact exception every live request raises on")
        print("       the vulnerable app (empty buffer after save consumes stream).")
    line()


if __name__ == "__main__":
    line()
    q1_corrupt_input()
    q2_shape_mismatch()
    q3_weapon_label_miss()
    ordering_root_cause()
    print("Done.")
