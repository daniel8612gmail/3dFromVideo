import torch
import torch.nn.functional as F
import numpy as np
from scipy import ndimage

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

def filter_direction_components(pixel_dirId, min_component_size=100):
    device = pixel_dirId.device
    result = pixel_dirId.clone()

    direction_ids = torch.unique(pixel_dirId)
    direction_ids = direction_ids[direction_ids >= 0]

    structure = np.ones((3, 3), dtype=np.uint8)

    for direction_id in direction_ids.tolist():
        mask = (pixel_dirId == direction_id).cpu().numpy()

        labels, num_components = ndimage.label(mask, structure=structure)

        if num_components == 0:
            continue

        counts = np.bincount(labels.ravel())

        remove = np.zeros(len(counts), dtype=bool)
        remove[counts < min_component_size] = True
        remove[0] = False

        remove_mask = remove[labels]

        result[
            torch.from_numpy(remove_mask).to(device)
        ] = -1

    return result

    
def apply_dominant_normals(
    normals,
    directions,
    pixel_dirId,
    dir_similarity=None,
    min_similarity=0.90,
):
    """
    Zastępuje normalną każdego piksela odpowiadającym jej
    dominującym kierunkiem.

    Parametry:
        normals:
            Tensor [H, W, 3] z oryginalnymi normalnymi.

        directions:
            Tensor [N, 3] z dominującymi kierunkami normalnych.

        pixel_dirId:
            Tensor [H, W] z ID kierunku dla każdego piksela.
            Wartość < 0 oznacza brak przypisanego kierunku.

        dir_similarity:
            Tensor [H, W] z podobieństwem piksela do przypisanego
            kierunku. Jeśli None, wszystkie przypisane piksele są używane.

        min_similarity:
            Minimalne podobieństwo wymagane do zastąpienia normalnej.

    Zwraca:
        new_normals:
            Tensor [H, W, 3].
    """

    new_normals = normals.clone()

    valid = pixel_dirId >= 0

    if dir_similarity is not None:
        valid &= dir_similarity >= min_similarity

    if not valid.any():
        return new_normals

    dir_ids = pixel_dirId[valid].long()

    new_normals[valid] = directions[dir_ids]

    return new_normals

def filter_top_directions(
    directions,
    pixel_dirId,
    dir_similarity,
    dir_density,
    top_n=10,
):
    top_n = min(top_n, directions.shape[0])

    top_ids = torch.argsort(
        dir_density,
        descending=True
    )[:top_n]

    mapping = torch.full(
        (directions.shape[0],),
        -1,
        dtype=torch.long,
        device=pixel_dirId.device
    )
    mapping[top_ids] = torch.arange(
        top_n,
        device=pixel_dirId.device
    )

    new_pixel_dirId = torch.full_like(pixel_dirId, -1)

    valid = pixel_dirId >= 0
    new_pixel_dirId[valid] = mapping[pixel_dirId[valid]]

    keep = new_pixel_dirId >= 0

    new_dir_similarity = torch.zeros_like(dir_similarity)

    if dir_similarity is not None:
        new_dir_similarity[keep] = dir_similarity[keep]

    return (
        directions[top_ids],
        new_pixel_dirId,
        new_dir_similarity,
        dir_density[top_ids],
    )