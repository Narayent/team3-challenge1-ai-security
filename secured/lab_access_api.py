"""Smart Lab Access API (hardened version).

Same job as the original - decide Allow/Deny/Alert from a face check and a
dangerous-object check - but with input validation, authentication, safe model
loading, size limits, rate limiting and audit logging. Intended to run behind a
real WSGI server in production; the built-in server here is for the lab only.
"""
import os
import json
import time
import uuid
import hmac
import logging
import threading
from collections import defaultdict, deque

import cv2
import numpy as np
from flask import Flask, request, jsonify, g
from werkzeug.utils import secure_filename

from safe_model_loader import load_model, ModelIntegrityError

# --- Configuration (env with safe defaults) --------------------------------
API_KEY = os.environ.get("LAB_API_KEY", "")
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
LOGS_DIR = os.path.abspath(os.environ.get("LOGS_DIR", "./logs"))
MODELS_DIR = os.environ.get("MODELS_DIR", "./models")

# Access-decision policy
FACE_ALLOW_CONF = float(os.environ.get("FACE_ALLOW_CONF", "0.90"))   # auto-allow
FACE_REVIEW_CONF = float(os.environ.get("FACE_REVIEW_CONF", "0.60")) # human review band
DANGER_CONF = float(os.environ.get("DANGER_CONF", "0.50"))           # block dangerous objects
DANGEROUS_LABELS = {
    "weapon", "knife", "gun", "pistol", "rifle", "firearm",
    "explosive", "grenade", "bomb",
}

# Per-IP rate limiting
RATE_MAX = int(os.environ.get("RATE_MAX", "30"))
RATE_WINDOW = int(os.environ.get("RATE_WINDOW", "60"))

# Accepted image signatures, checked alongside imdecode
_MAGIC = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG\r\n\x1a\n": "png",
}

os.makedirs(LOGS_DIR, exist_ok=True)

# --- Audit logging ---------------------------------------------------------
logger = logging.getLogger("lab_access")
logger.setLevel(logging.INFO)
_fh = logging.FileHandler(os.path.join(LOGS_DIR, "audit.log"))
_fh.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_fh)
_ch = logging.StreamHandler()
_ch.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_ch)


def audit(event, **fields):
    rec = {"ts": round(time.time(), 3), "event": event,
           "rid": getattr(g, "rid", None), **fields}
    logger.info(json.dumps(rec))


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES  # oversized uploads -> 413

# Load models without pickle: integrity-checked, allowlisted, data-only specs.
try:
    face_model = load_model("face_recognition_model.json", MODELS_DIR)
    object_model = load_model("object_detection_model.json", MODELS_DIR)
except (FileNotFoundError, ModelIntegrityError) as e:
    raise SystemExit(f"FATAL: safe model load failed: {e}")

# --- Rate limiter + anomaly counter ----------------------------------------
_rl_lock = threading.Lock()
_rl_hits = defaultdict(deque)
_anomalies = defaultdict(int)


def rate_limited(ip):
    now = time.time()
    with _rl_lock:
        dq = _rl_hits[ip]
        while dq and dq[0] <= now - RATE_WINDOW:
            dq.popleft()
        if len(dq) >= RATE_MAX:
            return True
        dq.append(now)
        return False


def note_anomaly(ip, kind):
    with _rl_lock:
        _anomalies[ip] += 1
        count = _anomalies[ip]
    audit("anomaly", ip=ip, kind=kind, ip_anomaly_count=count)


# --- Helpers ---------------------------------------------------------------
def client_ip():
    return request.remote_addr or "unknown"


def require_api_key():
    # Fail closed: if no key was configured, reject everything.
    presented = request.headers.get("X-API-Key", "")
    if not API_KEY:
        return False
    return hmac.compare_digest(presented, API_KEY)


def sniff_image(data):
    for magic, kind in _MAGIC.items():
        if data.startswith(magic):
            return kind
    return None


