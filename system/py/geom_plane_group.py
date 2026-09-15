import math
import torch
import torch.nn.functional as F


@torch.no_grad()
def find_plane_groups(
    points,
    planes,
    mask,
    normal_angle_deg=5.0,
    distance_threshold=0.02,
    min_points=300
):
    if not points.is_cuda:
        raise ValueError("points must be CUDA")

    if not planes.is_cuda:
        raise ValueError("planes must be CUDA")

    if not mask.is_cuda:
        raise ValueError("mask must be CUDA")

    if points.ndim != 3 or points.shape[-1] != 3:
        raise ValueError("points must have shape [H,W,3]")

    if planes.ndim != 3 or planes.shape[-1] != 4:
        raise ValueError("planes must have shape [H,W,4]")

    if points.shape[:2] != planes.shape[:2]:
        raise ValueError("points and planes must have the same H,W")

    if mask.shape != points.shape[:2]:
        raise ValueError("mask must have shape [H,W]")

    device = points.device

    H, W = mask.shape

    valid = (
        mask.bool()
        & torch.isfinite(points).all(dim=-1)
        & torch.isfinite(planes).all(dim=-1)
    )

    if not valid.any():
        return (
            torch.full(
                (H, W),
                -1,
                dtype=torch.long,
                device=device
            ),
            torch.empty(
                0,
                dtype=torch.long,
                device=device
            ),
            torch.empty(
                0,
                4,
                dtype=planes.dtype,
                device=device
            )
        )

    p = points[valid]
    plane = planes[valid]

    n = F.normalize(
        plane[:, :3],
        dim=1
    )

    d = plane[:, 3]

    dominant_axis = torch.argmax(
        torch.abs(n),
        dim=1
    )

    axis_sign = torch.gather(
        n,
        1,
        dominant_axis[:, None]
    ).squeeze(1)

    flip = axis_sign < 0

    n = torch.where(
        flip[:, None],
        -n,
        n
    )

    d = torch.where(
        flip,
        -d,
        d
    )

    angle_step = math.radians(normal_angle_deg)

    normal_step = 2.0 * math.sin(
        angle_step * 0.5
    )

    normal_step = max(
        normal_step,
        1e-4
    )

    qn = torch.round(
        n / normal_step
    ).to(torch.int32)

    d_step = max(
        distance_threshold,
        1e-5
    )

    qd = torch.round(
        d / d_step
    ).to(torch.int32)

    qn = qn.to(torch.int64)
    qd = qd.to(torch.int64)

    min_int = torch.iinfo(torch.int32).min

    qn = qn.clamp(
        min_int,
        -min_int - 1
    )

    qd = qd.clamp(
        min_int,
        -min_int - 1
    )

    offset = 1000000

    key = (
        (qn[:, 0] + offset)
        * 4000000000000
        +
        (qn[:, 1] + offset)
        * 2000000
        +
        (qn[:, 2] + offset)
        * 1000
        +
        (qd + offset)
    )

    unique_key, inverse, counts = torch.unique(
        key,
        return_inverse=True,
        return_counts=True
    )

    valid_groups = counts >= min_points

    if not valid_groups.any():
        return (
            torch.full(
                (H, W),
                -1,
                dtype=torch.long,
                device=device
            ),
            torch.empty(
                0,
                dtype=torch.long,
                device=device
            ),
            torch.empty(
                0,
                4,
                dtype=planes.dtype,
                device=device
            )
        )

    group_ids = torch.nonzero(
        valid_groups,
        as_tuple=False
    ).squeeze(1)

    new_group_id = torch.full(
        (unique_key.shape[0],),
        -1,
        dtype=torch.long,
        device=device
    )

    new_group_id[group_ids] = torch.arange(
        group_ids.shape[0],
        device=device,
        dtype=torch.long
    )

    labels_valid = new_group_id[inverse]

    num_groups = group_ids.shape[0]

    group_normal_sum = torch.zeros(
        num_groups,
        3,
        dtype=n.dtype,
        device=device
    )

    group_d_sum = torch.zeros(
        num_groups,
        dtype=d.dtype,
        device=device
    )

    group_normal_sum.index_add_(
        0,
        labels_valid[labels_valid >= 0],
        n[labels_valid >= 0]
    )

    group_d_sum.index_add_(
        0,
        labels_valid[labels_valid >= 0],
        d[labels_valid >= 0]
    )

    group_counts = torch.bincount(
        labels_valid[labels_valid >= 0],
        minlength=num_groups
    ).to(n.dtype)

    group_normals = F.normalize(
        group_normal_sum
        /
        group_counts.clamp_min(1).unsqueeze(1),
        dim=1
    )

    group_d = (
        group_d_sum
        /
        group_counts.clamp_min(1)
    )

    group_planes = torch.cat(
        (
            group_normals,
            group_d[:, None]
        ),
        dim=1
    )

    # Rzeczywisty błąd punktu względem grupowej płaszczyzny
    group_n = group_normals[labels_valid.clamp_min(0)]
    group_d_value = group_d[labels_valid.clamp_min(0)]

    point_error = torch.abs(
        (p * group_n).sum(dim=1)
        +
        group_d_value
    )

    labels_valid = torch.where(
        point_error <= distance_threshold,
        labels_valid,
        torch.full_like(
            labels_valid,
            -1
        )
    )

    final_counts = torch.bincount(
        labels_valid[labels_valid >= 0],
        minlength=num_groups
    )

    keep = final_counts >= min_points

    if not keep.any():
        return (
            torch.full(
                (H, W),
                -1,
                dtype=torch.long,
                device=device
            ),
            torch.empty(
                0,
                dtype=torch.long,
                device=device
            ),
            torch.empty(
                0,
                4,
                dtype=planes.dtype,
                device=device
            )
        )

    kept_ids = torch.nonzero(
        keep,
        as_tuple=False
    ).squeeze(1)

    remap = torch.full(
        (num_groups,),
        -1,
        dtype=torch.long,
        device=device
    )

    remap[kept_ids] = torch.arange(
        kept_ids.shape[0],
        device=device,
        dtype=torch.long
    )

    labels_valid = remap[
        labels_valid.clamp_min(0)
    ]

    valid_after = labels_valid >= 0

    labels_valid = torch.where(
        valid_after,
        labels_valid,
        torch.full_like(
            labels_valid,
            -1
        )
    )

    final_planes = group_planes[kept_ids]

    final_counts = torch.bincount(
        labels_valid[valid_after],
        minlength=kept_ids.shape[0]
    )

    plane_labels = torch.full(
        (H, W),
        -1,
        dtype=torch.long,
        device=device
    )

    flat_labels = plane_labels.view(-1)

    valid_indices = torch.nonzero(
        valid.reshape(-1),
        as_tuple=False
    ).squeeze(1)

    flat_labels[
        valid_indices
    ] = labels_valid

    plane_labels = flat_labels.reshape(H, W)

    return (
        plane_labels,
        final_counts,
        final_planes
    )
    
