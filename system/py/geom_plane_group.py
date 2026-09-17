import torch

@torch.no_grad()
def find_plane_groups(
    planes,
    normals_consolidated,
    distance_threshold=0.02,
    min_points=300,
):
    if not planes.is_cuda:
        raise ValueError("planes must be CUDA")

    if not normals_consolidated.is_cuda:
        raise ValueError("normals_consolidated must be CUDA")

    if planes.ndim != 3 or planes.shape[-1] != 4:
        raise ValueError("planes must have shape [H,W,4]")

    if normals_consolidated.shape != planes.shape[:2] + (3,):
        raise ValueError(
            "normals_consolidated must have shape [H,W,3]"
        )

    device = planes.device
    dtype = planes.dtype
    h, w = planes.shape[:2]

    normals = normals_consolidated.float()
    d_map = planes[..., 3]

    # Zerowa normalna = nieaktywny piksel
    valid = (
        (torch.linalg.norm(normals, dim=-1) > 1e-8)
        & torch.isfinite(d_map)
        & torch.isfinite(normals).all(dim=-1)
    )

    plane_labels = torch.full(
        (h, w),
        -1,
        dtype=torch.long,
        device=device
    )

    # Pobieramy tylko aktywne piksele
    flat_valid = valid.reshape(-1)
    indices = torch.nonzero(
        flat_valid,
        as_tuple=False
    ).squeeze(1)

    if indices.numel() == 0:
        return (
            plane_labels,
            torch.empty(0, dtype=torch.long, device=device),
            torch.empty(0, 4, dtype=dtype, device=device)
        )

    flat_normals = normals.reshape(-1, 3)
    flat_d = d_map.reshape(-1)

    active_normals = flat_normals[indices]
    active_d = flat_d[indices]

    # normals_consolidated pochodzi z directions,
    # więc identyczne normalne mają identyczne wartości.
    unique_normals, normal_ids = torch.unique(
        active_normals,
        dim=0,
        return_inverse=True
    )

    group_counts = []
    group_d_sums = []
    group_normal_ids = []

    group_offset = 0

    # Maksymalnie 10 normalnych
    for normal_id in range(unique_normals.shape[0]):

        select = normal_ids == normal_id

        pixel_indices = indices[select]
        values = active_d[select]

        if values.numel() == 0:
            continue

        # Sortowanie po D
        order = torch.argsort(values)

        values = values[order]
        pixel_indices = pixel_indices[order]

        # Nowa grupa gdy różnica D przekracza próg
        breaks = torch.empty(
            values.shape[0],
            dtype=torch.bool,
            device=device
        )

        breaks[0] = True

        if values.numel() > 1:
            breaks[1:] = (
                values[1:] - values[:-1]
                > distance_threshold
            )

        local_ids = (
            torch.cumsum(
                breaks.to(torch.long),
                dim=0
            ) - 1
        )

        num_groups = int(local_ids[-1].item()) + 1

        global_ids = local_ids + group_offset

        plane_labels.reshape(-1)[pixel_indices] = global_ids

        # Liczba pikseli w każdej grupie
        counts = torch.bincount(
            local_ids,
            minlength=num_groups
        )

        # Suma D
        d_sums = torch.zeros(
            num_groups,
            dtype=dtype,
            device=device
        )

        d_sums.scatter_add_(
            0,
            local_ids,
            values.to(dtype)
        )

        group_counts.append(counts)
        group_d_sums.append(d_sums)

        group_normal_ids.append(
            torch.full(
                (num_groups,),
                normal_id,
                dtype=torch.long,
                device=device
            )
        )

        group_offset += num_groups

    group_counts = torch.cat(group_counts)
    group_d_sums = torch.cat(group_d_sums)
    group_normal_ids = torch.cat(group_normal_ids)

    # min_points TYLKO filtruje gotowe grupy
    keep = group_counts >= min_points

    if not bool(keep.any()):
        return (
            torch.full_like(plane_labels, -1),
            torch.empty(0, dtype=torch.long, device=device),
            torch.empty(0, 4, dtype=dtype, device=device)
        )

    kept_ids = torch.nonzero(
        keep,
        as_tuple=False
    ).squeeze(1)

    plane_counts = group_counts[kept_ids]

    plane_d = (
        group_d_sums[kept_ids]
        / plane_counts.to(dtype)
    )

    plane_normals = unique_normals[
        group_normal_ids[kept_ids]
    ].to(dtype)

    planes_consolidated = torch.cat(
        (
            plane_normals,
            plane_d[:, None]
        ),
        dim=1
    )

    # Usunięcie odrzuconych grup
    remap = torch.full(
        (group_offset,),
        -1,
        dtype=torch.long,
        device=device
    )

    remap[kept_ids] = torch.arange(
        kept_ids.numel(),
        device=device
    )

    flat_labels = plane_labels.reshape(-1)
    valid_labels = flat_labels >= 0

    flat_labels[valid_labels] = remap[
        flat_labels[valid_labels]
    ]

    # Największe płaszczyzny pierwsze
    sort_order = torch.argsort(
        plane_counts,
        descending=True
    )

    plane_counts = plane_counts[sort_order]
    planes_consolidated = planes_consolidated[sort_order]

    # Aktualizacja ID po sortowaniu
    sorted_remap = torch.empty(
        sort_order.numel(),
        dtype=torch.long,
        device=device
    )

    sorted_remap[sort_order] = torch.arange(
        sort_order.numel(),
        device=device
    )

    valid_labels = flat_labels >= 0

    flat_labels[valid_labels] = sorted_remap[
        flat_labels[valid_labels]
    ]

    plane_labels = flat_labels.reshape(h, w)

    return (
        plane_labels,
        plane_counts,
        planes_consolidated
    )
    
    

#============================================================
# Sort and filter planes by count
#============================================================


def sort_and_filter(plane_labels, planes, plane_counts, limit = 5):
    top_indices = torch.argsort(
        plane_counts,
        descending=True
    )[:limit]

    top_planes = planes[top_indices]

    new_plane_labels = torch.full_like(
        plane_labels,
        -1
    )

    for new_id, old_id in enumerate(top_indices):
        new_plane_labels[
            plane_labels == old_id
        ] = new_id

    return new_plane_labels, top_planes, plane_counts[top_indices]


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