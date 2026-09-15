import cv2
import torch
import torch.nn.functional as F
import cv2
import numpy as np
import torch


@torch.no_grad()
def polygonize_planes(
    plane_labels,
    planes,
    min_region_size=500,
    smooth_radius=7,
    line_tolerance=3.0,
    min_segment_length=20,
    max_segment_length=250,
    segment_step=5,
    max_vertices=10,
    min_inlier_ratio=0.75,
    debug_dir=None,
    debug_image=None,
):
    if not plane_labels.is_cuda:
        raise ValueError("plane_labels must be CUDA")

    if not planes.is_cuda:
        raise ValueError("planes must be CUDA")

    device = plane_labels.device
    polygons = []

    def fit_line(points):
        center = points.mean(dim=0)
        q = points - center
        covariance = q.T @ q

        eigenvalues, eigenvectors = torch.linalg.eigh(
            covariance
        )

        direction = eigenvectors[:, -1]
        direction = F.normalize(direction, dim=0)

        normal = torch.stack(
            (-direction[1], direction[0])
        )

        distance = torch.abs(q @ normal)

        return center, direction, distance

    def segment_cost(points):
        center, direction, distance = fit_line(points)

        mse = torch.mean(
            torch.clamp(
                distance,
                max=line_tolerance * 3.0
            ) ** 2
        )

        ratio = (
            distance <= line_tolerance
        ).float().mean()

        return mse, ratio

    def make_segment(points):
        center, direction, distance = fit_line(points)

        inliers = distance <= line_tolerance

        if inliers.sum() < 3:
            return None

        points = points[inliers]

        center, direction, _ = fit_line(points)

        q = points - center
        t = q @ direction

        p0 = center + direction * t.min()
        p1 = center + direction * t.max()

        return p0, p1

    def rotate_contour(points):
        n = points.shape[0]

        prev = torch.roll(points, 1, 0)
        nxt = torch.roll(points, -1, 0)

        v1 = F.normalize(points - prev, dim=1)
        v2 = F.normalize(nxt - points, dim=1)

        dot = torch.clamp(
            (v1 * v2).sum(dim=1),
            -1.0,
            1.0
        )

        angles = torch.acos(dot)

        cut = torch.argmax(angles)

        return torch.roll(
            points,
            -int(cut.item()),
            dims=0
        )

    def segment_closed_contour(points):
        n = points.shape[0]

        if n < min_segment_length * 2:
            return []

        max_len = min(max_segment_length, n)

        if max_len < min_segment_length:
            return []

        points = rotate_contour(points)

        points2 = torch.cat(
            (points, points),
            dim=0
        )

        best_total = None
        best_segments = None

        max_start = min(
            n,
            max_len
        )

        for start_offset in range(
            0,
            max_start,
            segment_step
        ):
            start_point = start_offset
            count = n

            dp = torch.full(
                (count + 1,),
                float("inf"),
                device=device,
                dtype=torch.float32
            )

            prev = torch.full(
                (count + 1,),
                -1,
                device=device,
                dtype=torch.long
            )

            dp[0] = 0.0

            for end in range(
                min_segment_length,
                count + 1,
                segment_step
            ):
                start_min = max(
                    0,
                    end - max_len
                )

                start_max = (
                    end - min_segment_length
                )

                if start_max < start_min:
                    continue

                starts = torch.arange(
                    start_min,
                    start_max + 1,
                    step=segment_step,
                    device=device,
                    dtype=torch.long
                )

                candidate_costs = torch.full(
                    (starts.shape[0],),
                    float("inf"),
                    device=device,
                    dtype=torch.float32
                )

                for k in range(starts.shape[0]):

                    s = int(starts[k].item())
                    e = end

                    global_start = start_point + s
                    global_end = start_point + e

                    if global_start < 0:
                        continue

                    if global_end > points2.shape[0]:
                        continue

                    if global_end <= global_start:
                        continue

                    segment = points2[
                        global_start:global_end
                    ]

                    if segment.shape[0] < min_segment_length:
                        continue

                    mse, ratio = segment_cost(
                        segment
                    )

                    valid = (
                        ratio >= min_inlier_ratio
                    ) & (
                        mse <= line_tolerance ** 2
                    )

                    if bool(valid.item()):
                        candidate_costs[k] = (
                            dp[s]
                            + mse
                            + 0.5
                        )

                value, index = torch.min(
                    candidate_costs,
                    dim=0
                )

                if bool(torch.isfinite(value).item()):
                    dp[end] = value
                    prev[end] = starts[index]

            if not bool(torch.isfinite(dp[count]).item()):
                continue

            indices = []

            pos = count

            while pos > 0:

                previous = prev[pos]

                if previous < 0:
                    indices = []
                    break

                start = int(
                    previous.item()
                )

                indices.append(
                    (
                        start + start_point,
                        pos + start_point
                    )
                )

                pos = start

            if not indices:
                continue

            indices.reverse()

            segments = []

            for start, end in indices:

                if start < 0:
                    continue

                if end > points2.shape[0]:
                    continue

                if end <= start:
                    continue

                segment = points2[
                    start:end
                ]

                result = make_segment(
                    segment
                )

                if result is not None:

                    p0, p1 = result

                    segments.append(
                        (
                            start % n,
                            end % n,
                            p0,
                            p1
                        )
                    )

            if len(segments) < 3:
                continue

            total = dp[count]

            if (
                best_total is None
                or bool((total < best_total).item())
            ):
                best_total = total
                best_segments = segments

        return best_segments or []      
    def intersect_lines(p1, d1, p2, d2):
        cross = (
            d1[0] * d2[1]
            - d1[1] * d2[0]
        )

        if torch.abs(cross) < 1e-6:
            return (p1 + p2) * 0.5

        delta = p2 - p1

        t = (
            delta[0] * d2[1]
            - delta[1] * d2[0]
        ) / cross

        return p1 + d1 * t

    def build_polygon(segments):
        lines = []

        for start, end, p0, p1 in segments:
            direction = F.normalize(
                p1 - p0,
                dim=0
            )

            lines.append(
                (
                    p0,
                    direction
                )
            )

        vertices = []

        count = len(lines)

        for i in range(count):
            p1, d1 = lines[i]
            p2, d2 = lines[(i + 1) % count]

            vertex = intersect_lines(
                p1,
                d1,
                p2,
                d2
            )

            vertices.append(vertex)

        polygon = torch.stack(vertices)

        if polygon.shape[0] > 2:
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

            cross = (
                v1[:, 0] * v2[:, 1]
                - v1[:, 1] * v2[:, 0]
            )

            area = torch.sum(
                polygon[:, 0] * nxt[:, 1]
                - nxt[:, 0] * polygon[:, 1]
            )

            if area < 0:
                polygon = torch.flip(
                    polygon,
                    dims=[0]
                )

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

        return polygon

    plane_ids = torch.unique(
        plane_labels
    )

    plane_ids = plane_ids[
        plane_ids >= 0
    ]

    for plane_id in plane_ids.tolist():

        mask = (
            plane_labels == plane_id
        )

        if mask.sum() < min_region_size:
            continue

        x = mask.float()[None, None]

        eroded = -F.max_pool2d(
            -x,
            kernel_size=3,
            stride=1,
            padding=1
        )

        boundary = (
            mask
            &
            ~(eroded[0, 0] > 0.5)
        )

        boundary_cpu = (
            boundary
            .detach()
            .cpu()
            .numpy()
            .astype("uint8")
        )

        contours, _ = cv2.findContours(
            boundary_cpu,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_NONE
        )

        for contour in contours:

            if contour.shape[0] < min_segment_length * 2:
                continue

            contour = contour[:, 0, :]

            points = torch.from_numpy(
                contour.astype("float32")
            ).to(device)

            n = points.shape[0]

            if n < min_segment_length * 2:
                continue

            r = min(
                smooth_radius,
                max(1, (n - 1) // 4)
            )

            if r >= 2:

                kernel = torch.ones(
                    1,
                    1,
                    2 * r + 1,
                    device=device,
                    dtype=points.dtype
                )

                kernel /= kernel.shape[-1]

                px = points[:, 0][None, None]
                py = points[:, 1][None, None]

                px = torch.cat(
                    (
                        px[..., -r:],
                        px,
                        px[..., :r]
                    ),
                    dim=-1
                )

                py = torch.cat(
                    (
                        py[..., -r:],
                        py,
                        py[..., :r]
                    ),
                    dim=-1
                )

                px = F.conv1d(
                    px,
                    kernel
                )[0, 0]

                py = F.conv1d(
                    py,
                    kernel
                )[0, 0]

                points = torch.stack(
                    (px, py),
                    dim=1
                )

            segments = segment_closed_contour(
                points
            )

            if len(segments) < 3:
                continue

            polygon = build_polygon(
                segments
            )

            if debug_dir is not None:
                save_polygon_debug(
                    image=debug_image,
                    contour=contour,
                    segments=segments,
                    polygon=polygon,
                    output_path=debug_dir / f"plane_{plane_id:04d}.png"
                )

            if polygon.shape[0] < 3:
                continue

            polygons.append(
                {
                    "plane_id": plane_id,
                    "polygon": polygon
                }
            )

    return polygons


#================================================
# Debugging
#================================================


def save_polygon_debug(
    image,
    contour,
    segments,
    polygon,
    output_path
):
    if torch.is_tensor(contour):
        contour = contour.detach().float().cpu().numpy()

    if torch.is_tensor(polygon):
        polygon = polygon.detach().float().cpu().numpy()

    contour = np.asarray(contour, dtype=np.float32)
    polygon = np.asarray(polygon, dtype=np.float32)

    if image is None:
        h = int(np.ceil(contour[:, 1].max())) + 20
        w = int(np.ceil(contour[:, 0].max())) + 20
        debug = np.zeros((h, w, 3), dtype=np.uint8)
        debug[:] = 255
    else:
        if torch.is_tensor(image):
            image = image.detach().cpu().numpy()

        image = np.asarray(image)

        if image.ndim == 2:
            debug = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        else:
            debug = image.copy()

        if debug.dtype != np.uint8:
            debug = np.clip(debug, 0, 255).astype(np.uint8)

    h, w = debug.shape[:2]

    def point(p):
        return (
            int(round(float(p[0]))),
            int(round(float(p[1])))
        )

    contour_i = np.round(contour).astype(np.int32)

    if len(contour_i) >= 2:
        cv2.polylines(
            debug,
            [contour_i.reshape(-1, 1, 2)],
            True,
            (255, 255, 0),
            1,
            cv2.LINE_AA
        )

    for i, p in enumerate(contour):
        x, y = point(p)

        if 0 <= x < w and 0 <= y < h:
            cv2.circle(
                debug,
                (x, y),
                2,
                (255, 255, 0),
                -1
            )

    for segment_id, segment in enumerate(segments):

        start, end, p0, p1 = segment

        if torch.is_tensor(p0):
            p0 = p0.detach().float().cpu().numpy()

        if torch.is_tensor(p1):
            p1 = p1.detach().float().cpu().numpy()

        p0 = np.asarray(p0, dtype=np.float32)
        p1 = np.asarray(p1, dtype=np.float32)

        x1, y1 = point(p0)
        x2, y2 = point(p1)

        cv2.line(
            debug,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            2,
            cv2.LINE_AA
        )

        cv2.circle(
            debug,
            (x1, y1),
            5,
            (0, 255, 0),
            -1
        )

        cv2.circle(
            debug,
            (x2, y2),
            5,
            (0, 255, 0),
            -1
        )

        tx = int((x1 + x2) * 0.5)
        ty = int((y1 + y2) * 0.5)

        cv2.putText(
            debug,
            str(segment_id),
            (tx + 4, ty - 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            1,
            cv2.LINE_AA
        )
    
    if len(polygon) >= 2:
        polygon_i = np.round(polygon).astype(np.int32)

        cv2.polylines(
            debug,
            [polygon_i.reshape(-1, 1, 2)],
            True,
            (0, 0, 255),
            3,
            cv2.LINE_AA
        )

        for i, p in enumerate(polygon):
            x, y = point(p)

            cv2.circle(
                debug,
                (x, y),
                7,
                (0, 0, 255),
                -1
            )

            cv2.putText(
                debug,
                str(i),
                (x + 8, y - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 0, 255),
                2,
                cv2.LINE_AA
            )

    legend_x = 20
    legend_y = 30

    cv2.putText(
        debug,
        "CYAN = contour",
        (legend_x, legend_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 0),
        2,
        cv2.LINE_AA
    )

    cv2.putText(
        debug,
        "GREEN = fitted segments",
        (legend_x, legend_y + 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 0),
        2,
        cv2.LINE_AA
    )

    cv2.putText(
        debug,
        "RED = final polygon",
        (legend_x, legend_y + 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 0, 255),
        2,
        cv2.LINE_AA
    )

    output_path = str(output_path)

    cv2.imwrite(
        output_path,
        debug
    )