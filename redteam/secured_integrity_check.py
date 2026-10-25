"""Retest of the model-integrity defense.

The hardened app doesn't pickle.load model files; it reads JSON specs, checks
each file's SHA-256 against a pinned manifest, and instantiates an allowlisted
class. This shows a clean model loads fine and a tampered one is refused (which
also breaks the traversal -> overwrite-model -> RCE chain). Works on a temp copy
so the running server's models are untouched.
"""
import os
import sys
import shutil
import tempfile

SECURED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "secured"))
os.chdir(SECURED)
sys.path.insert(0, SECURED)

from safe_model_loader import load_model, ModelIntegrityError  # noqa

line = lambda: print("-" * 68)


def main():
    tmp = tempfile.mkdtemp(prefix="models_")
    for f in os.listdir("./models"):
        shutil.copy(os.path.join("./models", f), os.path.join(tmp, f))

    line()
    print("(1) Clean load with integrity verification:")
    m = load_model("face_recognition_model.json", tmp)
    print(f"    loaded OK -> {type(m).__name__} (no pickle, hash verified)")
    line()

    print("(2) Attacker tampers with a model file (simulating a poisoned model")
    print("    or a traversal overwrite), then the app tries to load it:")
    target = os.path.join(tmp, "face_recognition_model.json")
    with open(target, "r+b") as fh:
        data = fh.read()
        fh.seek(0)
        fh.write(data.replace(b"MockFaceRecognitionModel", b"EvilModelXXXXXXXXXXXXXXXX"))
    try:
        load_model("face_recognition_model.json", tmp)
        print("    [-] UNEXPECTED: tampered model loaded (defense failed)")
        rc = 1
    except ModelIntegrityError as e:
        print(f"    [+] REFUSED: {e}")
        print("    => tampering detected before any use; RCE chain broken.")
        rc = 0
    line()
    shutil.rmtree(tmp, ignore_errors=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
