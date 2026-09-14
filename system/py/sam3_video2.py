from pathlib import Path
import argparse
import cv2
import numpy as np
import torch

from sam3.model_builder import build_sam3_video_predictor

# --------------------------------------------------
# Args
# --------------------------------------------------

parser = argparse.ArgumentParser()

parser.add_argument(
    "--videoFile",
    required=True,
)

parser.add_argument(
    "--prompt",
    required=True,
)

parser.add_argument(
    "--outputPath",
    required=True,
)

args = parser.parse_args()

# --------------------------------------------------
# Paths
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

VIDEO = BASE_DIR / args.videoFile
PROMPT = args.prompt

OUTPUT_DIR = BASE_DIR / args.outputPath
OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

checkpoint_path = (
    BASE_DIR
    / "models"
    / "sam3"
    / "sam3.pt"
)

# --------------------------------------------------
# CUDA
# --------------------------------------------------

if not torch.cuda.is_available():
    raise RuntimeError("CUDA not available")

device = "cuda"

torch.backends.cudnn.benchmark = True
torch.set_float32_matmul_precision("high")

torch.cuda.empty_cache()

print(
    "GPU:",
    torch.cuda.get_device_name(0)
)

# --------------------------------------------------
# Model
# --------------------------------------------------

predictor = build_sam3_video_predictor(
    checkpoint_path=checkpoint_path
)

print(
    "VRAM after model:",
    round(
        torch.cuda.memory_allocated() / 1024**3,
        2
    ),
    "GB"
)

# --------------------------------------------------
# Inference
# --------------------------------------------------

with torch.inference_mode():

    with torch.autocast(
        device_type="cuda",
        dtype=torch.float16
    ):

        # ------------------------------
        # Start session
        # ------------------------------

        response = predictor.handle_request(
            request={
                "type": "start_session",
                "resource_path": str(VIDEO),
            }
        )

        session_id = response["session_id"]

        print(
            "VRAM after session:",
            round(
                torch.cuda.memory_allocated() / 1024**3,
                2
            ),
            "GB"
        )

        # ------------------------------
        # Initial prompt
        # ------------------------------

        predictor.handle_request(
            request={
                "type": "add_prompt",
                "session_id": session_id,
                "frame_index": 0,
                "text": PROMPT,
            }
        )

        print(
            "VRAM after prompt:",
            round(
                torch.cuda.memory_allocated() / 1024**3,
                2
            ),
            "GB"
        )

        # ------------------------------
        # Video propagation
        # ------------------------------

        for frame_count, response in enumerate(
            predictor.propagate_in_video(
                session_id,
                direction="forward"
            )
        ):

            frame_index = response["frame_index"]

            outputs = response["outputs"]

            masks = outputs["out_binary_masks"]

            if torch.is_tensor(masks):
                masks = masks.detach().cpu().numpy()

            mask = (
                np.any(
                    masks,
                    axis=0
                ).astype(np.uint8)
                * 255
            )

            cv2.imwrite(
                str(
                    OUTPUT_DIR /
                    f"frame_{frame_index:06d}.png"
                ),
                mask
            )

            # zwalnianie pamięci
            del outputs
            del masks
            del mask

            if frame_count % 50 == 0:

                torch.cuda.empty_cache()

                print(
                    f"frame={frame_index}",
                    "allocated=",
                    round(
                        torch.cuda.memory_allocated()
                        / 1024**3,
                        2
                    ),
                    "GB"
                )

print("Done.")