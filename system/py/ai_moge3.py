import cv2
import torch
import numpy as np
import trimesh
from pathlib import Path
import argparse
import math
from collections import deque
from geom_create_planes import create_planes
from geom_snap_matrix import normals_to_debug_image, snap_normals

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
# PLANAR SIMPLIFICATION
# ============================================================
# Maksymalny kąt pomiędzy normalnymi dwóch pikseli.
#
# 1.0 = bardzo restrykcyjne
# 2.0 = dobre dla czystych powierzchni
# 3.0 = bardziej agresywne
NORMAL_ANGLE_DEG = 2.0

# Maksymalny błąd punktu względem płaszczyzny.
#
# UWAGA:
# zależy od skali zwróconej przez MoGe.
#
# np.:
# 0.01 = 1 cm
# 0.02 = 2 cm
# 0.05 = 5 cm
PLANE_DISTANCE = 0.02

# Upraszczanie konturu w pikselach.
#
# większe = mniej punktów
#
# 1.0  -> zachowuje dużo szczegółów
# 2.0  -> umiarkowane
# 4.0  -> agresywne
CONTOUR_EPSILON = 2.0

# Minimalny region w pikselach.
#
# Małe regiony zostaną pominięte.
MIN_REGION_PIXELS = 100

# Minimalna długość boku wynikowego polygonu
# w pikselach.
MIN_CONTOUR_POINTS = 3

# ============================================================
# DEPTH
# ============================================================
DEPTH_THRESHOLD = 0.04
MAX_EDGE_RATIO = 0.10

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

# ============================================================
# NORMALNA -> KĄT
# ============================================================
NORMAL_COS = math.cos(
    math.radians(NORMAL_ANGLE_DEG)
)

# ============================================================
# FIT PLANE
# ============================================================
def fit_plane(points):
    """
    Dopasowuje płaszczyznę:
        n.x + d = 0
    do punktów 3D.
    """
    if len(points) < 3:
        return None, None
    center = np.mean(
        points,
        axis=0
    )
    centered = points - center
    _, _, vh = np.linalg.svd(
        centered,
        full_matrices=False
    )
    normal = vh[-1]
    normal /= (
        np.linalg.norm(normal)
        + 1e-12
    )
    d = -np.dot(
        normal,
        center
    )
    return normal, d

# ============================================================
# ODLEGŁOŚĆ PUNKTU OD PŁASZCZYZNY
# ============================================================
def plane_distance(
    point,
    normal,
    d
):
    return abs(
        np.dot(
            normal,
            point
        ) + d
    )

# ============================================================
# REGION GROWING
# ============================================================
def segment_planar_regions(
    points,
    normals,
    mask,
    plane_distance_threshold,
    normal_cos_threshold,
    min_region_pixels
):
    height, width = mask.shape
    visited = np.zeros(
        (height, width),
        dtype=bool
    )
    regions = []
    # --------------------------------------------------------
    # KANDYDACI
    # --------------------------------------------------------
    ys, xs = np.where(mask)
    # --------------------------------------------------------
    # REGION GROWING
    # --------------------------------------------------------
    for seed_y, seed_x in zip(
        ys,
        xs
    ):
        if visited[
            seed_y,
            seed_x
        ]:
            continue
        # ----------------------------------------------------
        # SEED
        # ----------------------------------------------------
        seed_point = points[
            seed_y,
            seed_x
        ]
        seed_normal = normals[
            seed_y,
            seed_x
        ]
        norm = np.linalg.norm(
            seed_normal
        )
        if norm < 1e-8:
            visited[
                seed_y,
                seed_x
            ] = True
            continue
        seed_normal = (
            seed_normal /
            norm
        )
        # Płaszczyzna początkowa
        plane_n = seed_normal.copy()
        plane_d = -np.dot(
            plane_n,
            seed_point
        )
        queue = deque()
        queue.append(
            (
                seed_y,
                seed_x
            )
        )
        visited[
            seed_y,
            seed_x
        ] = True
        region = []
        # ----------------------------------------------------
        # GROW
        # ----------------------------------------------------
        while queue:
            y, x = queue.popleft()
            region.append(
                (
                    y,
                    x
                )
            )
            # ------------------------------------------------
            # SĄSIEDZI 4-KIERUNKOWI
            # ------------------------------------------------
            neighbors = (
                (y - 1, x),
                (y + 1, x),
                (y, x - 1),
                (y, x + 1),
            )
            for ny, nx in neighbors:
                if ny < 0:
                    continue
                if ny >= height:
                    continue
                if nx < 0:
                    continue
                if nx >= width:
                    continue
                if visited[
                    ny,
                    nx
                ]:
                    continue
                if not mask[
                    ny,
                    nx
                ]:
                    continue
                candidate_normal = normals[
                    ny,
                    nx
                ]
                candidate_norm = np.linalg.norm(
                    candidate_normal
                )
                if candidate_norm < 1e-8:
                    visited[
                        ny,
                        nx
                    ] = True
                    continue
                candidate_normal = (
                    candidate_normal /
                    candidate_norm
                )
                # --------------------------------------------
                # NORMALNA
                # --------------------------------------------
                normal_similarity = abs(
                    np.dot(
                        plane_n,
                        candidate_normal
                    )
                )
                if (
                    normal_similarity
                    < normal_cos_threshold
                ):
                    continue
                # --------------------------------------------
                # PŁASZCZYZNA
                # --------------------------------------------
                candidate_point = points[
                    ny,
                    nx
                ]
                distance = plane_distance(
                    candidate_point,
                    plane_n,
                    plane_d
                )
                if (
                    distance
                    > plane_distance_threshold
                ):
                    continue
                # --------------------------------------------
                # AKCEPTUJ
                # --------------------------------------------
                visited[
                    ny,
                    nx
                ] = True
                queue.append(
                    (
                        ny,
                        nx
                    )
                )
        # ----------------------------------------------------
        # MINIMUM
        # ----------------------------------------------------
        if len(region) < min_region_pixels:
            continue
        regions.append(
            region
        )
    return regions

