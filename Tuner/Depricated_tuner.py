import sys, math, os, sqlite3
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QToolBar, QLineEdit, QSlider, QProgressBar, QSizePolicy,
    QListWidget, QListWidgetItem, QFileDialog, QTabWidget, QFrame, QSpinBox, QDialog, QScrollArea,
    QGroupBox, QTableWidget, QHeaderView, QMessageBox, QComboBox, QGridLayout
)
from PySide6.QtGui import QFont, QIcon, QAction, QPixmap
from PySide6.QtCore import Qt, QSize, QTimer, QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
import pyqtgraph as pg
from tuner_engine import TunerEngine
import sounddevice as sd
import soundfile as sf
import numpy as np
from scipy import signal
import librosa
from datetime import datetime
import time
import cv2
from PySide6.QtGui import QImage

class MusicPiece:
    def __init__(self, name, sheet_path, reference_audio_path=None, tempo=120, piece_id=None):
        self.id = piece_id
        self.name = name
        self.sheet_path = sheet_path
        self.reference_audio_path = reference_audio_path
        self.tempo = tempo
        self.recording_path = None
        self.accuracy_score = 0
        self.completion_percentage = 0
        self.practice_count = 0
        self.best_accuracy = 0
        self.total_practice_time = 0
        self.difficulty_level = None
        self.key_signature = None
        self.time_signature = None
        self.streak_count = 0
        self.longest_streak = 0
        self.average_session_duration = 0

