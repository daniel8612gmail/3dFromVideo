"""Aggregate registered per-frame GLBs and fuse overlapping planar textures.

CLI::

    python system/py/geom_aggregate_glb.py --manifest frames.json --output session.glb

Manifest schema (JSON, schemaVersion 1)::

    {
      "schemaVersion": 1,
      "systemSessionId": "session-id",
      "targetVersion": 3,
      "frames": [{
        "frameId": "frame-0001",
        "sequence": 1,
        "glbPath": "relative/or/absolute/frame_planes.glb",
        "translationM": [0, 0, 0],
        "rotationQuaternionXyzw": [0, 0, 0, 1]
      }]
    }

Matrices are row-major, column-vector homogeneous transforms.  The 4x4
``translationM`` and the normalized xyzw quaternion form the rigid
``T_session_from_captureCamera`` (translation in metres). Every frame must
register to the same capture session; no client-supplied axes, MoGe mapping,
or scale is accepted. Each GLB requires its adjacent
``<frame.glb>.convention.json`` produced by the worker from verified MoGe
runtime/checkpoint provenance and canonical input orientation.

The single-image exporter stores each MoGe point after
F = diag(1,-1,-1,1). Verified MoGe v3 returns metric metres in the OpenCV
camera basis (+X right,+Y down,+Z forward); the capture camera is ARCore's
OpenGL basis (+X right,+Y up,-Z forward). Aggregation applies fixed F once to
undo the legacy GLB storage basis and once to map MoGe to the capture camera.
Metric v3 output is used at units-per-metre scale 1, without a second scale:

    T_session_from_captureCamera @ F @ Scale(1) @ F

Any transforms already present in the input GLB scene graph are respected in
the stored-GLB basis before this conversion. Strictly planar rectangular
patches with textured UVs are grouped only when they are coplanar within the
registration tolerance and have meaningful footprint overlap. Their triangles
are emitted as one mesh with a shared orthographic UV atlas. Source texels are
projected through their original UVs; later sequence numbers deterministically
win in covered pixels using alpha compositing. Pixels not covered by a later
source retain the earlier texture. The mesh footprint is the union of input
vertices, never an enclosing rectangle. Non-textured, non-rectangular,
non-planar, or weakly overlapping surfaces remain independent. A textured
mesh with missing/invalid UV data or an unreadable image fails explicitly
rather than being reported as a successful texture merge.

Plane normals must differ by at most 1 degree, the full vertex extents must
remain within 5 mm plus 0.1% of the smaller footprint's diagonal, both
patches must be planar and rectangular within 1.5%, and their projected
intersection must cover at least 20% of the smaller footprint. This permits
real partial overlap while rejecting mere proximity and weak slivers.
Touching-only, non-rectangular, non-planar, insufficiently coplanar, and
weakly overlapping meshes stay separate. Exactly co-located real surfaces
cannot be distinguished from duplicate captures using only GLB geometry and
UVs; in that inherently ambiguous case later sequence content alpha-composites
over earlier content. Node names retain frame/sequence provenance.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from PIL import Image
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals
from moge_convention import (
    GLB_FROM_MOGE,
    ConventionError,
    validate_glb_sidecar,
)


QUATERNION_NORM_TOLERANCE = 1e-3
MAX_ABS_OUTPUT_COORDINATE_M = float(np.finfo(np.float32).max)
PLANE_NORMAL_ANGLE_DEGREES = 1.0
PLANE_OFFSET_ABSOLUTE_M = 0.005
PLANE_OFFSET_RELATIVE = 0.001
RECTANGLE_AREA_TOLERANCE = 0.015
PATCH_OVERLAP_MINIMUM = 0.20
MAX_ATLAS_DIMENSION = 8192
MAX_ATLAS_PIXELS = 32_000_000


JSON_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "3D From Video frame GLB aggregation manifest",
    "type": "object",
    "required": ["schemaVersion", "systemSessionId", "targetVersion", "frames"],
    "properties": {
        "schemaVersion": {"const": 1},
        "systemSessionId": {"type": "string", "minLength": 1},
        "targetVersion": {"type": "integer", "minimum": 1},
        "frames": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": [
                    "frameId", "sequence", "glbPath", "translationM",
                    "rotationQuaternionXyzw",
                ],
                "properties": {
                    "frameId": {"type": "string", "minLength": 1},
                    "sequence": {"type": "integer", "minimum": 0},
                    "glbPath": {"type": "string", "minLength": 1},
                    "translationM": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "rotationQuaternionXyzw": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
                },
            },
        },
    },
}


class AggregationError(ValueError):
    """A manifest, registration, or input geometry failed validation."""


def _finite_vector(value: Any, length: int, field: str) -> np.ndarray:
    try:
        result = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise AggregationError(f"{field} must contain {length} finite numbers") from exc
    if result.shape != (length,) or not np.isfinite(result).all():
        raise AggregationError(f"{field} must contain {length} finite numbers")
    return result


def _pose_matrix(translation: Any, quaternion: Any) -> np.ndarray:
    translation_m = _finite_vector(translation, 3, "translationM")
    q = _finite_vector(quaternion, 4, "rotationQuaternionXyzw")
    norm = float(np.linalg.norm(q))
    if norm == 0.0 or abs(norm - 1.0) > QUATERNION_NORM_TOLERANCE:
        raise AggregationError(
            "rotationQuaternionXyzw must be unit length within "
            f"{QUATERNION_NORM_TOLERANCE}; accepted quaternions are normalized"
        )
    x, y, z, w = q / norm
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]
    matrix[:3, 3] = translation_m
    return matrix


def _validate_frame(frame: Any, index: int, manifest_dir: Path) -> dict[str, Any]:
    label = f"frames[{index}]"
    if not isinstance(frame, dict):
        raise AggregationError(f"{label} must be an object")

    frame_id = frame.get("frameId")
    if not isinstance(frame_id, str) or not frame_id.strip():
        raise AggregationError(f"{label}.frameId must be a non-empty string")
    sequence = frame.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise AggregationError(f"{label}.sequence must be a non-negative integer")
    glb_value = frame.get("glbPath")
    if not isinstance(glb_value, str) or not glb_value.strip():
        raise AggregationError(f"{label}.glbPath must be a non-empty path")
    glb_path = Path(glb_value)
    if not glb_path.is_absolute():
        glb_path = manifest_dir / glb_path
    if not glb_path.is_file():
        raise AggregationError(f"{label}.glbPath does not exist: {glb_path}")

    client_convention_fields = {
        "mogeToCameraMatrix4x4", "scaleEstimate", "axes",
    }.intersection(frame)
    if client_convention_fields:
        names = ", ".join(sorted(client_convention_fields))
        raise AggregationError(
            f"{label} contains client-supplied convention field(s) {names}; "
            "axes, model mapping, and scale must come from the trusted worker sidecar."
        )
    sidecar_path = Path(str(glb_path) + ".convention.json")
    try:
        validate_glb_sidecar(sidecar_path)
    except ConventionError as exc:
        raise AggregationError(f"{label} has no acceptable trusted convention sidecar: {exc}") from exc
    pose = _pose_matrix(frame.get("translationM"), frame.get("rotationQuaternionXyzw"))
    metric_scale = np.eye(4, dtype=np.float64)
    # Sidecar validates both fixed transforms; explicitly undo the legacy
    # exporter flip and then map MoGe OpenCV axes into the capture ARCore basis.
    transform = pose @ GLB_FROM_MOGE @ metric_scale @ GLB_FROM_MOGE
    return {
        "frame_id": frame_id,
        "sequence": sequence,
        "path": glb_path,
        "transform": transform,
    }


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")[:80] or "frame"


def _scene_geometry(scene: trimesh.Scene, frame: dict[str, Any]) -> list[tuple[str, trimesh.Trimesh]]:
    result: list[tuple[str, trimesh.Trimesh]] = []
    for geometry_index, node_name in enumerate(scene.graph.nodes_geometry):
        node_transform, geometry_name = scene.graph[node_name]
        geometry = scene.geometry[geometry_name]
        if not isinstance(geometry, trimesh.Trimesh):
            continue
        if len(geometry.vertices) == 0 or len(geometry.faces) == 0:
            continue
        vertices = np.asarray(geometry.vertices, dtype=np.float64)
        faces = np.asarray(geometry.faces)
        if not np.isfinite(vertices).all():
            raise AggregationError(
                f"Input GLB {frame['path']} geometry {geometry_name!r} has non-finite vertices"
            )
        if faces.ndim != 2 or faces.shape[1] != 3 or faces.min() < 0 or faces.max() >= len(vertices):
            raise AggregationError(
                f"Input GLB {frame['path']} geometry {geometry_name!r} has invalid triangle indices"
            )
        node_matrix = np.asarray(node_transform, dtype=np.float64)
        if (node_matrix.shape != (4, 4) or not np.isfinite(node_matrix).all()
                or not np.allclose(node_matrix[3], [0.0, 0.0, 0.0, 1.0], atol=1e-7, rtol=0.0)):
            raise AggregationError(f"Input GLB {frame['path']} has an invalid scene node transform")
        triangles = vertices[faces]
        double_areas = np.linalg.norm(
            np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]),
            axis=1,
        )
        if not np.isfinite(double_areas).all() or not np.any(double_areas > 1e-12):
            raise AggregationError(
                f"Input GLB {frame['path']} geometry {geometry_name!r} is degenerate"
            )
        # Transform local vertices into stored GLB scene coordinates, then into
        # raw MoGe, camera, and common session coordinates.
        glb_world = trimesh.transform_points(vertices, node_matrix)
        transformed = trimesh.transform_points(glb_world, frame["transform"])
        if (not np.isfinite(transformed).all()
                or np.max(np.abs(transformed)) > MAX_ABS_OUTPUT_COORDINATE_M):
            raise AggregationError(
                f"Transformed geometry from {frame['path']} exceeds finite float32 GLB bounds"
            )
        mesh = geometry.copy()
        mesh.vertices = transformed
        mesh.metadata = dict(mesh.metadata)
        mesh.metadata.update({
            "source_frame_id": frame["frame_id"],
            "source_sequence": frame["sequence"],
            "source_glb": str(frame["path"]),
            "source_node": str(node_name),
        })
        provenance = (
            f"frame_{frame['sequence']:06d}_{_safe_name(frame['frame_id'])}"
            f"_mesh_{geometry_index:04d}_{_safe_name(str(node_name))}"
        )
        result.append((provenance, mesh))
    if not result:
        raise AggregationError(f"Input GLB has no non-empty triangle meshes: {frame['path']}")
    return result


def _polygon_area(polygon: np.ndarray) -> float:
    if len(polygon) < 3:
        return 0.0
    return abs(float(np.dot(polygon[:, 0], np.roll(polygon[:, 1], -1))
                     - np.dot(polygon[:, 1], np.roll(polygon[:, 0], -1)))) * 0.5


def _convex_hull_2d(points: np.ndarray) -> np.ndarray:
    unique = sorted(set(map(tuple, np.asarray(points, dtype=np.float64))))
    if len(unique) < 3:
        return np.empty((0, 2), dtype=np.float64)

    def cross(origin: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return ((a[0] - origin[0]) * (b[1] - origin[1])
                - (a[1] - origin[1]) * (b[0] - origin[0]))

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return np.asarray(lower[:-1] + upper[:-1], dtype=np.float64)


def _minimum_bounding_rectangle_area(hull: np.ndarray) -> float:
    minimum_area = math.inf
    for start, end in zip(hull, np.roll(hull, -1, axis=0)):
        edge = end - start
        length = float(np.linalg.norm(edge))
        if length <= 1e-12:
            continue
        axis_x = edge / length
        axis_y = np.array([-axis_x[1], axis_x[0]])
        projected = np.column_stack((hull @ axis_x, hull @ axis_y))
        extent = projected.max(axis=0) - projected.min(axis=0)
        minimum_area = min(minimum_area, float(extent[0] * extent[1]))
    return minimum_area


def _rectangle_profile(mesh: trimesh.Trimesh) -> dict[str, Any] | None:
    """Return a strict planar-rectangle profile, or None for ambiguous geometry."""
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    if len(vertices) < 3 or len(faces) == 0:
        return None
    center = vertices.mean(axis=0)
    try:
        _, singular_values, axes = np.linalg.svd(vertices - center, full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    if len(singular_values) < 3 or singular_values[0] <= 1e-10:
        return None
    normal = axes[-1]
    normal_length = float(np.linalg.norm(normal))
    if normal_length <= 1e-12:
        return None
    normal = normal / normal_length
    # Give the fitted normal a deterministic sign; pair comparisons remain unoriented.
    significant = np.flatnonzero(np.abs(normal) > 1e-10)
    if len(significant) and normal[significant[0]] < 0:
        normal = -normal
    diagonal = float(np.linalg.norm(vertices.max(axis=0) - vertices.min(axis=0)))
    if diagonal <= 1e-9:
        return None
    plane_tolerance = max(1e-6, diagonal * 0.001)
    if float(np.max(np.abs((vertices - center) @ normal))) > plane_tolerance:
        return None

    axis_x = axes[0] - normal * float(np.dot(axes[0], normal))
    axis_length = float(np.linalg.norm(axis_x))
    if axis_length <= 1e-10:
        return None
    axis_x /= axis_length
    significant = np.flatnonzero(np.abs(axis_x) > 1e-10)
    if len(significant) and axis_x[significant[0]] < 0:
        axis_x = -axis_x
    axis_y = np.cross(normal, axis_x)
    projected = np.column_stack(((vertices - center) @ axis_x, (vertices - center) @ axis_y))
    hull = _convex_hull_2d(projected)
    hull_area = _polygon_area(hull)
    if hull_area <= 1e-10:
        return None
    rectangle_area = _minimum_bounding_rectangle_area(hull)
    if rectangle_area <= 1e-10 or hull_area / rectangle_area < 1.0 - RECTANGLE_AREA_TOLERANCE:
        return None

    triangles = vertices[faces]
    projected_triangles = np.stack((
        (triangles - center) @ axis_x,
        (triangles - center) @ axis_y,
    ), axis=2)
    edge_a = projected_triangles[:, 1] - projected_triangles[:, 0]
    edge_b = projected_triangles[:, 2] - projected_triangles[:, 0]
    triangle_area = 0.5 * np.abs(edge_a[:, 0] * edge_b[:, 1]
                                 - edge_a[:, 1] * edge_b[:, 0]).sum()
    # Reject holes, substantial overlap, and otherwise incomplete/ambiguous surfaces.
    if abs(float(triangle_area) / hull_area - 1.0) > RECTANGLE_AREA_TOLERANCE:
        return None
    return {
        "center": center,
        "normal": normal,
        "axis_x": axis_x,
        "axis_y": axis_y,
        "diagonal": diagonal,
        "hull_area": hull_area,
    }


def _convex_intersection(subject: np.ndarray, clip: np.ndarray) -> np.ndarray:
    """Clip one CCW convex polygon by another (Sutherland-Hodgman)."""
    output = [point.copy() for point in subject]
    scale = max(
        1.0,
        float(np.ptp(subject, axis=0).max()),
        float(np.ptp(clip, axis=0).max()),
    )
    epsilon = 1e-10 * scale * scale
    for edge_start, edge_end in zip(clip, np.roll(clip, -1, axis=0)):
        if not output:
            break
        input_points = output
        output = []

        def signed_distance(point: np.ndarray) -> float:
            edge = edge_end - edge_start
            relative = point - edge_start
            return float(edge[0] * relative[1] - edge[1] * relative[0])

        previous = input_points[-1]
        previous_distance = signed_distance(previous)
        for current in input_points:
            current_distance = signed_distance(current)
            previous_inside = previous_distance >= -epsilon
            current_inside = current_distance >= -epsilon
            if current_inside != previous_inside:
                denominator = previous_distance - current_distance
                if abs(denominator) > 1e-15:
                    fraction = previous_distance / denominator
                    output.append(previous + fraction * (current - previous))
            if current_inside:
                output.append(current)
            previous = current
            previous_distance = current_distance
    return np.asarray(output, dtype=np.float64).reshape((-1, 2))


def _are_mergeable_patches(
    first: trimesh.Trimesh,
    first_profile: dict[str, Any],
    second: trimesh.Trimesh,
    second_profile: dict[str, Any],
) -> bool:
    normal_dot = abs(float(np.dot(first_profile["normal"], second_profile["normal"])))
    minimum_dot = math.cos(math.radians(PLANE_NORMAL_ANGLE_DEGREES))
    if normal_dot < minimum_dot:
        return False

    common_normal = first_profile["normal"] + (
        second_profile["normal"] if np.dot(first_profile["normal"], second_profile["normal"]) >= 0
        else -second_profile["normal"]
    )
    normal_length = float(np.linalg.norm(common_normal))
    if normal_length <= 1e-12:
        return False
    common_normal /= normal_length
    smallest_diagonal = min(first_profile["diagonal"], second_profile["diagonal"])
    plane_tolerance = PLANE_OFFSET_ABSOLUTE_M + PLANE_OFFSET_RELATIVE * smallest_diagonal
    first_vertices = np.asarray(first.vertices, dtype=np.float64)
    second_vertices = np.asarray(second.vertices, dtype=np.float64)
    # Check the whole extents against both fitted planes, not just centroid
    # separation; a small angular mismatch can otherwise look coplanar at its
    # center while diverging materially at the rectangle edges.
    first_plane_distance = float(np.max(np.abs(
        (second_vertices - first_profile["center"]) @ first_profile["normal"]
    )))
    second_plane_distance = float(np.max(np.abs(
        (first_vertices - second_profile["center"]) @ second_profile["normal"]
    )))
    if max(first_plane_distance, second_plane_distance) > plane_tolerance:
        return False

    axis_x = first_profile["axis_x"] - common_normal * float(
        np.dot(first_profile["axis_x"], common_normal)
    )
    axis_length = float(np.linalg.norm(axis_x))
    if axis_length <= 1e-10:
        return False
    axis_x /= axis_length
    axis_y = np.cross(common_normal, axis_x)
    origin = first_profile["center"]

    def project(mesh: trimesh.Trimesh) -> np.ndarray:
        points = np.asarray(mesh.vertices, dtype=np.float64) - origin
        return np.column_stack((points @ axis_x, points @ axis_y))

    first_hull = _convex_hull_2d(project(first))
    second_hull = _convex_hull_2d(project(second))
    first_area = _polygon_area(first_hull)
    second_area = _polygon_area(second_hull)
    if min(first_area, second_area) <= 1e-10:
        return False
    intersection_area = _polygon_area(_convex_intersection(first_hull, second_hull))
    return intersection_area / min(first_area, second_area) >= PATCH_OVERLAP_MINIMUM


def _texture_image_and_uv(mesh: trimesh.Trimesh) -> tuple[Image.Image, np.ndarray] | None:
    """Return a validated RGBA base-color image and per-vertex UVs if present."""
    visual = mesh.visual
    uv = getattr(visual, "uv", None)
    material = getattr(visual, "material", None)
    image = getattr(material, "baseColorTexture", None)
    if image is None:
        return None
    if uv is None:
        raise AggregationError("Textured patch has a base-color image but no UV coordinates")
    if not isinstance(image, Image.Image):
        try:
            image = Image.fromarray(np.asarray(image))
        except (TypeError, ValueError) as exc:
            raise AggregationError("Textured patch has an unreadable base-color texture") from exc
    if image.width < 1 or image.height < 1:
        raise AggregationError("Textured patch has an empty base-color texture")
    uv_array = np.asarray(uv, dtype=np.float64)
    if uv_array.shape != (len(mesh.vertices), 2) or not np.isfinite(uv_array).all():
        raise AggregationError("Textured patch must have finite per-vertex [u,v] coordinates")
    return image.convert("RGBA"), uv_array


def _sample_image(image: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Bilinearly sample a GLB UV image (v=1 addresses the image's bottom row)."""
    height, width = image.shape[:2]
    px = np.clip(u, 0.0, 1.0) * (width - 1)
    py = (1.0 - np.clip(v, 0.0, 1.0)) * (height - 1)
    x0 = np.floor(px).astype(np.int64)
    y0 = np.floor(py).astype(np.int64)
    x1 = np.minimum(x0 + 1, width - 1)
    y1 = np.minimum(y0 + 1, height - 1)
    dx = (px - x0)[..., None]
    dy = (py - y0)[..., None]
    top = image[y0, x0] * (1.0 - dx) + image[y0, x1] * dx
    bottom = image[y1, x0] * (1.0 - dx) + image[y1, x1] * dx
    return top * (1.0 - dy) + bottom * dy


