"""Mock model classes (pure Python / NumPy).

These live in a shared module so the pickled objects can be loaded by the Flask
app as well as the generator. If they were defined inside generate_models.py,
pickle would reference them as __main__.* and the API couldn't unpickle them.
"""
import numpy as np


class MockFaceRecognitionModel:
    def predict(self, image_tensor):
        if not isinstance(image_tensor, np.ndarray):
            raise TypeError(f"Model Error: Expected numpy.ndarray, got {type(image_tensor)}")
        if image_tensor.shape != (1, 224, 224, 3):
            raise ValueError(f"Model Error: Invalid input shape. Expected (1, 224, 224, 3), got {image_tensor.shape}")
        return {"label": "authorized", "confidence": 0.98}


class MockObjectDetectionModel:
    def predict(self, image_tensor):
        if not isinstance(image_tensor, np.ndarray):
            raise TypeError(f"Model Error: Expected numpy.ndarray, got {type(image_tensor)}")
        if image_tensor.shape != (1, 224, 224, 3):
            raise ValueError(f"Model Error: Invalid input shape. Expected (1, 224, 224, 3), got {image_tensor.shape}")
        return [
            {"label": "person", "confidence": 0.95},
            {"label": "knife", "confidence": 0.88},
            {"label": "backpack", "confidence": 0.75},
        ]
