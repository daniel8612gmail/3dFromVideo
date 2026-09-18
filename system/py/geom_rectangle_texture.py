import cv2
import numpy as np
import torch


def create_rectangle_textures(
    image,
    points,
    plane_labels,
    rectangles,
    texture_size=512,
    min_coverage=5.0,
):
    textures = []
    filtered_rectangles = []

    texture_pixels = texture_size * texture_size
    min_pixels = int(texture_pixels * min_coverage / 100.0)

    for rectangle in rectangles:
        plane_id = rectangle["plane_id"]
        corners = rectangle["rectangle"].to(
            device=points.device,
            dtype=points.dtype
        )

        valid = plane_labels == plane_id

        if valid.sum() < 3:
            continue

        ys, xs = torch.where(valid)
        plane_points = points[valid]

        u = corners[1] - corners[0]
        v = corners[3] - corners[0]

        width = torch.linalg.norm(u)
        height = torch.linalg.norm(v)

        if width <= 0 or height <= 0:
            continue

        u = u / width
        v = v / height

        relative = plane_points - corners[0]

        U = torch.sum(relative * u, dim=1)
        V = torch.sum(relative * v, dim=1)

        U = (U / width * (texture_size - 1)).round().long()
        V = (V / height * (texture_size - 1)).round().long()

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

        if len(U) == 0:
            continue

        # Liczba rzeczywiście zajętych pikseli tekstury
        pixel_ids = V * texture_size + U
        occupied_pixels = torch.unique(pixel_ids).numel()

        # Odrzuć prostokąt jeśli pokrycie < min_coverage
        if occupied_pixels < min_pixels:
            continue

        texture = np.zeros(
            (texture_size, texture_size, 4),
            dtype=np.uint8
        )

        ys_np = ys.cpu().numpy()
        xs_np = xs.cpu().numpy()
        U_np = U.cpu().numpy()
        V_np = V.cpu().numpy()

        pixels = image[ys_np, xs_np]

        pixels = cv2.cvtColor(
            pixels.reshape(-1, 1, 3),
            cv2.COLOR_BGR2RGB
        ).reshape(-1, 3)

        texture[V_np, U_np, :3] = pixels
        texture[V_np, U_np, 3] = 255

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

        filtered_rectangles.append(rectangle)

    return textures, filtered_rectangles



def analyze_texture_coverage(textures):
    results = []

    total_pixels = 0
    total_image_pixels = 0

    for i, item in enumerate(textures):
        if item is None:
            continue

        texture = item["texture"]

        alpha = texture[..., 3]

        image_pixels = int((alpha > 0).sum())
        empty_pixels = int((alpha == 0).sum())
        pixels = alpha.size

        image_percent = 100.0 * image_pixels / pixels
        empty_percent = 100.0 * empty_pixels / pixels

        results.append({
            "plane": i,
            "total": pixels,
            "image": image_pixels,
            "empty": empty_pixels,
            "image_percent": image_percent,
            "empty_percent": empty_percent
        })

        total_pixels += pixels
        total_image_pixels += image_pixels

    total_empty_pixels = total_pixels - total_image_pixels

    return {
        "textures": results,
        "total_pixels": total_pixels,
        "image_pixels": total_image_pixels,
        "empty_pixels": total_empty_pixels,
        "image_percent": 100.0 * total_image_pixels / total_pixels if total_pixels else 0,
        "empty_percent": 100.0 * total_empty_pixels / total_pixels if total_pixels else 0
    }
    
    
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