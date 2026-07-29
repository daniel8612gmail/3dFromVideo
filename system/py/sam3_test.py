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
import torch
import os
import time
start_time = time.perf_counter()
#################################### For Image ####################################
from PIL import Image
from sam3.model_builder import build_sam3_image_model
from sam3.model.sam3_image_processor import Sam3Processor

import json
import numpy as np
from PIL import Image


torch.set_float32_matmul_precision("high")

BASE_DIR = Path(__file__).resolve().parent.parent
checkpoint_path = BASE_DIR / "models" / "sam3" / "sam3.pt"
# Load the model
model = build_sam3_image_model(checkpoint_path=checkpoint_path)

model = model.float()
model.eval()

processor = Sam3Processor(model)
# Load an image

imagePath = "../test/home1.jpg";

image = Image.open(BASE_DIR / imagePath)

with torch.autocast(
    device_type="cuda",
    dtype=torch.float16
):
    inference_state = processor.set_image(image)

    output = processor.set_text_prompt(
        state=inference_state,
        prompt="detect building, houses and walls ",
    )

    # Get the masks, bounding boxes, and scores
    masks, boxes, scores = output["masks"], output["boxes"], output["scores"]

    OUTPUT_DIR = Path(BASE_DIR / "../test/sam3")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


    # zapis masek
    for i, mask in enumerate(masks):
        # mask jest prawdopodobnie torch.Tensor
        mask_np = mask.cpu().numpy()

        # jeżeli ma wymiar [1,H,W], usuń pierwszy wymiar
        mask_np = np.squeeze(mask_np)

        # zapis jako czarno-biały PNG
        mask_img = Image.fromarray(
            (mask_np * 255).astype(np.uint8)
        )

        mask_img.save(
            OUTPUT_DIR / f"mask_{i}.png"
        )


    # zapis bbox i score
    data = {
        "boxes": boxes.cpu().numpy().tolist(),
        "scores": scores.cpu().numpy().tolist()
    }

    with open(
        OUTPUT_DIR / "detections.json",
        "w"
    ) as f:
        json.dump(data, f, indent=2)

end_time = time.perf_counter()
elapsed = time.perf_counter() - start_time

minutes = int(elapsed // 60)
seconds = elapsed % 60

print(f"Czas działania: {minutes} min {seconds:.2f} s")