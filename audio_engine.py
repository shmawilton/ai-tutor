import threading
import time
from collections import deque

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QObject, QTimer, Signal

from pitch_analysis import ANALYSIS_SR, NOTE_NAMES, detect_pitch, freq_to_midi, midi_to_freq

TEMPERAMENTS = {
    "Equal": [0.0] * 12,
    "Just": [0, 11.73, 3.91, 15.64, -13.69, -1.96, -9.78, 1.96, 13.69, -15.64, 17.60, -11.73],
    "Pythagorean": [0, -9.78, 3.91, -5.87, 7.82, -1.96, 11.73, 1.96, -7.82, 5.87, -3.91, 9.78],
    "Meantone (1/4 comma)": [0, -23.95, -6.84, 10.26, -13.69, 3.42, -20.53, -3.42, -27.37, -10.26, 6.84, -17.11],
}
TRANSPOSITIONS = {"Concert (C flute)": 0, "Alto flute (G)": 5, "Bass flute (C, 8vb)": 12, "Piccolo (C, 8va)": -12}


class MicrophoneStream:
    """Non-blocking microphone capture with a ring buffer and optional full recording."""

    def __init__(self, samplerate=ANALYSIS_SR, blocksize=1024, buffer_seconds=1.0):
        self.samplerate = samplerate
        self.blocksize = blocksize
        self._ring = np.zeros(int(samplerate * buffer_seconds), dtype=np.float32)
        self._lock = threading.Lock()
        self._stream = None
        self._recording = None

    @property
    def active(self):
        return self._stream is not None

    def start(self, record=False):
        self.stop()
        with self._lock:
            self._ring[:] = 0
            self._recording = [] if record else None
        try:
            self._stream = sd.InputStream(samplerate=self.samplerate, channels=1, dtype="float32",
                                          blocksize=self.blocksize, callback=self._callback)
        except Exception:
            self.samplerate = int(sd.query_devices(kind="input")["default_samplerate"])
            self._stream = sd.InputStream(samplerate=self.samplerate, channels=1, dtype="float32",
                                          blocksize=self.blocksize, callback=self._callback)
        self._stream.start()

    def _callback(self, indata, frames, time_info, status):
        block = indata[:, 0].copy()
        n = min(len(block), len(self._ring))
        with self._lock:
            self._ring[:-n] = self._ring[n:]
            self._ring[-n:] = block[-n:]
            if self._recording is not None:
                self._recording.append(block)

    def latest(self, n):
        with self._lock:
            return self._ring[-n:].copy()

    def recorded(self):
        with self._lock:
            if not self._recording:
                return np.zeros(0, dtype=np.float32)
            return np.concatenate(self._recording)

    def level(self, n=2048):
        return float(np.sqrt(np.mean(self.latest(n) ** 2)))

    def stop(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


class TunerEngine:
    """Real-time note/cents reading with smoothing and note hysteresis."""

    def __init__(self, a4=440.0, window=2048):
        self.a4 = a4
        self.window = window
        self.temperament = "Equal"
        self.tonic = 0
        self.transpose = 0
        self.mic = MicrophoneStream()
        self._reset()

    def offset(self, midi):
        return TEMPERAMENTS[self.temperament][(midi - self.tonic) % 12]

    def target_freq(self, midi):
        return midi_to_freq(midi + self.offset(midi) / 100.0, self.a4)

    def level_db(self):
        if not self.mic.active:
            return -90.0
        return 20.0 * np.log10(self.mic.level() + 1e-9)

    def _reset(self):
        self._history = deque(maxlen=5)
        self._note = None
        self._pending = None
        self._pending_count = 0
        self._silent_frames = 0

    def start(self):
        self._reset()
        self.mic.start()

    def stop(self):
        self.mic.stop()
        self._reset()

    close = stop

    def read(self):
        if not self.mic.active:
            return None
        return self.process(detect_pitch(self.mic.latest(self.window), self.mic.samplerate))

    def process(self, freq):
        if freq <= 0:
            self._silent_frames += 1
            if self._silent_frames > 6:
                self._reset()
            return None
        self._silent_frames = 0

        midi_f = freq_to_midi(freq, self.a4)
        if self._history and abs(midi_f - float(np.median(self._history))) > 0.8:
            self._history.clear()
        self._history.append(midi_f)
        smooth = float(np.median(self._history))
        nearest = int(round(smooth))

        if self._note is None or nearest == self._note:
            self._note, self._pending, self._pending_count = nearest, None, 0
        else:
            self._pending_count = self._pending_count + 1 if self._pending == nearest else 1
            self._pending = nearest
            # flute overtones cause octave flicker — hold the line longer
            need = 4 if abs(nearest - self._note) == 12 else 2
            if self._pending_count >= need:
                self._note, self._pending, self._pending_count = nearest, None, 0

        written = self._note + self.transpose
        return {
            "freq": midi_to_freq(smooth, self.a4),
            "target": self.target_freq(self._note),
            "midi": self._note,
            "note": NOTE_NAMES[written % 12],
            "octave": written // 12 - 1,
            "concert": (NOTE_NAMES[self._note % 12] + str(self._note // 12 - 1)
                        if self.transpose else None),
            "cents": max(-50.0, min(50.0, (smooth - self._note) * 100.0 - self.offset(self._note))),
        }


class AudioPlayer(QObject):
    """Reference-audio playback via sounddevice (no QtMultimedia needed)."""
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = None
        self.samplerate = None
        self._start = None
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._poll)

    @property
    def duration(self):
        return 0.0 if self.data is None else len(self.data) / float(self.samplerate)

    @property
    def is_playing(self):
        return self._start is not None

    @property
    def position(self):
        return 0.0 if self._start is None else time.monotonic() - self._start

    def load(self, path):
        self.stop()
        try:
            import soundfile as sf
            self.data, self.samplerate = sf.read(path, dtype="float32")
        except Exception:
            import librosa
            self.data, self.samplerate = librosa.load(path, sr=None, mono=True)

    def play_array(self, data, samplerate):
        """Play raw samples directly (e.g. a recorded practice take)."""
        self.data, self.samplerate = np.asarray(data, dtype=np.float32), samplerate
        self.play()

    def play(self):
        if self.data is None:
            return
        self.stop()
        sd.play(self.data, self.samplerate)
        self._start = time.monotonic()
        self._timer.start()

    def stop(self):
        if self._start is not None:
            sd.stop()
        self._start = None
        self._timer.stop()

    def _poll(self):
        if self.position >= self.duration:
            self.stop()
            self.finished.emit()


def play_click(accent=False, samplerate=ANALYSIS_SR):
    t = np.arange(int(0.04 * samplerate)) / samplerate
    freq = 1600 if accent else 1000
    click = (0.4 * np.sin(2 * np.pi * freq * t) * np.exp(-t * 80)).astype(np.float32)
    try:
        sd.play(click, samplerate)
    except Exception as e:
        print(f"Metronome click failed: {e}")


SUBDIVISIONS = {
    "Quarter \u2669": [0.0],
    "Eighths \u266b": [0.0, 0.5],
    "Triplets": [0.0, 1 / 3, 2 / 3],
    "Sixteenths \u266c": [0.0, 0.25, 0.5, 0.75],
    "Swing (shuffle)": [0.0, 2 / 3],
    "Eighth + 2 sixteenths": [0.0, 0.5, 0.75],
    "2 sixteenths + eighth": [0.0, 0.25, 0.5],
    "Dotted eighth + sixteenth": [0.0, 0.75],
    "Quintuplets": [i / 5 for i in range(5)],
    "Sextuplets": [i / 6 for i in range(6)],
}


def _click_bank(sr):
    def tone(dur, decay, partials):
        t = np.arange(int(dur * sr)) / sr
        y = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * decay * k) for k, (f, a) in enumerate(partials, 1))
        return (y / np.abs(y).max()).astype(np.float32)

    bank = {"Click": {}, "Woodblock": {}, "Beep": {}}
    noise = np.random.default_rng(7).uniform(-0.5, 0.5, 64).astype(np.float32)
    for kind, f in (("accent", 2000), ("beat", 1500), ("sub", 1100)):
        click = tone(0.025, 160, [(f, 1.0), (f * 2.3, 0.4)])
        click[:64] += noise
        bank["Click"][kind] = click
    for kind, f in (("accent", 1300), ("beat", 1000), ("sub", 800)):
        bank["Woodblock"][kind] = tone(0.07, 60, [(f, 1.0), (f * 2.76, 0.35)])
    t = np.arange(int(0.08 * sr)) / sr
    env = np.minimum(1.0, np.minimum(t / 0.004, (0.08 - t) / 0.02))
    for kind, f in (("accent", 1760), ("beat", 880), ("sub", 660)):
        bank["Beep"][kind] = (np.sin(2 * np.pi * f * t) * env).astype(np.float32)
    return bank


