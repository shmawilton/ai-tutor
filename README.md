# Flute Tutor

A desktop application that helps flute players improve their playing by combining **real-time posture detection**, a **chromatic tuner**, **sheet music management**, and **pitch-based practice analysis** — all in a single PySide6 (Qt) GUI.

## Features

- **Posture Detection** — Live webcam feed that detects the player using a MobileNet-SSD person detector, then classifies their posture as *Correct* or *Incorrect* with a fine-tuned ResNet18 model. Correct posture is outlined in green, incorrect in red.
- **Real-Time Tuner** — FFT-based pitch detection from the microphone (48 kHz via PyAudio). Shows the detected note, deviation in cents, a live pitch-deviation graph, an adjustable tolerance slider, and target-note matching with visual feedback.
- **Sheet Music Library** — Import sheet music as PDF plus a reference audio file. Files are stored as BLOBs in a local SQLite database with metadata (title, tempo, time signature, level, key signature). Includes PDF rendering and zoom controls.
- **Practice Mode** — Practice window showing posture feedback and sheet music side-by-side. Real-time pitch recognition (librosa + sounddevice) compares your performance against the reference audio and reports accuracy over time.
- **Practice History** — Session metrics (accuracy, duration, intonation, rhythm, tempo, etc.) are persisted in the `practice_sessions` table for tracking progress.

## Tech Stack

- **GUI:** PySide6, pyqtgraph, matplotlib
- **Audio:** PyAudio, sounddevice, librosa, NumPy, SciPy
- **Computer Vision / ML:** OpenCV (MobileNet-SSD Caffe model), PyTorch + torchvision (ResNet18), scikit-learn
- **PDF:** PyMuPDF
- **Database:** SQLite (`database/sheet_music.db`)

## Project Structure

| File | Description |
|------|-------------|
| `main.py` | Application entry point. Tabbed window: "Posture & Tuner" tab and "Sheet Music" tab. |
| `Tuner.py` | Tuner UI window (`TunerWindow`) — note display, deviation meter/graph, target note input. |
| `tuner_engine.py` | Audio capture + FFT pitch detection, note assignment with smoothing and hysteresis. |
| `sheet_music.py` | Sheet music library widget — import dialog, PDF display, zoom, reference audio playback. |
| `practice_window.py` | Side-by-side practice window (posture camera + sheet music + pitch recording). |
| `pitch.py` | `PitchDetectionWidget` — real-time practice session comparing performance vs. reference pitch. |
| `database/sheet_music_db.py` | SQLite layer: `sheet_music` table (PDF/audio BLOBs) and `practice_sessions` table. |
| `posture_train.py` | Trains the ResNet18 posture classifier; logs to `training_log.csv` and saves `best_posture_model.pth`. |
| `crop_posture.py` | Splits raw posture images into `posture_data/{train,val,test}` (70/15/15). |
| `analyze_training.py` | Plots/analyzes the posture training log. |

## Requirements

- Python 3.10+
- Webcam (posture detection) and microphone (tuner / practice)
- Required model files in the project root:
  - `MobileNetSSD_deploy.prototxt`
  - `MobileNetSSD_deploy.caffemodel`
  - `best_posture_model.pth` (produced by `posture_train.py`, or use the included checkpoint)

Python dependencies:

```bash
pip install PySide6 opencv-python torch torchvision pillow numpy \
            pyaudio pyqtgraph librosa sounddevice matplotlib scipy \
            pymupdf scikit-learn
```

> Note: `PyAudio` may require a prebuilt wheel on Windows (`pip install pipwin && pipwin install pyaudio`) or use `pip install pyaudio` with a matching Python version.

## Usage

```bash
python main.py
```

- **Posture & Tuner tab:** webcam posture check on the left, tuner on the right. Press **Play** to start tuning; optionally set a target note (e.g., `A4`, `G#5`) and adjust the tolerance slider.
- **Sheet Music tab:** click **Import Sheet Music** to add a PDF + reference audio. Select a piece to view it, play its reference audio, or press **Practice with Pitch Detection** to open the practice window.

## Training the Posture Model

1. Place raw images in `data/raw/flutist_with_flute/{correct_posture,incorrect_posture}`.
2. Run `python crop_posture.py` to create the train/val/test split in `posture_data/`.
3. Run `python posture_train.py` — fine-tunes ResNet18 for 50 epochs, saves `best_posture_model.pth`, writes `training_log.csv`, and outputs loss/accuracy plots and a confusion matrix.
