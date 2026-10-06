import math
import sys
import time
from collections import deque

import numpy as np
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QPolygonF
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QSizePolicy, QSlider, QSpinBox,
                               QVBoxLayout, QWidget)

from audio_engine import TunerEngine, ToneGenerator, TEMPERAMENTS, TRANSPOSITIONS
from pitch_analysis import NOTE_NAMES
import theme
from theme import C

IN_TUNE_CENTS = 5
GREEN, YELLOW, RED = QColor("#27ae60"), QColor("#f39c12"), QColor("#e74c3c")
IDLE = QColor("#95a5a6")


class TunerMeter(QWidget):
    """Dial with a needle from -50 to +50 cents and a large note name."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        theme.on_change(self.update)
        self.reading = None
        self.display_cents = 0.0
        self.tolerance = IN_TUNE_CENTS
        self._anim = QTimer(self)
        self._anim.setInterval(16)
        self._anim.timeout.connect(self._step)
        self._anim.start()

    def set_reading(self, reading):
        self.reading = reading

    def _step(self):
        target = self.reading["cents"] if self.reading else 0.0
        if abs(target - self.display_cents) > 0.05:
            self.display_cents += (target - self.display_cents) * 0.25
            self.update()
        elif self.reading is None and self.display_cents != 0.0:
            self.display_cents = 0.0
            self.update()

    def _color(self):
        if not self.reading:
            return IDLE
        c = abs(self.reading["cents"])
        return GREEN if c <= self.tolerance else YELLOW if c <= self.tolerance * 3 else RED

    @staticmethod
    def _angle(cents):
        return 90.0 - cents * 1.2

    @staticmethod
    def _font(px, weight=QFont.Normal):
        font = QFont("Segoe UI")
        font.setPixelSize(max(10, int(px)))
        font.setWeight(weight)
        return font

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        in_tune = bool(self.reading) and abs(self.reading["cents"]) <= self.tolerance
        p.setPen(QPen(QColor(C["card_edge"]), 1))
        p.setBrush(QColor(C["in_tune_card"]) if in_tune else QColor(C["card"]))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)

        r = min(w * 0.46, h * 0.68)
        cx = w / 2.0
        cy = (h - 1.25 * r) / 2.0 + r
        box = QRectF(cx - r, cy - r, 2 * r, 2 * r)

        p.setPen(QPen(QColor(C["arc"]), r * 0.06, Qt.SolidLine, Qt.FlatCap))
        p.drawArc(box, int(30 * 16), int(120 * 16))
        for lo, hi, col in [(-3 * self.tolerance, 3 * self.tolerance, QColor(243, 156, 18, 80)),
                            (-self.tolerance, self.tolerance, GREEN)]:
            p.setPen(QPen(col, r * 0.06, Qt.SolidLine, Qt.FlatCap))
            p.drawArc(box, int(self._angle(hi) * 16), int((self._angle(lo) - self._angle(hi)) * 16))

        for c in range(-50, 51, 5):
            a = math.radians(self._angle(c))
            major = c % 25 == 0
            inner = r * (0.80 if major else 0.86)
            p.setPen(QPen(QColor(C["tick_major"]) if major else QColor(C["tick_minor"]),
                          2 if major else 1))
            p.drawLine(QPointF(cx + inner * math.cos(a), cy - inner * math.sin(a)),
                       QPointF(cx + r * 0.92 * math.cos(a), cy - r * 0.92 * math.sin(a)))
        p.setFont(self._font(r * 0.1))
        p.setPen(QColor(C["tick_major"]))
        for c, text in [(-50, "♭"), (50, "♯")]:
            a = math.radians(self._angle(c))
            p.drawText(QRectF(cx + r * 1.02 * math.cos(a) - 20, cy - r * 1.02 * math.sin(a) - 30, 40, 30),
                       Qt.AlignCenter, text)

        color = self._color()
        a = math.radians(self._angle(self.display_cents))
        p.setPen(QPen(color, max(3.0, r * 0.025), Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx + r * 0.62 * math.cos(a), cy - r * 0.62 * math.sin(a)),
                   QPointF(cx + r * 1.04 * math.cos(a), cy - r * 1.04 * math.sin(a)))
        p.setBrush(QBrush(color))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx + r * 1.04 * math.cos(a), cy - r * 1.04 * math.sin(a)), r * 0.03, r * 0.03)

        note = self.reading["note"] if self.reading else "–"
        p.setPen(color if self.reading else QColor(C["idle_note"]))
        p.setFont(self._font(r * 0.42, QFont.Bold))
        p.drawText(QRectF(cx - r, cy - r * 0.64, 2 * r, r * 0.52), Qt.AlignCenter, note)
        if self.reading:
            half = p.fontMetrics().horizontalAdvance(note) / 2.0
            p.setFont(self._font(r * 0.15))
            p.drawText(QRectF(cx + half + 2, cy - r * 0.32, r * 0.3, r * 0.2),
                       Qt.AlignLeft | Qt.AlignVCenter, str(self.reading["octave"]))

        p.setFont(self._font(r * 0.11, QFont.DemiBold))
        p.setPen(QColor(C["text"]))
        if self.reading:
            cents = int(round(self.reading["cents"]))
            label = "In tune" if abs(cents) <= self.tolerance else \
                f"{cents:+d} ¢  {'sharp' if cents > 0 else 'flat'}"
            sub = f"{self.reading['freq']:.1f} Hz  →  {self.reading['target']:.1f} Hz"
            if self.reading.get("concert"):
                sub += f"   ·   sounds {self.reading['concert']}"
        else:
            label, sub = "Play a note", ""
        p.drawText(QRectF(cx - r, cy - r * 0.08, 2 * r, r * 0.16), Qt.AlignCenter, label)
        p.setFont(self._font(r * 0.09))
        p.setPen(QColor(C["subtext"]))
        p.drawText(QRectF(cx - r, cy + r * 0.08, 2 * r, r * 0.14), Qt.AlignCenter, sub)


class PitchTrace(QWidget):
    """Scrolling cents-deviation graph, like TonalEnergy's analysis view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tolerance = IN_TUNE_CENTS
        self.samples = deque(maxlen=400)
        self.setMinimumHeight(56)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        theme.on_change(self.update)

    def push(self, cents):
        self.samples.append((time.monotonic(), cents))
        self.update()

    def clear(self):
        self.samples.clear()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(C["card_edge"]), 1))
        p.setBrush(QColor(C["card"]))
        p.drawRoundedRect(rect, 10, 10)
        w, h = rect.width(), rect.height()

        def y(cents):
            return rect.center().y() - cents / 50.0 * (h / 2 - 6)

        tol = self.tolerance
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(39, 174, 96, 28))
        p.drawRect(QRectF(rect.left() + 4, y(tol), w - 8, y(-tol) - y(tol)))
        p.setPen(QPen(QColor(C["tick_minor"]), 1, Qt.DashLine))
        for c in (-3 * tol, 3 * tol):
            if abs(c) <= 50:
                p.drawLine(QPointF(rect.left() + 4, y(c)), QPointF(rect.right() - 4, y(c)))
        p.setPen(QPen(QColor(C["tick_major"]), 1))
        p.drawLine(QPointF(rect.left() + 4, rect.center().y()),
                   QPointF(rect.right() - 4, rect.center().y()))

        if len(self.samples) >= 2:
            t1 = self.samples[-1][0]
            span = 10.0
            pts = []
            for t, c in self.samples:
                x = rect.right() - 6 - (t1 - t) / span * (w - 12)
                if x < rect.left() + 4:
                    continue
                pts.append(QPointF(x, y(max(-50, min(50, c)))))
            if len(pts) >= 2:
                p.setPen(QPen(QColor(C["trace"]), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawPolyline(QPolygonF(pts))


class TunerWidget(QWidget):
    def __init__(self, coach=None, parent=None):
        super().__init__(parent)
        self.engine = TunerEngine()
        self.drone = ToneGenerator()
        self.coach = coach
        self._session = []
        self._notes = set()
        self._streak = 0.0
        self._best_streak = 0.0
        self._last_tick = time.monotonic()
        self._auto_follow = 0.0
        self.meter = TunerMeter()
        self.trace = PitchTrace()

        self.toggle_button = QPushButton("Pause")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setCursor(Qt.PointingHandCursor)
        self.toggle_button.toggled.connect(self._toggle)

        self.a4_spin = QSpinBox()
        self.a4_spin.setRange(415, 466)
        self.a4_spin.setValue(440)
        self.a4_spin.setPrefix("A4 = ")
        self.a4_spin.setSuffix(" Hz")
        self.a4_spin.valueChanged.connect(self._set_a4)

        self.status = QLabel("Tuner is off")
        self.status.setAlignment(Qt.AlignCenter)

        self.hold_button = QPushButton("Hold")
        self.hold_button.setCheckable(True)
        self.hold_button.setObjectName("secondary")

        controls = QHBoxLayout()
        controls.addWidget(self.toggle_button, 2)
        controls.addWidget(self.a4_spin, 1)
        controls.addWidget(self.hold_button)

        self.tol_spin = QSpinBox(minimum=2, maximum=20, value=IN_TUNE_CENTS,
                                 prefix="±", suffix="¢")
        self.tol_spin.valueChanged.connect(self._set_tolerance)
        self.temp_combo = QComboBox()
        self.temp_combo.addItems(TEMPERAMENTS.keys())
        self.temp_combo.currentTextChanged.connect(lambda t: setattr(self.engine, "temperament", t))
        self.key_combo = QComboBox()
        self.key_combo.addItems(NOTE_NAMES)
        self.key_combo.currentIndexChanged.connect(lambda i: setattr(self.engine, "tonic", i))
        self.trans_combo = QComboBox()
        self.trans_combo.addItems(TRANSPOSITIONS.keys())
        self.trans_combo.currentTextChanged.connect(self._set_transpose)
        self._captions = []
        settings = QHBoxLayout()
        for caption, widget in [("Tune ±", self.tol_spin), ("Temp", self.temp_combo),
                                ("Key", self.key_combo)]:
            lbl = QLabel(caption)
            self._captions.append(lbl)
            settings.addWidget(lbl)
            settings.addWidget(widget, 1)

        self.gate = QSpinBox(minimum=-60, maximum=-20, value=-50, suffix=" dB")
        settings2 = QHBoxLayout()
        for caption, widget in [("Inst", self.trans_combo), ("Mic", self.gate)]:
            lbl = QLabel(caption)
            self._captions.append(lbl)
            settings2.addWidget(lbl)
            settings2.addWidget(widget, 1)

        self.drone_button = QPushButton("Drone")
        self.drone_button.setCheckable(True)
        self.drone_button.setObjectName("drone")
        self.drone_button.toggled.connect(self._toggle_drone)
        self.drone_note = QComboBox()
        self.drone_note.addItems(NOTE_NAMES)
        self.drone_note.setCurrentText("A")
        self.drone_octave = QSpinBox(minimum=3, maximum=6, value=4)
        self.drone_timbre = QComboBox()
        self.drone_timbre.addItems(ToneGenerator.TIMBRES.keys())
        self.drone_vol = QSlider(Qt.Horizontal, minimum=0, maximum=100, value=30)
        self.drone_vol.valueChanged.connect(lambda v: setattr(self.drone, "volume", v / 100))
        self.drone_auto = QCheckBox("Auto")
        self.drone_auto.setToolTip("Drone follows the note you play")
        self.drone_note.currentTextChanged.connect(self._update_drone_freq)
        self.drone_octave.valueChanged.connect(self._update_drone_freq)
        self.drone_timbre.currentTextChanged.connect(
            lambda t: setattr(self.drone, "timbre", t))
        drone_row = QHBoxLayout()
        drone_row.addWidget(self.drone_button)
        drone_row.addWidget(self.drone_note, 1)
        drone_row.addWidget(self.drone_octave)
        drone_row.addWidget(self.drone_timbre, 1)
        drone_row.addWidget(self.drone_auto)
        drone_row.addWidget(self.drone_vol, 2)

        self.stats = QLabel("")
        self.stats.setAlignment(Qt.AlignCenter)
        self.stats.setWordWrap(True)
        self.level = QProgressBar(minimum=-60, maximum=0, value=-60)
        self.level.setTextVisible(False)
        self.level.setFixedHeight(6)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.meter, 1)
        layout.addWidget(self.trace)
        layout.addWidget(self.stats)
        layout.addWidget(self.level)
        layout.addLayout(controls)
        layout.addLayout(settings)
        layout.addLayout(settings2)
        layout.addLayout(drone_row)
        layout.addWidget(self.status)

        theme.restyle(self._style)

        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._update)

    def _style(self):
        self.setStyleSheet(theme.qss("""
            QPushButton { background:$green; color:white; border:none; border-radius:8px;
                          padding:9px; font-size:14px; font-weight:bold; }
            QPushButton:checked { background:$red; }
            QPushButton#drone { background:$blue; font-size:12px; padding:8px; }
            QPushButton#drone:checked { background:$red; }
            QPushButton#secondary { background:$btn_bg; color:$text; border:1px solid $border;
                                    font-size:12px; padding:8px; }
            QPushButton#secondary:checked { background:$amber; color:white; }
            QCheckBox { color:$text; }
            QSpinBox, QComboBox { padding:5px; font-size:12px; border:1px solid $border;
                                  border-radius:6px; background:$field_bg; color:$text; }
            QProgressBar { border:1px solid $card_edge; border-radius:3px; background:$track; }
            QProgressBar::chunk { background:$accent; border-radius:2px; }
        """))
        for lbl in self._captions:
            lbl.setStyleSheet(f"color:{C['subtext']}; font-size:11px;")
        self.status.setStyleSheet(f"color:{C['subtext']};")
        self.stats.setStyleSheet(f"color:{C['subtext']}; font-size:11px;")

    def _set_a4(self, hz):
        self.engine.a4 = float(hz)
        self._update_drone_freq()

    def _set_transpose(self, name):
        self.engine.transpose = TRANSPOSITIONS[name]
        self._update_drone_freq()

    def _set_tolerance(self, cents):
        self.meter.tolerance = cents
        self.trace.tolerance = cents
        self.meter.update()
        self.trace.update()

    def _update_drone_freq(self, *args):
        written = self.drone_note.currentIndex() + (self.drone_octave.value() + 1) * 12
        concert = written - self.engine.transpose
        self.drone.freq = self.engine.target_freq(concert)

    def _toggle_drone(self, on):
        if on:
            self._update_drone_freq()
            try:
                self.drone.start()
            except Exception as e:
                self.status.setText(f"Drone error: {e}")
                self.drone_button.setChecked(False)
        else:
            self.drone.stop()

    def _toggle(self, on):
        if on:
            try:
                self.engine.start()
            except Exception as e:
                self.status.setText(f"Microphone error: {e}")
                self.toggle_button.setChecked(False)
                return
            self._session.clear()
            self._notes.clear()
            self._streak = self._best_streak = 0.0
            self.trace.clear()
            self.toggle_button.setText("Pause")
            self.status.setText("Listening…")
            self.timer.start()
        else:
            self.timer.stop()
            self.engine.stop()
            self.meter.set_reading(None)
            self.stats.setText("")
            self.level.setValue(-60)
            self.toggle_button.setText("Resume")
            self.status.setText("Tuner paused")

    def showEvent(self, event):
        super().showEvent(event)
        if not self.toggle_button.isChecked():
            self.toggle_button.setChecked(True)

    def _update(self):
        now = time.monotonic()
        dt, self._last_tick = now - self._last_tick, now
        self.level.setValue(int(max(-60, min(0, self.engine.level_db()))))
        if self.hold_button.isChecked():
            return

        reading = self.engine.read()
        if reading and self.engine.level_db() < self.gate.value():
            reading = None
        self.meter.set_reading(reading)

        if reading:
            self.trace.push(reading["cents"])
            self._session.append(reading["cents"])
            self._notes.add(reading["note"])
            if abs(reading["cents"]) <= self.meter.tolerance:
                self._streak += dt
                self._best_streak = max(self._best_streak, self._streak)
            else:
                self._streak = 0.0
            if len(self._session) > 10 and len(self._session) % 12 == 0:
                cents = np.array(self._session)
                in_tune = 100 * np.mean(np.abs(cents) <= self.meter.tolerance)
                self.stats.setText(
                    f"In tune {in_tune:.0f}% • avg {cents.mean():+.0f}¢ • "
                    f"wobble ±{cents.std():.0f}¢ • notes {len(self._notes)}")
                if self._best_streak >= 1.0:
                    self.stats.setText(
                        self.stats.text() +
                        f" • streak {self._streak:.1f}s / best {self._best_streak:.1f}s")
        else:
            self._streak = 0.0

        if (self.drone_button.isChecked() and self.drone_auto.isChecked() and reading
                and now - self._auto_follow > 0.3):
            self._auto_follow = now
            self.drone.freq = reading["target"]

        if self.coach is not None:
            self.coach.on_reading(reading, self.engine.level_db())

    def stop_all(self):
        """Stop tuner and drone (e.g. when leaving the tab)."""
        self.toggle_button.setChecked(False)
        self.drone_button.setChecked(False)

    def shutdown(self):
        self.stop_all()
        self.timer.stop()
        self.engine.close()
        self.drone.stop()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = TunerWidget()
    w.resize(560, 620)
    w.show()
    sys.exit(app.exec())
