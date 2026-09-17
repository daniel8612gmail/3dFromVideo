import math
import torch
import torch.nn.functional as F


@torch.no_grad()
def find_plane_boundary_directions(
    plane_labels,
    min_boundary_pixels=20,
    num_directions=18
):
    if not plane_labels.is_cuda:
        raise ValueError("plane_labels must be CUDA")

    device = plane_labels.device
    h, w = plane_labels.shape

    valid = plane_labels >= 0

    pair_a = []
    pair_b = []
    pair_y = []
    pair_x = []

    def add_edges(a, b, y, x):
        valid_pair = (
            (a >= 0)
            & (b >= 0)
            & (a != b)
        )

        a = a[valid_pair]
        b = b[valid_pair]
        y = y[valid_pair]
        x = x[valid_pair]

        lo = torch.minimum(a, b)
        hi = torch.maximum(a, b)

        pair_a.append(lo)
        pair_b.append(hi)
        pair_y.append(y)
        pair_x.append(x)

    y, x = torch.meshgrid(
        torch.arange(h, device=device),
        torch.arange(w, device=device),
        indexing="ij"
    )

    add_edges(
        plane_labels[:, :-1],
        plane_labels[:, 1:],
        y[:, :-1],
        x[:, :-1]
    )

    add_edges(
        plane_labels[:-1, :],
        plane_labels[1:, :],
        y[:-1, :],
        x[:-1, :]
    )

    if not pair_a:
        return []

    pair_a = torch.cat(pair_a)
    pair_b = torch.cat(pair_b)
    pair_y = torch.cat(pair_y)
    pair_x = torch.cat(pair_x)

    pair_key = (
        pair_a.to(torch.int64) * plane_labels.numel()
        + pair_b.to(torch.int64)
    )

    unique_key, inverse, counts = torch.unique(
        pair_key,
        return_inverse=True,
        return_counts=True
    )

    keep = counts >= min_boundary_pixels

    if not keep.any():
        return []

    group_ids = torch.nonzero(
        keep,
        as_tuple=False
    ).squeeze(1)

    results = []

    bin_width = math.pi / num_directions

    for group_id in group_ids.tolist():

        pixels = (
            inverse == group_id
        )

        ys = pair_y[pixels].float()
        xs = pair_x[pixels].float()

        points = torch.stack(
            (xs, ys),
            dim=1
        )

        if points.shape[0] < min_boundary_pixels:
            continue

        center = points.mean(dim=0)

        q = points - center

        covariance = q.T @ q

        eigenvalues, eigenvectors = torch.linalg.eigh(
            covariance
        )

        direction = eigenvectors[:, -1]
        direction = F.normalize(
            direction,
            dim=0
        )

        angle = torch.atan2(
            direction[1],
            direction[0]
        )

        angle = torch.remainder(
            angle,
            math.pi
        )

        direction_bin = torch.floor(
            angle / bin_width
        ).long()

        direction_bin = direction_bin.clamp(
            0,
            num_directions - 1
        )

        boundary_length = torch.sqrt(
            eigenvalues[-1]
        ) * 2.0

        key = unique_key[group_id]

        plane_b = key % plane_labels.numel()
        plane_a = key // plane_labels.numel()

        results.append(
            {
                "plane_a": int(plane_a.item()),
                "plane_b": int(plane_b.item()),
                "pixels": int(points.shape[0]),
                "length": float(boundary_length.item()),
                "angle_deg": float(
                    angle.item() * 180.0 / math.pi
                ),
                "direction_bin": int(
                    direction_bin.item()
                ),
                "direction": direction.detach(),
                "center": center.detach(),
            }
        )

    results.sort(
        key=lambda x: x["length"],
        reverse=True
    )

    return results


import cv2
import numpy as np


def save_plane_boundaries_debug(
    image,
    boundaries,
    output_path,
    top_n=None,
    line_thickness=3,
):
    if torch.is_tensor(image):
        image = image.detach().cpu().numpy()

    image = np.asarray(image)

    if image.dtype != np.uint8:
        image = np.clip(image, 0, 255).astype(np.uint8)

    debug = image.copy()

    if top_n is not None:
        boundaries = boundaries[:top_n]

    rng = np.random.default_rng(12345)

    for i, boundary in enumerate(boundaries):
        center = boundary["center"]

        if torch.is_tensor(center):
            center = center.detach().cpu().numpy()

        direction = boundary["direction"]

        if torch.is_tensor(direction):
            direction = direction.detach().cpu().numpy()

        center = np.asarray(center, dtype=np.float32)
        direction = np.asarray(direction, dtype=np.float32)

        length = float(boundary["length"])

        half_length = length * 0.5

        p0 = center - direction * half_length
        p1 = center + direction * half_length

        p0 = tuple(
            np.round(p0).astype(int)
        )

        p1 = tuple(
            np.round(p1).astype(int)
        )

        color = tuple(
            int(v)
            for v in rng.integers(
                50,
                256,
                size=3
            )
        )

        cv2.line(
            debug,
            p0,
            p1,
            color,
            line_thickness,
            cv2.LINE_AA
        )

        cv2.circle(
            debug,
            p0,
            5,
            color,
            -1,
            cv2.LINE_AA
        )

        cv2.circle(
            debug,
            p1,
            5,
            color,
            -1,
            cv2.LINE_AA
        )

        text = (
            f"{i + 1}: "
            f"{boundary['plane_a']}-"
            f"{boundary['plane_b']} "
            f"{length:.0f}px "
            f"{boundary['angle_deg']:.1f}deg"
        )

        tx = int(center[0]) + 5
        ty = int(center[1]) - 5

        cv2.putText(
            debug,
            text,
            (tx, ty),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )

        cv2.putText(
            debug,
            text,
            (tx, ty),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            1,
            cv2.LINE_AA
        )

    cv2.imwrite(
        str(output_path),
        debug
    )