import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audio_engine import SUBDIVISIONS, MetronomeEngine, ToneGenerator, TunerEngine
from pitch_analysis import detect_pitch, midi_to_freq

SR = 44100


def render(engine, seconds, block=512):
    n = int(seconds * SR)
    sizes = [block] * (n // block) + ([n % block] if n % block else [])
    return np.concatenate([engine.render(s) for s in sizes])


def onsets(audio, thresh=0.02):
    idx = np.flatnonzero(np.abs(audio) > thresh)
    if not len(idx):
        return np.zeros(0)
    return idx[np.insert(np.diff(idx) > 0.01 * SR, 0, True)] / SR


def test_quarter_notes_are_sample_accurate():
    m = MetronomeEngine(SR)
    m.bpm = 120
    on = onsets(render(m, 4.0))
    assert len(on) == 8, on
    assert np.all(np.abs(np.diff(on) - 0.5) < 0.001), np.diff(on)


def test_every_subdivision_pattern():
    for name, pattern in SUBDIVISIONS.items():
        m = MetronomeEngine(SR)
        m.bpm = 60
        m.subdivision = pattern
        on = onsets(render(m, 2.0))
        expected = np.concatenate([np.array(pattern), 1.0 + np.array(pattern)])
        assert len(on) == len(expected), (name, on)
        assert np.all(np.abs(on - expected) < 0.002), (name, on)


def test_accent_louder_and_muted_beat_silent():
    m = MetronomeEngine(SR)
    m.bpm = 120
    m.set_beats(4, [2, 0, 1, 1])
    audio = render(m, 2.0)
    assert np.allclose(onsets(audio), [0.0, 1.0, 1.5], atol=0.002), onsets(audio)
    assert np.abs(audio[:2000]).max() > 1.2 * np.abs(audio[SR:SR + 2000]).max()
    assert [info[0] for _, info in m.events] == [0, 1, 2, 3]


def test_speed_trainer_ramps_to_target():
    m = MetronomeEngine(SR)
    m.bpm = 100
    m.trainer = (5, 2, 110)
    render(m, 5.0)
    assert m.bpm == 105, m.bpm
    render(m, 15.0)
    assert m.bpm == 110, m.bpm


def test_gap_trainer_silences_alternate_bars():
    m = MetronomeEngine(SR)
    m.bpm = 120
    m.gap = (1, 1)
    audio = render(m, 4.0)
    assert len(onsets(audio[:2 * SR])) == 4 and len(onsets(audio[2 * SR:])) == 0
    assert [info[3] for _, info in m.events] == [False] * 4 + [True] * 4


def test_just_intonation_and_transposition():
    t = TunerEngine()
    just_e = midi_to_freq(60) * 5 / 4
    assert abs(t.process(just_e)["cents"] + 13.69) < 0.5
    t = TunerEngine()
    t.temperament, t.tonic = "Just", 0
    r = t.process(just_e)
    assert r["note"] == "E" and abs(r["cents"]) < 0.5, r
    assert abs(r["target"] - just_e) < 0.05
    t = TunerEngine()
    t.transpose = 5
    r = t.process(midi_to_freq(60))
    assert (r["note"], r["octave"]) == ("F", 4), r


def test_drone_pitch_and_smooth_retune():
    g = ToneGenerator(SR)
    g.timbre, g._target = "Pure", 1.0
    audio = np.concatenate([g.render(512) for _ in range(40)])
    assert abs(detect_pitch(audio[-4096:], SR) - 440.0) < 1.0
    g.freq = 466.16
    audio = np.concatenate([audio, g.render(512)])
    assert np.abs(np.diff(audio[-1024:])).max() < 0.05


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
