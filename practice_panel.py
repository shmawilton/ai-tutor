import time

import numpy as np
from PySide6.QtCore import Qt, QThread, QTimer, Signal, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QProgressBar, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from audio_engine import AudioPlayer, MicrophoneStream, play_click
from pitch_analysis import (ANALYSIS_SR, detect_pitch, evaluate_performance, freq_to_midi,
                            load_audio, midi_to_name, segment_notes, track_pitch)
import theme
from theme import C


def analyze_reference(path):
    y = load_audio(path)
    times, f0 = track_pitch(y)
    return {"notes": segment_notes(times, f0), "duration": len(y) / ANALYSIS_SR}


def analyze_performance(audio, sr, ref_notes, tempo):
    times, f0 = track_pitch(audio, sr)
    return evaluate_performance(ref_notes, segment_notes(times, f0), len(audio) / sr, tempo)


class Worker(QThread):
    done = Signal(object, object)
    failed = Signal(object, str)

    def __init__(self, tag, fn, *args):
        super().__init__()
        self.tag, self.fn, self.args = tag, fn, args

    def run(self):
        try:
            self.done.emit(self.tag, self.fn(*self.args))
        except Exception as e:
            self.failed.emit(self.tag, str(e))


class StatTile(QFrame):
    def __init__(self, caption, big=False, parent=None):
        super().__init__(parent)
        self.setObjectName("tile")
        self._size = 26 if big else 16
        self._color = C["text"]
        self.value = QLabel("--")
        self.value.setAlignment(Qt.AlignCenter)
        self.caption_label = QLabel(caption)
        self.caption_label.setWordWrap(True)
        self.caption_label.setAlignment(Qt.AlignCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)
        layout.addWidget(self.value)
        layout.addWidget(self.caption_label)
        theme.restyle(self._style)

    def _style(self):
        self.value.setStyleSheet(
            f"font-size:{self._size}px; font-weight:bold; color:{self._color};")
        self.caption_label.setStyleSheet(f"font-size:11px; color:{C['subtext']};")

    def set(self, text, color=None):
        self._color = color or C["text"]
        self._style()


def score_color(value):
    return "#27ae60" if value >= 80 else "#e67e22" if value >= 50 else "#c0392b"


def fmt_time(seconds):
    seconds = int(seconds or 0)
    return f"{seconds // 60}:{seconds % 60:02d}"


