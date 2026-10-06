import sys
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QMainWindow, QScrollArea, QWidget, QLabel,
    QVBoxLayout, QHBoxLayout, QTabWidget, QSplitter
)
from PySide6.QtCore import Qt

# Import components
from camera_service import CameraService, VideoView
from tuner_widget import TunerWidget
from metronome_widget import MetronomeWidget
from voice_coach import VoiceCoach
from database.sheet_music_db import SheetMusicDatabase
import theme
from theme import C

# Handle sheet music import with fallback
try:
    from sheet_music import SheetMusicWidget
    SHEET_MUSIC_AVAILABLE = True
except ImportError as e:
    print(f"Sheet music module not available: {e}")
    SHEET_MUSIC_AVAILABLE = False
    SheetMusicWidget = None

#######################################
# Tab 1: Posture + Tuner (Main)
#######################################
class MainTab(QWidget):
    def __init__(self, camera_service, coach=None, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Posture Detection (Left)
        posture_container = QWidget()
        posture_layout = QVBoxLayout(posture_container)
        posture_layout.setContentsMargins(5, 5, 5, 5)

        posture_header = QHBoxLayout()
        self._labels = []
        posture_label = QLabel("Posture Detection")
        self._labels.append(posture_label)
        posture_header.addWidget(posture_label)
        posture_header.addStretch(1)
        self.dark_toggle = QCheckBox("Dark mode")
        self.dark_toggle.setChecked(theme.theme_name() == "dark")
        self.dark_toggle.toggled.connect(
            lambda on: theme.apply_theme(QApplication.instance(),
                                         "dark" if on else "light"))
        posture_header.addWidget(self.dark_toggle)
        self.voice_toggle = QCheckBox("Voice coach")
        if coach is not None:
            self.voice_toggle.setChecked(coach.enabled)
            self.voice_toggle.toggled.connect(lambda on: setattr(coach, "enabled", on))
        else:
            self.voice_toggle.setVisible(False)
        posture_header.addWidget(self.voice_toggle)
        posture_layout.addLayout(posture_header)

        self.posture_widget = VideoView(camera_service)
        posture_layout.addWidget(self.posture_widget, 1)

        # Tuner + Metronome (Right, scrollable)
        right_content = QWidget()
        right_layout = QVBoxLayout(right_content)
        right_layout.setContentsMargins(5, 5, 5, 16)
        right_layout.setSpacing(8)

        tuner_label = QLabel("Tuner")
        self._labels.append(tuner_label)
        right_layout.addWidget(tuner_label)
        self.tuner_window = TunerWidget(coach=coach, db=SheetMusicDatabase())
        right_layout.addWidget(self.tuner_window)
        self.metronome = MetronomeWidget()
        right_layout.addWidget(self.metronome)
        right_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(right_content)

        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(posture_container)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)
        theme.restyle(self._style)

    def _style(self):
        for lbl in self._labels:
            lbl.setStyleSheet(
                f"font-size:16px; font-weight:bold; padding:5px; color:{C['text']};")
        self.setStyleSheet(theme.qss("QCheckBox { color:$text; }"))

    def shutdown(self):
        self.tuner_window.shutdown()
        self.metronome.shutdown()

#######################################
# Tab 2: Sheet Music with Small Posture
#######################################
class SheetMusicTab(QWidget):
    def __init__(self, camera_service, coach=None, parent=None):
        super().__init__(parent)
        self.sheet_music_widget = None
        self.coach = coach
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        if SHEET_MUSIC_AVAILABLE:
            try:
                self.sheet_music_widget = SheetMusicWidget(camera_service, coach=self.coach)
                main_layout.addWidget(self.sheet_music_widget)
            except Exception as e:
                error_label = QLabel(f"Sheet Music Error: {str(e)}")
                error_label.setAlignment(Qt.AlignCenter)
                main_layout.addWidget(error_label)
        else:
            error_label = QLabel("Sheet Music not available")
            error_label.setAlignment(Qt.AlignCenter)
            main_layout.addWidget(error_label)
    
    def shutdown(self):
        if self.sheet_music_widget is not None:
            self.sheet_music_widget.shutdown()

#######################################
# Main Tabbed Window
#######################################
class TabbedFluteTutor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Flute Tutor")
        self.resize(1400, 900)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Voice coach (spoken feedback for posture, intonation and practice)
        self.coach = VoiceCoach(self)

        # Create shared posture widget
        self.camera_service = CameraService(self)
        self.camera_service.posture_changed.connect(self.coach.on_posture)

        # Create tab widget
        self.tab_widget = QTabWidget()
        
        # Tab 1: Posture + Tuner
        self.main_tab = MainTab(self.camera_service, coach=self.coach)
        self.tab_widget.addTab(self.main_tab, "Posture && Tuner")
        
        # Tab 2: Sheet Music
        self.sheet_tab = SheetMusicTab(self.camera_service, coach=self.coach)
        self.tab_widget.addTab(self.sheet_tab, "Sheet Music")

        layout.addWidget(self.tab_widget)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.camera_service.start()

    def _on_tab_changed(self, index):
        if self.tab_widget.widget(index) is not self.main_tab:
            self.main_tab.tuner_window.stop_all()

    def closeEvent(self, event):
        for shutdown in (self.main_tab.shutdown, self.sheet_tab.shutdown,
                         self.camera_service.stop, self.coach.shutdown):
            try:
                shutdown()
            except Exception as e:
                print(f"Shutdown error: {e}")
        event.accept()

#######################################
# Main Execution
#######################################
def main():
    app = QApplication(sys.argv)
    initial = "dark" if app.styleHints().colorScheme() == Qt.ColorScheme.Dark else "light"
    theme.apply_theme(app, initial)
    window = TabbedFluteTutor()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
