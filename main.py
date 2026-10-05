import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QTabWidget, QSplitter
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

# Import components
from camera_service import CameraService, VideoView
from tuner_widget import TunerWidget

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
    def __init__(self, camera_service, parent=None):
        super().__init__(parent)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Posture Detection (Left)
        posture_container = QWidget()
        posture_layout = QVBoxLayout(posture_container)
        posture_layout.setContentsMargins(5, 5, 5, 5)
        
        posture_label = QLabel("Posture Detection")
        posture_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 5px;")
        posture_layout.addWidget(posture_label)
        
        self.posture_widget = VideoView(camera_service)
        posture_layout.addWidget(self.posture_widget, 1)
        
        # Tuner (Right)
        tuner_container = QWidget()
        tuner_layout = QVBoxLayout(tuner_container)
        tuner_layout.setContentsMargins(5, 5, 5, 5)
        
        tuner_label = QLabel("Tuner")
        tuner_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 5px;")
        tuner_layout.addWidget(tuner_label)
        
        self.tuner_window = TunerWidget()
        tuner_layout.addWidget(self.tuner_window, 1)
        
        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(posture_container)
        splitter.addWidget(tuner_container)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        
        layout.addWidget(splitter)

#######################################
# Tab 2: Sheet Music with Small Posture
#######################################
class SheetMusicTab(QWidget):
    def __init__(self, camera_service, parent=None):
        super().__init__(parent)
        self.sheet_music_widget = None
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        if SHEET_MUSIC_AVAILABLE:
            try:
                self.sheet_music_widget = SheetMusicWidget(camera_service)
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

        # Create shared posture widget
        self.camera_service = CameraService(self)

        # Create tab widget
        self.tab_widget = QTabWidget()
        
        # Tab 1: Posture + Tuner
        self.main_tab = MainTab(self.camera_service)
        self.tab_widget.addTab(self.main_tab, "Posture && Tuner")
        
        # Tab 2: Sheet Music
        self.sheet_tab = SheetMusicTab(self.camera_service)
        self.tab_widget.addTab(self.sheet_tab, "Sheet Music")

        layout.addWidget(self.tab_widget)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.camera_service.start()

    def _on_tab_changed(self, index):
        if self.tab_widget.widget(index) is not self.main_tab:
            self.main_tab.tuner_window.toggle_button.setChecked(False)

    def closeEvent(self, event):
        for shutdown in (self.main_tab.tuner_window.shutdown, self.sheet_tab.shutdown,
                         self.camera_service.stop):
            try:
                shutdown()
            except Exception as e:
                print(f"Shutdown error: {e}")
        event.accept()

#######################################
# Main Execution
#######################################
def apply_light_theme(app):
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    app.setStyle("Fusion")
    palette = QPalette(QColor("#ecf0f1"), QColor("#f5f6fa"))
    for role, color in [
        (QPalette.WindowText, "#2c3e50"), (QPalette.Text, "#2c3e50"), (QPalette.ButtonText, "#2c3e50"),
        (QPalette.Base, "#ffffff"), (QPalette.AlternateBase, "#f0f2f5"),
        (QPalette.ToolTipBase, "#ffffff"), (QPalette.ToolTipText, "#2c3e50"),
        (QPalette.PlaceholderText, "#95a5a6"), (QPalette.Highlight, "#3498db"),
        (QPalette.HighlightedText, "#ffffff"), (QPalette.Link, "#2980b9"),
    ]:
        palette.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor("#a4aeb8"))
    app.setPalette(palette)

def main():
    app = QApplication(sys.argv)
    apply_light_theme(app)
    window = TabbedFluteTutor()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