class HistoryChart(QWidget):
    """Accuracy trend across past sessions (oldest → newest, left → right)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = []
        self.setMinimumHeight(84)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        theme.on_change(self.update)

    def set_points(self, values):
        self.points = [float(v) for v in values]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(C["card_edge"]), 1))
        p.setBrush(QColor(C["card"]))
        p.drawRoundedRect(rect, 10, 10)
        w = rect.width() - 16
        left, right = rect.left() + 8, rect.right() - 8

        def y(v):
            return rect.bottom() - 8 - (v / 100.0) * (rect.height() - 16)

        if not self.points:
            p.setPen(QColor(C["faint"]))
            p.drawText(rect, Qt.AlignCenter, "History builds as you practice")
            return
        p.setPen(QPen(QColor(C["tick_minor"]), 1, Qt.DashLine))
        for v in (50, 80):
            p.drawLine(QPointF(left, y(v)), QPointF(right, y(v)))
        n = len(self.points)
        xs = [left + (w * i / (n - 1) if n > 1 else w / 2) for i in range(n)]
        if n >= 2:
            p.setPen(QPen(QColor(C["accent"]), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPolyline(QPolygonF([QPointF(x, y(v)) for x, v in zip(xs, self.points)]))
        p.setPen(Qt.NoPen)
        for x, v in zip(xs, self.points):
            p.setBrush(QColor(score_color(v)))
            p.drawEllipse(QPointF(x, y(v)), 3.5, 3.5)


class PracticePanel(QWidget):
    session_saved = Signal(int)

    def __init__(self, db, coach=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.coach = coach
        self._streak = 0
        self.sheet = None
        self.reference = None
        self.tempo, self.beats = 120, 4
        self.state = "idle"
        self._cache, self._workers = {}, []
        self.player = AudioPlayer(self)
        self.player.finished.connect(self._update_reference_ui)
        self.mic = MicrophoneStream()

        self.ref_button = QPushButton("▶  Play reference")
        self.ref_button.clicked.connect(self.toggle_reference)
        self.ref_time = QLabel("0:00 / 0:00")
        self.practice_button = QPushButton("●  Start practice")
        self.practice_button.setObjectName("practice")
        self.practice_button.clicked.connect(self.toggle_practice)

        self.info = QLabel("Select a piece to begin")
        self.info.setWordWrap(True)
        self.live_note = QLabel("–")
        self.live_note.setAlignment(Qt.AlignCenter)
        self._live_note_color = C["text"]
        self.live_detail = QLabel("")
        self.live_detail.setWordWrap(True)
        self.live_detail.setAlignment(Qt.AlignCenter)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)

        self.tiles = {key: StatTile(caption, big=(key == "accuracy")) for key, caption in [
            ("accuracy", "Accuracy"), ("notes", "Correct notes"), ("intonation", "Intonation"),
            ("rhythm", "Rhythm"), ("completion", "Completion"), ("tempo", "Tempo")]}
        grid = QGridLayout()
        grid.setSpacing(6)
        grid.addWidget(self.tiles["accuracy"], 0, 0, 1, 3)
        for i, key in enumerate(["notes", "intonation", "rhythm", "completion", "tempo"]):
            grid.addWidget(self.tiles[key], 1 + i // 3, i % 3)
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.history = QLabel("")
        self.history.setWordWrap(True)
        self.history_chart = HistoryChart()
        self.sessions = QListWidget()
        self.sessions.setMaximumHeight(150)
        self.sessions.itemSelectionChanged.connect(self._show_selected_session)

        ref_row = QHBoxLayout()
        ref_row.addWidget(self.ref_button, 1)
        ref_row.addWidget(self.ref_time)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(ref_row)
        layout.addWidget(self.practice_button)
        layout.addWidget(self.info)
        layout.addWidget(self.live_note)
        layout.addWidget(self.live_detail)
        layout.addWidget(self.progress)
        layout.addLayout(grid)
        layout.addWidget(self.detail)
        layout.addWidget(self.history)
        layout.addWidget(self.history_chart)
        layout.addWidget(self.sessions)
        layout.addStretch()

        theme.restyle(self._style)

        self._ui_timer = QTimer(self, interval=100, timeout=self._update_reference_ui)
        self._click_timer = QTimer(self, timeout=self._tick)
        self._live_timer = QTimer(self, interval=50, timeout=self._live_update)
        self._enc_timer = QTimer(self, interval=25000, timeout=self._encourage)
        self._set_enabled(False)

    def _style(self):
        self.setStyleSheet(theme.qss("""
            QPushButton { background:$blue; color:white; border:none; border-radius:8px;
                          padding:9px; font-weight:bold; }
            QPushButton:disabled { background:$disabled_bg; color:$disabled_text; }
            QPushButton#practice { background:$green; font-size:14px; padding:11px; }
            QPushButton#practice:disabled { background:$disabled_bg; color:$disabled_text; }
            QFrame#tile { background:$card; border:1px solid $card_edge; border-radius:8px; }
            QProgressBar { border:1px solid $card_edge; border-radius:3px; background:$track; }
            QProgressBar::chunk { background:$accent; border-radius:2px; }
        """))
        self.ref_time.setStyleSheet(f"color:{C['subtext']};")
        self.info.setStyleSheet(f"color:{C['subtext']};")
        self.live_detail.setStyleSheet(f"color:{C['text2']};")
        self.detail.setStyleSheet(f"color:{C['subtext']}; font-size:11px;")
        self.history.setStyleSheet(f"color:{C['text2']}; font-size:12px;")
        self.sessions.setStyleSheet(theme.qss("""
            QListWidget { background:$base; border:1px solid $card_edge; border-radius:6px;
                          color:$text; font-size:12px; }
            QListWidget::item { border-bottom:1px solid $card_edge; padding:4px 8px; }
            QListWidget::item:selected { background:$select; border-left:3px solid $accent; }
        """))
        self._set_live_note_color(self._live_note_color)

    def _set_live_note_color(self, color):
        self._live_note_color = color
        self.live_note.setStyleSheet(f"font-size:34px; font-weight:bold; color:{color};")

    def _set_enabled(self, ready):
        self.ref_button.setEnabled(self.player.data is not None)
        self.practice_button.setEnabled(ready)

    def set_sheet(self, sheet):
        self.stop_all()
        self.sheet = sheet
        self.reference = None
        try:
            self.tempo = int(str(sheet.tempo).split()[0])
        except (ValueError, IndexError):
            self.tempo = 120
        try:
            self.beats = int(str(sheet.time_signature).split("/")[0])
        except (ValueError, IndexError):
            self.beats = 4
        try:
            self.player.load(sheet.audio_path)
        except Exception as e:
            self.player.data = None
            self.info.setText(f"Could not load reference audio: {e}")
        self._update_reference_ui()
        self._show_result(None)
        self.refresh_history()

        cached = self._cache.get(sheet.db_id)
        if cached:
            self._on_reference_ready(sheet.db_id, cached)
            return
        self._set_enabled(False)
        self.info.setText("Analyzing reference audio…")
        worker = Worker(sheet.db_id, analyze_reference, sheet.audio_path)
        worker.done.connect(self._on_reference_ready)
        worker.failed.connect(self._on_reference_failed)
        self._start_worker(worker)

    def _start_worker(self, worker):
        self._workers = [w for w in self._workers if not w.isFinished()]
        self._workers.append(worker)
        worker.start()

    def _on_reference_failed(self, sheet_id, message):
        if self.sheet and self.sheet.db_id == sheet_id:
            self.info.setText(f"Reference analysis failed: {message}")

    def _on_reference_ready(self, sheet_id, reference):
        self._cache[sheet_id] = reference
        if not self.sheet or self.sheet.db_id != sheet_id:
            return
        self.reference = reference
        notes = reference["notes"]
        self._ref_starts = np.array([n["start"] for n in notes])
        self._ref_ends = np.array([n["end"] for n in notes])
        self._ref_midis = np.array([n["midi"] for n in notes])
        if not notes:
            self.info.setText("No melody detected in the reference audio.")
            self._set_enabled(False)
            return
        self.info.setText(f"{len(notes)} notes in reference • {self.tempo} BPM • {self.beats}-beat count-in")
        self._set_enabled(True)

    def toggle_reference(self):
        if self.player.is_playing:
            self.player.stop()
        elif self.state == "idle":
            self.player.play()
            self._ui_timer.start()
        self._update_reference_ui()

    def _update_reference_ui(self):
        playing = self.player.is_playing
        if not playing:
            self._ui_timer.stop()
        self.ref_button.setText("■  Stop reference" if playing else "▶  Play reference")
        self.ref_time.setText(f"{fmt_time(self.player.position)} / {fmt_time(self.player.duration)}")
        if self.state == "idle" and self.player.duration:
            self.progress.setValue(int(100 * min(1.0, self.player.position / self.player.duration)))

    def toggle_practice(self):
        if self.state == "idle":
            self._start_countin()
        elif self.state == "countin":
            self.stop_all()
        elif self.state == "recording":
            self._finish()

    def _start_countin(self):
        self.player.stop()
        self._update_reference_ui()
        self._show_result(None)
        self.state = "countin"
        self.ref_button.setEnabled(False)
        self.practice_button.setText("■  Cancel")
        self._beats_left = self.beats
        self._click_timer.start(int(60000 / max(30, self.tempo)))
        self._tick()
        if self.coach is not None:
            self.coach.practice_started()

    def _tick(self):
        if self._beats_left <= 0:
            self._click_timer.stop()
            self._start_recording()
            return
        play_click(accent=self._beats_left == self.beats)
        self.live_note.setText(str(self.beats - self._beats_left + 1))
        self.live_detail.setText("Get ready…")
        self._beats_left -= 1

    def _start_recording(self):
        try:
            self.mic.start(record=True)
        except Exception as e:
            self.stop_all()
            self.info.setText(f"Microphone error: {e}")
            return
        self.state = "recording"
        self.practice_button.setText("■  Stop && analyze")
        self._t0 = time.monotonic()
        self._voiced = self._matched = 0
        self._streak = 0
        self._live_timer.start()
        self._enc_timer.start()

    def _live_update(self):
        t = time.monotonic() - self._t0
        ref_dur = self.reference["duration"]
        self.progress.setValue(int(100 * min(1.0, t / ref_dur)))
        expected = ""
        idx = np.searchsorted(self._ref_starts, t, side="right") - 1
        if 0 <= idx < len(self._ref_ends) and self._ref_ends[idx] >= t:
            expected = midi_to_name(self._ref_midis[idx])

        freq = detect_pitch(self.mic.latest(2048), self.mic.samplerate)
        if freq > 0:
            m = freq_to_midi(freq)
            midi = int(round(m))
            window = (self._ref_starts <= t + 0.35) & (self._ref_ends >= t - 0.35)
            self._voiced += 1
            self._matched += int(np.any(self._ref_midis[window] == midi))
            ok = expected == midi_to_name(midi)
            self._streak = self._streak + 1 if expected and not ok else 0
            if self._streak == 25 and self.coach is not None:
                self.coach.practice_wrong_streak()
            self.live_note.setText(midi_to_name(midi))
            self._set_live_note_color(C["green"] if ok else C["text"])
            cents = f"{(m - midi) * 100:+.0f}¢"
        else:
            self.live_note.setText("…")
            self._set_live_note_color(C["faint"])
            cents = ""
        live = f" • following {100 * self._matched / self._voiced:.0f}%" if self._voiced else ""
        self.live_detail.setText(f"Expected: {expected or 'rest'}  {cents}{live}  •  {fmt_time(t)}")
        if t > max(ref_dur * 1.6, ref_dur + 10):
            self._finish()

    def _finish(self):
        self._live_timer.stop()
        audio, sr = self.mic.recorded(), self.mic.samplerate
        self.mic.stop()
        if audio.size < sr:
            self.stop_all()
            self.info.setText("Recording too short — play at least a few notes.")
            return
        self.state = "analyzing"
        self.practice_button.setEnabled(False)
        self.practice_button.setText("Analyzing…")
        self.live_detail.setText("Comparing with reference…")
        worker = Worker(self.sheet.db_id, analyze_performance, audio, sr, self.reference["notes"], self.tempo)
        worker.done.connect(self._on_result)
        worker.failed.connect(self._on_analysis_failed)
        self._start_worker(worker)

    def _on_analysis_failed(self, sheet_id, message):
        if self.state == "analyzing":
            self.stop_all()
        self.info.setText(f"Analysis failed: {message}")

    def _on_result(self, sheet_id, result):
        if self.state == "analyzing":
            self.stop_all()
        try:
            self.db.add_practice_session(sheet_id, result)
        except Exception as e:
            self.info.setText(f"Could not save session: {e}")
        if self.sheet is not None and self.sheet.db_id == sheet_id:
            self._show_result(result)
            self.refresh_history()
        if self.coach is not None:
            self.coach.practice_done(result)
        self.session_saved.emit(sheet_id)

    def _show_result(self, r):
        if r is None:
            for tile in self.tiles.values():
                tile.set("--", C["faint"])
            self.detail.setText("")
            return
        self.tiles["accuracy"].set(f"{r['accuracy']:.0f}%", score_color(r["accuracy"]))
        self.tiles["notes"].set(f"{r['notes_correct']}/{r['notes_expected']}", score_color(r["note_accuracy"]))
        for key in ("intonation", "rhythm", "completion"):
            self.tiles[key].set(f"{r[key]:.0f}%", score_color(r[key]))
        self.tiles["tempo"].set(f"{r['played_tempo']:.0f}" if r["played_tempo"] else "--")
        mean_cents = r["mean_cents"]
        pitch = ("on pitch" if abs(mean_cents) < 3
                 else f"{mean_cents:+.0f}¢ {'sharp' if mean_cents > 0 else 'flat'}")
        self.detail.setText(
            f"Played {r['notes_played']} notes in {fmt_time(r['duration'])} • "
            f"missed {r.get('notes_missed', '–')} • extra {r.get('extra_notes', '–')} • "
            f"octave errors {r.get('octave_errors', '–')} • average pitch {pitch}")
        self.live_note.setText(f"{r['accuracy']:.0f}%")
        self._set_live_note_color(score_color(r["accuracy"]))
        self.live_detail.setText("Session saved")

    def _show_selected_session(self):
        item = self.sessions.currentItem()
        if item is None or self.sheet is None:
            return
        row = item.data(Qt.UserRole)
        self._show_result(row)
        self.live_detail.setText(f"Session {str(row['practiced_at'])[:16]}")
        self.live_detail.setStyleSheet(f"color:{C['subtext']};")

    def refresh_history(self):
        if not self.sheet:
            self.history.setText("")
            self.history_chart.set_points([])
            self.sessions.clear()
            return
        try:
            rows = self.db.get_practice_sessions(self.sheet.db_id)
        except Exception:
            rows = []
        self.history_chart.set_points([r["accuracy"] for r in reversed(rows)])
        self.sessions.blockSignals(True)
        self.sessions.clear()
        for row in rows:
            item = QListWidgetItem(
                f"{str(row['practiced_at'])[:16]}   ·   {(row['accuracy'] or 0):.0f}%")
            item.setData(Qt.UserRole, row)
            self.sessions.addItem(item)
        self.sessions.blockSignals(False)
        s = self.db.get_practice_stats(self.sheet.db_id)
        if not s["sessions"]:
            self.history.setText("No practice sessions yet.")
            return
        self.history.setText(
            f"<b>History</b> — {s['sessions']} sessions • best {s['best_accuracy']:.0f}% • "
            f"last {s['last_accuracy']:.0f}% • avg {s['average_accuracy']:.0f}% • "
            f"total {fmt_time(s['total_time'])} • last practiced {str(s['last_practiced'])[:16]}")
        if rows and self.sessions.currentRow() < 0:
            self.sessions.setCurrentRow(0)

    def _encourage(self):
        if self.coach is not None and self.state == "recording":
            self.coach.practice_mid()

    def stop_all(self):
        self._click_timer.stop()
        self._live_timer.stop()
        self._enc_timer.stop()
        if self.coach is not None:
            self.coach.practice_stopped()
        self.mic.stop()
        self.player.stop()
        self.state = "idle"
        self.practice_button.setText("●  Start practice")
        self._set_enabled(self.reference is not None and bool(self.reference["notes"]))
        self._update_reference_ui()

    def clear_sheet(self):
        self.stop_all()
        self.sheet = None
        self.reference = None
        self.player.data = None
        self._show_result(None)
        self.live_note.setText("–")
        self.live_detail.setText("")
        self.history.setText("")
        self.history_chart.set_points([])
        self.sessions.clear()
        self.info.setText("Select a piece to begin")
        self._set_enabled(False)
        self._update_reference_ui()

    def shutdown(self):
        self.stop_all()
        for worker in list(self._workers):
            worker.wait(5000)