class DatabaseManager:
    def __init__(self):
        self.conn = sqlite3.connect('flute_tuner2.db')
        self.create_tables()
        print("Database connected and tables created.")
    
    def create_tables(self):
        cursor = self.conn.cursor()
        try:
            # Create pieces table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS pieces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sheet_data BLOB NOT NULL,
                reference_audio_data BLOB,
                sheet_filename TEXT NOT NULL,
                reference_audio_filename TEXT,
                tempo INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                difficulty_level TEXT CHECK(difficulty_level IN ('Beginner', 'Intermediate', 'Advanced')),
                key_signature TEXT,
                time_signature TEXT
            )

            ''')
            
            # Create recordings table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                piece_id INTEGER,
                recording_path TEXT NOT NULL,
                accuracy_score REAL,
                completion_percentage REAL,
                pitch_accuracy REAL,
                rhythm_accuracy REAL,
                practice_duration REAL,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes_played INTEGER,
                notes_correct INTEGER,
                FOREIGN KEY (piece_id) REFERENCES pieces (id)
            )
            ''')
            
            # Create practice_stats table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS practice_stats (
                piece_id INTEGER PRIMARY KEY,
                practice_count INTEGER DEFAULT 0,
                best_accuracy REAL DEFAULT 0,
                total_practice_time REAL DEFAULT 0,
                last_practiced TIMESTAMP,
                streak_count INTEGER DEFAULT 0,
                longest_streak INTEGER DEFAULT 0,
                average_session_duration REAL DEFAULT 0,
                FOREIGN KEY (piece_id) REFERENCES pieces (id)
            )
            ''')
            
            # Create practice_sessions table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS practice_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                piece_id INTEGER,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                duration REAL,
                accuracy_score REAL,
                notes_played INTEGER,
                notes_correct INTEGER,
                FOREIGN KEY (piece_id) REFERENCES pieces (id)
            )
            ''')
            
            self.conn.commit()
            print("Tables created successfully.")
        except sqlite3.Error as e:
            print(f"Error creating tables: {e}")
    
    def add_piece(self, name, sheet_path, reference_audio_path, tempo, difficulty_level=None, key_signature=None, time_signature=None):
        cursor = self.conn.cursor()
        try:
            # Read binary data
            with open(sheet_path, 'rb') as file:
                sheet_data = file.read()
            sheet_filename = os.path.basename(sheet_path)

            reference_audio_data = None
            reference_audio_filename = None
            if reference_audio_path:
                with open(reference_audio_path, 'rb') as file:
                    reference_audio_data = file.read()
                reference_audio_filename = os.path.basename(reference_audio_path)

            cursor.execute('''
            INSERT INTO pieces (name, sheet_data, reference_audio_data, sheet_filename, reference_audio_filename, tempo, difficulty_level, key_signature, time_signature)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (name, sheet_data, reference_audio_data, sheet_filename, reference_audio_filename, tempo, difficulty_level, key_signature, time_signature))
            self.conn.commit()
            print(f"Piece '{name}' added to database.")
            return cursor.lastrowid
        except sqlite3.Error as e:
            print(f"Error adding piece: {e}")
            self.conn.rollback()
            return None

    def get_sheet_music_file(self, piece_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT sheet_data, sheet_filename FROM pieces WHERE id=?', (piece_id,))
        result = cursor.fetchone()
        if result:
            sheet_data, sheet_filename = result
            temp_path = os.path.join("temp_sheets", sheet_filename)
            os.makedirs("temp_sheets", exist_ok=True)
            with open(temp_path, 'wb') as file:
                file.write(sheet_data)
            return temp_path
        return None
    
    def get_reference_audio_file(self, piece_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT reference_audio_data, reference_audio_filename FROM pieces WHERE id=?', (piece_id,))
        result = cursor.fetchone()
        if result and result[0]:
            audio_data, audio_filename = result
            temp_path = os.path.join("temp_audio", audio_filename)
            os.makedirs("temp_audio", exist_ok=True)
            with open(temp_path, 'wb') as file:
                file.write(audio_data)
            return temp_path
        return None


    def add_recording(self, piece_id, recording_path, accuracy_score, completion_percentage,
                     pitch_accuracy, rhythm_accuracy, practice_duration, notes_played, notes_correct):
        cursor = self.conn.cursor()
        try:
            # Add recording
            cursor.execute('''
            INSERT INTO recordings (piece_id, recording_path, accuracy_score, completion_percentage,
                                  pitch_accuracy, rhythm_accuracy, practice_duration, notes_played, notes_correct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (piece_id, recording_path, accuracy_score, completion_percentage,
                  pitch_accuracy, rhythm_accuracy, practice_duration, notes_played, notes_correct))
            
            # Update practice stats - now only updating total time and best accuracy
            cursor.execute('''
            INSERT OR REPLACE INTO practice_stats 
            (piece_id, practice_count, best_accuracy, total_practice_time, last_practiced)
            VALUES (
                ?,
                COALESCE((SELECT practice_count FROM practice_stats WHERE piece_id = ?), 0),
                MAX(COALESCE((SELECT best_accuracy FROM practice_stats WHERE piece_id = ?), 0),
                COALESCE((SELECT total_practice_time FROM practice_stats WHERE piece_id = ?), 0) + ?,
                CURRENT_TIMESTAMP
            )
            ''', (piece_id, piece_id, piece_id, accuracy_score, piece_id, practice_duration))
            
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error adding recording: {e}")
            self.conn.rollback()
            return False
    
    def get_pieces(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                SELECT 
                p.id, 
                p.name, 
                p.sheet_filename, 
                p.reference_audio_filename, 
                p.tempo, 
                p.created_at, 
                p.difficulty_level, 
                p.key_signature, 
                p.time_signature,
                ps.practice_count, 
                ps.best_accuracy, 
                ps.total_practice_time,
                ps.streak_count, 
                ps.longest_streak, 
                ps.average_session_duration
                FROM pieces p
                LEFT JOIN practice_stats ps ON p.id = ps.piece_id
            ''')
            pieces = cursor.fetchall()
            print(f"Loaded {len(pieces)} pieces from database.")
            return pieces
        except sqlite3.Error as e:
            print(f"Error getting pieces: {e}")
            return []

    
    def get_piece_recordings(self, piece_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
            SELECT * FROM recordings
            WHERE piece_id = ?
            ORDER BY recorded_at DESC
            ''', (piece_id,))
            return cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error getting recordings: {e}")
            return []
    
    def format_timestamp(self, timestamp):
        if not timestamp:
            return "Never"
        try:
            dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            now = datetime.now()
            diff = now - dt
            
            if diff.days == 0:
                if diff.seconds < 3600:
                    minutes = diff.seconds // 60
                    return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
                else:
                    hours = diff.seconds // 3600
                    return f"{hours} hour{'s' if hours != 1 else ''} ago"
            elif diff.days < 7:
                return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
            elif diff.days < 30:
                weeks = diff.days // 7
                return f"{weeks} week{'s' if weeks != 1 else ''} ago"
            else:
                return dt.strftime('%b %d, %Y')
        except:
            return "Invalid date"
    
    def close(self):
        try:
            self.conn.close()
        except sqlite3.Error as e:
            print(f"Error closing database: {e}")

    def increment_practice_count(self, piece_id):
        """Increment the practice count when a piece is selected"""
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
            INSERT OR REPLACE INTO practice_stats 
            (piece_id, practice_count, best_accuracy, total_practice_time, last_practiced)
            VALUES (
                ?,
                COALESCE((SELECT practice_count FROM practice_stats WHERE piece_id = ?), 0) + 1,
                COALESCE((SELECT best_accuracy FROM practice_stats WHERE piece_id = ?), 0),
                COALESCE((SELECT total_practice_time FROM practice_stats WHERE piece_id = ?), 0),
                CURRENT_TIMESTAMP
            )
            ''', (piece_id, piece_id, piece_id, piece_id))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error incrementing practice count: {e}")
            self.conn.rollback()
            return False

class ImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Sheet Music")
        self.setMinimumWidth(400)
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f6fa;
            }
            QLabel {
                color: #2c3e50;
                font-size: 13px;
            }
            QLineEdit, QComboBox, QSpinBox {
                background-color: white;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                padding: 4px;
                color: #2c3e50;
                selection-background-color: #3498db;
                selection-color: white;
                font-size: 13px;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 6px 12px;
                border-radius: 4px;
                border: none;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QGroupBox {
                background-color: white;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                margin-top: 8px;
                padding: 6px;
                font-size: 13px;
            }
            QGroupBox::title {
                color: #2c3e50;
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                font-size: 13px;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # Sheet Music File Selection
        sheet_layout = QHBoxLayout()
        self.sheet_path = QLineEdit()
        self.sheet_path.setPlaceholderText("Select sheet music file...")
        sheet_btn = QPushButton("Browse")
        sheet_btn.clicked.connect(self.browse_sheet)
        sheet_layout.addWidget(self.sheet_path)
        sheet_layout.addWidget(sheet_btn)
        layout.addLayout(sheet_layout)
        
        # Reference Audio Selection
        audio_layout = QHBoxLayout()
        self.audio_path = QLineEdit()
        self.audio_path.setPlaceholderText("Select reference audio file (optional)...")
        audio_btn = QPushButton("Browse")
        audio_btn.clicked.connect(self.browse_audio)
        audio_layout.addWidget(self.audio_path)
        audio_layout.addWidget(audio_btn)
        layout.addLayout(audio_layout)
        
        # Piece Details Group
        details_group = QGroupBox("Piece Details")
        details_layout = QVBoxLayout()
        
        # Tempo Input
        tempo_layout = QHBoxLayout()
        tempo_layout.addWidget(QLabel("Tempo (BPM):"))
        self.tempo_input = QSpinBox()
        self.tempo_input.setRange(40, 208)
        self.tempo_input.setValue(120)
        tempo_layout.addWidget(self.tempo_input)
        details_layout.addLayout(tempo_layout)
        
        # Difficulty Level
        difficulty_layout = QHBoxLayout()
        difficulty_layout.addWidget(QLabel("Difficulty:"))
        self.difficulty_input = QComboBox()
        self.difficulty_input.addItems(['Beginner', 'Intermediate', 'Advanced'])
        difficulty_layout.addWidget(self.difficulty_input)
        details_layout.addLayout(difficulty_layout)
        
        # Key Signature
        key_layout = QHBoxLayout()
        key_layout.addWidget(QLabel("Key Signature:"))
        self.key_input = QComboBox()
        self.key_input.addItems(['C', 'G', 'D', 'A', 'E', 'B', 'F#', 'C#', 'F', 'Bb', 'Eb', 'Ab', 'Db', 'Gb', 'Cb'])
        key_layout.addWidget(self.key_input)
        details_layout.addLayout(key_layout)
        
        # Time Signature
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Time Signature:"))
        self.time_input = QComboBox()
        self.time_input.addItems(['4/4', '3/4', '6/8', '2/4', '3/8', '9/8', '12/8'])
        time_layout.addWidget(self.time_input)
        details_layout.addLayout(time_layout)
        
        details_group.setLayout(details_layout)
        layout.addWidget(details_group)
        
        # Buttons
        buttons = QHBoxLayout()
        ok_button = QPushButton("Import")
        ok_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(ok_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)

    
    def browse_sheet(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select Sheet Music", "",
            "Sheet Music Files (*.pdf *.png *.jpg)"
        )
        if file_name:
            self.sheet_path.setText(file_name)
    
    def browse_audio(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select Reference Audio", "",
            "Audio Files (*.wav)"
        )
        if file_name:
            self.audio_path.setText(file_name)

class SheetMusicWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sheet Music Practice")
        self.setMinimumSize(1000, 600)
        self.setStyleSheet("background-color: white;")  # Set main window background to white

        # Initialize database connection
        self.db = DatabaseManager()
        
        # Store music pieces
        self.music_pieces = {}
        self.current_piece = None
        self.recording = False
        # Use QSoundEffect instead of QMediaPlayer since multimedia backend support is limited
        from PySide6.QtMultimedia import QSoundEffect
        self.audio_player = QSoundEffect()
        self.audio_player.setVolume(1.0)
        self.is_playing_reference = False
        self.is_playing_recording = False
        
        # Create central widget and main layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setSpacing(10)
        
        # Create scrollable left panel for piece selection
        left_panel = QScrollArea()
        left_panel.setWidgetResizable(True)
        left_panel.setMinimumWidth(350)  # Increase minimum width
        left_panel.setMaximumWidth(450)  # Increase maximum width
        
        left_content = QWidget()
        self.left_layout = QVBoxLayout(left_content)
        self.left_layout.setSpacing(10)
        self.left_layout.setContentsMargins(10, 10, 10, 10)
        
        # Title for piece library (removed inline comment from stylesheet)
        title_layout = QHBoxLayout()
        library_label = QLabel("Sheet Music Library")
        library_label.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #2c3e50;
        """)
        title_layout.addWidget(library_label)
        title_layout.addStretch()
        self.left_layout.addLayout(title_layout)
        
        # Create scrollable list for pieces
        self.pieces_container = QWidget()
        self.pieces_layout = QVBoxLayout(self.pieces_container)
        self.pieces_layout.setSpacing(8)
        self.pieces_layout.setAlignment(Qt.AlignTop)
        self.left_layout.addWidget(self.pieces_container)
        
        # Import button at the bottom
        import_btn = QPushButton("Import Sheet Music")
        import_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 12px;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        import_btn.clicked.connect(self.show_import_dialog)
        self.left_layout.addWidget(import_btn)
        
        left_panel.setWidget(left_content)
        main_layout.addWidget(left_panel)
        
        # Right panel (sheet music display and controls)
        right_panel = QTabWidget()
        right_panel.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #bdc3c7;
                background: white;
                border-radius: 5px;
            }
            QTabBar::tab {
                background: #ecf0f1;
                color: #2c3e50;
                padding: 8px 16px;
                border: 1px solid #bdc3c7;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: white;
                border-bottom: none;
            }
        """)
        
        # Sheet Music Display Tab
        sheet_display = QWidget()
        sheet_layout = QVBoxLayout(sheet_display)
        
        # Add zoom controls
        zoom_layout = QHBoxLayout()
        self.zoom_in_btn = QPushButton("Zoom In")
        self.zoom_out_btn = QPushButton("Zoom Out")
        self.zoom_fit_btn = QPushButton("Fit to Window")
        for btn in [self.zoom_in_btn, self.zoom_out_btn, self.zoom_fit_btn]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2c3e50;
                    color: white;
                    padding: 6px 12px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #34495e;
                }
            """)
        self.zoom_in_btn.clicked.connect(lambda: self.zoom_sheet_music(1.1))
        self.zoom_out_btn.clicked.connect(lambda: self.zoom_sheet_music(0.9))
        self.zoom_fit_btn.clicked.connect(self.fit_sheet_music)
        zoom_layout.addWidget(self.zoom_in_btn)
        zoom_layout.addWidget(self.zoom_out_btn)
        zoom_layout.addWidget(self.zoom_fit_btn)
        zoom_layout.addStretch()
        sheet_layout.addLayout(zoom_layout)
        
        # Sheet music scroll area
        self.sheet_scroll = QScrollArea()
        self.sheet_scroll.setWidgetResizable(True)
        self.sheet_scroll.setStyleSheet("""
            QScrollArea {
                background-color: #f5f6fa;
                border: 1px solid #dcdde1;
                border-radius: 4px;
            }
        """)
        
        self.sheet_display_label = QLabel("Select a piece to display sheet music")
        self.sheet_display_label.setStyleSheet("""
            QLabel {
                color: #7f8c8d;
                font-size: 16px;
            }
        """)
        self.sheet_display_label.setAlignment(Qt.AlignCenter)
        self.sheet_scroll.setWidget(self.sheet_display_label)
        sheet_layout.addWidget(self.sheet_scroll)
        
        # Practice Controls
        controls = QHBoxLayout()
        self.record_btn = QPushButton("Record")
        self.record_btn.setEnabled(False)
        self.record_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 10px 20px;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        self.record_btn.clicked.connect(self.toggle_recording)
        
        self.play_ref_btn = QPushButton("Play Reference")
        self.play_ref_btn.setEnabled(False)
        self.play_ref_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 10px 20px;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        self.play_ref_btn.clicked.connect(self.toggle_reference)
        
        controls.addWidget(self.record_btn)
        controls.addWidget(self.play_ref_btn)
        sheet_layout.addLayout(controls)
        
        right_panel.addTab(sheet_display, "Sheet Music")
        main_layout.addWidget(right_panel, stretch=2)
        
        # Initialize recording variables
        self.init_recording_variables()
        self.current_zoom = 1.0  # Initialize zoom factor
        
        # Load existing pieces from database
        self.load_pieces_from_db()


    def init_recording_variables(self):
        self.fs = 44100  # Sample rate
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.update_countdown)
        self.countdown = 4  # 4 beats countdown
        self.recording_start_time = 0
        self.recorded_audio = []
        self.stream = None
        self.should_stop_recording = False
        self.is_recording = False  # New flag to track recording state

    def load_pieces_from_db(self):
        pieces = self.db.get_pieces()
        # Sort pieces by difficulty level
        difficulty_order = {'Beginner': 0, 'Intermediate': 1, 'Advanced': 2}
        sorted_pieces = sorted(pieces, key=lambda x: difficulty_order.get(x[6], 3))
        
        # Clear existing items in the layout
        while self.pieces_layout.count() > 0:
            item = self.pieces_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        
        for piece in sorted_pieces:
            (piece_id, name, sheet_filename, ref_audio_filename, tempo, created_at, 
            difficulty, key_sig, time_sig, practice_count, best_accuracy, 
            total_time, streak_count, longest_streak, avg_duration) = piece
            print(f"Loading piece: {name}, {sheet_filename}, {difficulty}, {key_sig}, {time_sig}, {tempo}")
            piece_obj = MusicPiece(name, sheet_filename, ref_audio_filename, tempo, piece_id)
            piece_obj.difficulty_level = difficulty
            piece_obj.key_signature = key_sig
            piece_obj.time_signature = time_sig
            piece_obj.practice_count = practice_count or 0
            piece_obj.best_accuracy = best_accuracy or 0
            piece_obj.total_practice_time = total_time or 0
            piece_obj.streak_count = streak_count or 0
            piece_obj.longest_streak = longest_streak or 0
            piece_obj.average_session_duration = avg_duration or 0
            self.music_pieces[name] = piece_obj
            self.create_piece_list_item(piece_obj)
        
        print("Pieces loaded into the UI.")


    def create_piece_list_item(self, piece):
        # Create container widget for the piece
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #dcdde1;
                border-radius: 6px;
                margin: 3px;
            }
            QFrame:hover {
                border-color: #3498db;
            }
        """)

        layout = QVBoxLayout(container)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)

        # Top row: Title and difficulty badge
        top_row = QHBoxLayout()

        name_label = QLabel(piece.name)
        name_label.setStyleSheet("""
            font-size: 14px;
            font-weight: bold;
            color: #2c3e50;
        """)
        top_row.addWidget(name_label)

        difficulty_colors = {
            'Beginner': '#27ae60',
            'Intermediate': '#f39c12',
            'Advanced': '#e74c3c'
        }
        difficulty_color = difficulty_colors.get(piece.difficulty_level, '#95a5a6')

        difficulty_label = QLabel(piece.difficulty_level or "Unknown")
        difficulty_label.setStyleSheet(f"""
            background-color: {difficulty_color};
            color: white;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 11px;
        """)
        top_row.addWidget(difficulty_label)
        top_row.addStretch()
        layout.addLayout(top_row)

        # Basic details row
        details_row = QHBoxLayout()
        details = [
            ("Key", piece.key_signature or "N/A"),
            ("Time", piece.time_signature or "N/A"),
            ("Tempo", f"{piece.tempo} BPM"),
            ("Practiced", f"{piece.practice_count}x")
        ]

        for label, value in details:
            detail_widget = QWidget()
            detail_layout = QVBoxLayout(detail_widget)
            detail_layout.setSpacing(1)

            label_widget = QLabel(label)
            label_widget.setStyleSheet("color: #7f8c8d; font-size: 11px;")
            value_widget = QLabel(value)
            value_widget.setStyleSheet("color: #2c3e50; font-weight: bold; font-size: 12px;")

            detail_layout.addWidget(label_widget)
            detail_layout.addWidget(value_widget)
            details_row.addWidget(detail_widget)

        layout.addLayout(details_row)

        # Expandable statistics section
        stats_container = QWidget()
        stats_container.setVisible(False)
        stats_layout = QVBoxLayout(stats_container)
        stats_layout.setSpacing(8)

        stats_grid = QGridLayout()
        stats_grid.setSpacing(10)

        hours = int(piece.total_practice_time // 3600)
        minutes = int((piece.total_practice_time % 3600) // 60)
        time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

        stats = [
            ("Total Practice Time", time_str),
            ("Best Accuracy", f"{piece.best_accuracy:.1f}%"),
            ("Current Streak", f"{piece.streak_count} days"),
            ("Longest Streak", f"{piece.longest_streak} days"),
            ("Average Duration", f"{int(piece.average_session_duration // 60)}m"),
            ("Last Practice", self.db.format_timestamp(getattr(piece, 'last_practiced', None)))
        ]

        for idx, (label, value) in enumerate(stats):
            row = idx // 2
            col = idx % 2 * 2

            label_widget = QLabel(label)
            label_widget.setStyleSheet("color: #7f8c8d; font-size: 10px;")
            value_widget = QLabel(value)
            value_widget.setStyleSheet("color: #2c3e50; font-weight: bold; font-size: 11px;")

            stats_grid.addWidget(label_widget, row, col)
            stats_grid.addWidget(value_widget, row, col + 1)

        stats_layout.addLayout(stats_grid)
        layout.addWidget(stats_container)

        container.stats_container = stats_container
        container.name_label = name_label

        container.mousePressEvent = lambda e: self.toggle_piece_selection(container, piece)

        self.pieces_layout.addWidget(container)
        return container

    
    def toggle_piece_selection(self, container, piece):
        """Handle piece selection and expand/collapse statistics"""
        # Collapse all other pieces
        for i in range(self.pieces_layout.count()):
            widget = self.pieces_layout.itemAt(i).widget()
            if widget != container:
                widget.stats_container.setVisible(False)
                widget.setStyleSheet("""
                    QFrame {
                        background-color: white;
                        border: 1px solid #dcdde1;
                        border-radius: 8px;
                        margin: 4px;
                    }
                    QFrame:hover {
                        border-color: #3498db;
                    }
                """)
        
        # Toggle selected piece
        is_selected = not container.stats_container.isVisible()
        container.stats_container.setVisible(is_selected)
        
        if is_selected:
            container.setStyleSheet("""
                QFrame {
                    background-color: #f8f9fa;
                    border: 2px solid #3498db;
                    border-radius: 8px;
                    margin: 4px;
                }
            """)
            self.load_selected_piece(piece)
        else:
            container.setStyleSheet("""
                QFrame {
                    background-color: white;
                    border: 1px solid #dcdde1;
                    border-radius: 8px;
                    margin: 4px;
                }
                QFrame:hover {
                    border-color: #3498db;
                }
            """)
    
    def load_selected_piece(self, piece):
        """Load the selected piece and display its sheet music.
        If the sheet file is a PDF, convert its first page to an image."""
        self.current_piece = piece
        if self.current_piece:
            print(f"Loading piece: {self.current_piece.name}")
            
            # Increment practice count
            if self.db.increment_practice_count(self.current_piece.id):
                self.current_piece.practice_count += 1
            
            # Load sheet music from BLOB
            sheet_path = self.db.get_sheet_music_file(self.current_piece.id)
            if sheet_path:
                ext = os.path.splitext(sheet_path)[1].lower()
                if ext == ".pdf":
                    try:
                        from pdf2image import convert_from_path
                        # Convert only the first page
                        images = convert_from_path(sheet_path, first_page=1, last_page=1)
                        if images:
                            # Save the converted page to a temporary JPEG file
                            temp_image_path = os.path.join("temp_sheets", "temp_image.jpg")
                            images[0].save(temp_image_path, "JPEG")
                            self.original_pixmap = QPixmap(temp_image_path)
                        else:
                            self.original_pixmap = QPixmap()
                    except Exception as e:
                        print(f"Error converting PDF to image: {e}")
                        self.original_pixmap = QPixmap()
                else:
                    self.original_pixmap = QPixmap(sheet_path)
                    
                if not self.original_pixmap.isNull():
                    self.fit_sheet_music()
                    print("Sheet music loaded successfully")
                else:
                    print(f"Error: Could not load sheet music from temporary path {sheet_path}")
            else:
                print("Sheet music file not found in database.")

            # Load reference audio from BLOB
            reference_audio_path = self.db.get_reference_audio_file(self.current_piece.id)
            self.current_piece.reference_audio_path = reference_audio_path  # Update dynamically
            
            # Enable/disable buttons based on available features
            self.record_btn.setEnabled(True)
            self.play_ref_btn.setEnabled(bool(self.current_piece.reference_audio_path))
            
            # Update practice statistics
            self.update_practice_stats()
            print("Practice stats updated")


    
    def update_practice_stats(self):
        if self.current_piece and self.current_piece.id:
            # Create a more visually appealing stats display
            stats_frame = QFrame()
            stats_frame.setStyleSheet("""
                QFrame {
                    background-color: #34495e;
                    border-radius: 10px;
                    padding: 15px;
                }
            """)
            stats_layout = QVBoxLayout(stats_frame)
            
            # Title with difficulty badge
            title_layout = QHBoxLayout()
            title_label = QLabel("Practice Statistics")
            title_label.setStyleSheet("""
                color: white;
                font-size: 18px;
                font-weight: bold;
            """)
            title_layout.addWidget(title_label)
            
            # Difficulty badge
            difficulty_color = {
                'Beginner': '#27ae60',
                'Intermediate': '#f39c12',
                'Advanced': '#e74c3c'
            }.get(self.current_piece.difficulty_level, '#95a5a6')
            
            difficulty_label = QLabel(self.current_piece.difficulty_level)
            difficulty_label.setStyleSheet(f"""
                background-color: {difficulty_color};
                color: white;
                padding: 3px 8px;
                border-radius: 4px;
                font-size: 12px;
            """)
            title_layout.addWidget(difficulty_label)
            title_layout.addStretch()
            stats_layout.addLayout(title_layout)
            
            # Key and Time Signature
            signature_layout = QHBoxLayout()
            signature_layout.addWidget(QLabel(f"Key: {self.current_piece.key_signature}"))
            signature_layout.addWidget(QLabel(f"Time: {self.current_piece.time_signature}"))
            signature_layout.addWidget(QLabel(f"Tempo: {self.current_piece.tempo} BPM"))
            for label in signature_layout.findChildren(QLabel):
                label.setStyleSheet("color: #bdc3c7;")
            stats_layout.addLayout(signature_layout)
            
            # Practice Time
            hours = int(self.current_piece.total_practice_time // 3600)
            minutes = int((self.current_piece.total_practice_time % 3600) // 60)
            time_label = QLabel(f"Total Practice Time: {hours}h {minutes}m")
            time_label.setStyleSheet("""
                color: #3498db;
                font-size: 16px;
                font-weight: bold;
                padding: 5px 0;
            """)
            stats_layout.addWidget(time_label)
            
            # Accuracy Stats
            accuracy_frame = QFrame()
            accuracy_frame.setStyleSheet("""
                QFrame {
                    background-color: #2c3e50;
                    border-radius: 5px;
                    padding: 10px;
                }
            """)
            accuracy_layout = QVBoxLayout(accuracy_frame)
            
            accuracy_label = QLabel(f"Best Accuracy: {self.current_piece.best_accuracy:.1f}%")
            accuracy_label.setStyleSheet("""
                color: #2ecc71;
                font-size: 16px;
                font-weight: bold;
            """)
            accuracy_layout.addWidget(accuracy_label)
            
            # Get practice stats from database
            cursor = self.db.conn.cursor()
            cursor.execute('''
                SELECT practice_count, streak_count, longest_streak, average_session_duration
                FROM practice_stats WHERE piece_id = ?
            ''', (self.current_piece.id,))
            result = cursor.fetchone()
            
            if result:
                practice_count, streak_count, longest_streak, avg_duration = result
                
                # Practice Sessions
                sessions_label = QLabel(f"Practice Sessions: {practice_count}")
                sessions_label.setStyleSheet("color: #bdc3c7;")
                accuracy_layout.addWidget(sessions_label)
                
                # Current Streak
                streak_label = QLabel(f"Current Streak: {streak_count} days")
                streak_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
                accuracy_layout.addWidget(streak_label)
                
                # Best Streak
                best_streak_label = QLabel(f"Best Streak: {longest_streak} days")
                best_streak_label.setStyleSheet("color: #f39c12; font-weight: bold;")
                accuracy_layout.addWidget(best_streak_label)
                
                # Average Session Duration
                avg_minutes = int(avg_duration // 60)
                avg_label = QLabel(f"Average Session: {avg_minutes}m")
                avg_label.setStyleSheet("color: #bdc3c7;")
                accuracy_layout.addWidget(avg_label)
            
            stats_layout.addWidget(accuracy_frame)
            
            # Last Practice Time
            cursor.execute('''
                SELECT last_practiced FROM practice_stats WHERE piece_id = ?
            ''', (self.current_piece.id,))
            result = cursor.fetchone()
            if result and result[0]:
                last_practice = self.db.format_timestamp(result[0])
                last_practice_label = QLabel(f"Last Practice: {last_practice}")
                last_practice_label.setStyleSheet("""
                    color: #95a5a6;
                    font-style: italic;
                """)
                stats_layout.addWidget(last_practice_label)
            
            # Replace existing stats frame with new one
            if hasattr(self, 'stats_frame'):
                self.stats_frame.deleteLater()
            self.stats_frame = stats_frame
            self.left_layout.addWidget(self.stats_frame)

    def zoom_sheet_music(self, factor):
        if not hasattr(self, 'original_pixmap'):
            return
            
        self.current_zoom *= factor
        new_size = self.original_pixmap.size() * self.current_zoom
        scaled_pixmap = self.original_pixmap.scaled(
            new_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.sheet_display_label.setPixmap(scaled_pixmap)
    
    def fit_sheet_music(self):
        if not hasattr(self, 'original_pixmap'):
            return
            
        scroll_size = self.sheet_scroll.size()
        scaled_pixmap = self.original_pixmap.scaled(
            scroll_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.current_zoom = scaled_pixmap.width() / self.original_pixmap.width()
        self.sheet_display_label.setPixmap(scaled_pixmap)

    def update_countdown(self):
        self.countdown -= 1
        if self.countdown > 0:
            self.countdown_label.setText(str(self.countdown))
        elif self.countdown == 0:
            self.countdown_label.setText("Recording...")
            self.start_audio_recording()
        else:
            self.countdown_timer.stop()

    def closeEvent(self, event):
        """Ensure proper cleanup when window is closed"""
        try:
            if self.is_recording:
                self.stop_recording()
            if self.stream is not None:
                self.stream.close()
            self.db.close()
        except Exception as e:
            print(f"Error in closeEvent: {e}")
        event.accept()


    def check_recording_status(self):
        """Check if recording should be stopped"""
        if self.should_stop_recording:
            self.recording_timer.stop()
            self.stop_recording()

    def toggle_recording(self):
        """Toggle recording state"""
        if not self.current_piece:
            QMessageBox.warning(self, "Warning", "Please select a piece first")
            return
        
        if not self.is_recording:
            # Start recording
            self.should_stop_recording = False
            self.countdown = 4
            self.countdown_label.setText(str(self.countdown))
            self.countdown_timer.start(int(60000 / self.current_piece.tempo))  # Use piece's tempo
            self.record_btn.setText("Stop Recording")
            self.is_recording = True
            self.recording_start_time = time.time()
            self.recorded_audio = []
            print("Recording started")
        else:
            # Stop recording
            self.should_stop_recording = True
            self.record_btn.setEnabled(False)
            self.countdown_label.setText("Processing...")
            self.stop_recording()
            print("Recording stopped")

    def toggle_reference(self):
        """Toggle playback of reference audio using QSoundEffect."""
        if not self.current_piece or not self.current_piece.reference_audio_path:
            QMessageBox.warning(self, "Warning", "No reference audio available")
            return

        try:
            if not self.is_playing_reference:
                self.audio_player.setSource(QUrl.fromLocalFile(self.current_piece.reference_audio_path))
                self.audio_player.play()
                self.play_ref_btn.setText("Stop Reference")
                self.is_playing_reference = True
                print("Playing reference audio")
            else:
                self.audio_player.stop()
                self.play_ref_btn.setText("Play Reference")
                self.is_playing_reference = False
                print("Stopped reference audio")
        except Exception as e:
            print(f"Error playing reference audio: {e}")
            QMessageBox.warning(self, "Error", "Failed to play reference audio")

    def start_audio_recording(self):
        """Start recording audio"""
        try:
            self.stream = sd.InputStream(
                channels=1,
                samplerate=self.fs,
                callback=self.audio_callback
            )
            self.stream.start()
            self.recording_start_time = time.time()
            self.recording_timer.start()
        except Exception as e:
            print(f"Error starting recording: {e}")
            self.stop_recording()

    def audio_callback(self, indata, frames, time, status):
        """Callback for audio recording"""
        if status:
            print(f"Audio callback status: {status}")
        if not self.should_stop_recording:
            self.recorded_audio.extend(indata[:, 0])

    def stop_recording(self):
        """Stop recording and process the audio"""
        try:
            if self.stream is not None:
                self.stream.stop()
                self.stream.close()
                self.stream = None
            
            if self.recorded_audio:
                # Convert recorded audio to numpy array
                recorded_audio = np.array(self.recorded_audio)
                
                # Save recording to file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                recording_path = f"recordings/{self.current_piece.name}_{timestamp}.wav"
                os.makedirs("recordings", exist_ok=True)
                sf.write(recording_path, recorded_audio, self.fs)
                
                # Update piece with recording path
                self.current_piece.recording_path = recording_path
                
                # Process recording and update statistics
                self.process_recording(recorded_audio)
            
            # Reset recording state
            self.is_recording = False
            self.recorded_audio = []
            self.record_btn.setText("Record")
            self.record_btn.setEnabled(True)
            self.countdown_label.setText("Ready")
            
        except Exception as e:
            print(f"Error stopping recording: {e}")
            self.record_btn.setEnabled(True)
            self.countdown_label.setText("Error")

    def process_recording(self, recorded_audio):
        """Process the recorded audio and update statistics"""
        try:
            # Load reference audio
            ref_audio, _ = librosa.load(self.current_piece.reference_audio_path, sr=self.fs)
            
            # Compare recordings and get metrics
            accuracy, completion, pitch_acc, rhythm_acc, notes_played, notes_correct = self.compare_recordings(ref_audio, recorded_audio)
            
            # Update UI with results
            self.accuracy_label.setText(f"Accuracy Score: {accuracy:.1f}%")
            self.completion_label.setText(f"Completion: {completion:.1f}%")
            self.pitch_accuracy_label.setText(f"Pitch Accuracy: {pitch_acc:.1f}%")
            self.rhythm_accuracy_label.setText(f"Rhythm Accuracy: {rhythm_acc:.1f}%")
            self.total_notes_label.setText(f"Total Notes: {notes_played}")
            self.correct_notes_label.setText(f"Correct Notes: {notes_correct}")
            
            # Update graphs
            self.update_performance_graphs(ref_audio, recorded_audio)
            
            # Save recording data to database
            duration = len(recorded_audio) / self.fs
            self.db.add_recording(
                self.current_piece.id,
                self.current_piece.recording_path,
                accuracy,
                completion,
                pitch_acc,
                rhythm_acc,
                duration,
                notes_played,
                notes_correct
            )
            
            # Update practice statistics
            self.update_practice_stats()
            
        except Exception as e:
            print(f"Error processing recording: {e}")
            QMessageBox.warning(self, "Error", "Failed to process recording. Please try again.")

    def compare_recordings(self, ref_audio, rec_audio):
        """Compare reference and recorded audio to calculate accuracy metrics"""
        try:
            # Handle case where recording is longer than reference
            ref_length = len(ref_audio)
            rec_length = len(rec_audio)
            
            # Calculate completion percentage based on how much of the reference was played
            completion = min(100, (rec_length / ref_length) * 100)
            
            # Use the shorter length for comparison to avoid index errors
            comparison_length = min(ref_length, rec_length)
            ref_audio = ref_audio[:comparison_length]
            rec_audio = rec_audio[:comparison_length]
            
            # Calculate pitch accuracy using librosa's pitch detection
            pitches_ref, magnitudes_ref = librosa.piptrack(y=ref_audio, sr=self.fs)
            pitches_rec, magnitudes_rec = librosa.piptrack(y=rec_audio, sr=self.fs)
            
            # Get the most prominent pitches
            pitches_ref = np.array([pitches_ref[magnitudes_ref[:, i].argmax(), i] for i in range(pitches_ref.shape[1])])
            pitches_rec = np.array([pitches_rec[magnitudes_rec[:, i].argmax(), i] for i in range(pitches_rec.shape[1])])
            
            # Calculate pitch differences in cents
            pitch_diffs = []
            valid_pitch_count = 0
            for p_ref, p_rec in zip(pitches_ref, pitches_rec):
                if p_ref > 0 and p_rec > 0:  # Only compare valid pitches
                    cents = 1200 * math.log2(p_rec / p_ref)
                    pitch_diffs.append(cents)
                    valid_pitch_count += 1
            
            # Calculate pitch accuracy (percentage of notes within 50 cents)
            valid_pitches = [d for d in pitch_diffs if abs(d) < 50]
            pitch_accuracy = (len(valid_pitches) / valid_pitch_count) * 100 if valid_pitch_count > 0 else 0
            
            # Calculate rhythm accuracy using onset detection
            onset_ref = librosa.onset.onset_detect(y=ref_audio, sr=self.fs)
            onset_rec = librosa.onset.onset_detect(y=rec_audio, sr=self.fs)
            
            # Convert onsets to time points
            onset_ref_times = onset_ref / self.fs
            onset_rec_times = onset_rec / self.fs
            
            # Count aligned onsets within the completed portion
            aligned_onsets = 0
            total_ref_onsets = 0
            
            for o_ref in onset_ref_times:
                # Only count onsets within the completed portion
                if o_ref * self.fs <= comparison_length:
                    total_ref_onsets += 1
                    if np.any(np.abs(onset_rec_times - o_ref) < 0.1):  # 100ms tolerance
                        aligned_onsets += 1
            
            # Calculate rhythm accuracy based on completed portion
            rhythm_accuracy = (aligned_onsets / total_ref_onsets) * 100 if total_ref_onsets > 0 else 0
            
            # Calculate overall accuracy weighted by completion
            if completion > 0:
                # Weight the accuracy by the completion percentage
                accuracy = ((pitch_accuracy + rhythm_accuracy) / 2) * (completion / 100)
            else:
                accuracy = 0
            
            # Count notes
            notes_played = len(onset_rec)
            notes_correct = aligned_onsets
            
            return accuracy, completion, pitch_accuracy, rhythm_accuracy, notes_played, notes_correct
            
        except Exception as e:
            print(f"Error in compare_recordings: {e}")
            return 0, 0, 0, 0, 0, 0

    def update_performance_graphs(self, ref_audio, rec_audio):
        """Update the performance graphs with pitch and rhythm data"""
        try:
            # Ensure both audio arrays are the same length
            min_length = min(len(ref_audio), len(rec_audio))
            ref_audio = ref_audio[:min_length]
            rec_audio = rec_audio[:min_length]
            
            # Calculate pitch differences over time
            pitches_ref, magnitudes_ref = librosa.piptrack(y=ref_audio, sr=self.fs)
            pitches_rec, magnitudes_rec = librosa.piptrack(y=rec_audio, sr=self.fs)
            
            # Get the most prominent pitches
            pitches_ref = pitches_ref[magnitudes_ref.argmax(axis=0), range(pitches_ref.shape[1])]
            pitches_rec = pitches_rec[magnitudes_rec.argmax(axis=0), range(pitches_rec.shape[1])]
            
            # Calculate pitch differences in cents
            pitch_diffs = []
            for p_ref, p_rec in zip(pitches_ref, pitches_rec):
                if p_ref > 0 and p_rec > 0:
                    cents = 1200 * math.log2(p_rec / p_ref)
                    pitch_diffs.append(cents)
                else:
                    pitch_diffs.append(0)
            
            # Update pitch graph
            time_points = np.linspace(0, len(pitch_diffs) / self.fs, len(pitch_diffs))
            self.pitch_curve.setData(time_points, pitch_diffs)
            
            # Calculate onset envelopes for rhythm graph
            onset_env_ref = librosa.onset.onset_strength(y=ref_audio, sr=self.fs)
            onset_env_rec = librosa.onset.onset_strength(y=rec_audio, sr=self.fs)
            
            # Ensure onset envelopes are the same length
            min_env_length = min(len(onset_env_ref), len(onset_env_rec))
            onset_env_ref = onset_env_ref[:min_env_length]
            onset_env_rec = onset_env_rec[:min_env_length]
            
            # Update rhythm graph
            time_points = np.linspace(0, min_env_length / self.fs, min_env_length)
            self.rhythm_ref_curve.setData(time_points, onset_env_ref)
            self.rhythm_rec_curve.setData(time_points, onset_env_rec)
            
        except Exception as e:
            print(f"Error updating performance graphs: {e}")

    def show_import_dialog(self):
        """Display the import dialog for adding new sheet music."""
        dialog = ImportDialog(self)
        if dialog.exec() == QDialog.Accepted:
            # Retrieve data from dialog
            sheet_path = dialog.sheet_path.text()
            audio_path = dialog.audio_path.text() if dialog.audio_path.text() else None
            tempo = dialog.tempo_input.value()
            difficulty = dialog.difficulty_input.currentText()
            key_signature = dialog.key_input.currentText()
            time_signature = dialog.time_input.currentText()
            
            # Add new piece to the database
            piece_id = self.db.add_piece(
                name=os.path.basename(sheet_path),
                sheet_path=sheet_path,
                reference_audio_path=audio_path,
                tempo=tempo,
                difficulty_level=difficulty,
                key_signature=key_signature,
                time_signature=time_signature
            )
            
            if piece_id:
                # Create a new MusicPiece object and add it to the UI
                new_piece = MusicPiece(
                    name=os.path.basename(sheet_path),
                    sheet_path=sheet_path,
                    reference_audio_path=audio_path,
                    tempo=tempo,
                    piece_id=piece_id
                )
                new_piece.difficulty_level = difficulty
                new_piece.key_signature = key_signature
                new_piece.time_signature = time_signature
                self.music_pieces[new_piece.name] = new_piece
                self.create_piece_list_item(new_piece)
                print(f"Added new piece: {new_piece.name}")
            else:
                QMessageBox.warning(self, "Error", "Failed to add the new piece to the database.")

class TunerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Flute Tuner")
        self.setMinimumSize(800, 600)  # Overall window height

        # Initialize target note and history variables
        self.target_note = ""
        self.elapsed_time = 0.0
        self.history_time = []
        self.history_deviation = []

        # Create toolbar with mic icon (which will change to indicate recording)
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

        # Tuner display area (note and feedback with decorative flute icon)
        display_layout = QHBoxLayout()
        display_layout.setSpacing(20)

        self.tuner_container = QWidget()
        # Instead of fixed size, we set a minimum size and let it expand
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
        self.tuner_container.setStyleSheet(self.default_style)
        self.note_label.setStyleSheet("background: transparent;")
        tuner_layout.addWidget(self.note_label)
        
        self.feedback_label = QLabel()
        self.feedback_label.setAlignment(Qt.AlignCenter)
        tuner_layout.addWidget(self.feedback_label)
        
        display_layout.addWidget(self.tuner_container, 3)

        # Decorative flute icon (fixed size)
        flute_label = QLabel()
        flute_pixmap = QPixmap("images/flute.png")
        flute_pixmap = flute_pixmap.scaled(100, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        flute_label.setPixmap(flute_pixmap)
        flute_label.setAlignment(Qt.AlignCenter)
        flute_label.setStyleSheet("""
            QLabel {
                background-color: #ecf0f1;
                border: 2px solid #bdc3c7;
                border-radius: 10px;
            }
            QLabel:hover {
                background-color: #bdc3c7;
            }
        """)
        flute_label.mousePressEvent = self.show_sheet_music_window
        display_layout.addWidget(flute_label, 1)
        main_layout.addLayout(display_layout)

        # Instead of a controls panel widget, we directly add a horizontal layout for Play and Stop buttons.
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

        # Combined details row: Graph on left, and tolerance + deviation on right
        details_row = QHBoxLayout()
        details_row.setSpacing(20)

        # Left Column: Historical graph with fixed narrow vertical size
        self.plot_widget = pg.PlotWidget(title="Pitch Deviation Over Time (cents)")
        self.plot_widget.setLabel('left', 'Cents')
        self.plot_widget.setLabel('bottom', 'Time (s)')
        # Narrow vertical height so the y-axis is small (e.g., 300px wide x 100px tall)
        self.plot_widget.setFixedSize(300, 100)
        self.curve = self.plot_widget.plot([], [], pen=pg.mkPen(color='y', width=2))
        details_row.addWidget(self.plot_widget, 2)  # Left column stretches more

        # Right Column: Tolerance slider and frequency meter details
        details_container = QWidget()
        details_layout = QVBoxLayout(details_container)
        details_layout.setSpacing(10)
        details_layout.setContentsMargins(0, 0, 0, 0)
        
        # Tolerance calibration slider layout
        tolerance_layout = QHBoxLayout()
        self.tolerance_label = QLabel("Tolerance: 2%")
        self.tolerance_label.setFont(QFont("MusicFont", 16))
        self.tolerance_slider = QSlider(Qt.Horizontal)
        self.tolerance_slider.setMinimum(0)
        self.tolerance_slider.setMaximum(10)  # 0% to 10%
        self.tolerance_slider.setValue(2)
        tolerance_layout.addWidget(self.tolerance_label)
        tolerance_layout.addWidget(self.tolerance_slider)
        details_layout.addLayout(tolerance_layout)

        # Frequency meter layout: shows deviation in cents (from -50 to 50)
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
        
        details_row.addWidget(details_container, 1)  # Right column gets less stretch
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

        # Create tuner engine instance and a timer for updating the display
        self.tuner = TunerEngine()
        self.timer = QTimer()
        self.timer.setInterval(50)  # Update every 50 ms
        self.timer.timeout.connect(self.update_note)

        # Connect signals
        self.play_button.clicked.connect(self.start_tuning)
        self.stop_button.clicked.connect(self.stop_tuning)
        self.set_target_button.clicked.connect(self.set_target_note)
        self.clear_target_button.clicked.connect(self.clear_target_note)
        self.tolerance_slider.valueChanged.connect(self.update_tolerance)

    def normalize_note_input(self, note_text):
        note = note_text.strip().upper().replace(" ", "")
        if "SHARP" in note:
            note = note.replace("SHARP", "#")
        if "FLAT" in note:
            note = note.replace("FLAT", "B")
            if note == "BB":
                note = "Bb"
        return note

    def set_target_note(self):
        note_text = self.target_input.text()
        if note_text:
            normalized = self.normalize_note_input(note_text)
            self.target_note = normalized
            self.status_panel.setText(f"Status: Target Note Set to {self.target_note}")
        else:
            self.status_panel.setText("Status: Please enter a valid target note.")

    def clear_target_note(self):
        self.target_note = ""
        self.target_input.clear()
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
        self.note_label.setText(current_note if current_note else "...")
        current_freq = self.tuner.get_last_frequency()
        
        # Determine target frequency:
        # If a target note is set, use the allowed note that best matches it.
        # Otherwise, if a note is detected, use that note's reference.
        target_freq = None
        if self.target_note and current_note:
            for note, freq in self.tuner.allowed_notes.items():
                if note.startswith(self.target_note):
                    if target_freq is None or abs(current_freq - freq) < abs(current_freq - target_freq):
                        target_freq = freq
        elif current_note:
            target_freq = self.tuner.allowed_notes.get(current_note, None)
        
        if target_freq:
            try:
                cent_diff = 1200 * math.log2(current_freq / target_freq)
            except ValueError:
                cent_diff = 0
            clamped = max(min(cent_diff, 50), -50)
            self.freq_meter.setValue(clamped)
            # Update historical graph regardless of target note
            self.elapsed_time += 0.1
            self.history_time.append(self.elapsed_time)
            self.history_deviation.append(cent_diff)
            self.curve.setData(self.history_time, self.history_deviation)
            # Visual feedback: if deviation within 10 cents, use "correct" style
            if abs(cent_diff) < 10:
                self.tuner_container.setStyleSheet(self.correct_style)
                smile_pixmap = QPixmap("images/smile.png")
                smile_pixmap = smile_pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.feedback_label.setPixmap(smile_pixmap)
            else:
                self.tuner_container.setStyleSheet(self.incorrect_style)
                sad_pixmap = QPixmap("images/sad.png")
                sad_pixmap = sad_pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.feedback_label.setPixmap(sad_pixmap)
        else:
            self.freq_meter.setValue(0)
            self.tuner_container.setStyleSheet(self.default_style)
            self.feedback_label.clear()

    def closeEvent(self, event):
        self.tuner.close()
        event.accept()

    def show_sheet_music_window(self, event):
        self.sheet_music_window = SheetMusicWindow()
        self.sheet_music_window.show()

def main():
    app = QApplication(sys.argv)
    window = TunerWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    os.makedirs("temp_sheets", exist_ok=True)
    os.makedirs("temp_audio", exist_ok=True)
    os.makedirs("recordings", exist_ok=True)

    main()
