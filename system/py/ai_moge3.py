import cv2
import torch
import numpy as np
from pathlib import Path
import argparse
# ============================================================
# ARGUMENTY
# ============================================================
parser = argparse.ArgumentParser()
parser.add_argument(
    "-i",
    required=True,
    help="Path to the input directory"
)
args = parser.parse_args()
INPUT_DIR = Path(args.i)

# ============================================================
# KONFIGURACJA
# ============================================================
MODEL_PATH = Path(
    r"D:\AI3d\models\moge-3-vitl.pt"
)
DEVICE = "cuda"
USE_FP16 = True
REFINE_STEPS = 3
RESOLUTION_LEVEL = 9

# ============================================================
# IMPORT MOGE
# ============================================================
from moge.model import import_model_class_by_version

# ============================================================
# SPRAWDZENIE
# ============================================================
if not INPUT_DIR.exists():
    raise RuntimeError(
        f"Input folder does not exist:\n{INPUT_DIR}"
    )

if not MODEL_PATH.exists():
    raise RuntimeError(
        f"MoGe-3 model does not exist:\n{MODEL_PATH}"
    )

# ============================================================
# MODEL
# ============================================================
print("Loading MoGe-3...")
device = torch.device(DEVICE)
MoGeModel = import_model_class_by_version("v3")
model = (
    MoGeModel
    .from_pretrained(str(MODEL_PATH))
    .to(device)
    .eval()
)
print("MoGe-3 loaded.")

# ============================================================
# PLIKI
# ============================================================
image_paths = sorted(
    p for p in INPUT_DIR.iterdir()
    if p.is_file()
    and p.suffix.lower() in {
        ".jpg",
        ".jpeg",
        ".png"
    }
)
if not image_paths:
    raise RuntimeError(
        f"No images found in:\n{INPUT_DIR}"
    )

print(
    f"Found {len(image_paths)} images."
)
print()

def save_output(path, points, depth, mask, normals):
    torch.save({
        "points": points.detach().cpu(),
        "depth": depth.detach().cpu(),
        "mask": mask.detach().cpu(),
        "normals": normals.detach().cpu(),
    }, path)


def createDebugImage(depth, mask, normals, output_dbg_path):

    # -----------------------------
    # Convert to numpy
    # -----------------------------

    if hasattr(depth, "detach"):
        depth = depth.detach().float().cpu().numpy()

    if hasattr(mask, "detach"):
        mask = mask.detach().cpu().numpy()

    if hasattr(normals, "detach"):
        normals = normals.detach().float().cpu().numpy()

    depth = np.squeeze(depth)
    mask = np.squeeze(mask).astype(bool)
    normals = np.squeeze(normals)

    # -----------------------------
    # DEPTH
    # -----------------------------

    depth_img = np.zeros(depth.shape, dtype=np.uint8)

    valid = mask & np.isfinite(depth)

    if np.any(valid):
        dmin = depth[valid].min()
        dmax = depth[valid].max()

        if dmax > dmin:
            depth_img[valid] = (
                (depth[valid] - dmin)
                / (dmax - dmin)
                * 255
            ).astype(np.uint8)

    depth_img = cv2.applyColorMap(
        depth_img,
        cv2.COLORMAP_TURBO
    )

    # nieważne piksele = czarne
    depth_img[~valid] = 0

    # -----------------------------
    # MASK
    # -----------------------------

    mask_img = np.zeros(
        mask.shape,
        dtype=np.uint8
    )

    mask_img[mask] = 255

    # -----------------------------
    # NORMALS
    # -----------------------------

    # [-1, 1] -> [0, 255]
    normals_img = (
        (np.clip(normals, -1.0, 1.0) + 1.0)
        * 127.5
    ).astype(np.uint8)

    # nieważne piksele = czarne
    normals_img[~mask] = 0

    # RGB -> BGR dla OpenCV
    normals_img = cv2.cvtColor(
        normals_img,
        cv2.COLOR_RGB2BGR
    )

    # -----------------------------
    # SAVE
    # -----------------------------

    output_dbg_path = str(output_dbg_path)

    cv2.imwrite(
        output_dbg_path + "_depth.png",
        depth_img
    )

    cv2.imwrite(
        output_dbg_path + "_mask.png",
        mask_img
    )

    cv2.imwrite(
        output_dbg_path + "_normals.png",
        normals_img
    )

    print("Debug images saved:")
    print(output_dbg_path + "_depth.png")
    print(output_dbg_path + "_mask.png")
    print(output_dbg_path + "_normals.png")


