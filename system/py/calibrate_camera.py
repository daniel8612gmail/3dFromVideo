import cv2
import numpy as np
import yaml
import os
import glob
import argparse
import shutil
from pathlib import Path

# ---------------------------------
# Argumenty
# ---------------------------------

parser = argparse.ArgumentParser()

parser.add_argument(
    "--device",
    required=True,
    help="Device ID, device folder name"
)
parser.add_argument(
    "--user",
    required=True,
    help="User ID, user folder name"
)
parser.add_argument(
    "--videoFile",
    help="Path to video file to extract frames from"
)

args = parser.parse_args()

DEVICE_ID = args.device
VIDEO_FILE = args.videoFile
USER_ID = args.user


def extractFrames(videoPath, framePath, frameSteps):
    print("Frame extraction...")
    cap = cv2.VideoCapture(
        videoPath
    )
    frame_id = 0
    saved = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_id % frameSteps == 0:
            filename = os.path.join(
                framePath,
                f"{saved:04d}.jpg"
            )
            cv2.imwrite(
                filename,
                frame
            )
            print("Frame saved:", filename)
            saved += 1
        frame_id += 1
    cap.release()
    print(
        "Frames total:",
        saved
    )

# ---------------------------------
# Znalezienie urządzenia
# ---------------------------------



DEVICE_PATH = Path(VIDEO_FILE).parents[3]


print(
    "Device:",
    DEVICE_PATH
)

# ---------------------------------
# Konfiguracja
# ---------------------------------

CONFIG_FILE = os.path.join(
    Path(VIDEO_FILE).parents[7],
    "system",
    "calibration",
    "calibration.yaml"
)

with open(CONFIG_FILE) as f:
    config = yaml.safe_load(f)

corners = (
    config["checkerboard"]["corners_x"],
    config["checkerboard"]["corners_y"]
)

square_size = (
    config["checkerboard"]["square_size_mm"]
)

frame_step = (
    config["processing"]["frame_step"]
)

minimum_frames = (
    config["processing"]["minimum_frames"]
)

# ---------------------------------
# Ścieżki urządzenia
# ---------------------------------

FRAME_DIR = os.path.join(
    DEVICE_PATH,
    "calibration",
    "frames"
)


OUTPUT_FILE = os.path.join(
    DEVICE_PATH,
    "calibration",
    "current",
    "camera.yaml"
)

os.makedirs(
    os.path.dirname(OUTPUT_FILE),
    exist_ok=True
)

# ---------------------------------
# Wycinanie klatek
# ---------------------------------

if VIDEO_FILE:
    if os.path.exists(FRAME_DIR):
        shutil.rmtree(FRAME_DIR)
    os.makedirs(
        FRAME_DIR,
        exist_ok=True
    )
    extractFrames(
        VIDEO_FILE,
        FRAME_DIR,
        frame_step
    )
    os.remove(VIDEO_FILE)
else:
    print(
        "No video file, using existing frames"
    )

# ---------------------------------
# Punkty wzorcowe
# ---------------------------------

objp = np.zeros(
    (
        corners[0] * corners[1],
        3
    ),
    np.float32
)


objp[:, :2] = np.mgrid[
    0:corners[0],
    0:corners[1]
].T.reshape(-1,2)


objp *= square_size



object_points = []
image_points = []

image_size = None



# ---------------------------------
# Wyszukiwanie planszy
# ---------------------------------

print(
    "Detecting checkerboard..."
)


for file in glob.glob(
    FRAME_DIR + "/*.jpg"
):

    img = cv2.imread(file)

    gray = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2GRAY
    )


    image_size = gray.shape[::-1]


    found, pts = cv2.findChessboardCorners(
        gray,
        corners
    )


    if found:

        pts = cv2.cornerSubPix(
            gray,
            pts,
            (11,11),
            (-1,-1),
            (
                cv2.TERM_CRITERIA_EPS +
                cv2.TERM_CRITERIA_MAX_ITER,
                30,
                0.001
            )
        )


        object_points.append(objp)
        image_points.append(pts)


        print(
            "OK",
            os.path.basename(file)
        )
    else:
        print(
            "Checkerboard not found:",
            os.path.basename(file)
        )
        os.remove(file)

print(
    "Correctly detected frames:",
    len(object_points)
)



if len(object_points) < minimum_frames:

    raise Exception(
        "Not enough good frames"
    )



# ---------------------------------
# Kalibracja
# ---------------------------------

print(
    "Calibrating..."
)


rms, K, D, rvec, tvec = cv2.calibrateCamera(
    object_points,
    image_points,
    image_size,
    None,
    None
)

# ---------------------------------
# Zapis
# ---------------------------------

result = {

    "device_id": DEVICE_ID,

    "image_width":
        image_size[0],

    "image_height":
        image_size[1],


    "camera_matrix":
        K.tolist(),


    "distortion":
        D.tolist(),


    "checkerboard":
    {
        "corners_x": corners[0],
        "corners_y": corners[1],
        "square_size_mm": square_size
    },


    "rms_error":
        float(rms)

}



with open(
    OUTPUT_FILE,
    "w"
) as f:

    yaml.dump(
        result,
        f
    )


print()
print(
    "Gotowe."
)

print(
    "Wynik:",
    OUTPUT_FILE
)

print(
    "RMS:",
    rms
)

