"""Model loading without pickle.

Loads a small JSON spec, checks its SHA-256 against the pinned manifest, and
instantiates a class from a fixed allowlist. No code is deserialized, and a
tampered model file is rejected before it is used.
"""
import os
import json
import hashlib
import hmac

from mock_models import MockFaceRecognitionModel, MockObjectDetectionModel

_ALLOWLISTED_MODELS = {
    "MockFaceRecognitionModel": MockFaceRecognitionModel,
    "MockObjectDetectionModel": MockObjectDetectionModel,
}


class ModelIntegrityError(Exception):
    pass


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_model(spec_filename, models_dir="./models"):
    spec_path = os.path.join(models_dir, spec_filename)
    manifest_path = os.path.join(models_dir, "manifest.json")

    with open(manifest_path) as f:
        manifest = json.load(f)
    if spec_filename not in manifest:
        raise ModelIntegrityError(f"{spec_filename} not in manifest")

    expected = manifest[spec_filename]["sha256"]
    actual = _sha256_file(spec_path)
    if not hmac.compare_digest(expected, actual):
        raise ModelIntegrityError(
            f"integrity check FAILED for {spec_filename}: "
            f"expected {expected[:12]}..., got {actual[:12]}..."
        )

    with open(spec_path) as f:
        spec = json.load(f)
    cls_name = spec.get("model_class")
    if cls_name not in _ALLOWLISTED_MODELS:
        raise ModelIntegrityError(f"model_class {cls_name!r} not allowlisted")

    return _ALLOWLISTED_MODELS[cls_name]()
