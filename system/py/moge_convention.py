"""Trusted coordinate and provenance contract for MoGe v3 frame GLBs.

The convention is intentionally fixed in repository code. Worker environment
variables may pin an expected checkpoint and revision, but cannot select axes,
mapping matrices, or scale.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


SIDECAR_SCHEMA_VERSION = 1
CONVENTION_ID = "moge3-v3-metric-opencv-camera-legacy-glb"
OFFICIAL_CODE_REVISION = "74fbce054ebed49800de42d0ad0e83495065719a"
MOGE_BASIS = "opencv-camera,+X-right,+Y-down,+Z-forward"
CAPTURE_CAMERA_BASIS = "arcore-opengl,+X-right,+Y-up,-Z-forward"
WORLD_BASIS = "right-handed,+X-right,+Y-up,-Z-forward"
GLB_FROM_MOGE = np.diag([1.0, -1.0, -1.0, 1.0])
PROVENANCE_METHOD = "pinned-source-git-revision+configured-checkpoint-sha256"
ORIENTATION_METHOD = "EXIF orientation absent or 1; source pixels used without rotation or mirroring"


class ConventionError(ValueError):
    """A model, image orientation, or convention proof is missing or invalid."""


def _expected_checkpoint_hash() -> str:
    value = os.environ.get("MOGE_EXPECTED_CHECKPOINT_SHA256", "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ConventionError(
            "MOGE_EXPECTED_CHECKPOINT_SHA256 must be configured on the trusted worker "
            "with the approved checkpoint's 64-character SHA-256."
        )
    return value


def _expected_code_revision() -> str:
    value = os.environ.get("MOGE_EXPECTED_CODE_REVISION", "").strip().lower()
    if value != OFFICIAL_CODE_REVISION:
        raise ConventionError(
            "MOGE_EXPECTED_CODE_REVISION must equal the repository-verified MoGe v3 "
            f"revision {OFFICIAL_CODE_REVISION}; other/unpinned code is unsupported."
        )
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise ConventionError(f"Cannot read file for SHA-256 {path}: {exc}") from exc
    return digest.hexdigest()


def _verified_source_revision(module_file: str | Path) -> str:
    source = Path(module_file).resolve()
    try:
        root = subprocess.run(
            ["git", "-C", str(source.parent), "rev-parse", "--show-toplevel"],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        revision = subprocess.run(
            ["git", "-C", root, "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip().lower()
        relative_source = source.relative_to(Path(root).resolve())
        relative_package = relative_source.parts[0]
        tracked = subprocess.run(
            ["git", "-C", root, "ls-files", "--error-unmatch", str(relative_source)],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        changed = subprocess.run(
            ["git", "-C", root, "status", "--porcelain", "--", relative_package],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ConventionError(
            "Cannot prove the installed MoGe source revision from a clean Git checkout."
        ) from exc
    if not tracked or changed:
        raise ConventionError(
            "Installed MoGe source files are not tracked in a clean pinned checkout."
        )
    if revision != OFFICIAL_CODE_REVISION:
        raise ConventionError(
            f"Installed MoGe source revision {revision!r} is not the verified "
            f"revision {OFFICIAL_CODE_REVISION}."
        )
    return revision


def verify_runtime(model_path: str | Path, model_entrypoint_file: str | Path) -> dict[str, Any]:
    """Prove the checkpoint and source match trusted worker configuration."""
    expected_revision = _expected_code_revision()
    expected_hash = _expected_checkpoint_hash()
    checkpoint = Path(model_path).resolve()
    if not checkpoint.is_file():
        raise ConventionError(
            f"MoGe checkpoint must be a regular file for identity verification: {checkpoint}"
        )
    actual_hash = _sha256_file(checkpoint)
    if actual_hash != expected_hash:
        raise ConventionError(
            "MoGe checkpoint SHA-256 does not match MOGE_EXPECTED_CHECKPOINT_SHA256."
        )
    actual_revision = _verified_source_revision(model_entrypoint_file)
    if actual_revision != expected_revision:
        raise ConventionError("MoGe source revision does not match the trusted worker pin.")
    return {
        "modelVersion": "v3",
        "codeRevision": actual_revision,
        "checkpointSha256": actual_hash,
        "verification": PROVENANCE_METHOD,
    }


def runtime_provenance_for_mode(
    required: bool,
    model_path: str | Path,
    model_entrypoint_file: str | Path,
) -> dict[str, Any] | None:
    """Verify installed MoGe only when the caller explicitly requires provenance."""
    if not required:
        return None
    return verify_runtime(model_path, model_entrypoint_file)


def verify_canonical_orientation(image_path: str | Path) -> dict[str, Any]:
    """Accept only image bytes with no EXIF rotation/mirroring instruction."""
    path = Path(image_path)
    try:
        with Image.open(path) as image:
            orientation = image.getexif().get(274)
            if image.width < 1 or image.height < 1:
                raise ConventionError(f"Image {path} has empty dimensions.")
    except (OSError, ValueError) as exc:
        raise ConventionError(f"Cannot verify image orientation for {path}: {exc}") from exc
    if orientation not in (None, 1):
        raise ConventionError(
            f"Image {path} has EXIF orientation {orientation}; only canonical "
            "orientation (tag absent or 1) is supported."
        )
    return {
        "verified": True,
        "method": ORIENTATION_METHOD,
        "exifOrientation": orientation,
        "imageSha256": _sha256_file(path),
    }


def write_frame_provenance(
    path: str | Path,
    runtime: dict[str, Any],
    orientation: dict[str, Any],
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schemaVersion": SIDECAR_SCHEMA_VERSION, **runtime, "canonicalOrientation": orientation}
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        os.replace(temporary, destination)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ConventionError(f"Cannot write frame provenance {destination}: {exc}") from exc


def make_glb_sidecar(provenance: dict[str, Any]) -> dict[str, Any]:
    """Build the fixed, repository-owned transform declaration for one frame."""
    if not isinstance(provenance, dict):
        raise ConventionError("Frame provenance must be a JSON object.")
    orientation = provenance.get("canonicalOrientation")
    if (provenance.get("schemaVersion") != SIDECAR_SCHEMA_VERSION
            or provenance.get("modelVersion") != "v3"
            or provenance.get("codeRevision") != OFFICIAL_CODE_REVISION
            or provenance.get("verification") != PROVENANCE_METHOD
            or not isinstance(provenance.get("checkpointSha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", provenance["checkpointSha256"])
            or not isinstance(orientation, dict)
            or orientation.get("verified") is not True
            or orientation.get("method") != ORIENTATION_METHOD
            or orientation.get("exifOrientation") not in (None, 1)
            or not isinstance(orientation.get("imageSha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", orientation["imageSha256"])):
        raise ConventionError("Frame provenance is incomplete or does not verify the supported convention.")
    return {
        "schemaVersion": SIDECAR_SCHEMA_VERSION,
        "conventionId": CONVENTION_ID,
        "basis": {
            "moge": MOGE_BASIS,
            "storedGlb": "legacy-export-F-applied-to-MoGe",
            "captureCamera": CAPTURE_CAMERA_BASIS,
            "world": WORLD_BASIS,
        },
        "glbStoredToMogeMatrix4x4": GLB_FROM_MOGE.reshape(-1).tolist(),
        "mogeToCaptureCameraMatrix4x4": GLB_FROM_MOGE.reshape(-1).tolist(),
        "scale": 1.0,
        "unit": "m",
        "provenance": {
            "modelVersion": "v3",
            "codeRevision": provenance["codeRevision"],
            "checkpointSha256": provenance["checkpointSha256"],
            "verification": PROVENANCE_METHOD,
        },
        "canonicalOrientation": orientation,
    }


def write_glb_sidecar(
    glb_path: str | Path,
    provenance_path: str | Path,
) -> Path:
    """Write `<frame.glb>.convention.json` after validating inference provenance."""
    try:
        provenance = json.loads(Path(provenance_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConventionError(
            f"Cannot read verified frame provenance {provenance_path}: {exc}"
        ) from exc
    payload = make_glb_sidecar(provenance)
    payload["glbSha256"] = _sha256_file(Path(glb_path))
    destination = Path(str(glb_path) + ".convention.json")
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        os.replace(temporary, destination)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ConventionError(f"Cannot write GLB convention sidecar {destination}: {exc}") from exc
    return destination


def write_glb_sidecar_if_required(
    glb_path: str | Path,
    provenance_path: str | Path,
    required: bool,
) -> Path | None:
    """Write convention metadata only for workflows that consume verified geometry."""
    if not required:
        return None
    return write_glb_sidecar(glb_path, provenance_path)


def validate_glb_sidecar(path: str | Path) -> dict[str, Any]:
    """Validate trusted worker sidecar, including the configured checkpoint pin."""
    sidecar_path = Path(path)
    try:
        data = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConventionError(f"Cannot read frame convention sidecar {sidecar_path}: {exc}") from exc
    expected_revision = _expected_code_revision()
    expected_hash = _expected_checkpoint_hash()
    try:
        valid = (
            isinstance(data, dict)
            and type(data.get("schemaVersion")) is int
            and data.get("schemaVersion") == SIDECAR_SCHEMA_VERSION
            and data.get("conventionId") == CONVENTION_ID
            and data.get("basis") == {
                "moge": MOGE_BASIS,
                "storedGlb": "legacy-export-F-applied-to-MoGe",
                "captureCamera": CAPTURE_CAMERA_BASIS,
                "world": WORLD_BASIS,
            }
            and np.array_equal(
                np.asarray(data.get("glbStoredToMogeMatrix4x4"), dtype=np.float64).reshape(4, 4),
                GLB_FROM_MOGE,
            )
            and np.array_equal(
                np.asarray(data.get("mogeToCaptureCameraMatrix4x4"), dtype=np.float64).reshape(4, 4),
                GLB_FROM_MOGE,
            )
            and not isinstance(data.get("scale"), bool)
            and isinstance(data.get("scale"), (int, float))
            and data.get("scale") == 1.0
            and data.get("unit") == "m"
        )
    except (AttributeError, TypeError, ValueError):
        valid = False
    provenance = data.get("provenance") if isinstance(data, dict) else None
    orientation = data.get("canonicalOrientation") if isinstance(data, dict) else None
    valid = valid and isinstance(provenance, dict) and isinstance(orientation, dict)
    if valid:
        suffix = ".convention.json"
        glb_path = Path(str(sidecar_path)[:-len(suffix)]) if str(sidecar_path).endswith(suffix) else None
        valid = (
            glb_path is not None
            and glb_path.is_file()
            and data.get("glbSha256") == _sha256_file(glb_path)
            and provenance.get("modelVersion") == "v3"
            and provenance.get("codeRevision") == expected_revision
            and provenance.get("checkpointSha256") == expected_hash
            and provenance.get("verification") == PROVENANCE_METHOD
            and orientation.get("verified") is True
            and orientation.get("method") == ORIENTATION_METHOD
            and orientation.get("exifOrientation") in (None, 1)
            and isinstance(orientation.get("imageSha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", orientation["imageSha256"])
        )
    if not valid:
        raise ConventionError(
            f"Frame convention sidecar {sidecar_path} is unsupported, unverified, "
            "or does not match trusted worker model configuration."
        )
    return data
