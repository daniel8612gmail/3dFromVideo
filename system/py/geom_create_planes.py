import cv2
import numpy as np
from collections import deque
from pathlib import Path

# ============================================================
# PARAMETRY
# ============================================================
NORMAL_ANGLE_DEG = 5.0
# tolerancja odległości punktu od płaszczyzny
PLANE_DISTANCE_RATIO = 0.01
# minimalna liczba punktów aby uznać region za płaszczyznę
MIN_PLANE_POINTS = 50

# ============================================================
# NORMALNA
# ============================================================
def normal_similarity(n1, n2, max_angle_deg):
    """
    True jeśli kąt pomiędzy normalnymi jest <= max_angle_deg.
    """
    n1 = np.asarray(n1, dtype=np.float32)
    n2 = np.asarray(n2, dtype=np.float32)
    l1 = np.linalg.norm(n1)
    l2 = np.linalg.norm(n2)
    if l1 < 1e-8 or l2 < 1e-8:
        return False
    dot = np.dot(n1, n2) / (l1 * l2)
    dot = np.clip(abs(dot), -1.0, 1.0)
    angle = np.degrees(np.arccos(dot))
    return angle <= max_angle_deg

# ============================================================
# FIT PLANE
# ============================================================
def fit_plane(points):
    """
    Dopasowanie płaszczyzny:
        ax + by + cz + d = 0
    za pomocą SVD.
    """
    points = np.asarray(points, dtype=np.float32)
    if len(points) < 3:
        return None
    center = np.mean(points, axis=0)
    centered = points - center
    _, _, vh = np.linalg.svd(
        centered,
        full_matrices=False
    )
    normal = vh[-1]
    length = np.linalg.norm(normal)
    if length < 1e-8:
        return None
    normal = normal / length
    d = -np.dot(normal, center)
    return normal, d

# ============================================================
# DISTANCE FROM PLANE
# ============================================================
def point_plane_distance(point, normal, d):
    return abs(
        np.dot(normal, point) + d
    )

# ============================================================
# REGION GROWING
# ============================================================
def grow_plane(
    start_y,
    start_x,
    points,
    normals,
    mask,
    visited,
    normal_angle_deg,
    plane_distance
):
    """
    Tworzy jedną płaszczyznę zaczynając od punktu startowego.
    """
    height, width = mask.shape
    queue = deque()
    queue.append(
        (start_y, start_x)
    )
    visited[start_y, start_x] = True
    region = []
    reference_normal = normals[
        start_y,
        start_x
    ]
    # punkty używane do dopasowywania płaszczyzny
    plane_points = [
        points[start_y, start_x]
    ]
    plane = None
    while queue:
        y, x = queue.popleft()
        p = points[y, x]
        # ----------------------------------------------
        # dodajemy punkt do regionu
        # ----------------------------------------------
        region.append(
            (y, x)
        )
        # ----------------------------------------------
        # co pewien czas dopasowujemy płaszczyznę
        # ----------------------------------------------
        if len(plane_points) >= 3:
            plane = fit_plane(
                plane_points
            )
        # ----------------------------------------------
        # sąsiedzi
        # ----------------------------------------------
        neighbours = (
            (y - 1, x),
            (y + 1, x),
            (y, x - 1),
            (y, x + 1)
        )
        for ny, nx in neighbours:
            if ny < 0 or ny >= height:
                continue
            if nx < 0 or nx >= width:
                continue
            if visited[ny, nx]:
                continue
            if not mask[ny, nx]:
                continue
            np_ = points[ny, nx]
            nn = normals[ny, nx]
            # ------------------------------------------
            # normalna
            # ------------------------------------------
            if not normal_similarity(
                reference_normal,
                nn,
                normal_angle_deg
            ):
                continue
            # ------------------------------------------
            # płaszczyzna
            # ------------------------------------------
            if plane is not None:
                plane_normal, plane_d = plane
                distance = point_plane_distance(
                    np_,
                    plane_normal,
                    plane_d
                )
                if distance > plane_distance:
                    continue
            # ------------------------------------------
            # zaakceptowany
            # ------------------------------------------
            visited[ny, nx] = True
            queue.append(
                (ny, nx)
            )
            plane_points.append(
                np_
            )
    return region

