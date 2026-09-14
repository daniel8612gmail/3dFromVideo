from pathlib import Path
import argparse
parser = argparse.ArgumentParser()
parser.add_argument(
    "--file",
    required=True,
)
parser.add_argument(
    "--prompt",
    required=True,
)

args = parser.parse_args()

# --------------------------------------------------
# Paths
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent.parent

FILE = BASE_DIR / args.file
PROMPT = args.prompt
print("file", FILE)
OUTPUT_DIR = FILE.parent / FILE.stem
OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)
print("OUTPUT_DIR", OUTPUT_DIR)

from ultralytics import YOLO
model = YOLO("yolo26n-seg.pt")
results = model(FILE)
src = Path(FILE)

# katalog: <plik_bez_rozszerzenia>/yolo
output_dir = src.parent / src.stem / "yolo"
output_dir.mkdir(parents=True, exist_ok=True)

results = model(
    str(src),
    save=True,           # zapis obrazu/wideo z detekcjami
    save_txt=True,       # etykiety YOLO (*.txt)
    save_conf=True,      # confidence w plikach txt
    project=str(output_dir),
    name="",             # nie twórz exp, exp2...
    exist_ok=True
)


from ultralytics import settings
print("settings", settings)
print(settings["weights_dir"])