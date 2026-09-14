# snap_normals_cuda.py

import torch
import torch.nn.functional as F


NORMAL_ANGLE_DEG = 5.0
DEPTH_THRESHOLD_RATIO = 0.02

ITERATIONS = 4

# 3x3 = 8 sąsiadów + centrum
KERNEL_SIZE = 3

# Minimalna liczba zgodnych normalnych,
# żeby wykonać snap.
MIN_VOTES = 3


def normalize_normals(normals):
    return F.normalize(normals.float(), dim=-1, eps=1e-8)


@torch.no_grad()
def _get_neighbourhood(x):
    """
    x:
        [H, W, C]

    return:
        [H, W, 9, C]
    """

    H, W, C = x.shape

    x = x.permute(2, 0, 1).unsqueeze(0)

    x = F.pad(
        x,
        (1, 1, 1, 1),
        mode="replicate"
    )

    # [1, C*9, H, W]
    x = F.unfold(
        x,
        kernel_size=3
    )

    # [H, W, 9, C]
    x = x.squeeze(0)
    x = x.reshape(C, 9, H, W)
    x = x.permute(2, 3, 1, 0)

    return x


@torch.no_grad()
def _get_neighbourhood_mask(mask):
    """
    mask:
        [H, W]

    return:
        [H, W, 9]
    """

    H, W = mask.shape

    x = mask.float().unsqueeze(0).unsqueeze(0)

    x = F.pad(
        x,
        (1, 1, 1, 1),
        mode="constant",
        value=0
    )

    x = F.unfold(
        x,
        kernel_size=3
    )

    x = x.squeeze(0)

    x = x.reshape(9, H, W)
    x = x.permute(1, 2, 0)

    return x.bool()


@torch.no_grad()
def snap_normals(
    normals,
    depth,
    mask,
    iterations=ITERATIONS,
    normal_angle_deg=NORMAL_ANGLE_DEG,
    depth_threshold_ratio=DEPTH_THRESHOLD_RATIO,
    min_votes=MIN_VOTES
):
    """
    Dominant-normal filter.

    normals:
        [H,W,3] CUDA

    depth:
        [H,W] CUDA

    mask:
        [H,W] CUDA bool

    Returns:
        [H,W,3]
    """

    if not normals.is_cuda:
        raise RuntimeError(
            "snap_normals requires CUDA tensors."
        )

    normals = normalize_normals(normals)

    depth = depth.float()
    mask = mask.bool()

    H, W, _ = normals.shape

    cos_threshold = torch.cos(
        torch.tensor(
            normal_angle_deg,
            device=normals.device,
            dtype=torch.float32
        )
        * torch.pi
        / 180.0
    )

    # --------------------------------------------------
    # Depth threshold
    # --------------------------------------------------

    valid_depth = depth[mask]

    if valid_depth.numel() == 0:
        return normals

    median_depth = valid_depth.median()

    depth_threshold = (
        median_depth *
        depth_threshold_ratio
    )

    print(
        f"Depth threshold: "
        f"{depth_threshold.item():.6f}"
    )

    current = normals

    # --------------------------------------------------
    # Iterations
    # --------------------------------------------------

    for iteration in range(iterations):

        # ----------------------------------------------
        # 3x3 normals
        # ----------------------------------------------

        neighbours = _get_neighbourhood(current)

        # [H,W,9,3]

        neighbour_mask = _get_neighbourhood_mask(mask)

        # [H,W,9]

        # ----------------------------------------------
        # 3x3 depth
        # ----------------------------------------------

        depth_neighbours = _get_neighbourhood(
            depth.unsqueeze(-1)
        ).squeeze(-1)

        # [H,W,9]

        # ----------------------------------------------
        # Center
        # ----------------------------------------------

        center_normal = current.unsqueeze(2)

        center_depth = depth.unsqueeze(2)

        # ----------------------------------------------
        # Valid neighbours
        # ----------------------------------------------

        depth_difference = torch.abs(
            depth_neighbours -
            center_depth
        )

        valid_depth_neighbour = (
            depth_difference <=
            depth_threshold
        )

        valid = (
            neighbour_mask &
            valid_depth_neighbour &
            mask.unsqueeze(-1)
        )

        # ----------------------------------------------
        # Find dominant candidate
        # ----------------------------------------------

        best_votes = torch.zeros(
            (H, W),
            device=current.device,
            dtype=torch.int16
        )

        best_candidate = torch.zeros(
            (H, W),
            device=current.device,
            dtype=torch.long
        )

        # 9 candidate normals
        #
        # We intentionally loop only 9 times.
        # All pixel calculations remain on CUDA.

        for candidate_index in range(9):

            candidate = neighbours[
                ..., candidate_index, :
            ]

            # candidate:
            # [H,W,3]

            # Compare candidate with every
            # normal in the 3x3 neighbourhood.

            similarity = (
                neighbours *
                candidate.unsqueeze(2)
            ).sum(dim=-1)

            similar = (
                similarity >=
                cos_threshold
            )

            votes = (
                similar &
                valid
            ).sum(dim=-1)

            better = (
                votes >
                best_votes
            )

            best_votes = torch.where(
                better,
                votes,
                best_votes
            )

            best_candidate = torch.where(
                better,
                torch.tensor(
                    candidate_index,
                    device=current.device
                ),
                best_candidate
            )

        # ----------------------------------------------
        # Select dominant normal
        # ----------------------------------------------

        dominant = torch.gather(
            neighbours,
            2,
            best_candidate
                .unsqueeze(-1)
                .unsqueeze(-1)
                .expand(-1, -1, 1, 3)
        ).squeeze(2)

        # ----------------------------------------------
        # Snap only if enough votes
        # ----------------------------------------------

        should_snap = (
            mask &
            (best_votes >= min_votes)
        )

        current = torch.where(
            should_snap.unsqueeze(-1),
            dominant,
            current
        )

        current = normalize_normals(current)

        if torch.cuda.is_available():
            torch.cuda.synchronize()

        snapped_pixels = (
            should_snap.sum()
            .item()
        )

        print(
            f"Iteration "
            f"{iteration + 1}/{iterations} | "
            f"snapped: {snapped_pixels}"
        )

    return current


@torch.no_grad()
def normals_to_debug_image(normals):
    """
    Normal -> RGB PNG data.
    """

    normals = normalize_normals(normals)

    image = (
        normals + 1.0
    ) * 127.5

    image = torch.clamp(
        image,
        0,
        255
    )

    return image.to(torch.uint8)