# ============================================================
# REGION -> CONTOUR
# ============================================================
def region_to_contour(
    region,
    height,
    width
):
    region_mask = np.zeros(
        (height, width),
        dtype=np.uint8
    )
    for y, x in region:
        region_mask[
            y,
            x
        ] = 255
    contours, _ = cv2.findContours(
        region_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return None
    contour = max(
        contours,
        key=cv2.contourArea
    )
    return contour

# ============================================================
# UPROSZCZENIE KONTOURU
# ============================================================
def simplify_contour(
    contour,
    epsilon
):
    perimeter = cv2.arcLength(
        contour,
        True
    )
    simplified = cv2.approxPolyDP(
        contour,
        epsilon,
        True
    )
    return simplified.reshape(
        -1,
        2
    )

# ============================================================
# 2D POLYGON AREA
# ============================================================
def polygon_area_2d(
    polygon
):
    x = polygon[:, 0]
    y = polygon[:, 1]
    return 0.5 * (
        np.sum(
            x * np.roll(y, -1)
        )
        -
        np.sum(
            y * np.roll(x, -1)
        )
    )

# ============================================================
# POINT IN TRIANGLE
# ============================================================
def point_in_triangle(
    p,
    a,
    b,
    c
):
    def cross(
        p1,
        p2,
        p3
    ):
        return (
            (p2[0] - p1[0])
            * (p3[1] - p1[1])
            -
            (p2[1] - p1[1])
            * (p3[0] - p1[0])
        )
    c1 = cross(
        a,
        b,
        p
    )
    c2 = cross(
        b,
        c,
        p
    )
    c3 = cross(
        c,
        a,
        p
    )
    return (
        c1 >= 0
        and c2 >= 0
        and c3 >= 0
    ) or (
        c1 <= 0
        and c2 <= 0
        and c3 <= 0
    )

# ============================================================
# EAR CLIPPING
# ============================================================
def triangulate_polygon(
    polygon
):
    n = len(polygon)
    if n < 3:
        return []
    if n == 3:
        return [
            [0, 1, 2]
        ]
    # CCW
    if polygon_area_2d(
        polygon
    ) < 0:
        polygon = polygon[::-1]
        reversed_indices = True
    else:
        reversed_indices = False
    indices = list(
        range(len(polygon))
    )
    triangles = []
    guard = 0
    while len(indices) > 3:
        guard += 1
        if guard > n * n:
            break
        ear_found = False
        count = len(indices)
        for i in range(count):
            i_prev = indices[
                (i - 1) % count
            ]
            i_curr = indices[i]
            i_next = indices[
                (i + 1) % count
            ]
            a = polygon[
                i_prev
            ]
            b = polygon[
                i_curr
            ]
            c = polygon[
                i_next
            ]
            # ----------------------------------------------
            # WYPukłość
            # ----------------------------------------------
            cross = (
                (b[0] - a[0])
                * (c[1] - a[1])
                -
                (b[1] - a[1])
                * (c[0] - a[0])
            )
            if cross <= 0:
                continue
            # ----------------------------------------------
            # Czy jakiś punkt znajduje się wewnątrz?
            # ----------------------------------------------
            contains_point = False
            for j in indices:
                if j in (
                    i_prev,
                    i_curr,
                    i_next
                ):
                    continue
                if point_in_triangle(
                    polygon[j],
                    a,
                    b,
                    c
                ):
                    contains_point = True
                    break
            if contains_point:
                continue
            triangles.append(
                [
                    i_prev,
                    i_curr,
                    i_next
                ]
            )
            del indices[i]
            ear_found = True
            break
        if not ear_found:
            break
    if len(indices) == 3:
        triangles.append(
            [
                indices[0],
                indices[1],
                indices[2]
            ]
        )
    if reversed_indices:
        remap = np.arange(
            n - 1,
            -1,
            -1
        )
        triangles = [
            [
                remap[t[0]],
                remap[t[1]],
                remap[t[2]]
            ]
            for t in triangles
        ]
    return triangles

# ============================================================
# REGION -> 3D POLYGON
# ============================================================
def region_to_3d_polygon(
    contour,
    points,
    region_mask
):
    height, width = region_mask.shape
    polygon_3d = []
    polygon_2d = []
    for px, py in contour:
        # cv2:
        # x = kolumna
        # y = wiersz
        x = int(
            np.clip(
                px,
                0,
                width - 1
            )
        )
        y = int(
            np.clip(
                py,
                0,
                height - 1
            )
        )
        # ----------------------------------------------------
        # Znajdź najbliższy prawidłowy piksel regionu
        # ----------------------------------------------------
        found = False
        for radius in range(0, 4):
            for dy in range(
                -radius,
                radius + 1
            ):
                for dx in range(
                    -radius,
                    radius + 1
                ):
                    nx = x + dx
                    ny = y + dy
                    if (
                        nx < 0
                        or nx >= width
                        or ny < 0
                        or ny >= height
                    ):
                        continue
                    if region_mask[
                        ny,
                        nx
                    ]:
                        polygon_3d.append(
                            points[
                                ny,
                                nx
                            ]
                        )
                        polygon_2d.append(
                            [
                                nx,
                                ny
                            ]
                        )
                        found = True
                        break
                if found:
                    break
            if found:
                break
    if len(polygon_3d) < 3:
        return None, None
    return (
        np.asarray(
            polygon_3d,
            dtype=np.float32
        ),
        np.asarray(
            polygon_2d,
            dtype=np.float32
        )
    )

# ============================================================
# BUILD PLANAR MESH
# ============================================================
def build_mesh(
    points,
    depth,
    normals,
    mask,
    image
):
    height, width = depth.shape
    # --------------------------------------------------------
    # NORMALIZE NORMALS
    # --------------------------------------------------------
    normal_length = np.linalg.norm(
        normals,
        axis=2,
        keepdims=True
    )
    normals = (
        normals /
        np.maximum(
            normal_length,
            1e-8
        )
    )
    # --------------------------------------------------------
    # REGION SEGMENTATION
    # --------------------------------------------------------
    print(
        "segment_planar_regions"
        )
    regions = segment_planar_regions(
        points,
        normals,
        mask,
        PLANE_DISTANCE,
        NORMAL_COS,
        MIN_REGION_PIXELS
    )
    print(
        f"Regions found: {len(regions)}"
    )
    vertices = []
    faces = []
    vertex_colors = []
    region_counter = 0
    # --------------------------------------------------------
    # KAŻDY REGION
    # --------------------------------------------------------
    for region in regions:
        region_counter += 1
        if (
            region_counter % 100
            == 0
        ):
            print(
                f"  region "
                f"{region_counter}/"
                f"{len(regions)}"
            )
        # ----------------------------------------------------
        # REGION MASK
        # ----------------------------------------------------
        region_mask = np.zeros(
            (height, width),
            dtype=np.uint8
        )
        ys = np.array(
            [p[0] for p in region]
        )
        xs = np.array(
            [p[1] for p in region]
        )
        region_mask[
            ys,
            xs
        ] = 255
        # ----------------------------------------------------
        # CONTOUR
        # ----------------------------------------------------
        contour = region_to_contour(
            region,
            height,
            width
        )
        if contour is None:
            continue
        # ----------------------------------------------------
        # SIMPLIFY
        # ----------------------------------------------------
        contour = simplify_contour(
            contour,
            CONTOUR_EPSILON
        )
        if (
            len(contour)
            < MIN_CONTOUR_POINTS
        ):
            continue
        # ----------------------------------------------------
        # 3D POLYGON
        # ----------------------------------------------------
        polygon_3d, polygon_2d = (
            region_to_3d_polygon(
                contour,
                points,
                region_mask
            )
        )
        if polygon_3d is None:
            continue
        # ----------------------------------------------------
        # TRIANGULATE
        # ----------------------------------------------------
        triangles = triangulate_polygon(
            polygon_2d
        )
        if not triangles:
            continue
        # ----------------------------------------------------
        # REGION COLOR
        # ----------------------------------------------------
        colors = image[
            ys,
            xs
        ]
        color = np.median(
            colors,
            axis=0
        ).astype(
            np.uint8
        )
        # ----------------------------------------------------
        # DODAJ VERTICES
        #
        # Każdy region ma własne vertices.
        # Dzięki temu może mieć własny kolor.
        # ----------------------------------------------------
        base_index = len(vertices)
        for vertex in polygon_3d:
            vertices.append(
                vertex
            )
            vertex_colors.append(
                [
                    int(color[0]),
                    int(color[1]),
                    int(color[2]),
                    255
                ]
            )
        # ----------------------------------------------------
        # FACES
        # ----------------------------------------------------
        for triangle in triangles:
            faces.append(
                [
                    base_index + triangle[0],
                    base_index + triangle[1],
                    base_index + triangle[2]
                ]
            )
    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------
    if not faces:
        raise RuntimeError(
            "No planar polygons generated."
        )
    vertices = np.asarray(
        vertices,
        dtype=np.float32
    )
    faces = np.asarray(
        faces,
        dtype=np.int32
    )
    vertex_colors = np.asarray(
        vertex_colors,
        dtype=np.uint8
    )
    return (
        vertices,
        faces,
        vertex_colors
    )

# ============================================================
# PRZETWARZANIE
# ============================================================
for index, image_path in enumerate(
    image_paths,
    1
):
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
    height, width = image.shape[:2]
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
    glb_dir = (
        INPUT_DIR.parent /
        "GLB"
    )
    glb_dir.mkdir(
        parents=True,
        exist_ok=True
    )
    output_glb = (
        glb_dir /
        f"{image_path.stem}.glb"
    )
    output_dbg = (
        INPUT_DIR.parent
    )
    
    # --------------------------------------------------------
    #   SNAP NORMALS
    # --------------------------------------------------------
    print("snap_normals")
    points = output["points"].float().cuda()
    depth = output["depth"].float().cuda()
    mask = output["mask"].bool().cuda()
    normals = output["normal"].float().cuda()

    normals_snapped = snap_normals(
        normals,
        depth,
        mask,
        iterations=4,
        normal_angle_deg=5.0,
        depth_threshold_ratio=0.02,
        min_votes=3
    )
        
    debug = normals_to_debug_image(
        normals_snapped
    )
    debug = (
        debug
        .cpu()
        .numpy()
    )

    # RGB -> BGR
    debug = cv2.cvtColor(
        debug,
        cv2.COLOR_RGB2BGR
    )

    cv2.imwrite(
        output_dbg / "normals_snapped.png",
        debug
    )
    print("create plane")
    
    # --------------------------------------------------------
    # BUILD SIMPLIFIED MESH
    # --------------------------------------------------------
    
    create_planes(
        points,
        depth,
        normals,
        mask,
        output_dbg
    )
    
    print("build_mesh")
    (
        vertices,
        faces,
        vertex_colors
    ) = build_mesh(
        points,
        depth,
        normals,
        mask
    )
    print(
        "Mesh ready."
    )
    # --------------------------------------------------------
    # OPENGL
    # --------------------------------------------------------
    vertices = (
        vertices
        *
        np.array(
            [1, -1, -1],
            dtype=np.float32
        )
    )
    
    # --------------------------------------------------------
    # VERTEX COLORS
    #
    # BEZ TEKSTURY
    # --------------------------------------------------------
    visual = (
        trimesh.visual.ColorVisuals(
            vertex_colors=vertex_colors
        )
    )
    # --------------------------------------------------------
    # MESH
    # --------------------------------------------------------
    mesh = trimesh.Trimesh(
        vertices=vertices,
        faces=faces,
        visual=visual,
        process=False
    )
    # --------------------------------------------------------
    # EXPORT
    # --------------------------------------------------------
    mesh.export(
        str(output_glb),
        file_type="glb"
    )
    print()
    print(
        f"  vertices : "
        f"{len(vertices)}"
    )
    print(
        f"  triangles: "
        f"{len(faces)}"
    )
    print(
        f"  saved    : "
        f"{output_glb}"
    )
    print()
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