def _rasterize_patch(
    atlas: np.ndarray,
    image: np.ndarray,
    source_uv: np.ndarray,
    vertices_2d: np.ndarray,
    faces: np.ndarray,
    bounds: tuple[float, float, float, float],
) -> None:
    """Project source textured triangles into an atlas, alpha-over in call order."""
    min_x, min_y, max_x, max_y = bounds
    atlas_h, atlas_w = atlas.shape[:2]
    span_x = max(max_x - min_x, 1e-12)
    span_y = max(max_y - min_y, 1e-12)
    covered = np.zeros((atlas_h, atlas_w), dtype=bool)
    pixel_vertices = np.column_stack((
        (vertices_2d[:, 0] - min_x) / span_x * (atlas_w - 1),
        (max_y - vertices_2d[:, 1]) / span_y * (atlas_h - 1),
    ))
    for face in faces:
        points = pixel_vertices[face]
        uv = source_uv[face]
        low = np.maximum(np.floor(points.min(axis=0)).astype(int), [0, 0])
        high = np.minimum(np.ceil(points.max(axis=0)).astype(int), [atlas_w - 1, atlas_h - 1])
        if np.any(high < low):
            continue
        a, b, c = points
        denominator = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(float(denominator)) <= 1e-12:
            continue
        # Bound temporary raster arrays independently of atlas/face size.
        for row_start in range(low[1], high[1] + 1, 128):
            row_end = min(row_start + 127, high[1])
            x_grid, y_grid = np.meshgrid(
                np.arange(low[0], high[0] + 1),
                np.arange(row_start, row_end + 1),
            )
            weight_a = ((b[1] - c[1]) * (x_grid - c[0])
                        + (c[0] - b[0]) * (y_grid - c[1])) / denominator
            weight_b = ((c[1] - a[1]) * (x_grid - c[0])
                        + (a[0] - c[0]) * (y_grid - c[1])) / denominator
            weight_c = 1.0 - weight_a - weight_b
            inside = (weight_a >= -1e-6) & (weight_b >= -1e-6) & (weight_c >= -1e-6)
            inside &= ~covered[y_grid, x_grid]
            if not np.any(inside):
                continue
            weights = np.stack((weight_a, weight_b, weight_c), axis=-1)[inside]
            interpolated_uv = weights @ uv
            sampled = _sample_image(image, interpolated_uv[:, 0], interpolated_uv[:, 1])
            target_y = y_grid[inside]
            target_x = x_grid[inside]
            covered[target_y, target_x] = True
            destination = atlas[target_y, target_x].astype(np.float64) / 255.0
            source = sampled / 255.0
            alpha = source[:, 3:4]
            out_alpha = alpha + destination[:, 3:4] * (1.0 - alpha)
            numerator = source[:, :3] * alpha + destination[:, :3] * destination[:, 3:4] * (1.0 - alpha)
            out_rgb = np.divide(numerator, out_alpha, out=np.zeros_like(numerator), where=out_alpha > 1e-12)
            atlas[target_y, target_x, :3] = np.clip(np.round(out_rgb * 255.0), 0, 255).astype(np.uint8)
            atlas[target_y, target_x, 3] = np.clip(np.round(out_alpha[:, 0] * 255.0), 0, 255).astype(np.uint8)


