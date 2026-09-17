import cv2
import numpy as np
import torch


def create_rectangle_textures(
    image,
    points,
    plane_labels,
    rectangles,
    texture_size=512,
):
    textures = []

    for rectangle in rectangles:
        plane_id = rectangle["plane_id"]
        corners = rectangle["rectangle"].to(
            device=points.device,
            dtype=points.dtype
        )

        # Punkty należące do płaszczyzny
        valid = plane_labels == plane_id

        if valid.sum() < 3:
            textures.append(None)
            continue

        ys, xs = torch.where(valid)
        plane_points = points[valid]

        # --------------------------------------------------------
        # Lokalne osie prostokąta
        #
        # 0 -------- 1
        # |          |
        # |          |
        # 3 -------- 2
        # --------------------------------------------------------

        u = corners[1] - corners[0]
        v = corners[3] - corners[0]

        width = torch.linalg.norm(u)
        height = torch.linalg.norm(v)

        if width <= 0 or height <= 0:
            textures.append(None)
            continue

        u = u / width
        v = v / height

        # --------------------------------------------------------
        # Rzutowanie punktów 3D na lokalne U,V
        # --------------------------------------------------------

        relative = plane_points - corners[0]

        U = torch.sum(relative * u, dim=1)
        V = torch.sum(relative * v, dim=1)

        # --------------------------------------------------------
        # U,V -> współrzędne tekstury
        # --------------------------------------------------------

        U = (
            U / width * (texture_size - 1)
        ).round().long()

        V = (
            V / height * (texture_size - 1)
        ).round().long()

        inside = (
            (U >= 0) &
            (U < texture_size) &
            (V >= 0) &
            (V < texture_size)
        )

        U = U[inside]
        V = V[inside]
        ys = ys[inside]
        xs = xs[inside]

        # --------------------------------------------------------
        # RGBA
        # --------------------------------------------------------

        texture = np.zeros(
            (texture_size, texture_size, 4),
            dtype=np.uint8
        )

        if len(U) > 0:
            ys_np = ys.cpu().numpy()
            xs_np = xs.cpu().numpy()
            U_np = U.cpu().numpy()
            V_np = V.cpu().numpy()

            # cv2.imread() daje BGR
            pixels = image[
                ys_np,
                xs_np
            ]

            pixels = cv2.cvtColor(
                pixels.reshape(-1, 1, 3),
                cv2.COLOR_BGR2RGB
            ).reshape(-1, 3)

            texture[
                V_np,
                U_np,
                :3
            ] = pixels

            # Alpha = 255 tam, gdzie mamy rzeczywisty piksel
            texture[
                V_np,
                U_np,
                3
            ] = 255

        # --------------------------------------------------------
        # Wynik
        # --------------------------------------------------------

        textures.append({
            "texture": texture,
            "corners": corners,
            "center": rectangle["center"],
            "normal": rectangle["normal"],
            "u": u,
            "v": v,
            "width": width,
            "height": height,
            "point_count": rectangle["point_count"],
        })

    return textures



def save_rectangle_textures(textures, logdir):
    for i, item in enumerate(textures):
        if item is None:
            continue

        texture = item["texture"]

        if torch.is_tensor(texture):
            texture = texture.detach().cpu().numpy()

        texture = np.asarray(texture)

        if texture.ndim != 3 or texture.shape[2] != 4:
            raise ValueError(
                f"Texture {i} must have shape [H, W, 4], "
                f"got {texture.shape}"
            )

        path = f"{logdir}_texture_{i:03d}.png"

        # RGB(A) -> BGRA dla OpenCV
        texture_bgra = cv2.cvtColor(
            texture,
            cv2.COLOR_RGBA2BGRA
        )

        if not cv2.imwrite(str(path), texture_bgra):
            raise IOError(
                f"Failed to save texture: {path}"
            )