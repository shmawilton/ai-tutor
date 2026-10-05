import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pitch_analysis import (ANALYSIS_SR, detect_pitch, track_pitch, segment_notes,
                            evaluate_performance, freq_to_midi, midi_to_freq, midi_to_name)

SR = ANALYSIS_SR


def tone(freq, dur, sr=SR, amp=0.3):
    t = np.arange(int(dur * sr)) / sr
    y = sum(a * np.sin(2 * np.pi * freq * h * t) for h, a in [(1, 1.0), (2, 0.6), (3, 0.3), (4, 0.1)])
    env = np.minimum(1.0, np.minimum(t / 0.02, (dur - t) / 0.02))
    return (amp * y * env / 2.0).astype(np.float32)


def melody(midis, note_dur=0.4, gap=0.05, lead=0.0, cents=0.0):
    parts = [np.zeros(int(lead * SR), dtype=np.float32)]
    for m in midis:
        parts.append(tone(midi_to_freq(m) * 2 ** (cents / 1200), note_dur))
        parts.append(np.zeros(int(gap * SR), dtype=np.float32))
    return np.concatenate(parts)


def test_detect_pitch_flute_range():
    for midi in [60, 67, 72, 81, 88, 96]:
        f = midi_to_freq(midi)
        detected = detect_pitch(tone(f, 0.1)[:2048], SR)
        assert abs(1200 * np.log2(detected / f)) < 5, (midi, f, detected)


def test_detect_pitch_silence():
    assert detect_pitch(np.zeros(2048), SR) == 0.0
    assert detect_pitch(np.random.default_rng(0).normal(0, 0.001, 2048), SR) == 0.0


def test_note_names():
    assert midi_to_name(69) == "A4"
    assert midi_to_name(61) == "C#4"
    assert round(freq_to_midi(440.0)) == 69


def test_segment_notes():
    notes_in = [72, 74, 76, 77, 79]
    notes = segment_notes(*track_pitch(melody(notes_in), SR))
    assert [n["midi"] for n in notes] == notes_in


def test_perfect_performance_scores_high():
    ref = melody([72, 74, 76, 77, 79, 77, 76, 74, 72])
    perf = melody([72, 74, 76, 77, 79, 77, 76, 74, 72], lead=0.7)
    r = evaluate_performance(segment_notes(*track_pitch(ref)), segment_notes(*track_pitch(perf)),
                             len(perf) / SR, tempo=120)
    assert r["notes_correct"] == 9
    assert r["accuracy"] > 95, r


def test_wrong_notes_and_partial_play_score_lower():
    ref_notes = segment_notes(*track_pitch(melody([72, 74, 76, 77, 79, 77, 76, 74, 72])))
    perf = melody([72, 74, 75, 77, 79])
    r = evaluate_performance(ref_notes, segment_notes(*track_pitch(perf)), len(perf) / SR, tempo=120)
    assert r["notes_correct"] == 4
    assert r["completion"] < 70
    assert r["accuracy"] < 60


def test_out_of_tune_lowers_intonation():
    ref_notes = segment_notes(*track_pitch(melody([72, 74, 76, 77])))
    perf_notes = segment_notes(*track_pitch(melody([72, 74, 76, 77], cents=35)))
    r = evaluate_performance(ref_notes, perf_notes, 2.0, tempo=120)
    assert r["intonation"] < 50 and r["mean_cents"] > 25


def test_slower_tempo_detected():
    ref_notes = segment_notes(*track_pitch(melody([72, 74, 76, 77, 79, 81], note_dur=0.4)))
    perf_notes = segment_notes(*track_pitch(melody([72, 74, 76, 77, 79, 81], note_dur=0.8, gap=0.1)))
    r = evaluate_performance(ref_notes, perf_notes, 6.0, tempo=120)
    assert r["tempo_ratio"] < 0.6 and r["rhythm"] > 80, r


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
