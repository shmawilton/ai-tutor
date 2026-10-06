import sys
import time
from collections import deque

from PySide6.QtCore import Qt, QTimer, Signal, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout, QLabel,
                               QPushButton, QSizePolicy, QSlider, QSpinBox, QVBoxLayout,
                               QWidget)

from audio_engine import MetronomeEngine, SUBDIVISIONS
import theme
from theme import C

TEMPO_MARKS = [(40, "Grave"), (60, "Largo"), (66, "Larghetto"), (76, "Adagio"),
               (108, "Andante"), (120, "Moderato"), (168, "Allegro"),
               (200, "Presto"), (1000, "Prestissimo")]
TIME_SIGS = ["2/4", "3/4", "4/4", "5/4", "6/8", "7/8", "9/8", "12/8"]
SOUNDS = ["Click", "Woodblock", "Beep"]


def tempo_name(bpm):
    for hi, name in TEMPO_MARKS:
        if bpm < hi:
            return name
    return "Prestissimo"


def beats_per_bar(sig):
    num, den = (int(p) for p in sig.split("/"))
    return num // 3 if den == 8 and num % 3 == 0 else num


class BeatDots(QWidget):
    """One dot per beat (click to cycle accent / normal / mute) plus a row of
    subdivision ticks under the beat that is sounding right now."""
    beatClicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.count = 4
        self.accents = [2, 1, 1, 1]
        self.sub_count = 1
        self.active = -1
        self.sub_active = 0
        self.muted = False
        self.setMinimumHeight(48)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        theme.on_change(self.update)

    def set_meter(self, count, accents, sub_count):
        self.count, self.accents, self.sub_count = count, list(accents), sub_count
        self.active = -1
        self.update()

    def set_active(self, beat, sub, muted):
        if (beat, sub, muted) != (self.active, self.sub_active, self.muted):
            self.active, self.sub_active, self.muted = beat, sub, muted
            self.update()

    def _beat_x(self, i, w):
        pad = 24
        span = max(1, self.count - 1)
        return pad + (w - 2 * pad) * i / span

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        y, r = h * 0.40, min(11.0, (w - 48) / max(1, self.count) * 0.22 + 6)
        idle = {0: QColor(C["card"]), 1: QColor(C["dot_normal"]), 2: QColor(C["dot_accent"])}
        edge = {0: QColor(C["dot_off_edge"]), 1: QColor(C["dot_off_edge"]),
                2: QColor(C["dot_accent_edge"])}
        for i in range(self.count):
            x = self._beat_x(i, w)
            level = self.accents[i] if i < len(self.accents) else 1
            live = i == self.active
            fill = QColor(C["dot_live"]) if live and level else idle[level]
            if self.muted and live:
                fill = QColor(C["dot_muted"])
            p.setPen(QPen(QColor(C["dot_muted"]) if (self.muted and live) else edge[level], 2))
            p.setBrush(fill)
            p.drawEllipse(QRectF(x - r, y - r, 2 * r, 2 * r))
            if level == 2 and not live:
                p.setBrush(QColor(C["card"]))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QRectF(x - r * 0.32, y - r * 0.32, r * 0.64, r * 0.64))
        subs = self.sub_count - 1
        if self.active >= 0 and subs > 0:
            x = self._beat_x(self.active, w)
            y2, r2 = h * 0.82, 3.5
            for k in range(subs):
                sx = x + (k - (subs - 1) / 2.0) * (r + 10)
                p.setPen(QPen(QColor(C["dot_off_edge"]), 1))
                p.setBrush(QColor(C["dot_accent"]) if self.sub_active == k + 1 and not self.muted
                           else QColor(C["dot_normal"]))
                p.drawEllipse(QRectF(sx - r2, y2 - r2, 2 * r2, 2 * r2))

    def mousePressEvent(self, event):
        w = self.width()
        best = min(range(self.count), key=lambda i: abs(event.position().x() - self._beat_x(i, w)))
        if abs(event.position().x() - self._beat_x(best, w)) < 24:
            self.beatClicked.emit(best)


