import cv2
import numpy as np
import torch
from collections import deque


NORMAL_ANGLE_DEG = 4.0
MIN_REGION_SIZE = 300
CONNECTIVITY = 8


def normalize(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-8)


def region_growing(normals, mask,
                   angle_deg=NORMAL_ANGLE_DEG,
                   min_region_size=MIN_REGION_SIZE):

    # GPU -> CPU
    normals = normals.detach().float().cpu().numpy()
    mask = mask.detach().cpu().numpy().astype(bool)

    h, w, _ = normals.shape

    normals = normalize(normals)

    # cos(angle)
    cos_threshold = np.cos(np.deg2rad(angle_deg))

    labels = np.full((h, w), -1, dtype=np.int32)
    visited = np.zeros((h, w), dtype=np.bool_)

    if CONNECTIVITY == 8:
        neighbors = [
            (-1, -1), (-1, 0), (-1, 1),
            (0, -1),           (0, 1),
            (1, -1),  (1, 0),  (1, 1)
        ]
    else:
        neighbors = [
            (-1, 0),
            (0, -1), (0, 1),
            (1, 0)
        ]

    region_id = 0
    regions = {}

    for y in range(h):

        for x in range(w):

            if not mask[y, x] or visited[y, x]:
                continue

            # ----------------------------------------
            # STAŁE ZIARNO REGIONU
            # ----------------------------------------

            seed_normal = normals[y, x]

            queue = deque()
            queue.append((y, x))

            visited[y, x] = True

            pixels = []

            while queue:

                cy, cx = queue.popleft()

                pixels.append((cy, cx))

                for dy, dx in neighbors:

                    ny = cy + dy
                    nx = cx + dx

                    if ny < 0 or ny >= h:
                        continue

                    if nx < 0 or nx >= w:
                        continue

                    if visited[ny, nx]:
                        continue

                    if not mask[ny, nx]:
                        continue

                    candidate = normals[ny, nx]

                    # --------------------------------
                    # KLUCZOWE:
                    #
                    # porównujemy ze STAŁYM seed_normal
                    # a nie z normalną poprzedniego piksela
                    # --------------------------------

                    similarity = np.dot(seed_normal, candidate)

                    if similarity >= cos_threshold:

                        visited[ny, nx] = True
                        queue.append((ny, nx))

                    else:
                        # Nie oznaczamy jako visited.
                        # Może później rozpocząć własny region.
                        pass

            # ----------------------------------------
            # ODRZUCAMY MAŁE REGIONY
            # ----------------------------------------

            if len(pixels) < min_region_size:
                continue

            for py, px in pixels:
                labels[py, px] = region_id

            regions[region_id] = pixels

            region_id += 1

    print("Regions found:", region_id)

    return labels, regions


def calculate_region_dominants(labels, normals):

    normals = normals.detach().float().cpu().numpy()
    normals = normalize(normals)

    region_ids = np.unique(labels)
    region_ids = region_ids[region_ids >= 0]

    dominant = {}

    for region_id in region_ids:

        ys, xs = np.where(labels == region_id)

        if len(ys) == 0:
            continue

        region_normals = normals[ys, xs]

        # suma wektorów
        n = np.sum(region_normals, axis=0)

        length = np.linalg.norm(n)

        if length < 1e-8:
            continue

        n /= length

        dominant[int(region_id)] = n

    return dominant


def snap_regions(labels, dominant):

    h, w = labels.shape

    snapped = np.zeros(
        (h, w, 3),
        dtype=np.float32
    )

    for region_id, normal in dominant.items():

        mask = labels == region_id

        snapped[mask] = normal

    return snapped


def extract_boundaries(labels):

    boundaries = {}

    region_ids = np.unique(labels)
    region_ids = region_ids[region_ids >= 0]

    for region_id in region_ids:

        mask = np.zeros(
            labels.shape,
            dtype=np.uint8
        )

        mask[labels == region_id] = 255

        contours, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_NONE
        )

        if not contours:
            continue

        # największy kontur
        contour = max(
            contours,
            key=cv2.contourArea
        )

        boundaries[int(region_id)] = contour

    return boundaries


