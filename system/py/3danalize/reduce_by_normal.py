import cv2
import numpy as np
from collections import deque


# ============================================================
# PARAMETRY
# ============================================================

NORMAL_ANGLE_DEG = 5.0

# ile kolejnych błędnych pikseli oznacza koniec powierzchni
MAX_BAD_PIXELS = 1

# minimalny rozmiar regionu
MIN_REGION_PIXELS = 30

# maksymalny odstęp między punktami granicy podczas upraszczania
CONTOUR_EPSILON = 2.0


# ============================================================
# NORMALNA - KĄT
# ============================================================

def normals_similar(n1, n2, max_angle_deg):
    """
    Sprawdza, czy dwie normalne są wystarczająco podobne.
    """

    n1 = np.asarray(n1, dtype=np.float32)
    n2 = np.asarray(n2, dtype=np.float32)

    l1 = np.linalg.norm(n1)
    l2 = np.linalg.norm(n2)

    if l1 < 1e-8 or l2 < 1e-8:
        return False

    dot = np.dot(n1, n2) / (l1 * l2)

    # zabezpieczenie przed błędem numerycznym
    dot = np.clip(dot, -1.0, 1.0)

    angle = np.degrees(np.arccos(abs(dot)))

    return angle <= max_angle_deg


# ============================================================
# SKANOWANIE JEDNEGO WIERSZA
# ============================================================

def scan_row(y, normals, mask, angle_deg):
    """
    Skanuje jeden wiersz X.

    Zwraca odcinki:

        [(x1, x2), (x1, x2), ...]

    Jeden błędny pixel pomiędzy poprawnymi pixelami
    nie kończy regionu.
    """

    width = mask.shape[1]

    segments = []

    x = 0

    while x < width:

        # szukamy pierwszego poprawnego pixela
        while x < width and not mask[y, x]:
            x += 1

        if x >= width:
            break

        start_x = x

        # normalna odniesienia dla aktualnej płaszczyzny
        reference_normal = normals[y, x]

        bad_count = 0

        last_good_x = x

        x += 1

        while x < width:

            # poza maską = koniec obszaru
            if not mask[y, x]:
                break

            current_normal = normals[y, x]

            if normals_similar(
                reference_normal,
                current_normal,
                angle_deg
            ):
                # poprawny pixel
                bad_count = 0
                last_good_x = x

                # normalna odniesienia pozostaje taka sama
                x += 1
                continue

            # ------------------------------------------------
            # PIXEL NIE PASUJE
            # ------------------------------------------------

            bad_count += 1

            # sprawdzamy następny pixel
            next_x = x + 1

            if next_x < width and mask[y, next_x]:

                next_normal = normals[y, next_x]

                if normals_similar(
                    reference_normal,
                    next_normal,
                    angle_deg
                ):
                    # aktualny pixel był pojedynczym błędem
                    #
                    # NIE kończymy regionu
                    #
                    if bad_count <= MAX_BAD_PIXELS:
                        x += 1
                        continue

            # ------------------------------------------------
            # ZA DUŻO BŁĘDÓW
            # ------------------------------------------------

            break

        if last_good_x >= start_x:
            segments.append(
                (start_x, last_good_x)
            )

        # przechodzimy dalej
        x = max(x + 1, last_good_x + 1)

    return segments


# ============================================================
# SKANOWANIE CAŁEGO OBRAZU
# ============================================================

def detect_horizontal_segments(
    normals,
    mask,
    angle_deg=NORMAL_ANGLE_DEG
):
    """
    Wykrywa poziome fragmenty płaszczyzn.

    Zwraca:

        rows[y] = [
            (x1, x2),
            (x1, x2),
            ...
        ]
    """

    height, width = mask.shape

    rows = []

    for y in range(height):

        segments = scan_row(
            y,
            normals,
            mask,
            angle_deg
        )

        rows.append(segments)

    return rows


# ============================================================
# ŁĄCZENIE SEGMENTÓW POMIĘDZY WIERSZAMI
# ============================================================

def segments_overlap(a, b):
    """
    Czy dwa odcinki X mają wspólną część?
    """

    a1, a2 = a
    b1, b2 = b

    return not (
        a2 < b1 or
        b2 < a1
    )


