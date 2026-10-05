import sys
import cv2
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image
import numpy as np
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QSplitter, QSizePolicy, QPushButton, QMessageBox
)
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage, QPixmap

# Handle imports
try:
    import pymupdf as pdf_lib
except:
    try:
        import fitz as pdf_lib
    except:
        pdf_lib = None

#######################################
# Posture Detection Widget for Practice
#######################################
class PracticePostureWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Label for displaying video frames
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        
        # Initialize video capture
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.label.setText("Error: Could not open webcam.")
            return
        
        # Load MobileNet-SSD for person detection
        self.prototxt_path = "MobileNetSSD_deploy.prototxt"
        self.model_path = "MobileNetSSD_deploy.caffemodel"
        self.person_net = cv2.dnn.readNetFromCaffe(self.prototxt_path, self.model_path)
        
        # Load ResNet18-based posture classifier
        self.posture_labels = ["Correct", "Incorrect"]
        self.model = models.resnet18(weights=None)
        num_ftrs = self.model.fc.in_features
        self.model.fc = nn.Linear(num_ftrs, 2)
        self.model.load_state_dict(torch.load("best_posture_model.pth", map_location=torch.device("cpu")))
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = self.model.to(self.device)
        self.model.eval()
        
        self.posture_transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406],
                                 [0.229, 0.224, 0.225])
        ])
        
        # Timer to update video frames
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)
        
    def detect_persons(self, frame, conf_threshold=0.5):
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 0.007843, (300, 300), 127.5)
        self.person_net.setInput(blob)
        detections = self.person_net.forward()
        
        boxes = []
        person_class_id = 15
        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            class_id = int(detections[0, 0, i, 1])
            if class_id == person_class_id and confidence > conf_threshold:
                box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                (x1, y1, x2, y2) = box.astype("int")
                boxes.append((x1, y1, x2, y2))
        return boxes
    
    def classify_posture(self, crop):
        pil_img = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        input_tensor = self.posture_transform(pil_img).unsqueeze(0).to(self.device)
        with torch.no_grad():
            outputs = self.model(input_tensor)
            _, preds = torch.max(outputs, 1)
        return preds.item()
    
    def update_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            return
        
        boxes = self.detect_persons(frame)
        for (x1, y1, x2, y2) in boxes:
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            posture_class = self.classify_posture(crop)
            label_text = self.posture_labels[posture_class]
            box_color = (0, 255, 0) if posture_class == 0 else (0, 0, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
            cv2.putText(frame, f"Posture: {label_text}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, box_color, 2)
        
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
        self.label.setPixmap(QPixmap.fromImage(qt_image))
    
    def closeEvent(self, event):
        self.cap.release()
        event.accept()

#######################################
# Sheet Music Display Widget
#######################################
class SheetMusicDisplayWidget(QWidget):
    def __init__(self, sheet_music_data, parent=None):
        super().__init__(parent)
        self.sheet_music_data = sheet_music_data
        self.scale_factor = 1.0
        
        layout = QVBoxLayout(self)
        
        # Display label
        self.display_label = QLabel()
        self.display_label.setAlignment(Qt.AlignCenter)
        self.display_label.setMinimumSize(600, 400)
        layout.addWidget(self.display_label)
        
        # Zoom controls
        zoom_layout = QHBoxLayout()
        zoom_in_btn = QPushButton("Zoom In")
        zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_out_btn = QPushButton("Zoom Out")
        zoom_out_btn.clicked.connect(self.zoom_out)
        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self.reset_zoom)
        
        zoom_layout.addWidget(zoom_in_btn)
        zoom_layout.addWidget(zoom_out_btn)
        zoom_layout.addWidget(reset_btn)
        layout.addLayout(zoom_layout)
        
        # Update display
        self.update_display()
    
    def update_display(self):
        if pdf_lib and hasattr(self.sheet_music_data, 'pdf_path') and self.sheet_music_data.pdf_path:
            try:
                doc = pdf_lib.open(self.sheet_music_data.pdf_path)
                page = doc.load_page(0)
                mat = pdf_lib.Matrix(self.scale_factor, self.scale_factor)
                pix = page.get_pixmap(matrix=mat)
                from PySide6.QtGui import QImage
                image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                from PySide6.QtGui import QPixmap
                pixmap = QPixmap.fromImage(image)
                self.display_label.setPixmap(pixmap)
            except Exception as e:
                self.display_label.setText(f"Error loading PDF: {e}")
        else:
            self.display_label.setText("PDF not available")
    
    def zoom_in(self):
        self.scale_factor += 0.2
        self.update_display()
    
    def zoom_out(self):
        if self.scale_factor > 0.5:
            self.scale_factor -= 0.2
            self.update_display()
    
    def reset_zoom(self):
        self.scale_factor = 1.0
        self.update_display()

#######################################
# Practice Window - Posture + Sheet Music
#######################################
class PracticeWindow(QMainWindow):
    def __init__(self, sheet_music_data, tempo, time_signature, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Practice: {sheet_music_data.title}")
        self.resize(1400, 800)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create splitter
        splitter = QSplitter(Qt.Horizontal)
        
        # Posture widget (left)
        self.posture_widget = PracticePostureWidget()
        self.posture_widget.setMinimumSize(600, 400)
        splitter.addWidget(self.posture_widget)
        
        # Sheet music widget (right)
        self.sheet_widget = SheetMusicDisplayWidget(sheet_music_data)
        self.sheet_widget.setMinimumSize(600, 400)
        splitter.addWidget(self.sheet_widget)
        
        # Set stretch factors
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        
        # Main layout
        layout = QHBoxLayout(central_widget)
        layout.addWidget(splitter)
        
        # Add recording button
        self.record_button = QPushButton("Record & Analyze Pitch")
        self.record_button.clicked.connect(self.record_and_analyze)
        layout = QVBoxLayout(central_widget)
        layout.addWidget(self.record_button)
        layout.addWidget(splitter)
    
    def record_and_analyze(self):
        """Record audio and analyze pitch (simplified)"""
        try:
            import sounddevice as sd
            import numpy as np
            import librosa
            
            # Record for 5 seconds
            self.record_button.setEnabled(False)
            self.record_button.setText("Recording...")
            
            sample_rate = 44100
            duration = 5
            recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1)
            sd.wait()
            
            # Analyze pitch
            pitches, magnitudes = librosa.piptrack(y=recording.flatten(), sr=sample_rate)
            
            # Get dominant pitch
            if magnitudes.max() > 0:
                dominant_pitch = pitches[magnitudes.argmax()]
                result = f"Analysis complete. Dominant pitch: {dominant_pitch:.2f} Hz"
            else:
                result = "Analysis complete. No clear pitch detected."
            
            QMessageBox.information(self, "Pitch Analysis", result)
            
        except ImportError:
            QMessageBox.warning(self, "Not Available", "Sound recording requires sounddevice and librosa")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Recording failed: {str(e)}")
        finally:
            self.record_button.setEnabled(True)
            self.record_button.setText("Record & Analyze Pitch")
    
    def closeEvent(self, event):
        self.posture_widget.closeEvent(event)
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Create dummy sheet music data for testing
    class DummySheetData:
        def __init__(self):
            self.title = "Test Music"
            self.pdf_path = ""
    
    window = PracticeWindow(DummySheetData(), 120, "4/4")
    window.show()
    sys.exit(app.exec())
