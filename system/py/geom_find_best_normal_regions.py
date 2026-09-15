import torch
import torch.nn.functional as F


@torch.no_grad()
def find_dominant_normal_directions(
    normals,
    mask,
    num_directions=15,
    angle_radius_deg=7.0,
    min_similarity=0.90,
    azimuth_bins=180,
    elevation_bins=90,
):
    """
    Znajduje dominujące kierunki normalnych.

    Całość wykonywana na GPU.

    normals:
        [H, W, 3]

    mask:
        [H, W]

    Zwraca:
        directions:
            [N, 3]

        labels:
            [H, W]

        similarity:
            [H, W]

        density:
            [N]
    """

    device = normals.device

    # ==================================================
    # 1. NORMALIZACJA
    # ==================================================

    normals = F.normalize(
        normals.float(),
        dim=-1
    )

    valid = (
        mask &
        torch.isfinite(normals).all(dim=-1)
    )

    vectors = normals[valid]

    if vectors.numel() == 0:
        raise RuntimeError(
            "Brak poprawnych normalnych."
        )

    # ==================================================
    # 2. NORMALNE -> WSPÓŁRZĘDNE SFERYCZNE
    # ==================================================

    x = vectors[:, 0]
    y = vectors[:, 1]
    z = vectors[:, 2].clamp(-1.0, 1.0)

    azimuth = torch.atan2(y, x)

    # [-pi, pi] -> [0, 2pi]
    azimuth = azimuth + torch.pi

    elevation = torch.asin(z)

    # ==================================================
    # 3. KWANTYZACJA
    # ==================================================

    azimuth_step = (
        2.0 * torch.pi /
        azimuth_bins
    )

    elevation_step = (
        torch.pi /
        elevation_bins
    )

    ai = torch.floor(
        azimuth / azimuth_step
    ).long()

    ei = torch.floor(
        (elevation + torch.pi / 2)
        / elevation_step
    ).long()

    ai = ai.clamp(
        0,
        azimuth_bins - 1
    )

    ei = ei.clamp(
        0,
        elevation_bins - 1
    )

    bin_id = (
        ei * azimuth_bins +
        ai
    )

    num_bins = (
        azimuth_bins *
        elevation_bins
    )

    # ==================================================
    # 4. HISTOGRAM NA GPU
    # ==================================================

    density = torch.bincount(
        bin_id,
        minlength=num_bins
    ).float()

    density = density.reshape(
        elevation_bins,
        azimuth_bins
    )

    # ==================================================
    # 5. NMS
    # ==================================================

    # Promień w koszykach.
    radius = max(
        1,
        int(
            angle_radius_deg /
            min(
                360.0 / azimuth_bins,
                180.0 / elevation_bins
            )
        )
    )

    # MaxPool daje lokalne maksimum gęstości.
    kernel = radius * 2 + 1

    padded = F.pad(
        density.unsqueeze(0).unsqueeze(0),
        (
            radius,
            radius,
            radius,
            radius
        ),
        mode="circular"
    )

    local_max = F.max_pool2d(
        padded,
        kernel_size=kernel,
        stride=1
    )

    local_max = local_max[
        :,
        :,
        :elevation_bins,
        :azimuth_bins
    ][0, 0]

    peaks = (
        density == local_max
    )

    peak_density = torch.where(
        peaks,
        density,
        torch.zeros_like(density)
    )

    # ==================================================
    # 6. NAJLEPSZE PIKI
    # ==================================================

    flat = peak_density.flatten()

    k = min(
        num_directions,
        int(torch.count_nonzero(flat))
    )

    if k == 0:
        raise RuntimeError(
            "Nie znaleziono dominujących kierunków."
        )

    values, indices = torch.topk(
        flat,
        k=k
    )

    ei = indices // azimuth_bins
    ai = indices % azimuth_bins

    # ==================================================
    # 7. ŚRODKI KOSZYKÓW -> WEKTORY
    # ==================================================

    azimuth_center = (
        (ai.float() + 0.5)
        * azimuth_step
        - torch.pi
    )

    elevation_center = (
        (ei.float() + 0.5)
        * elevation_step
        - torch.pi / 2
    )

    cos_e = torch.cos(
        elevation_center
    )

    directions = torch.stack(
        [
            cos_e * torch.cos(
                azimuth_center
            ),
            cos_e * torch.sin(
                azimuth_center
            ),
            torch.sin(
                elevation_center
            )
        ],
        dim=1
    )

    directions = F.normalize(
        directions,
        dim=1
    )

    # ==================================================
    # 8. USUNIĘCIE ZBYT PODOBNYCH KIERUNKÓW
    # ==================================================

    selected_directions = []
    selected_density = []

    cos_radius = torch.cos(
        torch.tensor(
            angle_radius_deg *
            torch.pi / 180.0,
            device=device
        )
    )

    for i in range(directions.shape[0]):

        d = directions[i]

        if not selected_directions:

            selected_directions.append(d)
            selected_density.append(values[i])
            continue

        previous = torch.stack(
            selected_directions
        )

        similarity = previous @ d

        if torch.all(
            similarity < cos_radius
        ):
            selected_directions.append(d)
            selected_density.append(values[i])

        if len(selected_directions) >= num_directions:
            break

    directions = torch.stack(
        selected_directions
    )

    density_result = torch.stack(
        selected_density
    )

    # ==================================================
    # 9. KAŻDY PIKSEL -> NAJBLIŻSZY DOMINUJĄCY KIERUNEK
    # ==================================================

    # To jest bezpieczne:
    #
    # H*W × 15
    #
    # a nie H*W × H*W
    # ==================================================

    similarity = (
        normals.reshape(-1, 3)
        @ directions.T
    )

    best_similarity, best_labels = torch.max(
        similarity,
        dim=1
    )

    h, w = mask.shape

    best_similarity = best_similarity.reshape(
        h,
        w
    )

    best_labels = best_labels.reshape(
        h,
        w
    )

    # ==================================================
    # 10. SŁABE DOPASOWANIA
    # ==================================================

    best_labels = best_labels.clone()

    best_labels[
        best_similarity < min_similarity
    ] = -1

    best_labels[
        ~valid
    ] = -1

    return (
        directions,
        best_labels,
        best_similarity,
        density_result
    )