def build_regions(rows, mask):
    """
    Łączy poziome odcinki w większe regiony.

    Każdy region otrzymuje ID w label_image.
    """

    height, width = mask.shape

    labels = np.zeros(
        (height, width),
        dtype=np.int32
    )

    next_label = 1

    # --------------------------------------------------------
    # najpierw każdy odcinek dostaje własny region
    # --------------------------------------------------------

    segment_labels = []

    for y, row in enumerate(rows):

        current = []

        for x1, x2 in row:

            label = next_label
            next_label += 1

            labels[
                y,
                x1:x2 + 1
            ] = label

            current.append(
                (x1, x2, label)
            )

        segment_labels.append(current)

    # --------------------------------------------------------
    # union-find
    # --------------------------------------------------------

    parent = {
        i: i
        for i in range(1, next_label)
    }

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):

        a = find(a)
        b = find(b)

        if a != b:
            parent[b] = a

    # --------------------------------------------------------
    # łączenie sąsiednich wierszy
    # --------------------------------------------------------

    for y in range(1, height):

        previous = segment_labels[y - 1]
        current = segment_labels[y]

        for x1, x2, label_a in current:

            for p1, p2, label_b in previous:

                if segments_overlap(
                    (x1, x2),
                    (p1, p2)
                ):
                    union(label_a, label_b)

    # --------------------------------------------------------
    # kompresja ID
    # --------------------------------------------------------

    region_map = {}

    next_region = 1

    for y in range(height):
        for x in range(width):

            label = labels[y, x]

            if label == 0:
                continue

            root = find(label)

            if root not in region_map:
                region_map[root] = next_region
                next_region += 1

            labels[y, x] = region_map[root]

    return labels


# ============================================================
# USUWANIE MAŁYCH REGIONÓW
# ============================================================

def remove_small_regions(labels, min_pixels=MIN_REGION_PIXELS):

    result = labels.copy()

    ids, counts = np.unique(
        labels[labels > 0],
        return_counts=True
    )

    small = set(
        ids[counts < min_pixels]
    )

    if small:

        mask_small = np.isin(
            result,
            list(small)
        )

        result[mask_small] = 0

    return result


# ============================================================
# OBRYS REGIONU
# ============================================================

def region_contour(labels, region_id):

    region_mask = (
        labels == region_id
    ).astype(np.uint8) * 255

    contours, hierarchy = cv2.findContours(
        region_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_NONE
    )

    if not contours:
        return None

    contour = max(
        contours,
        key=cv2.contourArea
    )

    contour = contour.reshape(-1, 2)

    return contour


# ============================================================
# UPROSZCZENIE OBRYSU
# ============================================================

def simplify_contour(
    contour,
    epsilon=CONTOUR_EPSILON
):

    if contour is None or len(contour) < 3:
        return None

    contour_cv = contour.reshape(
        (-1, 1, 2)
    ).astype(np.float32)

    simplified = cv2.approxPolyDP(
        contour_cv,
        epsilon,
        True
    )

    simplified = simplified.reshape(
        (-1, 2)
    )

    if len(simplified) < 3:
        return None

    return simplified


# ============================================================
# KONWERSJA PIXEL → 3D
# ============================================================

def contour_to_3d(
    contour,
    points,
    labels,
    region_id
):

    result = []

    height, width = labels.shape

    for x, y in contour:

        x = int(x)
        y = int(y)

        # ----------------------------------------------------
        # znajdź najbliższy pixel należący do regionu
        # ----------------------------------------------------

        found = False

        for radius in range(0, 4):

            for yy in range(
                max(0, y - radius),
                min(height, y + radius + 1)
            ):

                for xx in range(
                    max(0, x - radius),
                    min(width, x + radius + 1)
                ):

                    if labels[yy, xx] == region_id:

                        p = points[yy, xx]

                        if np.all(np.isfinite(p)):
                            result.append(p)
                            found = True
                            break

                if found:
                    break

            if found:
                break

    if len(result) < 3:
        return None

    return np.asarray(
        result,
        dtype=np.float32
    )


# ============================================================
# TRIANGULACJA POLIGONU
# ============================================================

