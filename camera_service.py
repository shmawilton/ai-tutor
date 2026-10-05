import os
import sys
import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal, Qt, QObject
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget, QVBoxLayout

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class CameraWorker(QThread):
    frame_ready = Signal(QImage)
    posture_changed = Signal(str)
    error = Signal(str)

    def __init__(self, camera_index=0, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self._running = False
        self._last_status = None

    def _load_models(self):
        import torch
        import torch.nn as nn
        from torchvision import models, transforms

        self.torch = torch
        self.person_net = cv2.dnn.readNetFromCaffe(
            os.path.join(BASE_DIR, "MobileNetSSD_deploy.prototxt"),
            os.path.join(BASE_DIR, "MobileNetSSD_deploy.caffemodel"),
        )
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = models.resnet18(weights=None)
        model.fc = nn.Linear(model.fc.in_features, 2)
        model.load_state_dict(torch.load(os.path.join(BASE_DIR, "best_posture_model.pth"),
                                         map_location=torch.device("cpu")))
        self.model = model.to(self.device).eval()
        self.transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])

    def _detect_persons(self, frame, conf_threshold=0.5):
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 0.007843, (300, 300), 127.5)
        self.person_net.setInput(blob)
        detections = self.person_net.forward()
        boxes = []
        for i in range(detections.shape[2]):
            if int(detections[0, 0, i, 1]) == 15 and detections[0, 0, i, 2] > conf_threshold:
                x1, y1, x2, y2 = (detections[0, 0, i, 3:7] * np.array([w, h, w, h])).astype(int)
                boxes.append((max(0, x1), max(0, y1), min(w, x2), min(h, y2)))
        return boxes

    def _classify(self, crop):
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        tensor = self.transform(rgb).unsqueeze(0).to(self.device)
        with self.torch.no_grad():
            return int(self.model(tensor).argmax(1).item())

    def run(self):
        backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.camera_index, backend)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            self.error.emit("Could not open webcam. Check your camera connection.")
            return
        print("Webcam opened successfully")

        try:
            self._load_models()
            models_ok = True
        except Exception as e:
            print(f"Posture models unavailable: {e}")
            self.error.emit(f"Posture model unavailable: {e}")
            models_ok = False

        self._running = True
        frame_idx = 0
        cached = []
        while self._running:
            ret, frame = cap.read()
            if not ret:
                self.msleep(30)
                continue

            if models_ok and frame_idx % 3 == 0:
                cached = []
                for (x1, y1, x2, y2) in self._detect_persons(frame):
                    crop = frame[y1:y2, x1:x2]
                    if crop.size:
                        cached.append(((x1, y1, x2, y2), self._classify(crop)))
                self._emit_status(cached)
            frame_idx += 1

            for (x1, y1, x2, y2), cls in cached:
                color = (0, 200, 0) if cls == 0 else (0, 0, 230)
                label = "Correct" if cls == 0 else "Incorrect"
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f"Posture: {label}", (x1 + 4, max(20, y1 - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            self.frame_ready.emit(QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy())

        cap.release()

    def _emit_status(self, results):
        if not results:
            status = "No person detected"
        elif all(cls == 0 for _, cls in results):
            status = "Correct"
        else:
            status = "Incorrect"
        if status != self._last_status:
            self._last_status = status
            self.posture_changed.emit(status)

    def stop(self):
        self._running = False
        self.wait(3000)


class CameraService(QObject):
    """Owns the single webcam worker; any number of VideoViews can subscribe."""
    frame_ready = Signal(QImage)
    posture_changed = Signal(str)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = CameraWorker()
        self.worker.frame_ready.connect(self.frame_ready)
        self.worker.posture_changed.connect(self.posture_changed)
        self.worker.error.connect(self.error)

    def start(self):
        if not self.worker.isRunning():
            self.worker.start()

    def stop(self):
        self.worker.stop()


class VideoView(QWidget):
    """Displays the shared camera feed scaled to fit (never cropped/zoomed)."""

    STATUS_STYLES = {
        "Correct": "background:#27ae60; color:white;",
        "Incorrect": "background:#c0392b; color:white;",
    }
    NEUTRAL_STYLE = "background:#dfe4ea; color:#2c3e50;"

    def __init__(self, service, show_status=True, parent=None):
        super().__init__(parent)
        self._last_image = None

        self.video = QLabel("Starting camera...")
        self.video.setAlignment(Qt.AlignCenter)
        self.video.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.video.setMinimumSize(160, 120)
        self.video.setStyleSheet("background:#e9ecef; color:#7f8c8d; border:1px solid #dfe4ea; border-radius:8px;")

        self.status = QLabel("Posture: --")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet(f"{self.NEUTRAL_STYLE} border-radius:6px; padding:6px; font-weight:bold;")
        self.status.setVisible(show_status)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.video, 1)
        layout.addWidget(self.status)

        service.frame_ready.connect(self._on_frame)
        service.posture_changed.connect(self._on_posture)
        service.error.connect(self._on_error)

    def _on_frame(self, image):
        self._last_image = image
        if self.isVisible():
            self._render()

    def _render(self):
        if self._last_image is None:
            return
        pix = QPixmap.fromImage(self._last_image).scaled(
            self.video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.video.setPixmap(pix)

    def _on_posture(self, status):
        self.status.setText(f"Posture: {status}")
        style = self.STATUS_STYLES.get(status, self.NEUTRAL_STYLE)
        self.status.setStyleSheet(f"{style} border-radius:6px; padding:6px; font-weight:bold;")

    def _on_error(self, message):
        if self._last_image is None:
            self.video.setText(message)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()