# ============================================================
# MAIN
# ============================================================
def create_planes(
    points,
    depth,
    normals,
    mask,
    debug_path=None
):
    """
    Tworzy płaszczyzny na podstawie:
        points
        depth
        normals
        mask
    Zwraca:
        planes
        plane_ids
    planes:
        lista płaszczyzn
    plane_ids:
        obraz H x W, gdzie wartość oznacza ID płaszczyzny.
        -1 = brak płaszczyzny
    """
    height, width = mask.shape
    visited = np.zeros(
        (height, width),
        dtype=bool
    )
    plane_ids = np.full(
        (height, width),
        -1,
        dtype=np.int32
    )
    planes = []
    # ========================================================
    # tolerancja zależna od głębokości
    # ========================================================
    valid_depth = depth[
        mask &
        np.isfinite(depth)
    ]
    if len(valid_depth) == 0:
        raise RuntimeError(
            "No valid depth values."
        )
    median_depth = np.median(
        valid_depth
    )
    plane_distance = (
        median_depth *
        PLANE_DISTANCE_RATIO
    )
    print(
        "Plane distance threshold:",
        plane_distance
    )
    # ========================================================
    # SKANOWANIE OBRAZU
    # ========================================================
    plane_id = 0
    for y in range(height):
        for x in range(width):
            if not mask[y, x]:
                continue
            if visited[y, x]:
                continue
            # ----------------------------------------------
            # sprawdzenie poprawności punktu
            # ----------------------------------------------
            p = points[y, x]
            n = normals[y, x]
            if not np.all(np.isfinite(p)):
                visited[y, x] = True
                continue
            if not np.all(np.isfinite(n)):
                visited[y, x] = True
                continue
            # ----------------------------------------------
            # region growing
            # ----------------------------------------------
            region = grow_plane(
                y,
                x,
                points,
                normals,
                mask,
                visited,
                NORMAL_ANGLE_DEG,
                plane_distance
            )
            # ----------------------------------------------
            # za mały region
            # ----------------------------------------------
            if len(region) < MIN_PLANE_POINTS:
                continue
            # ----------------------------------------------
            # finalna płaszczyzna
            # ----------------------------------------------
            region_points = np.asarray(
                [
                    points[py, px]
                    for py, px in region
                ],
                dtype=np.float32
            )
            plane = fit_plane(
                region_points
            )
            if plane is None:
                continue
            plane_normal, plane_d = plane
            # ----------------------------------------------
            # zapis ID
            # ----------------------------------------------
            for py, px in region:
                plane_ids[
                    py,
                    px
                ] = plane_id
            planes.append(
                {
                    "id": plane_id,
                    "normal": plane_normal,
                    "d": float(plane_d),
                    "points": region_points,
                    "pixels": region,
                    "size": len(region)
                }
            )
            print(
                f"Plane {plane_id}: "
                f"{len(region)} pixels "
                f"normal={plane_normal}"
            )
            plane_id += 1
    # ========================================================
    # DEBUG
    # ========================================================
    if debug_path is not None:
        create_debug_image(
            plane_ids,
            planes,
            debug_path
        )
    return planes, plane_ids

# ============================================================
# DEBUG IMAGE
# ============================================================
def create_debug_image(
    plane_ids,
    planes,
    output_path
):
    """
    Każda płaszczyzna otrzymuje kolor wynikający
    z jej normalnej.
    normal:
        [-1,1]
    mapujemy na:
        [0,255]
    """
    height, width = plane_ids.shape
    debug = np.zeros(
        (height, width, 3),
        dtype=np.uint8
    )
    for plane in planes:
        plane_id = plane["id"]
        normal = plane["normal"]
        # ----------------------------------------------------
        # normalna [-1,+1]
        # →
        # kolor [0,255]
        # ----------------------------------------------------
        color = (
            (normal + 1.0) *
            127.5
        )
        color = np.clip(
            color,
            0,
            255
        ).astype(np.uint8)
        # OpenCV = BGR
        color = color[::-1]
        debug[
            plane_ids == plane_id
        ] = color
    output_path = Path(
        output_path
    )
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )
    cv2.imwrite(
        str(output_path),
        debug
    )
    print(
        "Debug saved:",
        output_path
    )