class MetronomeWidget(QWidget):
    """TonalEnergy-style metronome: tap tempo, time signatures, subdivisions,
    accent patterns, three click sounds, speed trainer and gap (silent-bar) trainer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = MetronomeEngine()
        self._taps = deque(maxlen=8)
        self._accents = [2, 1, 1, 1]

        header = QHBoxLayout()
        title = QLabel("Metronome")
        self._title = title
        self.counter = QLabel("–")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.counter)

        self.dots = BeatDots()
        self.dots.beatClicked.connect(self._cycle_accent)

        self.bpm_spin = QSpinBox(minimum=30, maximum=300, value=100)
        self.bpm_spin.setSuffix(" BPM")
        self.bpm_spin.setStyleSheet("font-size:18px; font-weight:bold; padding:6px;")
        self.bpm_spin.valueChanged.connect(lambda v: self._set_tempo(v, source="spin"))
        minus = QPushButton("−")
        plus = QPushButton("+")
        for btn in (minus, plus):
            btn.setFixedSize(36, 36)
            btn.setObjectName("round")
        minus.clicked.connect(lambda: self.bpm_spin.stepDown())
        plus.clicked.connect(lambda: self.bpm_spin.stepUp())
        self.mark = QLabel(tempo_name(100))
        self.tap = QPushButton("Tap")
        self.tap.setObjectName("secondary")
        self.tap.clicked.connect(self._tap)
        self.start_button = QPushButton("Start")
        self.start_button.setCheckable(True)
        self.start_button.toggled.connect(self._toggle)

        bpm_row = QHBoxLayout()
        bpm_row.addWidget(minus)
        bpm_row.addWidget(self.bpm_spin, 1)
        bpm_row.addWidget(plus)
        bpm_row.addWidget(self.mark)
        bpm_row.addWidget(self.tap)
        bpm_row.addWidget(self.start_button, 1)

        self.slider = QSlider(Qt.Horizontal, minimum=30, maximum=300, value=100)
        self.slider.valueChanged.connect(lambda v: self._set_tempo(v, source="slider"))

        self.sig = QComboBox()
        self.sig.addItems(TIME_SIGS)
        self.sig.setCurrentText("4/4")
        self.sig.currentTextChanged.connect(self._apply_meter)
        self.subdiv = QComboBox()
        self.subdiv.addItems(SUBDIVISIONS.keys())
        self.subdiv.setCurrentText("Eighths \u266b")
        self.subdiv.currentTextChanged.connect(self._apply_subdiv)
        self.sound = QComboBox()
        self.sound.addItems(SOUNDS)
        self.sound.currentTextChanged.connect(lambda s: setattr(self.engine, "sound", s))
        self._captions = [title, self.counter, self.mark]
        meter_row = QHBoxLayout()
        for caption, widget in [("Meter", self.sig), ("Subdiv", self.subdiv), ("Sound", self.sound)]:
            lbl = QLabel(caption)
            self._captions.append(lbl)
            meter_row.addWidget(lbl)
            meter_row.addWidget(widget, 1)

        self.vol = QSlider(Qt.Horizontal, minimum=0, maximum=100, value=80)
        self.vol.valueChanged.connect(lambda v: setattr(self.engine, "volume", v / 100))
        self.sub_vol = QSlider(Qt.Horizontal, minimum=0, maximum=100, value=50)
        self.sub_vol.valueChanged.connect(lambda v: setattr(self.engine, "sub_volume", v / 100))
        vol_row = QHBoxLayout()
        for caption, widget in [("Volume", self.vol), ("Sub vol", self.sub_vol)]:
            lbl = QLabel(caption)
            self._captions.append(lbl)
            vol_row.addWidget(lbl)
            vol_row.addWidget(widget, 1)

        self.trainer_on = QCheckBox("Speed trainer")
        self.trainer_step = QSpinBox(minimum=1, maximum=20, value=5, prefix="+", suffix=" BPM")
        self.trainer_every = QSpinBox(minimum=1, maximum=16, value=2, suffix=" bars")
        self.trainer_target = QSpinBox(minimum=30, maximum=300, value=140, prefix="→ ")
        self.trainer_on.toggled.connect(self._apply_trainer)
        for spin in (self.trainer_step, self.trainer_every, self.trainer_target):
            spin.valueChanged.connect(self._apply_trainer)
        trainer_row = QHBoxLayout()
        trainer_row.addWidget(self.trainer_on)
        trainer_row.addWidget(self.trainer_step)
        every_lbl = QLabel("every")
        self._captions.append(every_lbl)
        trainer_row.addWidget(every_lbl)
        trainer_row.addWidget(self.trainer_every)
        trainer_row.addWidget(self.trainer_target)
        trainer_row.addStretch(1)

        self.gap_on = QCheckBox("Mute bars")
        self.gap_play = QSpinBox(minimum=1, maximum=8, value=3, suffix=" play")
        self.gap_mute = QSpinBox(minimum=1, maximum=8, value=1, suffix=" mute")
        self.gap_on.toggled.connect(self._apply_gap)
        for spin in (self.gap_play, self.gap_mute):
            spin.valueChanged.connect(self._apply_gap)
        gap_row = QHBoxLayout()
        gap_row.addWidget(self.gap_on)
        gap_row.addWidget(self.gap_play)
        gap_row.addWidget(self.gap_mute)
        gap_row.addStretch(1)

        hint = QLabel("Click a beat dot to change its accent")
        self._hint = hint

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 14)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self.dots)
        layout.addLayout(bpm_row)
        layout.addWidget(self.slider)
        layout.addLayout(meter_row)
        layout.addLayout(vol_row)
        layout.addLayout(trainer_row)
        layout.addLayout(gap_row)
        layout.addWidget(hint)

        self.setAttribute(Qt.WA_StyledBackground, True)
        theme.restyle(self._style)

        self._apply_meter("4/4")
        self._apply_subdiv(self.subdiv.currentText())
        self._apply_trainer()
        self._apply_gap()

        self._ui = QTimer(self, interval=50, timeout=self._refresh)
        self._ui.start()

    def _style(self):
        self.setStyleSheet(theme.qss("""
            MetronomeWidget { background:$card; border:1px solid $card_edge; border-radius:12px; }
            QPushButton { background:$green; color:white; border:none; border-radius:8px;
                          padding:9px; font-weight:bold; }
            QPushButton:checked { background:$red; }
            QPushButton#secondary { background:$btn_bg; color:$text; border:1px solid $border; }
            QPushButton#round { background:$btn_bg; color:$text; border:1px solid $border;
                                font-size:16px; border-radius:18px; padding:0; }
            QComboBox, QSpinBox { background:$field_bg; color:$text; border:1px solid $border;
                                  border-radius:6px; padding:4px; }
            QCheckBox { color:$text; }
            QLabel { color:$text; }
        """))
        self._title.setStyleSheet(f"font-size:16px; font-weight:bold; color:{C['text']};")
        self.counter.setStyleSheet(f"color:{C['subtext']}; font-size:12px;")
        self.mark.setStyleSheet(f"color:{C['subtext']}; font-size:13px; font-style:italic;")
        self._hint.setStyleSheet(f"color:{C['faint']}; font-size:11px;")
        for lbl in self._captions[3:]:
            lbl.setStyleSheet(f"color:{C['subtext']}; font-size:11px;")

    # ---------------- controls ----------------
    def _set_tempo(self, value, source):
        value = int(round(value))
        self.engine.bpm = float(value)
        if source != "spin":
            self.bpm_spin.blockSignals(True)
            self.bpm_spin.setValue(value)
            self.bpm_spin.blockSignals(False)
        if source != "slider":
            self.slider.blockSignals(True)
            self.slider.setValue(value)
            self.slider.blockSignals(False)
        self.mark.setText(tempo_name(value))

    def _tap(self):
        now = time.monotonic()
        if self._taps and now - self._taps[-1] > 2.0:
            self._taps.clear()
        self._taps.append(now)
        if len(self._taps) >= 2:
            gaps = [b - a for a, b in zip(self._taps, list(self._taps)[1:])]
            bpm = 60.0 / sorted(gaps)[len(gaps) // 2]
            self._set_tempo(round(min(300, max(30, bpm))), source="tap")

    def _toggle(self, on):
        if on:
            try:
                self.engine.start()
            except Exception as e:
                self.counter.setText(f"Audio error: {e}")
                self.start_button.setChecked(False)
                return
            self.start_button.setText("Stop")
        else:
            self.engine.stop()
            self.dots.set_active(-1, 0, False)
            self.start_button.setText("Start")
            self.counter.setText("–")

    def _apply_meter(self, sig):
        beats = beats_per_bar(sig)
        self._accents = [2] + [1] * (beats - 1)
        self.engine.set_beats(beats, self._accents)
        self.dots.set_meter(beats, self._accents, self.dots.sub_count)

    def _apply_subdiv(self, name):
        pattern = SUBDIVISIONS[name]
        self.engine.subdivision = pattern
        self.dots.sub_count = len(pattern)
        self.dots.update()

    def _cycle_accent(self, beat):
        self._accents[beat] = (self._accents[beat] + 1) % 3
        self.engine.set_beats(self.engine.beats, self._accents)
        self.dots.set_meter(self.engine.beats, self._accents, self.dots.sub_count)

    def _apply_trainer(self, *args):
        if self.trainer_on.isChecked():
            self.engine.trainer = (self.trainer_step.value(), self.trainer_every.value(),
                                   float(self.trainer_target.value()))
            self.engine._bars_at_tempo = 0
        else:
            self.engine.trainer = None

    def _apply_gap(self, *args):
        self.engine.gap = (self.gap_play.value(), self.gap_mute.value()) \
            if self.gap_on.isChecked() else None

    # ---------------- refresh ----------------
    def _refresh(self):
        if not self.engine.running:
            return
        pos = self.engine.position()
        if pos:
            beat, sub, bar, muted = pos
            self.dots.set_active(beat, sub, muted)
            self.counter.setText(f"Bar {bar + 1} • {int(self.engine.elapsed) // 60}:"
                                 f"{int(self.engine.elapsed) % 60:02d}")
        if self.engine.trainer and not self.bpm_spin.hasFocus():
            current = int(round(self.engine.bpm))
            if current != self.bpm_spin.value():
                self._set_tempo(current, source="engine")

    def shutdown(self):
        self._ui.stop()
        self.engine.stop()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MetronomeWidget()
    w.resize(560, 380)
    w.show()
    sys.exit(app.exec())
