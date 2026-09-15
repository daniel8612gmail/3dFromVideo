import torch
import torch.nn.functional as F


@torch.no_grad()
def create_plane_tensor(points, normals, mask=None):
    """
    points  : [H, W, 3] CUDA
    normals : [H, W, 3] CUDA
    mask    : [H, W]    CUDA / bool

    return:
        planes : [H, W, 4] CUDA
                 [nx, ny, nz, d]

    Równanie:
        nx * X + ny * Y + nz * Z + d = 0
    """

    # normalizacja normalnych
    normals = F.normalize(normals.float(), dim=-1)
    points = points.float()

    # d = -n · P
    d = -(normals * points).sum(dim=-1, keepdim=True)

    # [H,W,3] + [H,W,1] -> [H,W,4]
    planes = torch.cat(
        (normals, d),
        dim=-1
    )

    # niepoprawne piksele
    if mask is not None:
        planes = planes.clone()
        planes[~mask] = 0.0

    return planes

def save_plane_debug(planes, mask, output_path):
    import torch
    import numpy as np
    import cv2

    if torch.is_tensor(planes):
        planes = planes.detach().float().cpu().numpy()

    if torch.is_tensor(mask):
        mask = mask.detach().cpu().numpy()

    normals = planes[..., :3]
    d = planes[..., 3]

    # --------------------------------------------------
    # NORMAL
    # --------------------------------------------------

    normal_img = (
        (np.clip(normals, -1.0, 1.0) + 1.0) * 127.5
    ).astype(np.uint8)

    normal_img[~mask] = 0

    # OpenCV zapisuje BGR
    normal_img = cv2.cvtColor(
        normal_img,
        cv2.COLOR_RGB2BGR
    )

    cv2.imwrite(
        str(output_path) + "_PlaneNormal.png",
        normal_img
    )

    # --------------------------------------------------
    # D
    # --------------------------------------------------

    valid_d = d[mask & np.isfinite(d)]

    d_img = np.zeros_like(d, dtype=np.uint8)

    if valid_d.size:
        d_min = np.percentile(valid_d, 2)
        d_max = np.percentile(valid_d, 98)

        if d_max > d_min:
            d_norm = np.clip(
                (d - d_min) / (d_max - d_min),
                0.0,
                1.0
            )

            d_img = (d_norm * 255).astype(np.uint8)

    d_img[~mask] = 0

    d_img = cv2.applyColorMap(
        d_img,
        cv2.COLORMAP_TURBO
    )

    d_img[~mask] = 0

    cv2.imwrite(
        str(output_path) + "_PlaneD.png",
        d_img
    )