class MetronomeEngine:
    """Sample-accurate metronome: clicks are mixed inside the audio callback, so timing never drifts."""

    def __init__(self, samplerate=ANALYSIS_SR):
        self.sr = samplerate
        self.bpm = 100.0
        self.beats = 4
        self.accents = [2, 1, 1, 1]
        self.subdivision = [0.0]
        self.sound = "Click"
        self.volume = 0.8
        self.sub_volume = 0.5
        self.trainer = None
        self.gap = None
        self.events = deque(maxlen=256)
        self._bank = _click_bank(samplerate)
        self._lock = threading.Lock()
        self._stream = None
        self._reset()

    def _reset(self):
        self._pos = 0
        self._next = 0.0
        self._beat_in_bar = 0
        self._pending = deque()
        self._voices = []
        self._clock = (0, time.monotonic())
        self._bars_at_tempo = 0
        self.bar = 0
        self.events.clear()

    @property
    def running(self):
        return self._stream is not None

    @property
    def elapsed(self):
        return self._pos / self.sr

    def set_beats(self, beats, accents=None):
        with self._lock:
            self.beats = beats
            self.accents = list(accents) if accents else [2] + [1] * (beats - 1)

    def start(self):
        self.stop()
        self._reset()
        self._stream = sd.OutputStream(samplerate=self.sr, channels=1, dtype="float32",
                                       latency="low", callback=self._callback)
        self._stream.start()

    def stop(self):
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    def _callback(self, outdata, frames, time_info, status):
        start = self._pos
        outdata[:, 0] = self.render(frames)
        stream = self._stream
        self._clock = (start, time.monotonic() + (stream.latency if stream is not None else 0.0))

    def position(self):
        """(beat, subdivision, bar, muted) of the click currently being heard, or None."""
        start, heard = self._clock
        now = start + (time.monotonic() - heard) * self.sr
        for t, info in reversed(list(self.events)):
            if t <= now:
                return info
        return None

    def render(self, frames):
        out = np.zeros(frames, dtype=np.float32)
        end = self._pos + frames
        with self._lock:
            while self._next < end:
                self._schedule_beat()
        while self._pending and self._pending[0][0] < end:
            t, wave, info = self._pending.popleft()
            if wave is not None:
                self._voices.append((int(round(t)), wave))
            self.events.append((t, info))
        alive = []
        for t0, wave in self._voices:
            a, b = max(t0, self._pos), min(t0 + len(wave), end)
            if a < b:
                out[a - self._pos:b - self._pos] += wave[a - t0:b - t0]
            if t0 + len(wave) > end:
                alive.append((t0, wave))
        self._voices = alive
        self._pos = end
        return np.clip(out, -1.0, 1.0)

    def _schedule_beat(self):
        if self._beat_in_bar >= self.beats:
            self._beat_in_bar = 0
            self.bar += 1
            self._bars_at_tempo += 1
            if self.trainer:
                step, every, target = self.trainer
                if self._bars_at_tempo >= every:
                    self.bpm = float(np.clip(self.bpm + step, min(self.bpm, target), max(self.bpm, target)))
                    self._bars_at_tempo = 0
        beat = self._beat_in_bar
        muted = bool(self.gap) and self.bar % (self.gap[0] + self.gap[1]) >= self.gap[0]
        beat_len = 60.0 * self.sr / self.bpm
        level = self.accents[beat] if beat < len(self.accents) else 1
        bank = self._bank[self.sound]
        for i, frac in enumerate(self.subdivision):
            if i == 0:
                wave = bank["accent"] if level == 2 else bank["beat"] * 0.7 if level == 1 else None
            else:
                wave = bank["sub"] * (0.55 * self.sub_volume) if self.sub_volume > 0 else None
            wave = None if wave is None or muted else wave * self.volume
            self._pending.append((self._next + frac * beat_len, wave, (beat, i, self.bar, muted)))
        self._next += beat_len
        self._beat_in_bar += 1