def _merge_patch_group(
    sources: list[tuple[str, trimesh.Trimesh, dict[str, Any]]],
) -> tuple[str, trimesh.Trimesh]:
    """Fuse one coplanar patch group into one mesh and one shared texture atlas."""
    sources = sorted(sources, key=lambda source: (
        int(source[1].metadata.get("source_sequence", 0)),
        str(source[1].metadata.get("source_frame_id", "")),
        str(source[1].metadata.get("source_node", "")),
    ))
    first_profile = sources[0][2]
    normal = first_profile["normal"].copy()
    axis_x = first_profile["axis_x"] - normal * float(np.dot(first_profile["axis_x"], normal))
    axis_x /= np.linalg.norm(axis_x)
    axis_y = np.cross(normal, axis_x)
    origin = first_profile["center"]

    projected: list[np.ndarray] = []
    visual_data: list[tuple[Image.Image, np.ndarray]] = []
    for _, mesh, _ in sources:
        vertices = np.asarray(mesh.vertices, dtype=np.float64)
        relative = vertices - origin
        projected.append(np.column_stack((relative @ axis_x, relative @ axis_y)))
        texture_data = _texture_image_and_uv(mesh)
        if texture_data is None:
            raise AggregationError("Cannot fuse a planar patch without a base-color texture and UVs")
        visual_data.append(texture_data)

    all_points = np.concatenate(projected, axis=0)
    min_x, min_y = all_points.min(axis=0)
    max_x, max_y = all_points.max(axis=0)
    span_x, span_y = max(max_x - min_x, 1e-9), max(max_y - min_y, 1e-9)
    density_x = max(image.width / max(np.ptp(points[:, 0]), 1e-9)
                    for (image, _), points in zip(visual_data, projected))
    density_y = max(image.height / max(np.ptp(points[:, 1]), 1e-9)
                    for (image, _), points in zip(visual_data, projected))
    atlas_w = max(2, min(MAX_ATLAS_DIMENSION, int(math.ceil(span_x * density_x)) + 1))
    atlas_h = max(2, min(MAX_ATLAS_DIMENSION, int(math.ceil(span_y * density_y)) + 1))
    if atlas_w * atlas_h > MAX_ATLAS_PIXELS:
        reduction = math.sqrt(MAX_ATLAS_PIXELS / float(atlas_w * atlas_h))
        atlas_w = max(2, int(atlas_w * reduction))
        atlas_h = max(2, int(atlas_h * reduction))
    atlas = np.zeros((atlas_h, atlas_w, 4), dtype=np.uint8)
    bounds = (float(min_x), float(min_y), float(max_x), float(max_y))

    vertex_chunks: list[np.ndarray] = []
    face_chunks: list[np.ndarray] = []
    uv_chunks: list[np.ndarray] = []
    vertex_offset = 0
    for (_, mesh, _), points, (image, source_uv) in zip(sources, projected, visual_data):
        faces = np.asarray(mesh.faces, dtype=np.int64)
        _rasterize_patch(
            atlas, np.asarray(image.convert("RGBA"), dtype=np.float64), source_uv,
            points, faces, bounds,
        )
        uv = np.column_stack((
            (points[:, 0] - min_x) / span_x,
            1.0 - (points[:, 1] - min_y) / span_y,
        ))
        # Snap accepted registration noise to the shared plane so overlapping
        # faces do not retain tiny depth offsets and z-fight in the viewer.
        vertex_chunks.append(
            origin + points[:, :1] * axis_x + points[:, 1:2] * axis_y
        )
        face_chunks.append(faces + vertex_offset)
        uv_chunks.append(uv)
        vertex_offset += len(mesh.vertices)

    # Exact co-registered duplicates share geometry rather than emitting
    # coincident triangles. Distinct footprints retain their actual vertices;
    # no bounding-box geometry is invented to fill gaps.
    vertices = np.concatenate(vertex_chunks, axis=0)
    faces = np.concatenate(face_chunks, axis=0)
    if len(sources) == 2:
        first_vertices, second_vertices = vertex_chunks
        first_faces, second_faces = np.asarray(sources[0][1].faces), np.asarray(sources[1][1].faces)
        if (first_vertices.shape == second_vertices.shape
                and first_faces.shape == second_faces.shape
                and np.allclose(first_vertices, second_vertices, atol=1e-7, rtol=0.0)
                and np.array_equal(first_faces, second_faces)):
            vertices, faces = first_vertices, first_faces
            uv_chunks = [uv_chunks[0]]
    uv = np.concatenate(uv_chunks, axis=0)
    material = PBRMaterial(
        baseColorTexture=Image.fromarray(atlas, "RGBA"),
        metallicFactor=0.0,
        roughnessFactor=1.0,
        doubleSided=True,
        alphaMode="BLEND",
    )
    merged = trimesh.Trimesh(
        vertices=vertices,
        faces=faces,
        visual=TextureVisuals(uv=uv, material=material),
        process=False,
    )
    merged.metadata = dict(sources[0][1].metadata)
    source_records = [{
        "frame_id": mesh.metadata.get("source_frame_id"),
        "sequence": mesh.metadata.get("source_sequence"),
        "glb": mesh.metadata.get("source_glb"),
        "node": mesh.metadata.get("source_node"),
    } for _, mesh, _ in sources]
    merged.metadata["merged_patch_sources"] = source_records
    # Retain this legacy diagnostic key for consumers that already display
    # suppressed duplicate provenance; entries now describe fused sources.
    merged.metadata["suppressed_duplicate_sources"] = source_records[1:]
    merged.metadata["texture_merge_policy"] = "sequence_order_alpha_over"
    return sources[0][0], merged


