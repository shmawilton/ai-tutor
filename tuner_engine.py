# tuner_engine.py

import pyaudio
import numpy as np

class TunerEngine:
    def __init__(self, tolerance=0.02, smoothing_factor=0.3, change_threshold=5):
        # Audio configuration
        self.sr = 48000
        self.buffer_samples = 2048
        self.tolerance = tolerance      # e.g., 0.02 for 2%
        self.smoothing_factor = smoothing_factor
        self.change_threshold = change_threshold  # Number of consecutive different readings to change note
        self.last_frequency = None
        self.stable_note = ""       # Holds the currently locked note
        self.change_counter = 0     # Counts how many cycles the detected note has been different

        # Set up PyAudio instance and stream
        self.pa = pyaudio.PyAudio()
        self.stream = None  # Will be created when needed
        self.is_active = False  # Flag to control processing

        # Allowed notes using exact frequencies from your provided data
        self.allowed_notes = {
            # Second file (C4 to B5)
            "C4": 261.626,
            "C#4": 277.183,
            "D4": 293.665,
            "D#4": 311.127,
            "E4": 329.628,
            "F4": 349.228,
            "F#4": 369.994,
            "G4": 391.995,
            "G#4": 415.305,
            "A4": 440.000,
            "A#4": 466.164,
            "B4": 493.883,
            "C5": 523.251,
            "C#5": 554.365,
            "D5": 587.330,
            "D#5": 622.254,
            "E5": 659.255,
            "F5": 698.457,
            "F#5": 739.989,
            "G5": 783.991,
            "G#5": 830.609,
            "A5": 880.000,
            "A#5": 932.328,
            "B5": 987.767,
            # First file (C6 to B7)
            "C6": 1046.502,
            "C#6": 1108.731,
            "D6": 1174.659,
            "D#6": 1244.508,
            "E6": 1318.510,
            "F6": 1396.913,
            "F#6": 1479.978,
            "G6": 1567.982,
            "G#6": 1661.219,
            "A6": 1760.000,
            "A#6": 1864.655,
            "B6": 1975.533,
            "C7": 2093.005,
            "C#7": 2217.461,
            "D7": 2349.318,
            "D#7": 2489.016,
            "E7": 2637.021,
            "F7": 2793.826,
            "F#7": 2959.956,
            "G7": 3135.964,
            "G#7": 3322.438,
            "A7": 3520.000,
            "A#7": 3729.310,
            "B7": 3951.066,
        }

    def record_audio(self):
        if not self.is_active or self.stream is None:
            return np.zeros(self.buffer_samples, dtype=np.int16)
        try:
            data = self.stream.read(self.buffer_samples, exception_on_overflow=False)
            return np.frombuffer(data, dtype=np.int16)
        except Exception as e:
            print("Audio read error:", e)
            return np.zeros(self.buffer_samples, dtype=np.int16)

    def get_frequency(self, signal):
        fft_result = np.fft.fft(signal)
        frequencies = np.fft.fftfreq(len(signal), 1/self.sr)
        index_max = np.argmax(np.abs(fft_result))
        return abs(frequencies[index_max])

    def assign_note(self, measured_freq):
        best_note = None
        best_diff = float("inf")
        for note, ref_freq in self.allowed_notes.items():
            diff = abs(measured_freq - ref_freq)
            margin = ref_freq * self.tolerance
            if diff <= margin and diff < best_diff:
                best_diff = diff
                best_note = note
        return best_note if best_note is not None else ""

    def get_current_note(self):
        signal = self.record_audio()
        raw_freq = self.get_frequency(signal)
        
        # Apply exponential smoothing to reduce flickering
        if self.last_frequency is None:
            self.last_frequency = raw_freq
        else:
            self.last_frequency = (self.smoothing_factor * raw_freq +
                                   (1 - self.smoothing_factor) * self.last_frequency)
        
        new_note = self.assign_note(self.last_frequency)
        
        # Hysteresis: only change the locked note if the new note is different for enough cycles
        if new_note == self.stable_note:
            self.change_counter = 0
        else:
            self.change_counter += 1
            if self.change_counter >= self.change_threshold:
                self.stable_note = new_note
                self.change_counter = 0
        return self.stable_note

    def get_last_frequency(self):
        return self.last_frequency if self.last_frequency is not None else 0

    def set_tolerance(self, new_tolerance):
        self.tolerance = new_tolerance

    def start_processing(self):
        if self.stream is None:
            try:
                self.stream = self.pa.open(format=pyaudio.paInt16,
                                         channels=1,
                                         rate=self.sr,
                                         input=True,
                                         frames_per_buffer=self.buffer_samples,
                                         stream_callback=None)
                self.stream.start_stream()
            except Exception as e:
                print("Error opening audio stream:", e)
                return
        self.is_active = True

    def stop_processing(self):
        self.is_active = False
        self.last_frequency = None
        self.stable_note = ""
        self.change_counter = 0
        if self.stream is not None:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass
            self.stream = None

    def close(self):
        self.stop_processing()
        if self.pa:
            self.pa.terminate()