#============================================================
# Debug
#============================================================
def save_plane_statistics(
    plane_labels,
    plane_counts,
    planes,
    output_path,
    top_n=100
):
    h, w = plane_labels.shape
    image_pixels = h * w

    top_n = min(top_n, plane_counts.numel())

    values, indices = torch.topk(
        plane_counts,
        k=top_n,
        largest=True,
        sorted=True
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"IMAGE_SIZE: {w} x {h}\n")
        f.write(f"IMAGE_PIXELS: {image_pixels}\n")
        f.write(f"PLANES_FOUND: {plane_counts.numel()}\n")
        f.write(f"TOP_PLANES: {top_n}\n")
        f.write("\n")

        f.write(
            "RANK\tPLANE_ID\tPIXELS\tCOVERAGE[%]"
            "\tNX\tNY\tNZ\tD\n"
        )

        for rank in range(top_n):
            plane_id = int(indices[rank].item())
            pixel_count = int(values[rank].item())

            coverage = (
                pixel_count
                / image_pixels
                * 100.0
            )

            plane = planes[plane_id]

            nx = float(plane[0].item())
            ny = float(plane[1].item())
            nz = float(plane[2].item())
            d = float(plane[3].item())

            f.write(
                f"{rank + 1}\t"
                f"{plane_id}\t"
                f"{pixel_count}\t"
                f"{coverage:.4f}\t"
                f"{nx:.6f}\t"
                f"{ny:.6f}\t"
                f"{nz:.6f}\t"
                f"{d:.6f}\n"
            )
            



#============================================================


import cv2
import numpy as np


def save_plane_groups_debug(
    plane_labels,
    plane_counts,
    planes,
    image,
    output_path,
    top_n=20
):
    if torch.is_tensor(plane_labels):
        labels = plane_labels.detach().cpu().numpy()
    else:
        labels = plane_labels

    if torch.is_tensor(plane_counts):
        counts = plane_counts.detach().cpu().numpy()
    else:
        counts = plane_counts

    if torch.is_tensor(image):
        image = image.detach().cpu().numpy()

    image = np.asarray(image)

    if image.dtype != np.uint8:
        image = np.clip(image, 0, 255).astype(np.uint8)

    h, w = labels.shape

    top_n = min(top_n, len(counts))

    top_indices = np.argsort(
        counts
    )[::-1][:top_n]

    colors = cv2.applyColorMap(
        np.linspace(
            0,
            255,
            top_n,
            dtype=np.uint8
        ).reshape(-1, 1),
        cv2.COLORMAP_TURBO
    ).reshape(-1, 3)

    color_map = np.zeros(
        (len(counts), 3),
        dtype=np.uint8
    )

    for i, plane_id in enumerate(top_indices):
        color_map[plane_id] = colors[i]

    groups = np.zeros(
        (h, w, 3),
        dtype=np.uint8
    )

    for plane_id in top_indices:
        groups[
            labels == plane_id
        ] = color_map[plane_id]

    overlay = image.copy()

    valid = np.zeros(
        (h, w),
        dtype=bool
    )

    for plane_id in top_indices:
        valid |= labels == plane_id

    overlay[valid] = cv2.addWeighted(
        image[valid],
        0.45,
        groups[valid],
        0.55,
        0
    )

    for rank, plane_id in enumerate(top_indices):

        ys, xs = np.where(
            labels == plane_id
        )

        if len(xs) == 0:
            continue

        cx = int(xs.mean())
        cy = int(ys.mean())

        coverage = (
            counts[plane_id]
            / float(h * w)
            * 100.0
        )

        text = (
            f"{rank + 1}: "
            f"{coverage:.1f}%"
        )

        cv2.putText(
            overlay,
            text,
            (cx, cy),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )

        cv2.putText(
            overlay,
            text,
            (cx, cy),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            tuple(int(x) for x in colors[rank]),
            1,
            cv2.LINE_AA
        )

    output_path = str(output_path)

    cv2.imwrite(
        output_path + "_all.png",
        groups
    )

    cv2.imwrite(
        output_path + "_overlay.png",
        overlay
    )