def _merge_coplanar_textured_patches(
    meshes: list[tuple[str, trimesh.Trimesh]],
) -> list[tuple[str, trimesh.Trimesh]]:
    """Merge overlapping coplanar textured rectangles without filling gaps."""
    ordered = sorted(
        meshes,
        key=lambda item: (
            int(item[1].metadata.get("source_sequence", 0)),
            str(item[1].metadata.get("source_frame_id", "")),
            str(item[1].metadata.get("source_node", "")),
            item[0],
        ),
    )
    groups: list[list[tuple[str, trimesh.Trimesh, dict[str, Any]]]] = []
    independent: list[tuple[str, trimesh.Trimesh]] = []
    for name, mesh in ordered:
        profile = _rectangle_profile(mesh)
        texture_data = _texture_image_and_uv(mesh)
        if profile is None or texture_data is None:
            independent.append((name, mesh))
            continue
        matching_group = None
        for group in groups:
            if any(_are_mergeable_patches(existing, existing_profile, mesh, profile)
                   for _, existing, existing_profile in group):
                matching_group = group
                break
        if matching_group is None:
            groups.append([(name, mesh, profile)])
        else:
            matching_group.append((name, mesh, profile))

    result = independent
    for group in groups:
        if len(group) == 1:
            result.append((group[0][0], group[0][1]))
        else:
            result.append(_merge_patch_group(group))
    return sorted(result, key=lambda item: item[0])


