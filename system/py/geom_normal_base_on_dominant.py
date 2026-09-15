import torch
import torch.nn.functional as F


def create_group_normals(
    normals,
    labels,
    mask
):
    original_shape = normals.shape

    flat_normals = normals.reshape(-1, 3)
    flat_labels = labels.reshape(-1)
    flat_mask = mask.reshape(-1).bool()

    valid = flat_mask & (flat_labels >= 0)

    group_normals = torch.zeros(
        labels.max() + 1,
        3,
        device=normals.device,
        dtype=normals.dtype
    )

    group_normals.index_add_(
        0,
        flat_labels[valid],
        flat_normals[valid]
    )

    counts = torch.bincount(
        flat_labels[valid],
        minlength=group_normals.shape[0]
    ).to(normals.dtype)

    group_normals = group_normals / counts.clamp_min(1).unsqueeze(1)

    group_normals = F.normalize(
        group_normals,
        dim=1
    )

    new_normals = torch.zeros_like(
        flat_normals
    )

    new_normals[valid] = group_normals[
        flat_labels[valid]
    ]

    return new_normals.reshape(original_shape), group_normals