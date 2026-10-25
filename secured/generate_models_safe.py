"""Write the model specs and their integrity manifest.

Persists data only - a JSON spec naming an allowlisted model class - plus a
manifest.json pinning each spec's SHA-256. No pickled objects.
"""
import json
import hashlib
import os

os.makedirs("./models", exist_ok=True)

SPECS = {
    "face_recognition_model.json": {
        "model_class": "MockFaceRecognitionModel",
        "version": "v1.2.4-secure",
        "input_shape": [1, 224, 224, 3],
    },
    "object_detection_model.json": {
        "model_class": "MockObjectDetectionModel",
        "version": "v1.2.4-secure",
        "input_shape": [1, 224, 224, 3],
    },
}


def main():
    manifest = {}
    for name, spec in SPECS.items():
        path = os.path.join("./models", name)
        # Deterministic serialization so the hash is reproducible.
        data = json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
        with open(path, "wb") as f:
            f.write(data)
        manifest[name] = {"sha256": hashlib.sha256(data).hexdigest()}
        print(f"wrote {path}  sha256={manifest[name]['sha256']}")

    with open("./models/manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print("wrote ./models/manifest.json (pinned integrity hashes)")


if __name__ == "__main__":
    main()
