from pathlib import Path
import numpy as np
import trimesh
import torch

def save_dominant_normal_pixels_to_glb(
    points,
    normals_consolidated,
    output_path,
    size=0.05,
):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    valid = (
        torch.linalg.norm(normals_consolidated, dim=-1) > 1e-8
    ) & torch.isfinite(points).all(dim=-1)

    ys, xs = torch.where(valid)

    if ys.numel() == 0:
        raise RuntimeError("No valid pixels with non-zero normals.")

    centers = points[ys, xs]
    normals = normals_consolidated[ys, xs]

    normals = normals / torch.linalg.norm(normals, dim=1, keepdim=True)

    ref = torch.zeros_like(normals)
    ref[:, 0] = 1.0

    parallel = torch.abs(torch.sum(normals * ref, dim=1)) > 0.9
    ref[parallel] = torch.tensor([0.0, 1.0, 0.0], device=normals.device, dtype=normals.dtype)

    u = torch.linalg.cross(normals, ref)
    u = u / torch.linalg.norm(u, dim=1, keepdim=True)

    v = torch.linalg.cross(normals, u)
    v = v / torch.linalg.norm(v, dim=1, keepdim=True)

    half = size * 0.5

    vertices = torch.stack([
        centers - u * half - v * half,
        centers + u * half - v * half,
        centers + u * half + v * half,
        centers - u * half + v * half,
    ], dim=1)

    count = vertices.shape[0]
    base = torch.arange(count, device=vertices.device) * 4

    faces = torch.stack([
        base, base + 1, base + 2,
        base, base + 2, base + 3,
    ], dim=1).reshape(-1, 3)

    mesh = trimesh.Trimesh(
        vertices=vertices.reshape(-1, 3).cpu().numpy(),
        faces=faces.cpu().numpy(),
        process=False,
    )

    mesh.visual.face_colors = np.array([180, 180, 180, 255], dtype=np.uint8)

    trimesh.Scene(mesh).export(str(output_path), file_type="glb")

    print(f"Saved {count} dominant-normal pixel squares: {output_path}")