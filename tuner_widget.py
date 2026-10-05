import math
import sys

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QSpinBox, QVBoxLayout, QWidget)

from audio_engine import TunerEngine

IN_TUNE_CENTS = 5
CLOSE_CENTS = 15
GREEN, YELLOW, RED = QColor("#27ae60"), QColor("#f39c12"), QColor("#e74c3c")
IDLE = QColor("#95a5a6")


class TunerMeter(QWidget):
    """Dial with a needle from -50 to +50 cents and a large note name."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.reading = None
        self.display_cents = 0.0
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
        return GREEN if c <= IN_TUNE_CENTS else YELLOW if c <= CLOSE_CENTS else RED

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
        in_tune = bool(self.reading) and abs(self.reading["cents"]) <= IN_TUNE_CENTS
        p.setPen(QPen(QColor("#dfe4ea"), 1))
        p.setBrush(QColor("#eafaf1") if in_tune else QColor("#ffffff"))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)

        r = min(w * 0.46, h * 0.68)
        cx = w / 2.0
        cy = (h - 1.25 * r) / 2.0 + r
        box = QRectF(cx - r, cy - r, 2 * r, 2 * r)

        p.setPen(QPen(QColor("#e5e8ec"), r * 0.06, Qt.SolidLine, Qt.FlatCap))
        p.drawArc(box, int(30 * 16), int(120 * 16))
        for lo, hi, col in [(-CLOSE_CENTS, CLOSE_CENTS, QColor(243, 156, 18, 80)),
                            (-IN_TUNE_CENTS, IN_TUNE_CENTS, GREEN)]:
            p.setPen(QPen(col, r * 0.06, Qt.SolidLine, Qt.FlatCap))
            p.drawArc(box, int(self._angle(hi) * 16), int((self._angle(lo) - self._angle(hi)) * 16))

        for c in range(-50, 51, 5):
            a = math.radians(self._angle(c))
            major = c % 25 == 0
            inner = r * (0.80 if major else 0.86)
            p.setPen(QPen(QColor("#7f8c8d") if major else QColor("#c3cad1"), 2 if major else 1))
            p.drawLine(QPointF(cx + inner * math.cos(a), cy - inner * math.sin(a)),
                       QPointF(cx + r * 0.92 * math.cos(a), cy - r * 0.92 * math.sin(a)))
        p.setFont(self._font(r * 0.1))
        p.setPen(QColor("#7f8c8d"))
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
        p.setPen(color if self.reading else QColor("#bdc3c7"))
        p.setFont(self._font(r * 0.42, QFont.Bold))
        p.drawText(QRectF(cx - r, cy - r * 0.64, 2 * r, r * 0.52), Qt.AlignCenter, note)
        if self.reading:
            half = p.fontMetrics().horizontalAdvance(note) / 2.0
            p.setFont(self._font(r * 0.15))
            p.drawText(QRectF(cx + half + 2, cy - r * 0.32, r * 0.3, r * 0.2),
                       Qt.AlignLeft | Qt.AlignVCenter, str(self.reading["octave"]))

        p.setFont(self._font(r * 0.11, QFont.DemiBold))
        p.setPen(QColor("#2c3e50"))
        if self.reading:
            cents = int(round(self.reading["cents"]))
            label = "In tune" if abs(cents) <= IN_TUNE_CENTS else f"{cents:+d} ¢  {'sharp' if cents > 0 else 'flat'}"
            sub = f"{self.reading['freq']:.1f} Hz"
        else:
            label, sub = "Play a note", ""
        p.drawText(QRectF(cx - r, cy - r * 0.08, 2 * r, r * 0.16), Qt.AlignCenter, label)
        p.setFont(self._font(r * 0.09))
        p.setPen(QColor("#7f8c8d"))
        p.drawText(QRectF(cx - r, cy + r * 0.08, 2 * r, r * 0.14), Qt.AlignCenter, sub)


class TunerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = TunerEngine()
        self.meter = TunerMeter()

        self.toggle_button = QPushButton("Start Tuner")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setCursor(Qt.PointingHandCursor)
        self.toggle_button.toggled.connect(self._toggle)

        self.a4_spin = QSpinBox()
        self.a4_spin.setRange(415, 466)
        self.a4_spin.setValue(440)
        self.a4_spin.setPrefix("A4 = ")
        self.a4_spin.setSuffix(" Hz")
        self.a4_spin.valueChanged.connect(lambda v: setattr(self.engine, "a4", float(v)))

        self.status = QLabel("Tuner is off")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("color:#7f8c8d;")

        controls = QHBoxLayout()
        controls.addWidget(self.toggle_button, 2)
        controls.addWidget(self.a4_spin, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.meter, 1)
        layout.addLayout(controls)
        layout.addWidget(self.status)

        self.setStyleSheet("""
            QPushButton { background:#27ae60; color:white; border:none; border-radius:8px;
                          padding:10px; font-size:14px; font-weight:bold; }
            QPushButton:checked { background:#c0392b; }
            QSpinBox { padding:8px; font-size:13px; border:1px solid #bdc3c7; border-radius:8px;
                       background:#ffffff; color:#2c3e50; }
        """)

        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._update)

    def _toggle(self, on):
        if on:
            try:
                self.engine.start()
            except Exception as e:
                self.status.setText(f"Microphone error: {e}")
                self.toggle_button.setChecked(False)
                return
            self.toggle_button.setText("Stop Tuner")
            self.status.setText("Listening…")
            self.timer.start()
        else:
            self.timer.stop()
            self.engine.stop()
            self.meter.set_reading(None)
            self.toggle_button.setText("Start Tuner")
            self.status.setText("Tuner is off")

    def _update(self):
        self.meter.set_reading(self.engine.read())

    def shutdown(self):
        self.timer.stop()
        self.engine.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = TunerWidget()
    w.resize(480, 520)
    w.show()
    sys.exit(app.exec())
