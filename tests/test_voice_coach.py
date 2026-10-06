import os
import sys
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from voice_coach import VoiceCoach, VOICES_DIR

app = QApplication.instance() or QApplication([])


def test_parent_widget_is_not_swallowed_as_dir():
    from PySide6.QtWidgets import QWidget
    coach = VoiceCoach(QWidget())
    assert isinstance(coach.dir, str) and os.path.isdir(coach.dir)


def test_every_clip_decodes():
    coach = VoiceCoach()
    missing = []
    for folder in os.listdir(VOICES_DIR):
        path = os.path.join(VOICES_DIR, folder)
        if not os.path.isdir(path):
            continue
        for f in os.listdir(path):
            if f.lower().endswith((".mp3", ".wav")):
                if coach._load(f"{folder}/{f}") is None:
                    missing.append(f"{folder}/{f}")
    assert not missing, missing


def test_cooldown_and_queue_without_device():
    coach = VoiceCoach()
    coach._load = lambda rel: np.zeros(100, dtype=np.float32)  # pretend decoded
    coach._ensure_stream = lambda: True                        # pretend device works
    assert coach.say("a.mp3", cooldown=10)
    assert not coach.say("a.mp3", cooldown=10)      # cooldown blocks repeat
    coach._last_clip["a.mp3"] -= 20                # pretend cooldown expired
    assert coach.say("a.mp3", cooldown=10)
    assert not coach.say("b.mp3")                  # queue full (cap 2)
    coach.enabled = False
    coach._queue.clear()
    assert not coach.say("a.mp3", cooldown=0)      # muted


def test_practice_done_picks_clip():
    picked = []
    coach = VoiceCoach()
    coach.say = lambda rel, cooldown=0: picked.append(rel) or True
    coach.say_random = lambda clips, cooldown=0: picked.append(clips[0]) or True
    coach.practice_done({"accuracy": 92})
    coach.practice_done({"accuracy": 65})
    coach.practice_done({"accuracy": 30, "tempo_ratio": 0.5})
    coach.practice_done({"accuracy": 30, "tempo_ratio": 1.0})
    assert picked[0].endswith("great-work-today.mp3")
    assert "making progress" in picked[1].lower()
    assert picked[2].endswith("keep-the-tempo-steady.mp3")
    assert "try-that-again" in picked[3] or "one-more-time" in picked[3], picked


def test_posture_feedback_after_sustained_bad():
    spoken = []
    coach = VoiceCoach()
    coach.say = lambda rel, cooldown=0: spoken.append(rel) or True
    coach.on_posture("Incorrect")
    coach._posture_since = time.monotonic() - 10   # pretend held 10s
    coach._check_posture()
    assert spoken and spoken[0].startswith("posture/"), spoken


def test_repeated_reminders_rotate_clips():
    spoken = []
    coach = VoiceCoach()
    coach.say = lambda rel, cooldown=0: spoken.append(rel) or True
    coach.on_posture("Incorrect")
    for _ in range(3):
        coach._posture_since = time.monotonic() - 10
        coach._check_posture()
    assert len(spoken) == 3 and len(set(spoken)) == 3, spoken


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
