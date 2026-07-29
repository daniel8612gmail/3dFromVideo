import warnings
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated"
)

warnings.filterwarnings(
    "ignore",
    message="Importing from .* is deprecated"
)

from pathlib import Path
import time
import json
import cv2

import torch
import numpy as np
from PIL import Image


import argparse
parser = argparse.ArgumentParser()
parser.add_argument(
    "--imgPath",
    help="Path to frame"
)
parser.add_argument(
    "--prompt",
    required=True,
    help="What to detect"
)
args = parser.parse_args()
IMG_PATH = args.imgPath
start_time = time.perf_counter()

torch.set_float32_matmul_precision("high")

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
image_path = BASE_DIR / IMG_PATH
output_dir = image_path.parent / image_path.stem
output_dir.mkdir(
    parents=True,
    exist_ok=True
)

checkpoint_path = (
    BASE_DIR /
    "models" /
    "sam3" /
    "sam3.pt"
)

from sam3.model_builder import build_sam3_image_model
from sam3.model.sam3_image_processor import Sam3Processor

# Load model
model = build_sam3_image_model(
    checkpoint_path=checkpoint_path
)

model = model.float()
model.eval()

processor = Sam3Processor(model)

# Load image
image = Image.open(
    image_path
).convert("RGB")

# SAM3 inference
with torch.autocast(
    device_type="cuda",
    dtype=torch.float16
):

    state = processor.set_image(image)

    output = processor.set_text_prompt(
        state=state,
        prompt="building"
    )
masks = output["masks"]
boxes = output["boxes"]
scores = output["scores"]
# print("boxes:", boxes.shape)
# Save detections
detections = {
    "image": {
        "file": str(image_path.name),
        "width": image.width,
        "height": image.height
    },

    "objects": []
}

for i, mask in enumerate(masks):
    # mask tensor -> numpy
    print("Maski:",
        i,
        mask.sum().item()
    )
    mask_np = mask.detach().cpu().numpy()

    mask_np = np.squeeze(mask_np)

    mask_bin = (
        mask_np > 0.5
    ).astype(np.uint8)

    # save mask
    mask_file = f"mask_{i:03d}.png"

    Image.fromarray(
        mask_bin * 255
    ).save(
        output_dir / mask_file
    )

    # bbox
    box = boxes[i].detach().cpu().numpy()

    x1, y1, x2, y2 = map(
        int,
        box
    )

    bbox_xywh = [
        x1,
        y1,
        x2-x1,
        y2-y1
    ]

    # area + centroid
    ys, xs = np.where(
        mask_bin > 0
    )

    area = int(
        len(xs)
    )

    if area > 0:

        centroid = [
            float(xs.mean()),
            float(ys.mean())
        ]

    else:

        centroid = [
            0,
            0
        ]

    # contour
    contours, _ = cv2.findContours(
        mask_bin,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    polygon = []

    if contours:

        largest = max(
            contours,
            key=cv2.contourArea
        )

        epsilon = 0.005 * cv2.arcLength(
            largest,
            True
        )

        approx = cv2.approxPolyDP(
            largest,
            epsilon,
            True
        )

        polygon = (
            approx.reshape(-1,2)
            .tolist()
        )

    # object json
    detections["objects"].append({

        "id": i,

        "score": float(
            scores[i]
            .detach()
            .cpu()
        ),

        "mask": {
            "file": f"{mask_file}",
            "area": area
        },

        "bbox": {

            "xyxy": [
                x1,
                y1,
                x2,
                y2
            ],

            "xywh": bbox_xywh
        },

        "centroid": centroid,

        "polygon": polygon

    })

# save json
with open(
    output_dir / "detections.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        detections,
        f,
        indent=2,
        ensure_ascii=False
    )

# Time
elapsed = (
    time.perf_counter()
    -
    start_time
)

minutes = int(
    elapsed // 60
)

seconds = elapsed % 60


print(
    f"Czas działania: {minutes} min {seconds:.2f} s"
)

print(
    f"Wykryto obiektów: {len(detections['objects'])}"
)