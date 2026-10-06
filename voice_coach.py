import os
import random
import time
from collections import deque

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QObject, QTimer

from pitch_analysis import ANALYSIS_SR

VOICES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voices")

POSTURE_BAD = ["posture/relax-your-shoulders.mp3", "posture/find-a-more-comftable-position.mp3",
               "posture/bring-the-flute-into-position.mp3"]
POSTURE_GOOD = ["posture/great-posture.mp3", "posture/keep-that-position.mp3"]
IN_TUNE_CLIPS = ["Intonation/nicely-in-tune.mp3", "Intonation/beautiful.mp3",
                 "Intonation/exelent-control.mp3"]
WOBBLE_CLIPS = ["Intonation/relax-the-air.mp3", "Intonation/surport-the-sound.mp3"]
MORE_AIR = "Intonation/give-the-note-a-little-more-air.mp3"
# Under-supported tone tends flat; overblown tone tends sharp — pair the direct
# observation with the likely cause so repeated advice doesn't sound identical.
FLAT_CLIPS = ["Intonation/a-little-flat.mp3", "Intonation/surport-the-sound.mp3"]
SHARP_CLIPS = ["Intonation/a-little-sharp.mp3", "Intonation/relax-the-air.mp3"]
MID_CLIPS = ["doing excercise/keep-going.mp3", "doing excercise/stay-focused.mp3",
             "doing excercise/you-are-getting-it.mp3", "doing excercise/thats-improving.mp3",
             "doing excercise/much-better.mp3", "doing excercise/good-start.mp3"]
WRONG_STREAK = "doing excercise/lets-try-that-again.mp3"
TRY_AGAIN = ["doing excercise/lets-try-that-again.mp3", "doing excercise/one-more-time.mp3"]
STEADY_TEMPO = "doing excercise/keep-the-tempo-steady.mp3"
DONE_GREAT = "sess-done/great-work-today.mp3"
DONE_PROGRESS = "sess-done/You're making progress. Keep it up..mp3"
DONE_POSTURE = "sess-done/You maintained good posture for most of the session.mp3"


