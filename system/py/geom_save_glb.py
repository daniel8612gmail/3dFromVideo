from pathlib import Path

import numpy as np
import torch
import trimesh

from PIL import Image
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals


def save_rectangles_to_glb(
    rectangles,
    textures,
    output_path,
):
    output_path = Path(output_path)
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    if len(rectangles) != len(textures):
        raise ValueError(
            f"Rectangles/textures count mismatch: "
            f"{len(rectangles)} != {len(textures)}"
        )

    scene = trimesh.Scene()

    for rectangle_data, texture_data in zip(
        rectangles,
        textures
    ):
        rectangle = rectangle_data["rectangle"]

        if torch.is_tensor(rectangle):
            rectangle = rectangle.detach().float().cpu().numpy()

        rectangle = np.asarray(
            rectangle,
            dtype=np.float32
        )

        if rectangle.shape != (4, 3):
            continue

        texture = texture_data["texture"]

        if torch.is_tensor(texture):
            texture = texture.detach().cpu().numpy()

        texture = np.asarray(texture)

        if texture.ndim != 3 or texture.shape[2] != 4:
            raise ValueError(
                "Texture must have shape [H, W, 4] (RGBA)."
            )

        # OpenCV/BGR(A) -> RGB(A), jeśli tekstura pochodzi z cv2
        image = Image.fromarray(texture, "RGBA")

        vertices = rectangle

        faces = np.array(
            [
                [0, 1, 2],
                [0, 2, 3],
            ],
            dtype=np.int64
        )

        uv = np.array(
            [
                [0.0, 1.0],
                [1.0, 1.0],
                [1.0, 0.0],
                [0.0, 0.0],
            ],
            dtype=np.float32
        )

        material = PBRMaterial(
            baseColorTexture=image,
            metallicFactor=0.0,
            roughnessFactor=1.0,
            doubleSided=True,
            alphaMode="BLEND",
            alphaCutoff=0.01,
        )

        visual = TextureVisuals(
            uv=uv,
            material=material
        )

        mesh = trimesh.Trimesh(
            vertices=vertices,
            faces=faces,
            visual=visual,
            process=False
        )

        mesh.metadata["plane_id"] = int(
            rectangle_data["plane_id"]
        )

        scene.add_geometry(
            mesh,
            node_name=(
                f"plane_"
                f"{int(rectangle_data['plane_id']):04d}"
            )
        )

    if len(scene.geometry) == 0:
        raise RuntimeError(
            "No rectangle meshes were created."
        )

    scene.export(
        str(output_path),
        file_type="glb"
    )