# ============================================================
# PRZETWARZANIE
# ============================================================
for index, image_path in enumerate(
    image_paths,
    1
):
    output_dbg_path = INPUT_DIR / image_path.stem
    output_path = output_dbg_path / "moge3.pt"

    if output_path.exists():
        print(
            f"[{index}/{len(image_paths)}] "
            f"{image_path.name} - skipped (already processed)"
        )
        continue

    print(
        f"[{index}/{len(image_paths)}] "
        f"{image_path.name}"
    )
    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------
    image = cv2.imread(
        str(image_path)
    )
    if image is None:
        print(
            "ERROR: cannot read image"
        )
        continue
    image = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2RGB
    )
    # --------------------------------------------------------
    # TORCH
    # --------------------------------------------------------
    image_tensor = torch.from_numpy(
        image.astype(
            np.float32
        ) / 255.0
    ).to(device)
    image_tensor = (
        image_tensor
        .permute(2, 0, 1)
        .contiguous()
    )
    # --------------------------------------------------------
    # MOGE-3
    # --------------------------------------------------------
    with torch.inference_mode():
        output = model.infer(
            image_tensor,
            resolution_level=RESOLUTION_LEVEL,
            refine_steps=REFINE_STEPS,
            use_fp16=USE_FP16,
            apply_mask=True
        )
    print("MoGe-3 inference done.")
    # --------------------------------------------------------
    # POINTS
    # --------------------------------------------------------
    points = (
        output["points"]
        .detach()
        .float()
        .cpu()
        .numpy()
    )
    depth = (
        output["depth"]
        .detach()
        .float()
        .cpu()
        .numpy()
    )
    mask = (
        output["mask"]
        .detach()
        .cpu()
        .numpy()
        .astype(bool)
    )
    
    # --------------------------------------------------------
    # NORMALS
    # --------------------------------------------------------
    if "normal" not in output:
        raise RuntimeError(
            "MoGe-3 output does not contain normal."
        )
    normals = (
        output["normal"]
        .detach()
        .float()
        .cpu()
        .numpy()
    )
    # --------------------------------------------------------
    # VALID VALUES
    # --------------------------------------------------------
    finite = (
        np.isfinite(
            points
        ).all(axis=2)
        &
        np.isfinite(
            depth
        )
        &
        np.isfinite(
            normals
        ).all(axis=2)
    )
    mask &= finite
    
    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    output_dbg_path.mkdir(
        parents=True,
        exist_ok=True
    )
    
    # --------------------------------------------------------
    #   SNAP NORMALS
    # --------------------------------------------------------
    print("snap_normals")
    points = output["points"].float().cuda()
    depth = output["depth"].float().cuda()
    mask = output["mask"].bool().cuda()
    normals = output["normal"].float().cuda()
    
    save_output(
        output_path,
        points,
        depth,
        mask,
        normals
    )
    
    createDebugImage(depth, mask, normals, output_dbg_path / "debug")

    print(
        f"  saved    : "
        f"{output_dbg_path}"
    )
    # --------------------------------------------------------
    # CLEANUP
    # --------------------------------------------------------
    del output
    del image_tensor
    del points
    del depth
    del normals
    del mask
    torch.cuda.empty_cache()

print()
print("========================================")
print("DONE")
print("========================================")