import sys, os
import shutil
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QToolButton,
    QApplication, QComboBox, QDialog, QLineEdit, QFormLayout,
    QFileDialog, QDialogButtonBox, QMessageBox, QScrollArea, QListWidget,
    QListWidgetItem, QSplitter, QFrame
)
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import Qt, QTimer, QSize
import tempfile

# Handle PyMuPDF import with fallback
try:
    import pymupdf as pdf_lib  # PyMuPDF for rendering PDFs
    PDF_AVAILABLE = True
except ImportError:
    try:
        import fitz as pdf_lib  # Fallback to old name
        PDF_AVAILABLE = True
    except ImportError:
        pdf_lib = None
        PDF_AVAILABLE = False
        print("PyMuPDF not available - PDF viewing disabled")

from database.sheet_music_db import SheetMusicDatabase
from practice_panel import PracticePanel
from camera_service import VideoView

# Data container for sheet music metadata
class SheetMusicData:
    def __init__(self, title, pdf_path, tempo, time_signature, level, key_signature, audio_path):
        self.title = title
        self.pdf_path = pdf_path
        self.tempo = tempo
        self.time_signature = time_signature
        self.level = level
        self.key_signature = key_signature
        self.audio_path = audio_path

def pdf_to_pixmaps(pdf_path, zoom=1.0):
    """
    Render every page of the PDF as a list of QPixmaps.
    """
    if not PDF_AVAILABLE:
        return []
    pixmaps = []
    with pdf_lib.open(pdf_path) as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=pdf_lib.Matrix(zoom, zoom), alpha=False)
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            pixmaps.append(QPixmap.fromImage(image.copy()))
    return pixmaps