def _validate_base_frame(frames: list[dict[str, Any]]) -> None:
    """Require one sequence-zero capture-camera reference for publisher output."""
    if any(not isinstance(frame, dict) for frame in frames):
        raise AggregationError("Every publisher frame entry must be an object")
    base_frames = [frame for frame in frames if frame.get("sequence") == 0]
    if len(base_frames) != 1:
        raise AggregationError(
            "Publisher aggregation requires exactly one sequence-0 base frame"
        )
    base = base_frames[0]
    translation = _finite_vector(base.get("translationM"), 3, "translationM")
    quaternion = _finite_vector(
        base.get("rotationQuaternionXyzw"), 4, "rotationQuaternionXyzw"
    )
    norm = float(np.linalg.norm(quaternion))
    if norm == 0.0 or abs(norm - 1.0) > QUATERNION_NORM_TOLERANCE:
        raise AggregationError(
            "rotationQuaternionXyzw must be unit length within "
            f"{QUATERNION_NORM_TOLERANCE}; accepted quaternions are normalized"
        )
    normalized_quaternion = quaternion / norm
    # Quaternion signs are equivalent; use the same positive-w canonical
    # representation as the publisher when checking the sequence-zero pose.
    if normalized_quaternion[3] < 0:
        normalized_quaternion = -normalized_quaternion
    if (not np.allclose(translation, [0.0, 0.0, 0.0], atol=1e-3, rtol=0.0)
            or not np.allclose(normalized_quaternion, [0.0, 0.0, 0.0, 1.0],
                               atol=1e-3, rtol=0.0)):
        raise AggregationError(
            "Sequence 0 must use identity translation [0,0,0] and "
            "identity xyzw rotation"
        )
    references = [
        frame.get("poseReference", "cameraToFirstFrame")
        for frame in frames
    ]
    if any(reference != "cameraToFirstFrame" for reference in references):
        raise AggregationError(
            "All publisher frame poses must reference cameraToFirstFrame"
        )