class VoiceCoach(QObject):
    """Speaks short tutor clips. Owns its own output stream so it never
    interrupts the metronome, the drone or reference playback.

    - say(rel): play a clip honouring per-clip cooldowns (queue holds 2).
    - on_posture(status): feed CameraService.posture_changed.
    - on_reading(reading, level_db): feed TunerEngine readings each tick.
    - practice_started / practice_mid / practice_done(result): feed PracticePanel.
    """

    COOLDOWN = 45.0
    POSTURE_COOLDOWN = 40.0
    INTONATION_COOLDOWN = 60.0

    def __init__(self, parent=None, voices_dir=VOICES_DIR, samplerate=ANALYSIS_SR):
        super().__init__(parent)
        self.dir = voices_dir
        self.sr = samplerate
        self.enabled = True
        self._queue = deque()
        self._current = None
        self._cache = {}
        self._last_clip = {}
        self._stream = None
        self._stream_failed = False

        self._pools = {}
        self._posture = None
        self._posture_since = time.monotonic()
        self._posture_timer = QTimer(self, interval=1000, timeout=self._check_posture)
        self._posture_timer.start()

        self._intonation_zone = None
        self._intonation_since = 0.0
        self._recent_cents = deque(maxlen=50)
        self._wobble_since = 0.0
        self._faint_since = 0.0

        self._practice_on = False
        self._posture_good = 0.0
        self._posture_bad = 0.0

    # ---------------- playback ----------------
    def _ensure_stream(self):
        if self._stream is not None:
            return True
        if self._stream_failed:
            return False
        try:
            self._stream = sd.OutputStream(samplerate=self.sr, channels=1, dtype="float32",
                                           callback=self._callback)
            self._stream.start()
            return True
        except Exception as e:
            print(f"Voice coach audio unavailable: {e}")
            self._stream_failed = True
            return False

    def _load(self, rel):
        if rel in self._cache:
            return self._cache[rel]
        samples = None
        path = os.path.join(self.dir, rel)
        try:
            import soundfile as sf
            data, sr = sf.read(path, dtype="float32", always_2d=True)
            samples = (data[:, 0], sr)
        except Exception:
            try:
                import librosa
                data, sr = librosa.load(path, sr=None, mono=True)
                samples = (data, sr)
            except Exception as e:
                print(f"Could not decode voice clip {rel}: {e}")
        if samples is None:
            self._cache[rel] = None
            return None
        data, sr = samples
        if sr != self.sr and len(data):
            n = int(round(len(data) * self.sr / sr))
            data = np.interp(np.linspace(0, len(data) - 1, n), np.arange(len(data)), data)
        data = np.asarray(data, dtype=np.float32)
        peak = np.abs(data).max()
        self._cache[rel] = data * (0.9 / peak) if peak > 0 else data
        return self._cache[rel]

    def _callback(self, outdata, frames, time_info, status):
        out = np.zeros(frames, dtype=np.float32)
        i = 0
        while i < frames:
            if self._current is None:
                if not self._queue:
                    break
                self._current = [self._queue.popleft(), 0]
            buf, pos = self._current
            n = min(frames - i, len(buf) - pos)
            out[i:i + n] += buf[pos:pos + n]
            self._current[1] = pos + n
            if pos + n >= len(buf):
                self._current = None
            i += n
        outdata[:, 0] = out

    def say(self, rel, cooldown=COOLDOWN):
        """Queue a clip. Returns True if it was accepted."""
        if not self.enabled:
            return False
        now = time.monotonic()
        if now - self._last_clip.get(rel, -1e9) < cooldown:
            return False
        samples = self._load(rel)
        if samples is None or len(self._queue) >= 2 or not self._ensure_stream():
            return False
        self._last_clip[rel] = now
        self._queue.append(samples)
        return True

    def say_random(self, clips, cooldown=COOLDOWN):
        clips = list(clips)
        random.shuffle(clips)
        for rel in clips:
            if self.say(rel, cooldown):
                return rel
        return None

    def say_group(self, folder, cooldown=COOLDOWN):
        try:
            clips = [f"{folder}/{f}" for f in os.listdir(os.path.join(self.dir, folder))
                     if f.lower().endswith((".mp3", ".wav"))]
        except OSError:
            return None
        return self.say_random(clips, cooldown)

    def say_rotating(self, key, clips, cooldown=COOLDOWN):
        """Play clips in a shuffled rotation: each clip is heard once before any
        repeat, so feedback never says the same thing twice in a row."""
        pool = self._pools.setdefault(key, [])
        if not pool:
            pool.extend(clips)
            random.shuffle(pool)
        for _ in range(len(pool)):
            rel = pool.pop(0)
            if self.say(rel, cooldown):
                return rel
            pool.append(rel)
        return None

    # ---------------- posture ----------------
    def on_posture(self, status):
        if status != self._posture:
            if self._practice_on:
                held = time.monotonic() - self._posture_since
                if self._posture == "Correct":
                    self._posture_good += held
                elif self._posture == "Incorrect":
                    self._posture_bad += held
            self._posture = status
            self._posture_since = time.monotonic()

    def _check_posture(self):
        if self._posture is None:
            return
        now = time.monotonic()
        held = now - self._posture_since
        if self._practice_on:
            if self._posture == "Correct":
                self._posture_good += held
            elif self._posture == "Incorrect":
                self._posture_bad += held
            self._posture_since = now
        if not self.enabled:
            return
        if self._posture == "Incorrect" and held >= 5:
            if self.say_rotating("posture_bad", POSTURE_BAD, self.POSTURE_COOLDOWN):
                self._posture_since = now
        elif self._posture == "Correct" and held >= 15:
            if self.say_rotating("posture_good", POSTURE_GOOD, self.POSTURE_COOLDOWN * 1.5):
                self._posture_since = now

    # ---------------- tuner ----------------
    def on_reading(self, reading, level_db=-90.0):
        now = time.monotonic()
        if reading is None:
            self._intonation_zone = None
            self._recent_cents.clear()
            self._wobble_since = self._faint_since = 0.0
            return
        self._recent_cents.append(reading["cents"])

        zone = "in" if abs(reading["cents"]) <= 5 else \
               "sharp" if reading["cents"] > 15 else \
               "flat" if reading["cents"] < -15 else None
        if zone != self._intonation_zone:
            self._intonation_zone, self._intonation_since = zone, now
        elif zone is not None:
            hold = 4.0 if zone == "in" else 6.0
            if now - self._intonation_since >= hold:
                clips = IN_TUNE_CLIPS if zone == "in" else SHARP_CLIPS if zone == "sharp" else FLAT_CLIPS
                if self.say_rotating(f"int_{zone}", clips, self.INTONATION_COOLDOWN):
                    self._intonation_since = now

        if len(self._recent_cents) >= 40 and np.std(self._recent_cents) > 8:
            self._wobble_since = self._wobble_since or now
            if now - self._wobble_since >= 3 and self.say_rotating("wobble", WOBBLE_CLIPS,
                                                                  self.INTONATION_COOLDOWN):
                self._wobble_since = 0.0
        else:
            self._wobble_since = 0.0

        if level_db < -45:
            self._faint_since = self._faint_since or now
            if now - self._faint_since >= 3 and self.say(MORE_AIR, self.INTONATION_COOLDOWN):
                self._faint_since = 0.0
        else:
            self._faint_since = 0.0

    # ---------------- practice ----------------
    def practice_started(self):
        self._practice_on = True
        self._posture_good = self._posture_bad = 0.0
        self.say_group("starting-practice", cooldown=0)

    def practice_mid(self):
        self.say_group("doing excercise", cooldown=90)

    def practice_wrong_streak(self):
        self.say(WRONG_STREAK, cooldown=90)

    def practice_stopped(self):
        self._practice_on = False

    def practice_done(self, result):
        self._practice_on = False
        acc = result.get("accuracy", 0)
        if acc >= 80:
            self.say(DONE_GREAT, cooldown=0)
        elif acc >= 55:
            if self._posture_good > 2 * self._posture_bad and self._posture_good > 15:
                self.say_random([DONE_POSTURE, DONE_PROGRESS], cooldown=0)
            else:
                self.say(DONE_PROGRESS, cooldown=0)
        else:
            ratio = result.get("tempo_ratio") or 1.0
            if ratio < 0.8 or ratio > 1.25:
                self.say(STEADY_TEMPO, cooldown=0)
            else:
                self.say_random(TRY_AGAIN, cooldown=0)

    # ---------------- lifecycle ----------------
    def shutdown(self):
        self._posture_timer.stop()
        self._queue.clear()
        self._current = None
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
