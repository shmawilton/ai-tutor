import math
import numpy as np

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLUTE_FMIN = 200.0
FLUTE_FMAX = 2600.0
ANALYSIS_SR = 44100
FRAME_LENGTH = 2048
HOP_LENGTH = 512
SILENCE_RMS = 0.004


def freq_to_midi(freq, a4=440.0):
    return 69.0 + 12.0 * math.log2(freq / a4)


def midi_to_name(midi):
    midi = int(round(midi))
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def midi_to_freq(midi, a4=440.0):
    return a4 * 2.0 ** ((midi - 69) / 12.0)


def yin_frames(frames, sr, fmin=FLUTE_FMIN, fmax=FLUTE_FMAX, threshold=0.15, voicing=0.25):
    """Vectorized YIN. Returns (f0, aperiodicity) per frame; f0 == 0 means unvoiced."""
    frames = np.atleast_2d(np.asarray(frames, dtype=np.float64))
    frames = frames - frames.mean(axis=1, keepdims=True)
    n, length = frames.shape
    tau_min = max(2, int(sr / fmax))
    tau_max = min(int(sr / fmin) + 1, length // 2)
    win = length - tau_max
    nfft = 1 << int(np.ceil(np.log2(length + win)))

    spec = np.fft.rfft(frames, nfft, axis=1)
    spec_w = np.fft.rfft(frames[:, :win], nfft, axis=1)
    cross = np.fft.irfft(spec * np.conj(spec_w), nfft, axis=1)[:, :tau_max + 1]

    sq = np.concatenate([np.zeros((n, 1)), np.cumsum(frames ** 2, axis=1)], axis=1)
    taus = np.arange(tau_max + 1)
    diff = sq[:, win][:, None] + (sq[:, taus + win] - sq[:, taus]) - 2.0 * cross
    diff = np.maximum(diff, 0.0)
    diff[:, 0] = 0.0
    cmnd = np.ones_like(diff)
    cmnd[:, 1:] = diff[:, 1:] * taus[1:] / np.maximum(np.cumsum(diff[:, 1:], axis=1), 1e-12)

    seg = cmnd[:, tau_min:tau_max]
    below = seg < threshold
    idx = np.where(below.any(axis=1), np.argmax(below, axis=1), np.argmin(seg, axis=1))
    rows = np.arange(n)
    for _ in range(seg.shape[1]):
        nxt = np.minimum(idx + 1, seg.shape[1] - 1)
        move = seg[rows, nxt] < seg[rows, idx]
        if not move.any():
            break
        idx = np.where(move, nxt, idx)

    tau = idx + tau_min
    a = cmnd[rows, np.clip(tau - 1, 1, tau_max)]
    b = cmnd[rows, tau]
    c = cmnd[rows, np.clip(tau + 1, 1, tau_max)]
    denom = a - 2.0 * b + c
    shift = np.where(np.abs(denom) > 1e-12, 0.5 * (a - c) / np.where(denom == 0, 1, denom), 0.0)
    period = tau + np.clip(shift, -1.0, 1.0)
    f0 = np.where(b < voicing, sr / period, 0.0)
    return f0, b


def detect_pitch(block, sr, rms_gate=SILENCE_RMS):
    """Single-block pitch for real-time use. Returns frequency in Hz or 0."""
    block = np.asarray(block, dtype=np.float64)
    if block.size < 512 or np.sqrt(np.mean(block ** 2)) < rms_gate:
        return 0.0
    f0, _ = yin_frames(block[None, :], sr)
    return float(f0[0])


def track_pitch(y, sr=ANALYSIS_SR, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH, chunk=256):
    """Offline pitch track. Returns (times, f0) with f0 == 0 for silence/unvoiced."""
    y = np.asarray(y, dtype=np.float32).flatten()
    if y.size < frame_length:
        y = np.pad(y, (0, frame_length - y.size))
    n_frames = 1 + (y.size - frame_length) // hop_length
    f0 = np.zeros(n_frames)
    rms = np.zeros(n_frames)
    offsets = np.arange(frame_length)[None, :]
    for start in range(0, n_frames, chunk):
        stop = min(n_frames, start + chunk)
        frames = y[np.arange(start, stop)[:, None] * hop_length + offsets]
        f0[start:stop], _ = yin_frames(frames, sr)
        rms[start:stop] = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    gate = max(SILENCE_RMS, 0.06 * np.percentile(rms, 95)) if rms.size else SILENCE_RMS
    f0 = np.where(rms > gate, f0, 0.0)
    times = (np.arange(n_frames) * hop_length + frame_length / 2.0) / sr
    return times, f0


def load_audio(path, sr=ANALYSIS_SR):
    import librosa
    y, _ = librosa.load(path, sr=sr, mono=True)
    return y.astype(np.float32)


def segment_notes(times, f0, min_dur=0.08, max_gap_frames=2):
    """Group a pitch track into note events: dicts with start, end, midi, freq."""
    notes, cur, gap = [], None, 0
    hop = float(times[1] - times[0]) if len(times) > 1 else HOP_LENGTH / ANALYSIS_SR

    def close(note):
        if note and note["end"] - note["start"] + hop >= min_dur:
            freq = float(np.median(note["freqs"]))
            notes.append({"start": note["start"], "end": note["end"] + hop,
                          "midi": note["midi"], "freq": freq})

    for t, f in zip(times, f0):
        if f <= 0:
            gap += 1
            if cur and gap > max_gap_frames:
                close(cur)
                cur = None
            continue
        gap = 0
        m = freq_to_midi(f)
        if cur and abs(m - cur["midi"]) < 0.7:
            cur["end"] = t
            cur["freqs"].append(f)
        else:
            close(cur)
            cur = {"start": t, "end": t, "midi": int(round(m)), "freqs": [f]}
    close(cur)
    return notes


def align_notes(ref, perf):
    """Semi-global alignment of note sequences (free trailing reference gap).
    Returns (pairs, covered) where pairs = [(ref_idx|None, perf_idx|None)]."""
    n, m = len(ref), len(perf)
    gap = -1.0

    def score(a, b):
        if a == b:
            return 2.0
        if a % 12 == b % 12:
            return 0.5
        return -1.0

    D = [[0.0] * (m + 1) for _ in range(n + 1)]
    T = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        D[i][0], T[i][0] = gap * i, 1
    for j in range(1, m + 1):
        D[0][j], T[0][j] = gap * j, 2
    ref_m = [r["midi"] for r in ref]
    perf_m = [p["midi"] for p in perf]
    for i in range(1, n + 1):
        Di, Dp, Ti, rm = D[i], D[i - 1], T[i], ref_m[i - 1]
        for j in range(1, m + 1):
            diag = Dp[j - 1] + score(rm, perf_m[j - 1])
            up = Dp[j] + gap
            left = Di[j - 1] + gap
            if diag >= up and diag >= left:
                Di[j], Ti[j] = diag, 0
            elif up >= left:
                Di[j], Ti[j] = up, 1
            else:
                Di[j], Ti[j] = left, 2

    covered = max(range(n + 1), key=lambda i: D[i][m]) if m else 0
    pairs, i, j = [], covered, m
    while i > 0 or j > 0:
        move = T[i][j] if i > 0 and j > 0 else (1 if i > 0 else 2)
        if move == 0:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif move == 1:
            pairs.append((i - 1, None))
            i -= 1
        else:
            pairs.append((None, j - 1))
            j -= 1
    pairs.reverse()
    return pairs, covered


def evaluate_performance(ref_notes, perf_notes, perf_duration, tempo=None):
    """Compare performed notes with reference notes and return accuracy metrics."""
    result = {
        "accuracy": 0.0, "note_accuracy": 0.0, "intonation": 0.0, "rhythm": 0.0,
        "completion": 0.0, "notes_expected": len(ref_notes), "notes_played": len(perf_notes),
        "notes_correct": 0, "notes_missed": 0, "extra_notes": 0, "octave_errors": 0,
        "mean_cents": 0.0, "tempo_ratio": 1.0, "played_tempo": tempo,
        "duration": perf_duration, "time_offset": 0.0,
    }
    if not ref_notes or not perf_notes:
        return result

    pairs, covered = align_notes(ref_notes, perf_notes)
    correct = [(r, p) for r, p in pairs if r is not None and p is not None
               and ref_notes[r]["midi"] == perf_notes[p]["midi"]]
    result["octave_errors"] = sum(1 for r, p in pairs if r is not None and p is not None
                                  and ref_notes[r]["midi"] != perf_notes[p]["midi"]
                                  and ref_notes[r]["midi"] % 12 == perf_notes[p]["midi"] % 12)
    result["notes_missed"] = sum(1 for r, p in pairs if r is not None and p is None)
    result["extra_notes"] = sum(1 for r, p in pairs if r is None and p is not None)
    result["notes_correct"] = len(correct)
    covered = max(covered, 1)
    result["completion"] = 100.0 * covered / len(ref_notes)
    result["note_accuracy"] = 100.0 * len(correct) / covered

    if correct:
        cents = np.array([1200.0 * math.log2(perf_notes[p]["freq"] / ref_notes[r]["freq"])
                          for r, p in correct])
        result["intonation"] = 100.0 * float(np.mean(np.abs(cents) <= 25.0))
        result["mean_cents"] = float(np.mean(cents))

        ref_on = np.array([ref_notes[r]["start"] for r, _ in correct])
        perf_on = np.array([perf_notes[p]["start"] for _, p in correct])
        if len(correct) >= 4 and np.ptp(ref_on) > 1.0:
            slope = float(np.clip(np.polyfit(ref_on, perf_on, 1)[0], 0.5, 2.0))
        else:
            slope = 1.0
        intercept = float(np.median(perf_on - slope * ref_on))
        residual = perf_on - (slope * ref_on + intercept)
        beat = 60.0 / tempo if tempo else 0.5
        tolerance = max(0.12, 0.25 * beat * slope)
        result["rhythm"] = 100.0 * float(np.mean(np.abs(residual) <= tolerance))
        result["tempo_ratio"] = 1.0 / slope
        result["played_tempo"] = tempo / slope if tempo else None
        result["time_offset"] = float(intercept)

    quality = 0.5 * result["note_accuracy"] + 0.25 * result["intonation"] + 0.25 * result["rhythm"]
    result["accuracy"] = quality * result["completion"] / 100.0
    return result