def aggregate_manifest(
    manifest_path: str | Path,
    output_path: str | Path,
    *,
    require_base_frame: bool = False,
) -> dict[str, Any]:
    manifest_path = Path(manifest_path).resolve()
    output_path = Path(output_path).resolve()
    try:
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise AggregationError(f"Cannot read manifest {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise AggregationError("Manifest root must be a JSON object")
    if manifest.get("schemaVersion") != 1:
        raise AggregationError("schemaVersion must be 1")
    session_id = manifest.get("systemSessionId")
    if not isinstance(session_id, str) or not session_id.strip():
        raise AggregationError("systemSessionId must be a non-empty string")
    target_version = manifest.get("targetVersion")
    if isinstance(target_version, bool) or not isinstance(target_version, int) or target_version < 1:
        raise AggregationError("targetVersion must be a positive integer")
    frames_data = manifest.get("frames")
    if not isinstance(frames_data, list) or not frames_data:
        raise AggregationError("frames must be a non-empty array")
    if require_base_frame:
        _validate_base_frame(frames_data)

    validated = [
        _validate_frame(frame, index, manifest_path.parent)
        for index, frame in enumerate(frames_data)
    ]
    frame_ids = [frame["frame_id"] for frame in validated]
    sequences = [frame["sequence"] for frame in validated]
    if len(set(frame_ids)) != len(frame_ids) or len(set(sequences)) != len(sequences):
        raise AggregationError("frameId and sequence values must each be unique")

    output_scene = trimesh.Scene()
    mesh_count = 0
    all_meshes: list[tuple[str, trimesh.Trimesh]] = []
    for frame in sorted(validated, key=lambda item: (item["sequence"], item["frame_id"])):
        try:
            source_scene = trimesh.load(frame["path"], force="scene", process=False)
        except Exception as exc:
            raise AggregationError(f"Cannot load input GLB {frame['path']}: {exc}") from exc
        if not isinstance(source_scene, trimesh.Scene):
            raise AggregationError(f"Input is not a GLB scene: {frame['path']}")
        for node_name, mesh in _scene_geometry(source_scene, frame):
            all_meshes.append((node_name, mesh))
    for node_name, mesh in _merge_coplanar_textured_patches(all_meshes):
        output_scene.add_geometry(mesh, node_name=node_name, geom_name=node_name)
        mesh_count += 1
    if mesh_count == 0:
        raise AggregationError("No geometry was accepted")

    vertices = np.concatenate([
        np.asarray(mesh.vertices, dtype=np.float64)
        for mesh in output_scene.geometry.values()
        if isinstance(mesh, trimesh.Trimesh)
    ])
    bounds = np.array([vertices.min(axis=0), vertices.max(axis=0)])
    if not np.isfinite(bounds).all() or not np.isfinite(vertices).all():
        raise AggregationError("Output bounds contain non-finite coordinates")
    if float(np.max(bounds[1] - bounds[0])) <= 1e-9:
        raise AggregationError("Aggregated geometry has degenerate zero-size bounds")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output_path.stem}.",
            suffix=".glb",
            dir=output_path.parent,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
        output_scene.export(str(temp_path), file_type="glb")
        # Ensure the temporary artifact is a readable, non-empty GLB before
        # replacing any previously published version at this path.
        if not temp_path.is_file() or temp_path.stat().st_size < 20:
            raise AggregationError("GLB export produced an empty or truncated file")
        check_scene = trimesh.load(temp_path, force="scene", process=False)
        if not isinstance(check_scene, trimesh.Scene) or not check_scene.geometry:
            raise AggregationError("Exported GLB failed structural verification")
        os.replace(temp_path, output_path)
        temp_path = None
    except AggregationError:
        raise
    except Exception as exc:
        raise AggregationError(f"Failed to write aggregate GLB {output_path}: {exc}") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    return {
        "systemSessionId": session_id,
        "targetVersion": target_version,
        "outputPath": str(output_path),
        "frameCount": len(validated),
        "meshCount": mesh_count,
        "boundsM": bounds.tolist(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate explicitly registered per-frame textured GLBs.",
        epilog=(
            "Manifest details and transform semantics are documented in this module "
            "docstring. Use --schema to print the JSON Schema."
        ),
    )
    parser.add_argument("--manifest", type=Path, help="Path to schemaVersion 1 JSON manifest")
    parser.add_argument("--output", type=Path, help="Aggregate GLB output path")
    parser.add_argument("--schema", action="store_true", help="Print the accepted manifest JSON Schema")
    args = parser.parse_args(argv)
    if args.schema:
        print(json.dumps(JSON_SCHEMA, indent=2))
        return 0
    if args.manifest is None or args.output is None:
        parser.error("--manifest and --output are required unless --schema is used")
    try:
        result = aggregate_manifest(args.manifest, args.output)
    except AggregationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "ok", **result}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
