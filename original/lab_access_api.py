import cv2
import numpy as np
import pickle
import os
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- Model Loading ---
# The development team used pickle to serialize their custom models.
with open("./models/face_recognition_model.pkl", "rb") as f:
    face_model = pickle.load(f)
with open("./models/object_detection_model.pkl", "rb") as f:
    object_model = pickle.load(f)

# --- Preprocessing ---
def preprocess_image(image_bytes):
    # Convert bytes to numpy array for OpenCV
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # TODO: The team forgot to add image resizing and normalization here.
    # The model expects a 224x224 normalized tensor, but receives raw image bytes.
    return img

# --- API Endpoint ---
@app.route('/api/access', methods=['POST'])
def check_access():
    # Receive image from camera
    file = request.files.get('image')
    if not file:
        return jsonify({"error": "No image provided"}), 400
    filename = file.filename

    # Save image to local logs for auditing purposes
    save_path = os.path.join("./logs/", filename)
    file.save(save_path)

    # Read image bytes and preprocess
    image_bytes = file.read()
    img = preprocess_image(image_bytes)

    # Run AI Models
    # Note: face_model.predict() expects a specific tensor shape, not a raw OpenCV image.
    face_prediction = face_model.predict(img)
    object_prediction = object_model.predict(img)

    # Check for dangerous objects
    has_danger = False
    for obj in object_prediction:
        # The model outputs specific classes like 'knife', 'gun', 'explosive', not just 'weapon'
        if obj['label'] == 'weapon' and obj['confidence'] > 0.15:
            has_danger = True
            break

    # Make access decision
    access_granted = False
    if face_prediction['label'] == 'authorized' and not has_danger:
        access_granted = True

    # Return response to the physical door controller
    response = {
        "access": access_granted,
        "face_confidence": face_prediction['confidence'],
        "objects_detected": object_prediction,
        "debug_info": {
            "model_version": "v1.2.4-beta",
            "internal_model_path": "./models/face_recognition_model.pkl",
            "server_ip": "192.168.1.50",
            "saved_log_path": save_path,
        },
    }
    return jsonify(response)

if __name__ == '__main__':
    # Start the server
    app.run(host='0.0.0.0', port=80, debug=True)