# Dialog to import new sheet music details
class ImportSheetMusicDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Sheet Music")
        self.setMinimumWidth(400)
        self.sheet_data = None  # Will hold the created SheetMusicData
        
        # Title (free text)
        self.title_edit = QLineEdit()
        
        # For the other details we use combo boxes with preset options.
        self.tempo_combo = QComboBox()
        self.tempo_combo.addItems(["60 BPM", "80 BPM", "100 BPM", "120 BPM", "140 BPM", "160 BPM"])
        
        self.time_signature_combo = QComboBox()
        self.time_signature_combo.addItems(["4/4", "3/4", "6/8"])
        
        self.level_combo = QComboBox()
        self.level_combo.addItems(["Beginner", "Intermediate", "Advanced"])
        
        self.key_signature_combo = QComboBox()
        self.key_signature_combo.addItems(["C Major", "G Major", "D Major", "A Major", "E Major", "F Major", "Bb Major", "Eb Major"])
        
        # PDF file selection for sheet music
        self.pdf_path_edit = QLineEdit()
        self.pdf_browse_button = QPushButton("Browse...")
        self.pdf_browse_button.clicked.connect(self.browse_pdf)
        
        # Reference audio file selection
        self.audio_path_edit = QLineEdit()
        self.audio_browse_button = QPushButton("Browse...")
        self.audio_browse_button.clicked.connect(self.browse_audio)
        
        # Build the form layout
        form_layout = QFormLayout()
        form_layout.addRow("Title:", self.title_edit)
        form_layout.addRow("Tempo:", self.tempo_combo)
        form_layout.addRow("Time Signature:", self.time_signature_combo)
        form_layout.addRow("Level:", self.level_combo)
        form_layout.addRow("Key Signature:", self.key_signature_combo)
        
        pdf_layout = QHBoxLayout()
        pdf_layout.addWidget(self.pdf_path_edit)
        pdf_layout.addWidget(self.pdf_browse_button)
        form_layout.addRow("PDF File:", pdf_layout)
        
        audio_layout = QHBoxLayout()
        audio_layout.addWidget(self.audio_path_edit)
        audio_layout.addWidget(self.audio_browse_button)
        form_layout.addRow("Audio File:", audio_layout)
        
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.validate_and_accept)
        self.button_box.rejected.connect(self.reject)
        
        main_layout = QVBoxLayout(self)
        main_layout.addLayout(form_layout)
        main_layout.addWidget(self.button_box)
    
    def browse_pdf(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Select Sheet Music PDF", "", "PDF Files (*.pdf)")
        if filename:
            self.pdf_path_edit.setText(filename)
    
    def browse_audio(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Select Reference Audio", "", "Audio Files (*.wav *.mp3 *.flac *.ogg)")
        if filename:
            self.audio_path_edit.setText(filename)
    
    def validate_and_accept(self):
        if (self.title_edit.text().strip() and self.pdf_path_edit.text().strip() and self.audio_path_edit.text().strip()):
            self.sheet_data = SheetMusicData(
                title=self.title_edit.text().strip(),
                pdf_path=self.pdf_path_edit.text().strip(),
                tempo=self.tempo_combo.currentText(),
                time_signature=self.time_signature_combo.currentText(),
                level=self.level_combo.currentText(),
                key_signature=self.key_signature_combo.currentText(),
                audio_path=self.audio_path_edit.text().strip()
            )
            self.accept()
        else:
            QMessageBox.warning(self, "Missing information",
                                "Please provide a title, a PDF file and a reference audio file.")

class SheetMusicListItem(QWidget):
    LEVEL_COLORS = {"Beginner": "#27ae60", "Intermediate": "#f39c12", "Advanced": "#e74c3c"}

    def __init__(self, sheet_data, stats=None, parent=None):
        super().__init__(parent)
        self.sheet_data = sheet_data

        title_label = QLabel(sheet_data.title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet("font-size:13px; font-weight:bold; color:#2c3e50;")
        level_label = QLabel(sheet_data.level)
        level_label.setStyleSheet(
            f"background:{self.LEVEL_COLORS.get(sheet_data.level, '#95a5a6')}; color:white;"
            "border-radius:4px; padding:1px 6px; font-size:10px;")
        meta_label = QLabel(f"{sheet_data.tempo} • {sheet_data.time_signature} • {sheet_data.key_signature}")
        meta_label.setWordWrap(True)
        meta_label.setStyleSheet("font-size:11px; color:#7f8c8d;")
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("font-size:11px; color:#2980b9;")

        top_row = QHBoxLayout()
        top_row.addWidget(title_label, 1)
        top_row.addWidget(level_label, 0, Qt.AlignTop)
        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.addLayout(top_row)
        layout.addWidget(meta_label)
        layout.addWidget(self.stats_label)
        self.set_stats(stats)

    def set_stats(self, stats):
        if stats and stats.get("sessions"):
            self.stats_label.setText(f"Best {stats['best_accuracy']:.0f}% • {stats['sessions']} sessions")
        else:
            self.stats_label.setText("Not practiced yet")

class SheetMusicWidget(QWidget):
    def __init__(self, camera_service=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sheet Music Practice")
        self.resize(1300, 800)
        self.scale_factor = 1.0
        self.min_scale_factor = 0.5
        self.max_scale_factor = 3.0
        self.camera_service = camera_service
        
        # Initialize database
        self.db = SheetMusicDatabase()
        
        self.sheet_music_list = []
        self.current_sheet = None
        self.page_pixmaps = []
        self.page_labels = []
        
        # Create temporary directory for extracted files
        self.temp_dir = tempfile.mkdtemp()
        self._resize_timer = QTimer(self, singleShot=True, interval=60, timeout=self.update_display)
        
        # Initialize UI components
        self._init_ui()
        
        # Load existing sheet music from database
        self.load_from_database()
        
        # If there are any sheet music entries, select the first one
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
    
    def _init_ui(self):
        """Initialize all UI components."""
        self.setStyleSheet("""
            QPushButton, QToolButton { background:#ffffff; color:#2c3e50; border:1px solid #cfd6dd;
                                       border-radius:6px; padding:6px 12px; font-weight:bold; }
            QPushButton:hover, QToolButton:hover { background:#eef2f5; }
            QPushButton:disabled { background:#f4f6f8; color:#a4aeb8; }
            QLabel#section { font-size:15px; font-weight:bold; color:#2c3e50; }
        """)

        left_panel = QWidget()
        left_panel.setMinimumWidth(220)
        left_panel.setMaximumWidth(340)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        header_row = QHBoxLayout()
        library_label = QLabel("Library")
        library_label.setObjectName("section")
        import_button = QPushButton("+ Import")
        import_button.clicked.connect(self.import_sheet_music)
        header_row.addWidget(library_label)
        header_row.addStretch()
        header_row.addWidget(import_button)
        left_layout.addLayout(header_row)
        
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget { background:#ffffff; border:1px solid #dcdde1; border-radius:6px; }
            QListWidget::item { border-bottom:1px solid #e1e4e8; }
            QListWidget::item:selected { background:#d6eaf8; border-left:4px solid #3498db; }
        """)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.currentRowChanged.connect(self.on_sheet_selected)
        left_layout.addWidget(self.list_widget, 1)
        self.delete_button = QPushButton("Remove selected")
        self.delete_button.clicked.connect(self.delete_selected)
        left_layout.addWidget(self.delete_button)

        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(8, 8, 8, 8)
        toolbar = QHBoxLayout()
        self.title_label = QLabel("No sheet music selected")
        self.title_label.setObjectName("section")
        self.title_label.setWordWrap(True)
        zoom_out_button = QToolButton(text="−")
        zoom_out_button.clicked.connect(self.zoom_out)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(44)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        zoom_in_button = QToolButton(text="+")
        zoom_in_button.clicked.connect(self.zoom_in)
        fit_button = QPushButton("Fit width")
        fit_button.clicked.connect(self.reset_zoom)
        toolbar.addWidget(self.title_label, 1)
        for widget in (zoom_out_button, self.zoom_label, zoom_in_button, fit_button):
            toolbar.addWidget(widget)
        center_layout.addLayout(toolbar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background:#e5e8eb; border:none; border-radius:6px; }")
        self.pages_widget = QWidget()
        self.pages_widget.setStyleSheet("background:#e5e8eb;")
        self.pages_layout = QVBoxLayout(self.pages_widget)
        self.pages_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.pages_layout.setSpacing(12)
        self.placeholder = QLabel("Import or select a piece from the library")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet("color:#7f8c8d; font-size:14px; padding:40px;")
        self.pages_layout.addWidget(self.placeholder)
        self.scroll_area.setWidget(self.pages_widget)
        center_layout.addWidget(self.scroll_area, 1)

        right_content = QWidget()
        right_layout = QVBoxLayout(right_content)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(8)
        if self.camera_service is not None:
            posture_label = QLabel("Posture")
            posture_label.setObjectName("section")
            right_layout.addWidget(posture_label)
            self.video_view = VideoView(self.camera_service)
            self.video_view.setFixedHeight(290)
            right_layout.addWidget(self.video_view)
        practice_label = QLabel("Practice")
        practice_label.setObjectName("section")
        right_layout.addWidget(practice_label)
        self.practice_panel = PracticePanel(self.db)
        self.practice_panel.session_saved.connect(self._on_session_saved)
        right_layout.addWidget(self.practice_panel, 1)
        right_panel = QScrollArea()
        right_panel.setWidgetResizable(True)
        right_panel.setFrameShape(QFrame.NoFrame)
        right_panel.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_panel.setWidget(right_content)
        right_panel.setMinimumWidth(360)
        right_panel.setMaximumWidth(440)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(left_panel)
        self.splitter.addWidget(center_panel)
        self.splitter.addWidget(right_panel)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([250, 800, 380])
        self.splitter.splitterMoved.connect(self._resize_timer.start)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)
    
    def import_sheet_music(self):
        """Import new sheet music into the database."""
        dialog = ImportSheetMusicDialog(self)
        if dialog.exec() == QDialog.Accepted:
            sheet_data = dialog.sheet_data
            try:
                # Add to database
                sheet_id = self.db.add_sheet_music(
                    title=sheet_data.title,
                    tempo=sheet_data.tempo,
                    time_signature=sheet_data.time_signature,
                    level=sheet_data.level,
                    key_signature=sheet_data.key_signature,
                    pdf_path=sheet_data.pdf_path,
                    audio_path=sheet_data.audio_path
                )
                
                if sheet_id:
                    # Add to list
                    sheet_data.db_id = sheet_id
                    self.sheet_music_list.append(sheet_data)
                    self._add_list_item(sheet_data)
                    self.list_widget.setCurrentRow(self.list_widget.count() - 1)
                else:
                    QMessageBox.warning(self, "Error", "Failed to import sheet music.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error importing sheet music: {str(e)}")
    
    def load_from_database(self):
        """Load sheet music from database."""
        try:
            sheets = self.db.get_all_sheet_music()
            for sheet in sheets:
                sheet_id, title, tempo, time_signature, level, key_signature, created_at = sheet
                sheet_data = SheetMusicData(
                    title=title,
                    pdf_path="",  # Will be loaded on demand
                    tempo=tempo,
                    time_signature=time_signature,
                    level=level,
                    key_signature=key_signature,
                    audio_path=""  # Will be loaded on demand
                )
                sheet_data.db_id = sheet_id
                self.sheet_music_list.append(sheet_data)
                self._add_list_item(sheet_data)
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Error loading from database: {str(e)}")
    
    def on_sheet_selected(self, row):
        """Handle sheet music selection."""
        if row < 0 or row >= len(self.sheet_music_list):
            return
        
        sheet_data = self.sheet_music_list[row]
        self.current_sheet = sheet_data
        
        # Export files from database
        pdf_path = os.path.join(self.temp_dir, f"sheet_{sheet_data.db_id}.pdf")
        audio_path = os.path.join(self.temp_dir, f"audio_{sheet_data.db_id}.wav")
        
        if self.db.export_sheet_music_files(sheet_data.db_id, pdf_path, audio_path):
            sheet_data.pdf_path = pdf_path
            sheet_data.audio_path = audio_path
            
            # Display PDF
            try:
                self.page_pixmaps = pdf_to_pixmaps(pdf_path, zoom=2.0)
            except Exception as e:
                print(f"Error rendering PDF: {e}")
                self.page_pixmaps = []
            self.title_label.setText(f"{sheet_data.title}   ·   {sheet_data.tempo} · "
                                     f"{sheet_data.time_signature} · {sheet_data.key_signature}")
            self._build_pages()
            
            # Load audio
            self.practice_panel.set_sheet(sheet_data)
        else:
            QMessageBox.warning(self, "Error", "Failed to load sheet music files.")
    
    def _add_list_item(self, sheet_data):
        item = QListWidgetItem()
        item_widget = SheetMusicListItem(sheet_data, self.db.get_practice_stats(sheet_data.db_id))
        item.setSizeHint(QSize(0, item_widget.sizeHint().height()))
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, item_widget)

    def delete_selected(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        sheet_data = self.sheet_music_list[row]
        answer = QMessageBox.question(self, "Remove sheet music",
                                      f"Remove '{sheet_data.title}' and its practice history?")
        if answer != QMessageBox.Yes:
            return
        self.practice_panel.clear_sheet()
        self.db.delete_sheet_music(sheet_data.db_id)
        self.sheet_music_list.pop(row)
        self.list_widget.takeItem(row)
        if not self.sheet_music_list:
            self.current_sheet = None
            self.page_pixmaps = []
            self.title_label.setText("No sheet music selected")
            self._build_pages()

    def _on_session_saved(self, sheet_id):
        stats = self.db.get_practice_stats(sheet_id)
        for row, sheet_data in enumerate(self.sheet_music_list):
            if sheet_data.db_id == sheet_id:
                widget = self.list_widget.itemWidget(self.list_widget.item(row))
                if widget:
                    widget.set_stats(stats)

    def _build_pages(self):
        for label in self.page_labels:
            label.deleteLater()
        self.page_labels = []
        self.placeholder.setVisible(not self.page_pixmaps)
        if not self.current_sheet:
            self.placeholder.setText("Import or select a piece from the library")
        elif not self.page_pixmaps:
            self.placeholder.setText("Could not render this PDF" if PDF_AVAILABLE
                                     else "Install PyMuPDF (pip install pymupdf) to view PDFs")
        for _ in self.page_pixmaps:
            label = QLabel()
            label.setStyleSheet("background:white; border:1px solid #d0d4d9;")
            self.pages_layout.addWidget(label)
            self.page_labels.append(label)
        self.update_display()

    def update_display(self):
        """Update the sheet music display."""
        self.zoom_label.setText(f"{self.scale_factor * 100:.0f}%")
        width = int(max(200, self.scroll_area.viewport().width() - 32) * self.scale_factor)
        for label, pixmap in zip(self.page_labels, self.page_pixmaps):
            label.setPixmap(pixmap.scaledToWidth(width, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.page_pixmaps:
            self._resize_timer.start()
    
    def zoom_in(self):
        if self.scale_factor < self.max_scale_factor:
            self.scale_factor += 0.2
            self.update_display()
    
    def zoom_out(self):
        if self.scale_factor > self.min_scale_factor:
            self.scale_factor -= 0.2
            self.update_display()
    
    def reset_zoom(self):
        self.scale_factor = 1.0
        self.update_display()
    
    def shutdown(self):
        self.practice_panel.shutdown()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def closeEvent(self, event):
        """Clean up temporary files."""
        self.shutdown()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SheetMusicWidget()
    window.show()
    sys.exit(app.exec())
