import sqlite3
import os
from pathlib import Path

class SheetMusicDatabase:
    def __init__(self):
        # Ensure database directory exists
        db_dir = Path(__file__).resolve().parent
        db_dir.mkdir(exist_ok=True)
        
        self.db_path = db_dir / "sheet_music.db"
        self._create_tables()
    
    def _create_tables(self):
        """Create the necessary tables if they don't exist."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            
            # Create sheet_music table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sheet_music (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    tempo TEXT NOT NULL,
                    time_signature TEXT NOT NULL,
                    level TEXT NOT NULL,
                    key_signature TEXT NOT NULL,
                    pdf_data BLOB,
                    audio_data BLOB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS practice_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sheet_id INTEGER NOT NULL,
                    practiced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    duration REAL,
                    accuracy REAL,
                    note_accuracy REAL,
                    intonation REAL,
                    rhythm REAL,
                    completion REAL,
                    notes_expected INTEGER,
                    notes_played INTEGER,
                    notes_correct INTEGER,
                    mean_cents REAL,
                    played_tempo REAL,
                    FOREIGN KEY (sheet_id) REFERENCES sheet_music (id)
                )
            ''')
            conn.commit()
    
    def add_sheet_music(self, title, tempo, time_signature, level, key_signature, pdf_path, audio_path):
        """Add new sheet music to the database."""
        try:
            # Read PDF file as binary
            with open(pdf_path, 'rb') as pdf_file:
                pdf_data = pdf_file.read()
            
            # Read audio file as binary
            with open(audio_path, 'rb') as audio_file:
                audio_data = audio_file.read()
            
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO sheet_music 
                    (title, tempo, time_signature, level, key_signature, pdf_data, audio_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (title, tempo, time_signature, level, key_signature, pdf_data, audio_data))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            print(f"Error adding sheet music: {e}")
            return None
    
    def get_all_sheet_music(self):
        """Retrieve all sheet music metadata (without binary data)."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, title, tempo, time_signature, level, key_signature, created_at
                FROM sheet_music
            ''')
            return cursor.fetchall()
    
    def get_sheet_music_by_id(self, sheet_id):
        """Retrieve complete sheet music data by ID."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM sheet_music WHERE id = ?', (sheet_id,))
            return cursor.fetchone()
    
    def export_sheet_music_files(self, sheet_id, pdf_output_path, audio_output_path):
        """Export the PDF and audio files for a given sheet music ID."""
        try:
            data = self.get_sheet_music_by_id(sheet_id)
            if not data:
                return False
            
            # Extract PDF and audio data
            pdf_data = data[6]  # Index based on table structure
            audio_data = data[7]
            
            # Write PDF file
            with open(pdf_output_path, 'wb') as pdf_file:
                pdf_file.write(pdf_data)
            
            # Write audio file
            with open(audio_output_path, 'wb') as audio_file:
                audio_file.write(audio_data)
            
            return True
        except Exception as e:
            print(f"Error exporting files: {e}")
            return False
    
    def delete_sheet_music(self, sheet_id):
        """Delete a sheet music entry by ID."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM practice_sessions WHERE sheet_id = ?', (sheet_id,))
            cursor.execute('DELETE FROM sheet_music WHERE id = ?', (sheet_id,))
            conn.commit()
            return cursor.rowcount > 0

    SESSION_FIELDS = ("duration", "accuracy", "note_accuracy", "intonation", "rhythm", "completion",
                      "notes_expected", "notes_played", "notes_correct", "mean_cents", "played_tempo")

    def add_practice_session(self, sheet_id, metrics):
        """Store the results of one practice session."""
        values = [metrics.get(field) for field in self.SESSION_FIELDS]
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"INSERT INTO practice_sessions (sheet_id, {', '.join(self.SESSION_FIELDS)}) "
                f"VALUES (?, {', '.join('?' * len(self.SESSION_FIELDS))})",
                [sheet_id] + values)
            conn.commit()
            return cursor.lastrowid

    def get_practice_sessions(self, sheet_id, limit=200):
        """Return every stored session for a sheet, newest first."""
        keys = ("id", "practiced_at") + self.SESSION_FIELDS
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT id, practiced_at, {', '.join(self.SESSION_FIELDS)} "
                "FROM practice_sessions WHERE sheet_id = ? "
                "ORDER BY practiced_at DESC, id DESC LIMIT ?", (sheet_id, limit))
            return [dict(zip(keys, row)) for row in cursor.fetchall()]

    def get_practice_stats(self, sheet_id):
        """Aggregate practice statistics for a sheet."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*), MAX(accuracy), AVG(accuracy), COALESCE(SUM(duration), 0), MAX(practiced_at)
                FROM practice_sessions WHERE sheet_id = ?
            ''', (sheet_id,))
            count, best, avg, total, last = cursor.fetchone()
            cursor.execute('''
                SELECT accuracy FROM practice_sessions WHERE sheet_id = ?
                ORDER BY practiced_at DESC, id DESC LIMIT 1
            ''', (sheet_id,))
            row = cursor.fetchone()
        return {"sessions": count, "best_accuracy": best, "average_accuracy": avg,
                "total_time": total, "last_practiced": last, "last_accuracy": row[0] if row else None}