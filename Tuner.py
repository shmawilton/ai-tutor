import sys, math, os, time
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QToolBar, QLineEdit, QSlider, QProgressBar, QSizePolicy, QMessageBox
)
from PySide6.QtGui import QFont, QIcon, QPixmap, QAction
from PySide6.QtCore import Qt, QSize, QTimer
import pyqtgraph as pg
from tuner_engine import TunerEngine

class TunerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Flute Tuner")
        self.setMinimumSize(800, 600)
        self.scale_factor = 1.0  # used for responsive scaling
        
        # Initialize target note and history variables
        self.target_note = ""
        self.elapsed_time = 0.0
        self.history_time = []
        self.history_deviation = []
        
        # Create toolbar with mic icon
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setIconSize(QSize(32, 32))
        self.toolbar.setStyleSheet("background-color: #34495e;")
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)
        
        self.mic_action = QAction(QIcon("images/mic.svg"), "Microphone", self)
        self.toolbar.addAction(self.mic_action)
        settings_action = QAction(QIcon("images/settings.svg"), "Settings", self)
        tuningfork_action = QAction(QIcon("images/fork.png"), "Tuning Fork", self)
        refresh_action = QAction(QIcon("images/refresh.svg"), "Refresh", self)
        help_action = QAction(QIcon("images/help.svg"), "Help", self)
        self.toolbar.addAction(settings_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(tuningfork_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(refresh_action)
        self.toolbar.addAction(help_action)
        
        # Main widget layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Tuner display area (note display and feedback)
        display_layout = QHBoxLayout()
        display_layout.setSpacing(20)
        
        self.tuner_container = QWidget()
        self.tuner_container.setMinimumSize(600, 150)
        self.tuner_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        tuner_layout = QVBoxLayout(self.tuner_container)
        tuner_layout.setSpacing(10)
        tuner_layout.setAlignment(Qt.AlignCenter)
        
        self.note_label = QLabel("Tuner Display")
        self.note_label.setAlignment(Qt.AlignCenter)
        self.note_label.setFont(QFont("MusicFont", 50))
        self.note_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.default_style = (
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2c3e50, stop:1 #3498db);"
            "color: white; border-radius: 10px;"
        )
        self.correct_style = "background-color: #2ecc71; color: white; border-radius: 10px;"
        self.incorrect_style = "background-color: #e74c3c; color: white; border-radius: 10px;"
        
        # Emojis for feedback
        self.correct_emoji = "😊"
        self.incorrect_emoji = "😢"
        self.tuner_container.setStyleSheet(self.default_style)
        self.note_label.setStyleSheet("background: transparent;")
        tuner_layout.addWidget(self.note_label)
        
        self.feedback_label = QLabel()
        self.feedback_label.setAlignment(Qt.AlignCenter)
        tuner_layout.addWidget(self.feedback_label)
        
        display_layout.addWidget(self.tuner_container, 3)
        
        # Decorative flute icon (stored as an attribute for dynamic scaling)
        self.flute_button = QPushButton()
        flute_pixmap = QPixmap("images/flute.png")
        flute_pixmap = flute_pixmap.scaled(100, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.flute_button.setIcon(QIcon(flute_pixmap))
        self.flute_button.setIconSize(QSize(100, 150))
        self.flute_button.setFixedSize(120, 170)
        self.flute_button.setCursor(Qt.PointingHandCursor)
        self.flute_button.setStyleSheet("""
            QPushButton {
                background-color: #ecf0f1;
                border: 2px solid #bdc3c7;
                border-radius: 10px;
            }
            QPushButton:hover {
                background-color: #bdc3c7;
                border: 2px solid #3498db;
            }
            QPushButton:pressed {
                background-color: #bdc3c7;
            }
        """)
        self.flute_button.clicked.connect(self.flute_clicked)
        display_layout.addWidget(self.flute_button, 1)
        main_layout.addLayout(display_layout)
        
        # Play and Stop buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(20)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        
        self.play_button = QPushButton("Play")
        self.play_button.setIcon(QIcon("images/play.svg"))
        self.play_button.setFont(QFont("MusicFont", 18))
        self.play_button.setStyleSheet(
            "padding: 15px; border-radius: 5px; background-color: #27ae60; color: white;"
        )
        
        self.stop_button = QPushButton("Stop")
        self.stop_button.setIcon(QIcon("images/stop.svg"))
        self.stop_button.setFont(QFont("MusicFont", 18))
        self.stop_button.setStyleSheet(
            "padding: 15px; border-radius: 5px; background-color: #c0392b; color: white;"
        )
        
        buttons_layout.addWidget(self.play_button)
        buttons_layout.addWidget(self.stop_button)
        main_layout.addLayout(buttons_layout)
        
        # Target note input area
        target_layout = QHBoxLayout()
        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("Enter target note (e.g., G#, Bb)")
        self.target_input.setFont(QFont("MusicFont", 16))
        self.set_target_button = QPushButton("Set Target")
        self.clear_target_button = QPushButton("Clear Target")
        target_layout.addWidget(self.target_input)
        target_layout.addWidget(self.set_target_button)
        target_layout.addWidget(self.clear_target_button)
        main_layout.addLayout(target_layout)
        
        # Combined details row: Graph on left and tolerance slider + deviation meter on right
        details_row = QHBoxLayout()
        details_row.setSpacing(20)
        
        self.plot_widget = pg.PlotWidget(title="Pitch Deviation Over Time (cents)")
        self.plot_widget.setLabel('left', 'Cents')
        self.plot_widget.setLabel('bottom', 'Time (s)')
        self.plot_widget.setFixedSize(300, 100)
        self.curve = self.plot_widget.plot([], [], pen=pg.mkPen(color='y', width=2))
        details_row.addWidget(self.plot_widget, 2)
        
        details_container = QWidget()
        details_layout = QVBoxLayout(details_container)
        details_layout.setSpacing(10)
        details_layout.setContentsMargins(0, 0, 0, 0)
        
        tolerance_layout = QHBoxLayout()
        self.tolerance_label = QLabel("Tolerance: 2%")
        self.tolerance_label.setFont(QFont("MusicFont", 16))
        self.tolerance_slider = QSlider(Qt.Horizontal)
        self.tolerance_slider.setMinimum(0)
        self.tolerance_slider.setMaximum(10)
        self.tolerance_slider.setValue(2)
        tolerance_layout.addWidget(self.tolerance_label)
        tolerance_layout.addWidget(self.tolerance_slider)
        details_layout.addLayout(tolerance_layout)
        
        freq_meter_layout = QHBoxLayout()
        self.freq_meter_label = QLabel("Deviation (cents):")
        self.freq_meter_label.setFont(QFont("MusicFont", 16))
        self.freq_meter = QProgressBar()
        self.freq_meter.setMinimum(-50)
        self.freq_meter.setMaximum(50)
        self.freq_meter.setValue(0)
        self.freq_meter.setFormat("%v cents")
        freq_meter_layout.addWidget(self.freq_meter_label)
        freq_meter_layout.addWidget(self.freq_meter)
        details_layout.addLayout(freq_meter_layout)
        
        details_row.addWidget(details_container, 1)
        main_layout.addLayout(details_row)
        
        # Status panel
        self.status_panel = QLabel("Status: Waiting for input...")
        self.status_panel.setAlignment(Qt.AlignCenter)
        self.status_panel.setFont(QFont("MusicFont", 16))
        self.status_panel.setStyleSheet(
            "background-color: #34495e; color: #ecf0f1; border-radius: 5px; padding: 10px;"
        )
        self.status_panel.setFixedHeight(50)
        main_layout.addWidget(self.status_panel)
        
        # Create tuner engine instance and timer for updating display
        self.tuner = TunerEngine()
        self.timer = QTimer()
        self.timer.setInterval(50)  # update every 50 ms
        self.timer.timeout.connect(self.update_note)
        
        # Connect signals
        self.play_button.clicked.connect(self.start_tuning)
        self.stop_button.clicked.connect(self.stop_tuning)
        self.set_target_button.clicked.connect(self.set_target_note)
        self.clear_target_button.clicked.connect(self.clear_target_note)
        self.tolerance_slider.valueChanged.connect(self.update_tolerance)
        
        # Responsive scaling
        font_large = QFont("MusicFont", 22)
        font_medium = QFont("MusicFont", 16)
        self.note_label.setFont(font_large)
        self.play_button.setFont(font_medium)
        self.stop_button.setFont(font_medium)
        
        # Initial button states (NOT auto-starting)
        self.play_button.setEnabled(True)
        self.stop_button.setEnabled(False)
    
    def set_target_note(self):
        target = self.target_input.text().strip().upper()
        if target:
            self.target_note = target
            self.status_panel.setText(f"Status: Target note set to {target}")
            self.target_input.clear()
    
    def clear_target_note(self):
        self.target_note = ""
        self.status_panel.setText("Status: Target Cleared")
        self.tuner_container.setStyleSheet(self.default_style)
        self.feedback_label.clear()
        self.freq_meter.setValue(0)

    def update_tolerance(self, value):
        tolerance_fraction = value / 100.0
        self.tolerance_label.setText(f"Tolerance: {value}%")
        self.tuner.set_tolerance(tolerance_fraction)

    def start_tuning(self):
        self.status_panel.setText("Status: Tuning...")
        self.tuner.start_processing()
        self.timer.start()
        self.mic_action.setIcon(QIcon("images/mic_on.png"))
        self.elapsed_time = 0.0
        self.history_time = []
        self.history_deviation = []

    def stop_tuning(self):
        self.timer.stop()
        self.tuner.stop_processing()
        self.status_panel.setText("Status: Stopped")
        self.note_label.setText("Tuner Display")
        self.tuner_container.setStyleSheet(self.default_style)
        self.feedback_label.clear()
        self.freq_meter.setValue(0)
        self.mic_action.setIcon(QIcon("images/mic.svg"))

    def update_note(self):
        current_note = self.tuner.get_current_note()
        current_freq = self.tuner.get_last_frequency()
        
        if current_note:
            self.note_label.setText(current_note)
            
            # Check if note matches target
            if self.target_note and current_note == self.target_note:
                self.tuner_container.setStyleSheet(self.correct_style)
                self.feedback_label.setText(f"{self.correct_emoji} Perfect! In tune.")
            elif self.target_note:
                self.tuner_container.setStyleSheet(self.incorrect_style)
                self.feedback_label.setText(f"{self.incorrect_emoji} Target: {self.target_note}")
            else:
                self.tuner_container.setStyleSheet(self.default_style)
                self.feedback_label.clear()
            
            # Calculate deviation in cents
            if current_freq > 0 and self.target_note:
                target_freq = self.tuner.allowed_notes.get(self.target_note, 440.0)
                deviation_cents = 1200 * math.log2(current_freq / target_freq)
                self.freq_meter.setValue(int(deviation_cents))
                
                # Update history for graph
                self.elapsed_time += 0.05
                self.history_time.append(self.elapsed_time)
                self.history_deviation.append(deviation_cents)
                
                # Update graph
                self.curve.setData(self.history_time, self.history_deviation)
            else:
                self.freq_meter.setValue(0)
        else:
            self.note_label.setText("Tuner Display")
            self.tuner_container.setStyleSheet(self.default_style)
            self.feedback_label.clear()
            self.freq_meter.setValue(0)

    def flute_clicked(self, event):
        """Handle flute icon click - show reference note information"""
        info_text = """
        <h3>Flute Tuning Reference</h3>
        <p><b>Standard Flute Notes:</b></p>
        <ul>
            <li>C4 (Middle C): 261.63 Hz</li>
            <li>A4 (Standard Pitch): 440.00 Hz</li>
            <li>C5 (High C): 523.25 Hz</li>
        </ul>
        <p><b>Tuning Tips:</b></p>
        <ul>
            <li>Use the tuning fork button for A4 reference</li>
            <li>Set your target note using the input field</li>
            <li>Adjust your embouchure for fine tuning</li>
        </ul>
        """
        
        QMessageBox.information(self, "Flute Tuning Guide", info_text)

    def closeEvent(self, event):
        self.tuner.close()
        event.accept()

def main():
    app = QApplication(sys.argv)
    window = TunerWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
