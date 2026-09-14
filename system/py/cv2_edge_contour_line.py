import time
start_time = time.perf_counter()

import cv2
import json
from pathlib import Path
import numpy as np
import argparse
from debugging import draw_lines_debug, save_debug_contours, save_debug_lines, save_debug_mask, save_debug_mask_overlay
from extract_geometry import draw_geometry_intersections, draw_geometry_lines, process_lines, save_geometry, save_lines, draw_geometry
from extract_corners import extract_corners
from repair_building_mask import repair_mask
from extract_boundary_edges import extract_boundary_edges
from detect_boundary_lines import detect_boundary_lines
from cv2_functions import edgedetection

parser = argparse.ArgumentParser()
parser.add_argument(
    "--imgPath",
    help="Path to frame IMG"
)
args = parser.parse_args()
IMG_PATH = args.imgPath
BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_FILE = BASE_DIR / IMG_PATH
OUTPUT_DIR = INPUT_FILE.parent / INPUT_FILE.stem
OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)
geometry_dir = OUTPUT_DIR #/ Path("geometry")
geometry_dir.mkdir(exist_ok=True)

# Wczytaj obraz
img = cv2.imread(INPUT_FILE)
# Load detections
detections_file = OUTPUT_DIR / "detections.json"

# Konwersja do skali szarości
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
lines = []

if not detections_file.exists():
    lines = edgedetection(img, 0, geometry_dir)
    objects = [{"id":"0001", "img": img}]
else:
    detections = json.load(open(OUTPUT_DIR / "detections.json"))
    objects = detections["objects"]
    
for obj in objects:
    obj_id = obj["id"]
    mask_file = OUTPUT_DIR / obj["mask"]["file"]
    print(f"Processing object {INPUT_FILE.stem} | {obj_id}")

    # Wczytanie maski
    mask = cv2.imread(mask_file, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        print("Missing mask:", mask_file)
        continue
    # upewnienie się że maska ma wartości 0/255
    mask = np.where(mask > 0,255,0).astype(np.uint8)

    # Wycięcie obiektu
    lines = edgedetection(img, obj_id, geometry_dir)



elapsed = (time.perf_counter() - start_time)
minutes = int( elapsed // 60)
seconds = elapsed % 60
print(f"Execution time: {minutes} min {seconds:.2f} s")