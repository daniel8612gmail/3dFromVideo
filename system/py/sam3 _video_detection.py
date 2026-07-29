from pathlib import Path
import numpy as np
import argparse

from sam3.model_builder import build_sam3_video_predictor

parser = argparse.ArgumentParser()
parser.add_argument(
    "--videoFile",
    help="Path to video file to extract frames from"
)
parser.add_argument(
    "--prompt",
    required=True,
    help="What to detect"
)
parser.add_argument(
    "--outputPath",
    required=True,
    help="Path to the output directory"
)

BASE_DIR = Path(__file__).resolve().parent.parent

args = parser.parse_args()

VIDEO = BASE_DIR / args.videoFile
PROMPT = args.prompt
OUTPUT_DIR = BASE_DIR / args.outputPath

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
checkpoint_path = BASE_DIR / "models" / "sam3" / "sam3.pt"
# Load predictor
predictor = build_sam3_video_predictor(checkpoint_path=checkpoint_path)

# Start session
response = predictor.handle_request(
    request={
        "type": "start_session",
        "resource_path": str(VIDEO),
    }
)
session_id = response["session_id"]

# Prompt
response = predictor.handle_request(
    request={
        "type": "add_prompt",
        "session_id": session_id,
        "frame_index": 0,
        "text": PROMPT,
    }
)

print("Initial response keys:")
print(response.keys())

# Propagate through video
for response in predictor.propagate_in_video(
    session_id,
    direction="forward"
):
    frame_index = response["frame_index"]
    outputs = response["outputs"]
    # pierwszy raz pokaż strukturę
    if frame_index == 0:
        print(outputs.keys())
    masks = outputs["out_binary_masks"]
    # Tensor -> numpy
    if hasattr(masks, "cpu"):
        masks = masks.cpu().numpy()
    # kilka masek -> jedna
    mask = np.any(masks, axis=0).astype(np.uint8) * 255
    cv2.imwrite(
        str(OUTPUT_DIR / f"frame_{frame_index:06d}.png"),
        mask,
    )
print("Done.")