def create_debug_image(labels):
    if torch.is_tensor(labels):
        labels = labels.detach().cpu().numpy()

    labels = labels.astype(np.int32)

    h, w = labels.shape

    debug = np.zeros(
        (h, w, 3),
        dtype=np.uint8
    )

    rng = np.random.default_rng(12345)

    region_ids = np.unique(labels)
    region_ids = region_ids[region_ids >= 0]

    for region_id in region_ids:

        color = rng.integers(
            40,
            255,
            size=3,
            dtype=np.uint8
        )

        debug[labels == region_id] = color

    return debug


def segment_normals(normals, mask,
                    angle_deg=4.0,
                    min_region_size=300):

    labels, regions = region_growing(
        normals,
        mask,
        angle_deg=angle_deg,
        min_region_size=min_region_size
    )

    dominant = calculate_region_dominants(
        labels,
        normals
    )

    snapped = snap_regions(
        labels,
        dominant
    )

    boundaries = extract_boundaries(
        labels
    )

    return (
        labels,
        snapped,
        dominant,
        boundaries
    )
    
    
def cleanup_regions(
    labels,
    min_region_size=300,
    hole_size=500,
    simplify_epsilon=3.0
):
    """
    Upraszcza mapę regionów:
    - usuwa małe dziury,
    - usuwa małe regiony,
    - upraszcza granice.
    """

    labels = labels.copy()

    h, w = labels.shape

    # -------------------------------------------------
    # 1. MAŁE DZIURY
    # -------------------------------------------------

    region_ids = np.unique(labels)
    region_ids = region_ids[region_ids >= 0]

    for region_id in region_ids:

        region_mask = np.uint8(labels == region_id)

        contours, hierarchy = cv2.findContours(
            region_mask,
            cv2.RETR_CCOMP,
            cv2.CHAIN_APPROX_SIMPLE
        )

        if hierarchy is None:
            continue

        hierarchy = hierarchy[0]

        for i, contour in enumerate(contours):

            # tylko kontury będące dziurami
            parent = hierarchy[i][3]

            if parent < 0:
                continue

            area = cv2.contourArea(contour)

            if area > hole_size:
                continue

            cv2.drawContours(
                labels,
                [contour],
                -1,
                int(region_id),
                thickness=cv2.FILLED
            )

    # -------------------------------------------------
    # 2. MAŁE REGIONY
    # -------------------------------------------------

    region_ids = np.unique(labels)
    region_ids = region_ids[region_ids >= 0]

    for region_id in region_ids:

        region_mask = labels == region_id

        size = np.count_nonzero(region_mask)

        if size >= min_region_size:
            continue

        # znajdź sąsiadujące regiony
        dilated = cv2.dilate(
            np.uint8(region_mask),
            np.ones((3, 3), np.uint8)
        )

        border = (
            (dilated > 0) &
            (~region_mask)
        )

        neighbours = labels[border]

        neighbours = neighbours[neighbours >= 0]

        if len(neighbours) == 0:
            continue

        # najczęstszy sąsiad
        values, counts = np.unique(
            neighbours,
            return_counts=True
        )

        target = values[np.argmax(counts)]

        labels[region_mask] = target

    # -------------------------------------------------
    # 3. UPROSZCZENIE GRANIC
    # -------------------------------------------------

    simplified_boundaries = {}

    region_ids = np.unique(labels)
    region_ids = region_ids[region_ids >= 0]

    for region_id in region_ids:

        mask = np.uint8(labels == region_id)

        contours, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_NONE
        )

        if not contours:
            continue

        contour = max(
            contours,
            key=cv2.contourArea
        )

        perimeter = cv2.arcLength(
            contour,
            True
        )

        epsilon = simplify_epsilon

        # dodatkowe ograniczenie względem wielkości
        epsilon = max(
            epsilon,
            perimeter * 0.002
        )

        simplified = cv2.approxPolyDP(
            contour,
            epsilon,
            True
        )

        simplified_boundaries[int(region_id)] = simplified

    return labels, simplified_boundaries


