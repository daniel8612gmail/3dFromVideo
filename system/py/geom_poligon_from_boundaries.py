import torch
import torch.nn.functional as F


@torch.no_grad()
def build_polygons_from_plane_boundaries(
    plane_labels,
    boundaries,
    max_edges_per_plane=8,
    max_vertices=10,
    min_edge_length=30.0,
    intersection_tolerance=5.0,
):
    if not plane_labels.is_cuda:
        raise ValueError("plane_labels must be CUDA")

    device = plane_labels.device
    h, w = plane_labels.shape

    selected = [
        b for b in boundaries
        if b["length"] >= min_edge_length
    ]

    if len(selected) < 3:
        return []

    selected.sort(
        key=lambda x: x["length"],
        reverse=True
    )

    plane_edge_count = {}
    lines = []

    for b in selected:
        a = b["plane_a"]
        c = b["plane_b"]

        if plane_edge_count.get(a, 0) >= max_edges_per_plane:
            continue

        if plane_edge_count.get(c, 0) >= max_edges_per_plane:
            continue

        center = b["center"].to(
            device=device,
            dtype=torch.float32
        )

        direction = F.normalize(
            b["direction"].to(
                device=device,
                dtype=torch.float32
            ),
            dim=0
        )

        half_length = (
            float(b["length"]) * 0.5
        )

        p0 = center - direction * half_length
        p1 = center + direction * half_length

        lines.append(
            {
                "plane_a": a,
                "plane_b": c,
                "center": center,
                "direction": direction,
                "p0": p0,
                "p1": p1,
                "length": float(b["length"]),
            }
        )

        plane_edge_count[a] = (
            plane_edge_count.get(a, 0) + 1
        )

        plane_edge_count[c] = (
            plane_edge_count.get(c, 0) + 1
        )

    if len(lines) < 3:
        return []

    def line_intersection(l1, l2):
        p1 = l1["center"]
        d1 = l1["direction"]

        p2 = l2["center"]
        d2 = l2["direction"]

        cross = (
            d1[0] * d2[1]
            - d1[1] * d2[0]
        )

        if abs(float(cross.item())) < 1e-5:
            return None

        delta = p2 - p1

        t = (
            delta[0] * d2[1]
            - delta[1] * d2[0]
        ) / cross

        return p1 + d1 * t

    def point_inside_plane(
        plane_id,
        point,
        radius=0
    ):
        x = int(
            round(float(point[0].item()))
        )

        y = int(
            round(float(point[1].item()))
        )

        if radius <= 0:
            if (
                x < 0
                or x >= w
                or y < 0
                or y >= h
            ):
                return False

            return bool(
                (
                    plane_labels[y, x]
                    == plane_id
                ).item()
            )

        x0 = max(0, x - radius)
        x1 = min(w, x + radius + 1)

        y0 = max(0, y - radius)
        y1 = min(h, y + radius + 1)

        if x0 >= x1 or y0 >= y1:
            return False

        local = plane_labels[
            y0:y1,
            x0:x1
        ]

        return bool(
            torch.any(
                local == plane_id
            ).item()
        )

    def distance_to_line_segment(
        point,
        line
    ):
        p = point
        p0 = line["p0"]
        p1 = line["p1"]

        d = p1 - p0
        length2 = torch.dot(d, d)

        if float(length2.item()) < 1e-8:
            return torch.linalg.vector_norm(
                p - p0
            )

        t = torch.dot(
            p - p0,
            d
        ) / length2

        t = torch.clamp(
            t,
            0.0,
            1.0
        )

        closest = p0 + t * d

        return torch.linalg.vector_norm(
            p - closest
        )

    polygons = []

    plane_ids = set()

    for line in lines:
        plane_ids.add(line["plane_a"])
        plane_ids.add(line["plane_b"])

    for plane_id in sorted(plane_ids):

        plane_lines = [
            line
            for line in lines
            if (
                line["plane_a"] == plane_id
                or line["plane_b"] == plane_id
            )
        ]

        if len(plane_lines) < 3:
            continue

        plane_lines.sort(
            key=lambda x: x["length"],
            reverse=True
        )

        vertices = []

        for i in range(
            len(plane_lines)
        ):
            l1 = plane_lines[i]

            for j in range(
                i + 1,
                len(plane_lines)
            ):
                l2 = plane_lines[j]

                vertex = line_intersection(
                    l1,
                    l2
                )

                if vertex is None:
                    continue

                x = float(vertex[0].item())
                y = float(vertex[1].item())

                if (
                    x < 0
                    or x >= w
                    or y < 0
                    or y >= h
                ):
                    continue

                d1 = distance_to_line_segment(
                    vertex,
                    l1
                )

                d2 = distance_to_line_segment(
                    vertex,
                    l2
                )

                if (
                    float(d1.item())
                    > intersection_tolerance
                    or
                    float(d2.item())
                    > intersection_tolerance
                ):
                    continue

                if not point_inside_plane(
                    plane_id,
                    vertex,
                    radius=max(
                        1,
                        int(
                            intersection_tolerance
                        )
                    )
                ):
                    continue

                if vertices:

                    existing = torch.stack(
                        vertices,
                        dim=0
                    )

                    distance = torch.linalg.vector_norm(
                        existing - vertex,
                        dim=1
                    )

                    if bool(
                        torch.any(
                            distance
                            <= intersection_tolerance
                        ).item()
                    ):
                        continue

                vertices.append(vertex)

        if len(vertices) < 3:
            continue

        vertices = torch.stack(
            vertices,
            dim=0
        )

        center = vertices.mean(
            dim=0
        )

        angle = torch.atan2(
            vertices[:, 1] - center[1],
            vertices[:, 0] - center[0]
        )

        order = torch.argsort(
            angle
        )

        polygon = vertices[order]

        if polygon.shape[0] > max_vertices:

            while polygon.shape[0] > max_vertices:

                n = polygon.shape[0]

                prev = torch.roll(
                    polygon,
                    1,
                    dims=0
                )

                nxt = torch.roll(
                    polygon,
                    -1,
                    dims=0
                )

                v1 = F.normalize(
                    polygon - prev,
                    dim=1
                )

                v2 = F.normalize(
                    nxt - polygon,
                    dim=1
                )

                dot = torch.clamp(
                    (v1 * v2).sum(dim=1),
                    -1.0,
                    1.0
                )

                angle = torch.acos(dot)

                remove = torch.argmin(
                    angle
                )

                keep = torch.ones(
                    n,
                    dtype=torch.bool,
                    device=device
                )

                keep[remove] = False

                polygon = polygon[keep]

        if polygon.shape[0] < 3:
            continue

        area = torch.abs(
            0.5
            * torch.sum(
                polygon[:, 0]
                * torch.roll(
                    polygon[:, 1],
                    -1
                )
                -
                polygon[:, 1]
                * torch.roll(
                    polygon[:, 0],
                    -1
                )
            )
        )

        if float(area.item()) <= 1.0:
            continue

        polygons.append(
            {
                "plane_id": plane_id,
                "polygon": polygon,
                "area": area,
            }
        )

    polygons.sort(
        key=lambda x: float(
            x["area"].item()
        ),
        reverse=True
    )

    return polygons