def preprocess_image(image_bytes):
    """Decode, resize to 224x224, normalize, reshape to (1,224,224,3).
    Returns None if the bytes can't be decoded as an image."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    img = cv2.resize(img, (224, 224), interpolation=cv2.INTER_AREA)
    img = img.astype(np.float32) / 255.0
    return np.expand_dims(img, axis=0)


def safe_audit_save(validated_bytes, ext):
    """Save an audit copy under a server-generated name, confined to LOGS_DIR."""
    name = secure_filename(f"{uuid.uuid4().hex}.{ext}") or uuid.uuid4().hex
    dest = os.path.abspath(os.path.join(LOGS_DIR, name))
    if os.path.commonpath([dest, LOGS_DIR]) != LOGS_DIR:
        raise ValueError("refusing to write outside logs dir")
    with open(dest, "wb") as f:
        f.write(validated_bytes)
    return dest


@app.before_request
def _assign_rid():
    g.rid = uuid.uuid4().hex[:12]


@app.errorhandler(413)
def _too_large(e):
    audit("reject_too_large", ip=client_ip(), limit=MAX_UPLOAD_BYTES)
    return jsonify({"error": "payload too large"}), 413


@app.route("/api/access", methods=["POST"])
def check_access():
    ip = client_ip()

    if rate_limited(ip):
        note_anomaly(ip, "rate_limit")
        return jsonify({"error": "rate limit exceeded"}), 429

    if not require_api_key():
        note_anomaly(ip, "auth_fail")
        return jsonify({"error": "unauthorized"}), 401

    file = request.files.get("image")
    if not file:
        return jsonify({"error": "no image provided"}), 400

    # Read the upload once, before any save, so we never lose the stream.
    image_bytes = file.read()
    if not image_bytes:
        return jsonify({"error": "empty upload"}), 400

    kind = sniff_image(image_bytes)
    if kind is None:
        note_anomaly(ip, "bad_magic")
        return jsonify({"error": "unsupported or non-image file"}), 415

    tensor = preprocess_image(image_bytes)
    if tensor is None:
        note_anomaly(ip, "undecodable")
        return jsonify({"error": "corrupted or undecodable image"}), 400

    try:
        saved = safe_audit_save(image_bytes, kind)
    except ValueError:
        return jsonify({"error": "internal save error"}), 500

    try:
        face_prediction = face_model.predict(tensor)
        object_prediction = object_model.predict(tensor)
    except Exception as e:
        audit("model_error", ip=ip, err=str(e))
        return jsonify({"error": "model inference failed"}), 500

    detected_dangers = [
        {"label": o["label"], "confidence": o["confidence"]}
        for o in object_prediction
        if o["label"].lower() in DANGEROUS_LABELS and o["confidence"] >= DANGER_CONF
    ]
    has_danger = len(detected_dangers) > 0

    face_label = face_prediction.get("label")
    face_conf = float(face_prediction.get("confidence", 0.0))

    # Deny by default; low-confidence authorized faces go to human review.
    if has_danger:
        decision, reason = "deny", "dangerous_object_detected"
    elif face_label == "authorized" and face_conf >= FACE_ALLOW_CONF:
        decision, reason = "allow", "authorized_high_confidence"
    elif face_label == "authorized" and face_conf >= FACE_REVIEW_CONF:
        decision, reason = "pending_human_review", "authorized_but_low_confidence"
    else:
        decision, reason = "deny", "not_authorized"

    access_granted = decision == "allow"

    audit("access_decision", ip=ip, decision=decision, reason=reason,
          face_conf=face_conf, dangers=[d["label"] for d in detected_dangers],
          saved=os.path.basename(saved))

    return jsonify({
        "request_id": g.rid,
        "access": access_granted,
        "decision": decision,
        "reason": reason,
        "dangerous_objects": detected_dangers,
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    if not API_KEY:
        raise SystemExit("FATAL: set LAB_API_KEY before starting (fail closed).")
    app.run(host=HOST, port=PORT, debug=False)
