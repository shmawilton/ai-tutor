import os
import random
import shutil

random.seed(42)

SRC_CORRECT = "data/raw/flutist_with_flute/correct_posture"
SRC_INCORRECT = "data/raw/flutist_with_flute/incorrect_posture"

DEST_DIR = "posture_data"  # new dataset root
splits = ['train', 'val', 'test']
ratios = [0.7, 0.15, 0.15]  # train, val, test

for split in splits:
    os.makedirs(os.path.join(DEST_DIR, split, "correct_posture"), exist_ok=True)
    os.makedirs(os.path.join(DEST_DIR, split, "incorrect_posture"), exist_ok=True)

def split_folder(src_folder, class_name):
    files = [f for f in os.listdir(src_folder) if f.lower().endswith(('.jpg', '.png'))]
    random.shuffle(files)
    total = len(files)
    train_end = int(ratios[0] * total)
    val_end = train_end + int(ratios[1] * total)

    # Slices
    train_files = files[:train_end]
    val_files = files[train_end:val_end]
    test_files = files[val_end:]

    # Move files
    for f in train_files:
        shutil.copy(os.path.join(src_folder, f), os.path.join(DEST_DIR, "train", class_name, f))
    for f in val_files:
        shutil.copy(os.path.join(src_folder, f), os.path.join(DEST_DIR, "val", class_name, f))
    for f in test_files:
        shutil.copy(os.path.join(src_folder, f), os.path.join(DEST_DIR, "test", class_name, f))

split_folder(SRC_CORRECT, "correct_posture")
split_folder(SRC_INCORRECT, "incorrect_posture")

print("Splitting complete!")