import cv2
import numpy as np


def save_polygons_debug(
    image,
    polygons,
    output_path,
):
    if torch.is_tensor(image):
        image = image.detach().cpu().numpy()

    image = np.asarray(image)

    if image.dtype != np.uint8:
        image = np.clip(image, 0, 255).astype(np.uint8)

    debug = image.copy()

    rng = np.random.default_rng()

    for i, item in enumerate(polygons):
        polygon = item["polygon"]

        if torch.is_tensor(polygon):
            polygon = polygon.detach().cpu().numpy()

        polygon = np.round(
            polygon
        ).astype(np.int32)

        if polygon.shape[0] < 3:
            continue

        color = tuple(
            int(x)
            for x in rng.integers(
                50,
                256,
                size=3
            )
        )

        polygon_cv = polygon.reshape(
            -1, 1, 2
        )

        overlay = debug.copy()

        cv2.fillPoly(
            overlay,
            [polygon_cv],
            color
        )

        debug = cv2.addWeighted(
            debug,
            0.55,
            overlay,
            0.45,
            0
        )

        cv2.polylines(
            debug,
            [polygon_cv],
            True,
            color,
            1,
            cv2.LINE_AA
        )

        center = polygon.mean(
            axis=0
        ).astype(np.int32)

        cv2.putText(
            debug,
            str(i + 1),
            tuple(center),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )

    cv2.imwrite(
        str(output_path),
        debug
    )