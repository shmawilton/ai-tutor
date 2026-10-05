import sys, random
import numpy as np
import librosa
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTabWidget, QListWidget, QApplication, QMessageBox, QFrame
)
from PySide6.QtCore import Qt, QTimer
import sounddevice as sd
import queue
import threading
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from scipy.signal import find_peaks
import os
import time

class PitchDetectionWidget(QMainWindow):
    def __init__(self, tempo=120, time_signature="4/4", performance_duration=30,
                 reference_audio_path=None, sheet_title=None):
        """
        Parameters:
          tempo: Beats per minute.
          time_signature: e.g. "4/4" (the numerator is used as beats per measure).
          performance_duration: Duration (in seconds) for the simulated performance.
          reference_audio_path: Path to the reference audio file.
          sheet_title: Title of the sheet music.
        """
        super().__init__()
        self.setWindowTitle(f"Practice: {sheet_title}" if sheet_title else "Pitch Recognition Practice")
        self.resize(1000, 800)
        
        # Store parameters
        self.tempo = tempo
        self.time_signature = time_signature
        self.performance_duration = performance_duration
        self.reference_audio_path = reference_audio_path
        self.sheet_title = sheet_title
        
        try:
            self.beats_per_measure = int(self.time_signature.split('/')[0])
        except Exception:
            self.beats_per_measure = 4  # default
        
        # Calculate measure duration and a three-measure countdown
        self.measure_duration = 60 / self.tempo * self.beats_per_measure
        self.countdown_time = int(self.measure_duration * 3)
        
        # Performance state
        self.performance_started = False
        self.elapsed_time = 0
        self.performance_history = []  # List of tuples: (accuracy, percentage_completed)
        
        # Audio processing parameters
        self.sample_rate = 44100
        self.chunk_size = 2048  # Increased for better pitch detection
        self.audio_queue = queue.Queue()
        self.is_recording = False
        self.recorded_audio = []
        self.reference_pitches = []
        self.performance_pitches = []
        self.reference_times = []
        self.performance_times = []
        
        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        
        # Title and instructions
        title_label = QLabel("Practice with Real-time Pitch Recognition")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        main_layout.addWidget(title_label)
        
        instructions = QLabel(
            f"Practice the piece at {self.tempo} BPM in {self.time_signature} time.\n"
            "Your pitch accuracy will be compared with the reference audio in real-time."
        )
        instructions.setStyleSheet("margin: 10px;")
        main_layout.addWidget(instructions)
        
        # Control buttons
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Practice")
        self.stop_button = QPushButton("Stop Practice")
        self.stop_button.setEnabled(False)
        
        self.start_button.clicked.connect(self.start_recording)
        self.stop_button.clicked.connect(self.stop_recording)
        
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        main_layout.addLayout(button_layout)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(self.performance_duration)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)
        
        # Accuracy display
        self.accuracy_label = QLabel("Accuracy: --%")
        self.accuracy_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        main_layout.addWidget(self.accuracy_label)
        
        # Matplotlib figure for pitch comparison
        self.figure, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(10, 8))
        self.canvas = FigureCanvas(self.figure)
        main_layout.addWidget(self.canvas)
        
        # Timer for updating progress and visualization
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_progress)
        self.start_time = 0
        
        # Load reference audio if available
        if self.reference_audio_path and os.path.exists(self.reference_audio_path):
            self.load_reference_audio()
    
    def load_reference_audio(self):
        try:
            # Load reference audio and extract pitches
            y, sr = librosa.load(self.reference_audio_path)
            pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
            
            # Get the most prominent pitch at each time
            self.reference_pitches = []
            self.reference_times = []
            for time_idx in range(pitches.shape[1]):
                pitches_at_time = pitches[:, time_idx]
                magnitudes_at_time = magnitudes[:, time_idx]
                if magnitudes_at_time.max() > 0:
                    dominant_pitch = pitches_at_time[magnitudes_at_time.argmax()]
                    self.reference_pitches.append(dominant_pitch)
                    self.reference_times.append(time_idx / sr)  # Convert to seconds
                else:
                    self.reference_pitches.append(0)
                    self.reference_times.append(time_idx / sr)
            
            # Normalize the reference pitches
            self.reference_pitches = np.array(self.reference_pitches)
            self.reference_pitches = (self.reference_pitches - self.reference_pitches.min()) / \
                                   (self.reference_pitches.max() - self.reference_pitches.min())
            
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Could not load reference audio: {str(e)}")
    
    def start_recording(self):
        self.is_recording = True
        self.recorded_audio = []
        self.performance_pitches = []
        self.performance_times = []
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.start_time = time.time()
        
        # Start audio recording thread
        self.recording_thread = threading.Thread(target=self.record_audio)
        self.recording_thread.start()
        
        # Start progress timer
        self.timer.start(100)  # Update every 100ms
    
    def stop_recording(self):
        self.is_recording = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.timer.stop()
        
        # Calculate final accuracy
        if self.performance_pitches and self.reference_pitches:
            accuracy = self.calculate_accuracy()
            self.accuracy_label.setText(f"Final Accuracy: {accuracy:.1f}%")
            
            # Show results dialog
            QMessageBox.information(
                self,
                "Practice Results",
                f"Your performance accuracy: {accuracy:.1f}%\n"
                f"Practice duration: {self.progress_bar.value()} seconds"
            )
    
    def record_audio(self):
        with sd.InputStream(samplerate=self.sample_rate, channels=1, callback=self.audio_callback):
            while self.is_recording:
                sd.sleep(100)
    
    def audio_callback(self, indata, frames, time, status):
        if status:
            print(status)
        self.audio_queue.put(indata.copy())
    
    def update_progress(self):
        current_time = time.time() - self.start_time
        self.progress_bar.setValue(int(current_time))
        
        # Process audio data and update visualization
        while not self.audio_queue.empty():
            audio_chunk = self.audio_queue.get()
            self.recorded_audio.extend(audio_chunk.flatten())
            
            # Extract pitch from the chunk
            pitches, magnitudes = librosa.piptrack(
                y=np.array(self.recorded_audio[-self.chunk_size:]),
                sr=self.sample_rate
            )
            
            if pitches.size > 0:
                # Get the most prominent pitch
                dominant_pitch = pitches[magnitudes.argmax()]
                self.performance_pitches.append(dominant_pitch)
                self.performance_times.append(current_time)
        
        # Update visualization
        self.update_visualization()
        
        # Check if we've reached the performance duration
        if current_time >= self.performance_duration:
            self.stop_recording()
    
    def calculate_accuracy(self):
        if not self.performance_pitches or not self.reference_pitches:
            return 0.0
        
        # Normalize performance pitches
        perf_pitches = np.array(self.performance_pitches)
        perf_pitches = (perf_pitches - perf_pitches.min()) / \
                      (perf_pitches.max() - perf_pitches.min())
        
        # Calculate accuracy based on pitch similarity and timing
        min_len = min(len(perf_pitches), len(self.reference_pitches))
        pitch_diff = np.abs(perf_pitches[:min_len] - self.reference_pitches[:min_len])
        
        # Weight accuracy by pitch difference and timing
        accuracy = 100 * (1 - np.mean(pitch_diff))
        
        return max(0, min(100, accuracy))
    
    def update_visualization(self):
        self.ax1.clear()
        self.ax2.clear()
        
        # Plot 1: Pitch comparison
        if self.reference_pitches:
            self.ax1.plot(self.reference_times, self.reference_pitches, 
                         label='Reference', color='blue', alpha=0.5)
        
        if self.performance_pitches:
            perf_pitches = np.array(self.performance_pitches)
            perf_pitches = (perf_pitches - perf_pitches.min()) / \
                          (perf_pitches.max() - perf_pitches.min())
            self.ax1.plot(self.performance_times, perf_pitches, 
                         label='Your Performance', color='red', alpha=0.5)
        
        self.ax1.set_title('Pitch Comparison')
        self.ax1.set_xlabel('Time (seconds)')
        self.ax1.set_ylabel('Normalized Pitch')
        self.ax1.legend()
        self.ax1.grid(True)
        
        # Plot 2: Accuracy over time
        if self.performance_pitches and self.reference_pitches:
            accuracy_history = []
            for i in range(len(self.performance_pitches)):
                if i < len(self.reference_pitches):
                    perf_pitch = self.performance_pitches[i]
                    ref_pitch = self.reference_pitches[i]
                    accuracy = 100 * (1 - abs(perf_pitch - ref_pitch))
                    accuracy_history.append(accuracy)
            
            if accuracy_history:
                self.ax2.plot(self.performance_times, accuracy_history, 
                             label='Accuracy', color='green')
                self.ax2.set_title('Accuracy Over Time')
                self.ax2.set_xlabel('Time (seconds)')
                self.ax2.set_ylabel('Accuracy (%)')
                self.ax2.grid(True)
        
        # Update accuracy display
        accuracy = self.calculate_accuracy()
        self.accuracy_label.setText(f"Current Accuracy: {accuracy:.1f}%")
        
        self.figure.tight_layout()
        self.canvas.draw()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    widget = PitchDetectionWidget()
    widget.show()
    sys.exit(app.exec())
