import pickle
import os

from mock_models import MockFaceRecognitionModel, MockObjectDetectionModel

os.makedirs("./models", exist_ok=True)

face_model = MockFaceRecognitionModel()
object_model = MockObjectDetectionModel()

with open("./models/face_recognition_model.pkl", "wb") as f:
    pickle.dump(face_model, f)
with open("./models/object_detection_model.pkl", "wb") as f:
    pickle.dump(object_model, f)

print("Mock models generated successfully in ./models/")