def triangulate_polygon_2d(polygon):

    polygon = np.asarray(
        polygon,
        dtype=np.float32
    )

    n = len(polygon)

    if n < 3:
        return []

    # orientacja CCW
    area = 0.0

    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]

        area += x1 * y2 - x2 * y1

    if area < 0:
        polygon = polygon[::-1]

    indices = list(range(n))

    triangles = []

    guard = 0

    while len(indices) > 3 and guard < n * n:

        guard += 1

        ear_found = False

        for i in range(len(indices)):

            i_prev = indices[
                (i - 1) % len(indices)
            ]

            i_curr = indices[i]

            i_next = indices[
                (i + 1) % len(indices)
            ]

            a = polygon[i_prev]
            b = polygon[i_curr]
            c = polygon[i_next]

            # convex
            cross = (
                (b[0] - a[0]) *
                (c[1] - a[1])
                -
                (b[1] - a[1]) *
                (c[0] - a[0])
            )

            if cross <= 0:
                continue

            # czy któryś vertex znajduje się
            # wewnątrz trójkąta?
            valid = True

            for j in indices:

                if j in (
                    i_prev,
                    i_curr,
                    i_next
                ):
                    continue

                p = polygon[j]

                c1 = (
                    (b[0] - a[0]) *
                    (p[1] - a[1])
                    -
                    (b[1] - a[1]) *
                    (p[0] - a[0])
                )

                c2 = (
                    (c[0] - b[0]) *
                    (p[1] - b[1])
                    -
                    (c[1] - b[1]) *
                    (p[0] - b[0])
                )

                c3 = (
                    (a[0] - c[0]) *
                    (p[1] - c[1])
                    -
                    (a[1] - c[1]) *
                    (p[0] - c[0])
                )

                if c1 >= 0 and c2 >= 0 and c3 >= 0:
                    valid = False
                    break

            if not valid:
                continue

            triangles.append(
                (
                    i_prev,
                    i_curr,
                    i_next
                )
            )

            indices.pop(i)

            ear_found = True
            break

        if not ear_found:
            break

    if len(indices) == 3:

        triangles.append(
            (
                indices[0],
                indices[1],
                indices[2]
            )
        )

    return triangles


# ============================================================
# GŁÓWNY ALGORYTM
# ============================================================

def build_planar_mesh(
    points,
    depth,
    mask,
    normals
):
    """
    Główna funkcja.

    Zwraca:

        vertices
        faces
        region_ids
    """

    print("Scanning horizontal planes...")

    rows = detect_horizontal_segments(
        normals,
        mask,
        NORMAL_ANGLE_DEG
    )

    print("Building regions...")

    labels = build_regions(
        rows,
        mask
    )

    labels = remove_small_regions(
        labels,
        MIN_REGION_PIXELS
    )

    region_ids = np.unique(
        labels[labels > 0]
    )

    print(
        "Detected regions:",
        len(region_ids)
    )

    vertices = []
    faces = []

    for region_id in region_ids:

        contour = region_contour(
            labels,
            region_id
        )

        if contour is None:
            continue

        contour = simplify_contour(
            contour,
            CONTOUR_EPSILON
        )

        if contour is None:
            continue

        polygon_3d = contour_to_3d(
            contour,
            points,
            labels,
            region_id
        )

        if polygon_3d is None:
            continue

        # ----------------------------------------------------
        # triangulacja
        #
        # ważne:
        # polygon_3d ma ten sam porządek vertexów
        # co contour
        # ----------------------------------------------------

        triangles = triangulate_polygon_2d(
            contour
        )

        if not triangles:
            continue

        base = len(vertices)

        vertices.extend(
            polygon_3d.tolist()
        )

        for a, b, c in triangles:

            faces.append(
                (
                    base + a,
                    base + b,
                    base + c
                )
            )

    vertices = np.asarray(
        vertices,
        dtype=np.float32
    )

    faces = np.asarray(
        faces,
        dtype=np.int64
    )

    print(
        "Final vertices:",
        len(vertices)
    )

    print(
        "Final triangles:",
        len(faces)
    )

    return (
        vertices,
        faces,
        labels
    )