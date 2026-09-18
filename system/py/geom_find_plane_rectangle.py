import torch


def find_plane_rectangles(
    points,
    plane_labels,
    planes_consolidated,
):
    rectangles = []

    for plane_index, plane in enumerate(planes_consolidated):
        plane_id = int(plane["plane_id"]) if isinstance(plane, dict) else plane_index

        valid = plane_labels == plane_id
        plane_points = points[valid]

        if plane_points.shape[0] < 3:
            rectangles.append(None)
            continue

        center = plane_points.mean(dim=0)

        if isinstance(plane, dict):
            normal = plane["normal"]
        else:
            normal = plane[:3]

        normal = normal.to(
            device=points.device,
            dtype=points.dtype
        )

        normal_length = torch.linalg.norm(normal)

        if normal_length < 1e-8:
            rectangles.append(None)
            continue

        normal = normal / normal_length

        # Wybór wektora referencyjnego nie równoległego do normalnej
        if torch.abs(normal[0]) < 0.9:
            ref = torch.tensor(
                [1.0, 0.0, 0.0],
                device=points.device,
                dtype=points.dtype
            )
        else:
            ref = torch.tensor(
                [0.0, 1.0, 0.0],
                device=points.device,
                dtype=points.dtype
            )

        # Osie lokalnego układu płaszczyzny
        u = torch.cross(normal, ref, dim=0)
        u = u / torch.linalg.norm(u).clamp_min(1e-8)

        v = torch.cross(normal, u, dim=0)
        v = v / torch.linalg.norm(v).clamp_min(1e-8)

        # Współrzędne punktów w układzie płaszczyzny
        relative = plane_points - center

        U = torch.sum(relative * u, dim=1)
        V = torch.sum(relative * v, dim=1)

        u_min = U.min()
        u_max = U.max()
        v_min = V.min()
        v_max = V.max()

        # Prostokąt w lokalnym układzie płaszczyzny
        rectangle = torch.stack([
            center + u * u_min + v * v_min,
            center + u * u_max + v * v_min,
            center + u * u_max + v * v_max,
            center + u * u_min + v * v_max,
        ])

        # Sprawdzenie rzeczywistego kierunku normalnej prostokąta
        rectangle_normal = torch.cross(
            rectangle[1] - rectangle[0],
            rectangle[2] - rectangle[0],
            dim=0
        )

        rectangle_normal = rectangle_normal / torch.linalg.norm(
            rectangle_normal
        ).clamp_min(1e-8)

        # Wymuszenie zgodności windingu z normalną płaszczyzny
        if torch.dot(rectangle_normal, normal) < 0:
            rectangle = rectangle[[0, 3, 2, 1]]

            # U też musi odpowiadać faktycznej kolejności
            u = rectangle[1] - rectangle[0]
            u = u / torch.linalg.norm(u).clamp_min(1e-8)

            v = rectangle[3] - rectangle[0]
            v = v / torch.linalg.norm(v).clamp_min(1e-8)

        width = u_max - u_min
        height = v_max - v_min
        area = width * height

        rectangles.append({
            "plane_id": plane_id,
            "rectangle": rectangle,
            "center": center,
            "normal": normal,
            "u": u,
            "v": v,
            "width": width,
            "height": height,
            "area": area,
            "point_count": plane_points.shape[0],
        })

    return rectangles