import cv2
import numpy as np


def find_best_normal_regions(
    normals,
    mask,
    steps=20,
    min_similarity=0.80,
    max_similarity=0.995,
    min_region_size=300,
    min_line_length=30,
    max_line_gap=5,
    top_n=3
):
    """
    Szuka najlepszych progów podobieństwa normalnych.

    Wynikiem jest TOP N macierzy regionów.

    labels[y, x]:
        -1  -> brak regionu
         0+ -> ID regionu

    Każdy krok oceniany jest na podstawie:
        - liczby długich odcinków granic,
        - ich łącznej długości,
        - długości średniej,
        - liczby dużych regionów.

    Zwraca listę TOP N wyników.
    """

    # --------------------------------------------------
    # NORMALNE -> NUMPY
    # --------------------------------------------------

    if hasattr(normals, "detach"):
        normals = normals.detach().float().cpu().numpy()

    if hasattr(mask, "detach"):
        mask = mask.detach().cpu().numpy()

    normals = np.squeeze(normals)
    mask = np.squeeze(mask).astype(bool)

    # --------------------------------------------------
    # NORMALIZACJA
    # --------------------------------------------------

    length = np.linalg.norm(
        normals,
        axis=2,
        keepdims=True
    )

    normals = normals / np.maximum(length, 1e-8)

    h, w, _ = normals.shape

    # --------------------------------------------------
    # PODOBIEŃSTWO SĄSIADÓW
    # --------------------------------------------------

    horizontal = np.sum(
        normals[:, :-1] * normals[:, 1:],
        axis=2
    )

    vertical = np.sum(
        normals[:-1] * normals[1:],
        axis=2
    )

    horizontal_valid = (
        mask[:, :-1] &
        mask[:, 1:]
    )

    vertical_valid = (
        mask[:-1] &
        mask[1:]
    )

    # --------------------------------------------------
    # PRZESZUKIWANIE PROGÓW
    # --------------------------------------------------

    thresholds = np.linspace(
        min_similarity,
        max_similarity,
        steps
    )

    results = []

    for threshold in thresholds:

        # ==================================================
        # 1. TWORZYMY POŁĄCZENIA PODOBNYCH NORMALNYCH
        # ==================================================

        graph = np.zeros(
            (h, w),
            dtype=np.uint8
        )

        # Pionowe sąsiedztwo
        similar_v = (
            vertical >= threshold
        ) & vertical_valid

        # Poziome sąsiedztwo
        similar_h = (
            horizontal >= threshold
        ) & horizontal_valid

        # ==================================================
        # 2. REGIONY = CONNECTED COMPONENTS
        # ==================================================

        # Tworzymy obraz krawędzi "odwrotnie":
        # piksele, które mają podobnych sąsiadów,
        # zostaną połączone przez flood fill.
        #
        # Najpierw każdy piksel dostaje własną etykietę,
        # potem Union-Find scala podobne sąsiedztwa.
        # ==================================================

        parent = np.arange(
            h * w,
            dtype=np.int32
        )

        size = np.ones(
            h * w,
            dtype=np.int32
        )

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a, b):

            a = find(a)
            b = find(b)

            if a == b:
                return

            if size[a] < size[b]:
                a, b = b, a

            parent[b] = a
            size[a] += size[b]

        # poziome
        ys, xs = np.where(similar_h)

        for y, x in zip(ys, xs):

            a = y * w + x
            b = y * w + x + 1

            union(a, b)

        # pionowe
        ys, xs = np.where(similar_v)

        for y, x in zip(ys, xs):

            a = y * w + x
            b = (y + 1) * w + x

            union(a, b)

        # ==================================================
        # 3. GENERUJEMY LABELS
        # ==================================================

        labels = np.full(
            (h, w),
            -1,
            dtype=np.int32
        )

        valid_indices = np.flatnonzero(mask)

        roots = np.array(
            [find(int(i)) for i in valid_indices],
            dtype=np.int32
        )

        unique_roots, inverse, counts = np.unique(
            roots,
            return_inverse=True,
            return_counts=True
        )

        # tylko odpowiednio duże regiony
        valid_region = (
            counts >= min_region_size
        )

        region_map = np.full(
            len(unique_roots),
            -1,
            dtype=np.int32
        )

        region_map[
            valid_region
        ] = np.arange(
            np.count_nonzero(valid_region)
        )

        labels_flat = labels.reshape(-1)

        labels_flat[
            valid_indices
        ] = region_map[inverse]

        labels = labels_flat.reshape(h, w)

        # ==================================================
        # 4. GRANICE REGIONÓW
        # ==================================================

        boundary = np.zeros(
            (h, w),
            dtype=np.uint8
        )

        # różne etykiety poziomo
        diff_h = (
            labels[:, :-1] !=
            labels[:, 1:]
        )

        valid_h = (
            (labels[:, :-1] >= 0) &
            (labels[:, 1:] >= 0)
        )

        diff_h &= valid_h

        boundary[:, :-1][diff_h] = 255
        boundary[:, 1:][diff_h] = 255

        # różne etykiety pionowo
        diff_v = (
            labels[:-1] !=
            labels[1:]
        )

        valid_v = (
            (labels[:-1] >= 0) &
            (labels[1:] >= 0)
        )

        diff_v &= valid_v

        boundary[:-1][diff_v] = 255
        boundary[1:][diff_v] = 255

        # ==================================================
        # 5. ODCINKI GRANIC
        # ==================================================

        lines = cv2.HoughLinesP(
            boundary,
            rho=1,
            theta=np.pi / 180,
            threshold=max(
                10,
                min_line_length // 2
            ),
            minLineLength=min_line_length,
            maxLineGap=max_line_gap
        )

        line_lengths = []

        if lines is not None:

            for line in lines[:, 0]:

                x1, y1, x2, y2 = line

                length = np.hypot(
                    x2 - x1,
                    y2 - y1
                )

                if length >= min_line_length:
                    line_lengths.append(length)

        line_count = len(line_lengths)

        total_length = float(
            np.sum(line_lengths)
        )

        avg_length = (
            total_length / line_count
            if line_count
            else 0.0
        )

        # ==================================================
        # 6. LICZBA REGIONÓW
        # ==================================================

        region_count = int(
            np.count_nonzero(valid_region)
        )

        # ==================================================
        # 7. WAGA KROKU
        # ==================================================

        # Preferujemy:
        # - długie granice
        # - kilka dużych regionów
        # - unikamy masy krótkich odcinków
        #
        # Długość ma największe znaczenie.
        # ==================================================

        score = (
            total_length
            * np.sqrt(max(line_count, 1))
            * np.sqrt(max(region_count, 1))
        )

        results.append({
            "threshold": float(threshold),

            # NAJWAŻNIEJSZY WYNIK
            "labels": labels,

            # pomocniczo
            "boundary": boundary,
            "lines": lines,

            "region_count": region_count,
            "line_count": line_count,
            "total_length": total_length,
            "avg_length": avg_length,
            "score": float(score)
        })

    # ==================================================
    # 8. TOP N
    # ==================================================

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    best = results[:top_n]

    # ==================================================
    # INFO
    # ==================================================

    print()
    print("BEST NORMAL REGION STEPS")
    print("------------------------")

    for i, r in enumerate(best):

        print(
            f"{i + 1}. "
            f"threshold={r['threshold']:.5f} | "
            f"regions={r['region_count']} | "
            f"lines={r['line_count']} | "
            f"length={r['total_length']:.1f} | "
            f"avg={r['avg_length']:.1f} | "
            f"score={r['score']:.1f}"
        )

    return best