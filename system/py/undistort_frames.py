import cv2
import yaml
import os
import glob
import argparse
parser = argparse.ArgumentParser()

parser.add_argument(
    "--inputPath",
    required=True,
    help="Path to the input directory"
)
parser.add_argument(
    "--calibrationPath",
    required=True,
    help="Path to the calibration file"
)
parser.add_argument(
    "--outputPath",
    required=True,
    help="Path to the output directory"
)

args = parser.parse_args()

INPUT_DIR = args.inputPath
CALIBRATION_PATH = args.calibrationPath
OUTPUT_DIR = args.outputPath

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)

# -----------------------------
# Wczytanie kalibracji
# -----------------------------

with open(CALIBRATION_PATH, "r") as f:
    calibration = yaml.safe_load(f)

camera_matrix = calibration["camera_matrix"]
distortion = calibration["distortion"]

import numpy as np

camera_matrix = np.array(
    camera_matrix,
    dtype=np.float64
)
distortion = np.array(
    distortion,
    dtype=np.float64
)

print("Camera matrix:")
print(camera_matrix)
print("Distortion:")
print(distortion)

# Obróbka klatek
extensions = [
    "*.jpg",
    "*.jpeg",
    "*.png"
]

files = []

for ext in extensions:
    files.extend(
        glob.glob(
            os.path.join(INPUT_DIR, ext)
        )
    )

files = sorted(files)

print(
    "Klatek:",
    len(files)
)
for file in files:
    img = cv2.imread(file)
    if img is None:
        print(
            "Nie można odczytać:",
            file
        )
        continue
    h,w = img.shape[:2]
    # korekcja
    corrected = cv2.undistort(
        img,
        camera_matrix,
        distortion
    )
    output = os.path.join(
        OUTPUT_DIR,
        os.path.basename(file)
    )
    cv2.imwrite(
        output,
        corrected
    )
    print(
        "OK:",
        output
    )
print("Gotowe")