class ToneGenerator:
    """Sustained reference pitch (drone) with smooth fades and phase-continuous retuning."""
    TIMBRES = {"Pure": [1.0], "Soft": [1.0, 0.3, 0.1], "Rich": [1.0, 0.6, 0.45, 0.3, 0.2, 0.12]}

    def __init__(self, samplerate=ANALYSIS_SR):
        self.sr = samplerate
        self.freq = 440.0
        self.volume = 0.3
        self.timbre = "Soft"
        self._phase = 0.0
        self._gain = 0.0
        self._target = 0.0
        self._stream = None

    @property
    def running(self):
        return self._stream is not None

    def start(self):
        self._target = 1.0
        if self._stream is None:
            self._stream = sd.OutputStream(samplerate=self.sr, channels=1, dtype="float32",
                                           callback=self._callback)
            self._stream.start()

    def stop(self):
        stream, self._stream = self._stream, None
        if stream is not None:
            self._target = 0.0
            time.sleep(0.06)
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    def _callback(self, outdata, frames, time_info, status):
        outdata[:, 0] = self.render(frames)

    def render(self, frames):
        partials = self.TIMBRES.get(self.timbre, [1.0])
        phase = self._phase + 2 * np.pi * self.freq / self.sr * np.arange(1, frames + 1)
        wave = sum(a * np.sin(h * phase) for h, a in enumerate(partials, 1)) / sum(partials)
        self._phase = float(phase[-1] % (2 * np.pi))
        step = frames / (0.03 * self.sr)
        new_gain = self._gain + float(np.clip(self._target - self._gain, -step, step))
        env = np.linspace(self._gain, new_gain, frames)
        self._gain = new_gain
        return (wave * env * self.volume).astype(np.float32)
