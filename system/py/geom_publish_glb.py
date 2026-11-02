"""Crash-safe publisher for per-frame GLB aggregation.

The CLI is the adapter invoked by ``system/img3d_ws_aggregator/agent.js``.
Accepted frame contributions and publication transactions are serialized by a
per-session OS file lock. A model version is written before the atomic
``current-version.json`` pointer is advanced, so readers never observe a
pointer to a missing model.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import sys
import stat
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import trimesh

from geom_aggregate_glb import AggregationError, aggregate_manifest


SESSION_ID_RE = re.compile(r"^[a-f0-9]{32}$")
REQUEST_ID_RE = re.compile(r"^[a-f0-9]{32}$")
FRAME_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,96}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
MAX_METADATA_BYTES = 1024 * 1024
MAX_GLB_BYTES = 512 * 1024 * 1024
MAX_VERSION = 999_999_999
MAX_SEQUENCE = 9_007_199_254_740_991
QUATERNION_TOLERANCE = 1e-3
_thread_locks: dict[str, threading.Lock] = {}
_thread_locks_guard = threading.Lock()


class PublisherError(ValueError):
    """A permanent request, state, or candidate validation error."""


class PublicationPending(RuntimeError):
    """A valid contribution is durably accepted but cannot yet be published."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_glb_file(path: Path) -> None:
    size = path.stat().st_size
    if size < 20 or size > MAX_GLB_BYTES:
        raise PublisherError("Staged input GLB has an unsupported size")
    with path.open("rb") as stream:
        header = stream.read(12)
    if (len(header) != 12 or header[:4] != b"glTF"
            or int.from_bytes(header[4:8], "little") != 2
            or int.from_bytes(header[8:12], "little") != size):
        raise PublisherError("Staged input is not a complete glTF 2.0 binary GLB")


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _durable_replace_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _write_json(path: Path, value: Any) -> None:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    _durable_replace_bytes(path, encoded)


def _read_json(path: Path, maximum: int = 16 * 1024 * 1024) -> Any:
    try:
        file_stat = path.lstat()
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > maximum:
            raise PublisherError(f"Expected a regular bounded JSON file: {path}")
        return json.loads(path.read_text(encoding="utf-8"))
    except PublisherError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublisherError(f"Cannot read JSON file {path}: {exc}") from exc


class _SessionLock:
    """Blocking process/thread lock backed by flock or Windows byte locking."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.descriptor: int | None = None
        key = str(path.resolve())
        with _thread_locks_guard:
            self.thread_lock = _thread_locks.setdefault(key, threading.Lock())

    def __enter__(self) -> "_SessionLock":
        self.thread_lock.acquire()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.descriptor = os.open(
                self.path, os.O_CREAT | os.O_RDWR, 0o600
            )
            if os.name == "nt":
                import msvcrt

                if os.fstat(self.descriptor).st_size == 0:
                    os.write(self.descriptor, b"\0")
                    os.fsync(self.descriptor)
                while True:
                    try:
                        os.lseek(self.descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(self.descriptor, msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        time.sleep(0.05)
            else:
                import fcntl

                fcntl.flock(self.descriptor, fcntl.LOCK_EX)
            return self
        except BaseException:
            if self.descriptor is not None:
                os.close(self.descriptor)
                self.descriptor = None
            self.thread_lock.release()
            raise

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        assert self.descriptor is not None
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(self.descriptor, 0, os.SEEK_SET)
                msvcrt.locking(self.descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.descriptor, fcntl.LOCK_UN)
        finally:
            os.close(self.descriptor)
            self.descriptor = None
            self.thread_lock.release()


def _safe_session_paths(data_dir: Path, session_id: str) -> tuple[Path, Path]:
    if not SESSION_ID_RE.fullmatch(session_id):
        raise PublisherError("systemSessionId must be 32 lowercase hexadecimal characters")
    try:
        root = data_dir.resolve(strict=True)
        sessions = root / "system-sessions"
        session = sessions / session_id
        if (not sessions.is_dir() or sessions.is_symlink()
                or not session.is_dir() or session.is_symlink()
                or session.resolve(strict=True).parent != sessions.resolve(strict=True)):
            raise PublisherError("System session storage is missing or is not a regular directory")
    except OSError as exc:
        raise PublisherError(f"Cannot access system session storage: {exc}") from exc
    return root, session


def _relative_data_path(
    root: Path, value: Any, field: str, *, must_exist: bool = True
) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise PublisherError(f"{field} must be a non-empty forward-slash DATA_DIR path")
    relative = Path(value)
    if relative.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise PublisherError(f"{field} is not a safe relative DATA_DIR path")
    result = (root / relative).resolve(strict=must_exist)
    if result == root or root not in result.parents:
        raise PublisherError(f"{field} escaped DATA_DIR")
    return result


def _finite_values(value: Any, count: int, field: str) -> list[float]:
    if (not isinstance(value, list) or len(value) != count
            or any(isinstance(item, bool) or not isinstance(item, (int, float))
                   or not math.isfinite(item) for item in value)):
        raise PublisherError(f"{field} must contain exactly {count} finite numbers")
    return [float(item) for item in value]


def _normalize_pose(frame: dict[str, Any]) -> tuple[list[float], list[float]]:
    reference = frame.get("poseReference", "cameraToFirstFrame")
    if reference != "cameraToFirstFrame":
        raise PublisherError("All publisher poses must reference cameraToFirstFrame")
    pose = frame.get("cameraToFirstFrame")
    if not isinstance(pose, dict) or set(pose) != {
        "translationM", "rotationQuaternionXyzw"
    }:
        raise PublisherError(
            "Each frame must provide cameraToFirstFrame translationM and "
            "rotationQuaternionXyzw"
        )
    translation = _finite_values(pose["translationM"], 3, "translationM")
    quaternion = _finite_values(
        pose["rotationQuaternionXyzw"], 4, "rotationQuaternionXyzw"
    )
    norm = float(np.linalg.norm(quaternion))
    if norm == 0.0 or abs(norm - 1.0) > QUATERNION_TOLERANCE:
        raise PublisherError("cameraToFirstFrame quaternion must be unit length")
    if any(abs(value) > 1_000_000 for value in translation):
        raise PublisherError("cameraToFirstFrame translation exceeds the supported range")
    quaternion = [value / norm for value in quaternion]
    # q and -q denote the same rotation. Canonicalizing avoids treating the
    # same frame pose as a new contribution on an otherwise identical retry.
    if quaternion[3] < 0:
        quaternion = [-value for value in quaternion]
    return translation, quaternion


def _validate_metadata(
    metadata: Any,
    request_id: str,
    session_id: str,
    frame_id: str,
    input_path: Path,
    root: Path,
) -> tuple[dict[str, Any], Path]:
    if (not isinstance(metadata, dict)
            or isinstance(metadata.get("schemaVersion"), bool)
            or metadata.get("schemaVersion") != 1):
        raise PublisherError("Publisher metadata must be a schemaVersion 1 object")
    if metadata.get("requestId") != request_id:
        raise PublisherError("metadata requestId does not match --request-id")
    if metadata.get("systemSessionId") != session_id:
        raise PublisherError("metadata systemSessionId does not match the CLI")
    if metadata.get("frameId") != frame_id or not FRAME_ID_RE.fullmatch(frame_id):
        raise PublisherError("metadata frameId does not match --frame-id")
    sequence = metadata.get("sequence")
    if (isinstance(sequence, bool) or not isinstance(sequence, int)
            or sequence < 0 or sequence > MAX_SEQUENCE):
        raise PublisherError("metadata sequence must be a non-negative integer")
    input_hash = metadata.get("inputGlbSha256")
    if not isinstance(input_hash, str) or not SHA256_RE.fullmatch(input_hash):
        raise PublisherError("metadata inputGlbSha256 must be a lowercase SHA-256")
    if not input_path.is_file() or input_path.is_symlink():
        raise PublisherError("--input-glb must be an existing regular file")
    _validate_glb_file(input_path)
    if _sha256_file(input_path) != input_hash:
        raise PublisherError("--input-glb SHA-256 does not match publisher metadata")
    if metadata.get("inputGlbPath") is not None:
        resolved_metadata_input = _relative_data_path(
            root, metadata["inputGlbPath"], "inputGlbPath"
        )
        if resolved_metadata_input != input_path:
            raise PublisherError("metadata inputGlbPath does not match --input-glb")

    records = metadata.get("frames")
    if not isinstance(records, list) or not records or len(records) > 500:
        raise PublisherError("metadata frames must contain 1..500 frame records")
    seen_ids: set[str] = set()
    seen_sequences: set[int] = set()
    current: dict[str, Any] | None = None
    for index, record in enumerate(records):
        label = f"frames[{index}]"
        if not isinstance(record, dict):
            raise PublisherError(f"{label} must be an object")
        identifier = record.get("frameId")
        seq = record.get("sequence")
        if (not isinstance(identifier, str) or not FRAME_ID_RE.fullmatch(identifier)
                or isinstance(seq, bool) or not isinstance(seq, int)
                or seq < 0 or seq > MAX_SEQUENCE):
            raise PublisherError(f"{label} has an invalid frameId or sequence")
        if identifier in seen_ids or seq in seen_sequences:
            raise PublisherError("Publisher metadata frameId and sequence values must be unique")
        seen_ids.add(identifier)
        seen_sequences.add(seq)
        translation, quaternion = _normalize_pose(record)
        if seq == 0:
            raw_pose = record["cameraToFirstFrame"]
            raw_translation = _finite_values(raw_pose["translationM"], 3, "translationM")
            if (not np.allclose(raw_translation, [0.0, 0.0, 0.0], atol=1e-3, rtol=0.0)
                    or not np.allclose(quaternion, [0.0, 0.0, 0.0, 1.0],
                                       atol=1e-3, rtol=0.0)):
                raise PublisherError(
                    "Sequence 0 must use identity translation [0,0,0] and "
                    "identity xyzw rotation"
                )
        glb_path = record.get("glbPath")
        sidecar_path = record.get("conventionSidecarPath")
        if (not isinstance(glb_path, str) or not isinstance(sidecar_path, str)
                or sidecar_path != glb_path + ".convention.json"):
            raise PublisherError(f"{label} has invalid GLB/sidecar paths")
        glb_absolute = _relative_data_path(
            root, glb_path, f"{label}.glbPath", must_exist=False
        )
        sidecar_absolute = _relative_data_path(
            root, sidecar_path, f"{label}.conventionSidecarPath", must_exist=False
        )
        if record.get("poseReference", "cameraToFirstFrame") != "cameraToFirstFrame":
            raise PublisherError("Mixed or unsupported publisher pose references")
        normalized = {
            "frameId": identifier,
            "sequence": seq,
            "translationM": translation,
            "rotationQuaternionXyzw": quaternion,
            "poseReference": "cameraToFirstFrame",
            "glbPath": str(glb_absolute),
            "conventionSidecarPath": str(sidecar_absolute),
        }
        if identifier == frame_id and seq == sequence:
            if glb_absolute != input_path:
                raise PublisherError("Current frame metadata does not point to --input-glb")
            current = normalized
    if current is None:
        raise PublisherError("Current frame is absent from publisher metadata")
    sidecar_path = Path(current["conventionSidecarPath"])
    try:
        sidecar_stat = sidecar_path.lstat()
        if not stat.S_ISREG(sidecar_stat.st_mode) or sidecar_stat.st_size > 64 * 1024:
            raise PublisherError("Current frame sidecar is not a regular bounded file")
        sidecar_data = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except PublisherError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublisherError(f"Cannot read current frame sidecar: {exc}") from exc
    if (not isinstance(sidecar_data, dict)
            or sidecar_data.get("glbSha256") != input_hash):
        raise PublisherError("Current frame sidecar is not bound to the staged input GLB")
    return current, input_path


def _read_state(path: Path, session_id: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "schemaVersion": 1,
            "systemSessionId": session_id,
            "currentVersion": 0,
            "frames": {},
            "requests": {},
            "pending": None,
        }
    state = _read_json(path)
    if (not isinstance(state, dict)
            or isinstance(state.get("schemaVersion"), bool)
            or state.get("schemaVersion") != 1
            or state.get("systemSessionId") != session_id
            or isinstance(state.get("currentVersion"), bool)
            or not isinstance(state.get("currentVersion"), int)
            or state["currentVersion"] < 0
            or state["currentVersion"] > MAX_VERSION
            or not isinstance(state.get("frames"), dict)
            or not isinstance(state.get("requests"), dict)
            or ("pending" in state and state["pending"] is not None
                and not isinstance(state["pending"], dict))):
        raise PublisherError("Publisher state is malformed or belongs to another session")
    state.setdefault("pending", None)
    return state


def _read_current_version(session_dir: Path) -> int:
    pointer = session_dir / "current-version.json"
    if not pointer.exists():
        return 0
    value = _read_json(pointer, 64 * 1024)
    version = value.get("currentVersion") if isinstance(value, dict) else None
    if (isinstance(version, bool) or not isinstance(version, int)
            or version < 0 or version > MAX_VERSION):
        raise PublisherError("current-version.json must contain a non-negative integer currentVersion")
    if version > 0:
        model = session_dir / f"model.v{version}.glb"
        if not model.is_file() or model.is_symlink():
            raise PublisherError(
                f"current-version.json references missing model {model.name}"
            )
    return version


def _validate_candidate(path: Path, *, sync_file: bool = False) -> None:
    if not path.is_file() or path.is_symlink() or path.stat().st_size < 20:
        raise AggregationError("Candidate GLB is missing, empty, or not a regular file")
    try:
        scene = trimesh.load(path, force="scene", process=False)
    except Exception as exc:
        raise AggregationError(f"Candidate GLB is unreadable: {exc}") from exc
    if not isinstance(scene, trimesh.Scene) or not scene.geometry:
        raise AggregationError("Candidate GLB contains no geometry")
    vertices = [
        np.asarray(mesh.vertices, dtype=np.float64)
        for mesh in scene.geometry.values()
        if isinstance(mesh, trimesh.Trimesh) and len(mesh.vertices)
    ]
    if not vertices:
        raise AggregationError("Candidate GLB contains no mesh vertices")
    combined = np.concatenate(vertices)
    if not np.isfinite(combined).all():
        raise AggregationError("Candidate GLB contains non-finite vertices")
    extent = np.ptp(combined, axis=0)
    if not np.isfinite(extent).all() or float(np.max(extent)) <= 1e-9:
        raise AggregationError("Candidate GLB has degenerate zero-size bounds")
    if sync_file:
        with path.open("rb+") as stream:
            stream.flush()
            os.fsync(stream.fileno())


def _finalize_pending(state: dict[str, Any], state_path: Path, version: int) -> None:
    pending = state.get("pending")
    if not isinstance(pending, dict) or pending.get("version") != version:
        raise PublisherError("Publication pointer and durable pending state disagree")
    for frame in state["frames"].values():
        if frame.get("status") == "durable-accepted":
            frame["status"] = "committed"
            frame["version"] = version
    request_id = pending.get("requestId")
    for request in state["requests"].values():
        if request.get("status") == "durable-accepted":
            request["status"] = "committed"
            request["version"] = version
    if request_id in state["requests"]:
        state["requests"][request_id]["status"] = "committed"
        state["requests"][request_id]["version"] = version
    state["currentVersion"] = version
    state["pending"] = None
    _write_json(state_path, state)


def _canonical_metadata_hash(value: Any) -> str:
    def canonical(item: Any) -> str:
        if isinstance(item, list):
            return "[" + ",".join(canonical(child) for child in item) + "]"
        if isinstance(item, dict):
            return "{" + ",".join(
                json.dumps(key, ensure_ascii=False) + ":" + canonical(item[key])
                for key in sorted(item)
            ) + "}"
        return json.dumps(item, ensure_ascii=False, separators=(",", ":"))

    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _initialize_pointer(session_dir: Path) -> int:
    pointer = session_dir / "current-version.json"
    if not pointer.exists():
        _write_json(pointer, {"currentVersion": 0})
    return _read_current_version(session_dir)


def _publish_pending(
    state: dict[str, Any],
    state_path: Path,
    session_dir: Path,
    aggregate_fn: Callable[..., dict[str, Any]],
    fault_hook: Callable[[str], None] | None = None,
) -> None:
    pending = state.get("pending")
    if not isinstance(pending, dict):
        return
    version = pending.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise PublisherError("Pending publication has an invalid target version")
    pointer_version = _read_current_version(session_dir)
    target_model = session_dir / f"model.v{version}.glb"

    if pointer_version == version:
        expected_hash = pending.get("candidateSha256")
        if (not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash)
                or _sha256_file(target_model) != expected_hash):
            raise PublisherError("Published model does not match the durable candidate hash")
        _validate_candidate(target_model)
        _finalize_pending(state, state_path, version)
        return
    if pointer_version > version or pointer_version + 1 != version:
        raise PublisherError("Pending version is inconsistent with current-version.json")

    if target_model.exists():
        expected_hash = pending.get("candidateSha256")
        if (not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash)
                or _sha256_file(target_model) != expected_hash):
            # The pointer still references the previous version, so this is an
            # uncommitted artifact. Remove it and rebuild from durable inputs.
            target_model.unlink(missing_ok=True)
            _fsync_directory(session_dir)
            pending.pop("candidateSha256", None)
            _write_json(state_path, state)
    if target_model.exists():
        try:
            _validate_candidate(target_model)
        except AggregationError:
            target_model.unlink(missing_ok=True)
            _fsync_directory(session_dir)
            raise
    else:
        frames = sorted(
            state["frames"].values(),
            key=lambda item: (item["sequence"], item["frameId"]),
        )
        if not frames or sum(frame["sequence"] == 0 for frame in frames) != 1:
            raise PublicationPending(
                "Waiting for exactly one accepted sequence-0 base frame before publishing"
            )
        if any(frame.get("poseReference") != "cameraToFirstFrame" for frame in frames):
            raise AggregationError("Accepted frame set mixes pose references")
        manifest = {
            "schemaVersion": 1,
            "systemSessionId": state["systemSessionId"],
            "targetVersion": version,
            "frames": [
                {
                    "frameId": frame["frameId"],
                    "sequence": frame["sequence"],
                    "glbPath": frame["glbPath"],
                    "translationM": frame["translationM"],
                    "rotationQuaternionXyzw": frame["rotationQuaternionXyzw"],
                    "poseReference": frame["poseReference"],
                }
                for frame in frames
            ],
        }
        descriptor, manifest_name = tempfile.mkstemp(
            prefix=".publisher-manifest.", suffix=".json", dir=session_dir
        )
        os.close(descriptor)
        manifest_path = Path(manifest_name)
        candidate = session_dir / f".model.v{version}.{pending['requestId']}.candidate.glb"
        try:
            for frame in frames:
                glb_path = Path(frame["glbPath"])
                sidecar_path = Path(frame["conventionSidecarPath"])
                glb_stat = glb_path.lstat()
                sidecar_stat = sidecar_path.lstat()
                if (not stat.S_ISREG(glb_stat.st_mode)
                        or not stat.S_ISREG(sidecar_stat.st_mode)
                        or sidecar_stat.st_size > 64 * 1024
                        or _sha256_file(glb_path) != frame["inputGlbSha256"]
                        or _sha256_file(sidecar_path) != frame["sidecarSha256"]):
                    raise AggregationError(
                        f"Accepted frame {frame['frameId']} failed durable input integrity checks"
                    )
            _durable_replace_bytes(
                manifest_path,
                json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            )
            aggregate_fn(manifest_path, candidate, require_base_frame=True)
            _validate_candidate(candidate, sync_file=True)
            pending["candidateSha256"] = _sha256_file(candidate)
            _write_json(state_path, state)
            # The session lock prevents competing publishers; refuse to replace
            # any unexpected version artifact rather than overwrite a commit.
            if target_model.exists():
                raise PublisherError(f"Refusing to overwrite existing {target_model.name}")
            os.replace(candidate, target_model)
            _fsync_directory(session_dir)
        finally:
            manifest_path.unlink(missing_ok=True)
            candidate.unlink(missing_ok=True)

    if fault_hook is not None:
        fault_hook("after-model-rename")
    pointer_path = session_dir / "current-version.json"
    _write_json(pointer_path, {"currentVersion": version})
    if fault_hook is not None:
        fault_hook("after-pointer")
    _finalize_pending(state, state_path, version)


def _reject_pending(state: dict[str, Any], state_path: Path, error: str) -> None:
    pending = state.get("pending")
    if not isinstance(pending, dict):
        return
    # The full candidate is built from all newly accepted frames at once. If it
    # fails, none of those uncommitted inputs may remain in the next candidate;
    # retaining one could strand the session even after the pending request is
    # rejected (for example, a bad non-base frame accepted before sequence 0).
    rejected_ids = {
        request_id
        for request_id, request in state["requests"].items()
        if request.get("status") == "durable-accepted"
    }
    for request_id in rejected_ids:
        request = state["requests"][request_id]
        request["status"] = "rejected"
        request["error"] = error[:1000]
    for frame_id, frame in list(state["frames"].items()):
        if frame.get("status") == "durable-accepted":
            del state["frames"][frame_id]
    state["pending"] = None
    _write_json(state_path, state)


def _recover(
    state: dict[str, Any],
    state_path: Path,
    session_dir: Path,
    aggregate_fn: Callable[..., dict[str, Any]],
    fault_hook: Callable[[str], None] | None = None,
) -> None:
    pointer = _read_current_version(session_dir)
    if pointer > state["currentVersion"]:
        pending = state.get("pending")
        if not isinstance(pending, dict) or pending.get("version") != pointer:
            raise PublisherError(
                "Published pointer is ahead of durable publisher state without a matching transaction"
            )
    elif pointer < state["currentVersion"]:
        raise PublisherError("current-version.json is behind durable publisher state")
    if state.get("pending") is not None:
        try:
            _publish_pending(
                state, state_path, session_dir, aggregate_fn, fault_hook
            )
        except PublicationPending:
            raise
        except AggregationError as exc:
            _reject_pending(state, state_path, str(exc))
        # _publish_pending writes its final state atomically.


def publish_request(
    request_id: str,
    system_session_id: str,
    frame_id: str,
    input_glb: str | Path,
    metadata_json: str | Path,
    data_dir: str | Path,
    *,
    aggregate_fn: Callable[..., dict[str, Any]] = aggregate_manifest,
    fault_hook: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Accept one frame and publish a new immutable model version if possible."""
    if not REQUEST_ID_RE.fullmatch(request_id):
        raise PublisherError("requestId must be 32 lowercase hexadecimal characters")
    root, session_dir = _safe_session_paths(Path(data_dir), system_session_id)
    input_argument = Path(input_glb)
    if input_argument.is_symlink():
        raise PublisherError("--input-glb must not be a symlink")
    input_path = input_argument.resolve(strict=True)
    expected_input = (
        session_dir / "aggregator-inbox" / request_id / "input.glb"
    ).resolve(strict=True)
    if input_path != expected_input:
        raise PublisherError("--input-glb must be this request's staged inbox/input.glb")
    metadata_path = Path(metadata_json)
    metadata_stat = metadata_path.lstat()
    if not stat.S_ISREG(metadata_stat.st_mode) or metadata_stat.st_size > MAX_METADATA_BYTES:
        raise PublisherError("--metadata-json must be a regular JSON file up to 1 MiB")
    metadata_bytes = metadata_path.read_bytes()
    try:
        metadata = json.loads(metadata_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PublisherError(f"Cannot parse --metadata-json: {exc}") from exc

    session_lock = _SessionLock(session_dir / ".publisher.lock")
    with session_lock:
        state_path = session_dir / "publisher-state.json"
        state = _read_state(state_path, system_session_id)
        _initialize_pointer(session_dir)
        _recover(state, state_path, session_dir, aggregate_fn, fault_hook)
        # Reload after recovery because the recovery helper atomically replaces
        # the state file and may have finalized an earlier transaction.
        state = _read_state(state_path, system_session_id)
        pointer = _read_current_version(session_dir)
        if pointer != state["currentVersion"]:
            raise PublisherError("Durable publisher state does not match current-version.json")

        current, _ = _validate_metadata(
            metadata, request_id, system_session_id, frame_id, input_path, root
        )
        current["inputGlbSha256"] = metadata["inputGlbSha256"]
        current["sidecarSha256"] = _sha256_file(
            Path(current["conventionSidecarPath"])
        )
        request_fingerprint = {
            "frameId": frame_id,
            "sequence": current["sequence"],
            "inputGlbSha256": metadata["inputGlbSha256"],
            "metadataSha256": _canonical_metadata_hash(metadata),
            "translationM": current["translationM"],
            "rotationQuaternionXyzw": current["rotationQuaternionXyzw"],
        }
        prior_request = state["requests"].get(request_id)
        if prior_request is not None:
            comparable = {key: prior_request.get(key) for key in request_fingerprint}
            if comparable != request_fingerprint:
                return {"requestId": request_id, "status": "rejected",
                        "error": "requestId was replayed with different bytes or metadata"}
            if prior_request["status"] == "committed":
                return {"requestId": request_id, "status": "committed",
                        "version": prior_request["version"]}
            if prior_request["status"] == "rejected":
                return {"requestId": request_id, "status": "rejected",
                        "error": prior_request.get("error", "Request was previously rejected")}

        for existing in state["frames"].values():
            if existing["frameId"] == frame_id or existing["sequence"] == current["sequence"]:
                same = (
                    existing["frameId"] == frame_id
                    and existing["sequence"] == current["sequence"]
                    and existing["inputGlbSha256"] == current["inputGlbSha256"]
                    and np.allclose(existing["translationM"], current["translationM"], atol=1e-9)
                    and np.allclose(existing["rotationQuaternionXyzw"],
                                    current["rotationQuaternionXyzw"], atol=1e-9)
                )
                if not same:
                    return {"requestId": request_id, "status": "rejected",
                            "error": "frameId/sequence conflicts with an accepted contribution"}
                state["requests"][request_id] = {
                    **request_fingerprint,
                    "status": existing.get("status", "durable-accepted"),
                    **({"version": existing["version"]} if existing.get("version") else {}),
                }
                _write_json(state_path, state)
                if state["requests"][request_id]["status"] == "committed":
                    return {"requestId": request_id, "status": "committed",
                            "version": state["requests"][request_id]["version"]}
                raise PublicationPending(
                    "Duplicate frame is durable and awaiting sequence-0 publication"
                )

        if current["sequence"] == 0 and (
            not np.allclose(current["translationM"], [0.0, 0.0, 0.0], atol=1e-3, rtol=0.0)
            or not np.allclose(current["rotationQuaternionXyzw"],
                               [0.0, 0.0, 0.0, 1.0], atol=1e-3, rtol=0.0)
        ):
            return {"requestId": request_id, "status": "rejected",
                    "error": "Sequence 0 must use identity translation and xyzw rotation"}

        if any(record.get("poseReference", "cameraToFirstFrame") != "cameraToFirstFrame"
               for record in metadata["frames"]):
            return {"requestId": request_id, "status": "rejected",
                    "error": "Publisher metadata mixes pose references"}

        new_state = copy.deepcopy(state)
        contribution = {
            **current,
            "requestId": request_id,
            "status": "durable-accepted",
        }
        new_state["frames"][frame_id] = contribution
        new_state["requests"][request_id] = {
            **request_fingerprint,
            "status": "durable-accepted",
        }

        accepted = list(new_state["frames"].values())
        base_count = sum(frame["sequence"] == 0 for frame in accepted)
        if base_count > 1:
            return {"requestId": request_id, "status": "rejected",
                    "error": "Accepted frame set contains more than one sequence-0 base frame"}
        if base_count == 0:
            _write_json(state_path, new_state)
            raise PublicationPending(
                "Frame durably accepted; waiting for the sequence-0 base frame"
            )

        next_version = pointer + 1
        if next_version > MAX_VERSION:
            return {"requestId": request_id, "status": "rejected",
                    "error": "Maximum published model version has been reached"}
        new_state["pending"] = {
            "version": next_version,
            "requestId": request_id,
            "frameId": frame_id,
        }
        _write_json(state_path, new_state)
        state = new_state
        try:
            _publish_pending(
                state, state_path, session_dir, aggregate_fn, fault_hook
            )
        except PublicationPending:
            raise
        except AggregationError as exc:
            _reject_pending(state, state_path, str(exc))
            return {"requestId": request_id, "status": "rejected", "error": str(exc)[:1000]}

        finalized = _read_state(state_path, system_session_id)
        committed = finalized["requests"].get(request_id)
        if not committed or committed.get("status") != "committed":
            raise PublisherError("Publication completed without committing its request state")
        return {
            "requestId": request_id,
            "status": "committed",
            "version": committed["version"],
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Durably accept a frame contribution and publish an immutable session GLB."
    )
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--system-session-id", required=True)
    parser.add_argument("--frame-id", required=True)
    parser.add_argument("--input-glb", type=Path, required=True)
    parser.add_argument("--metadata-json", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--result-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = publish_request(
            args.request_id,
            args.system_session_id,
            args.frame_id,
            args.input_glb,
            args.metadata_json,
            args.data_dir,
        )
    except PublicationPending as exc:
        print(f"Publisher retry required: {exc}", file=sys.stderr)
        return 1
    except (PublisherError, OSError, AggregationError) as exc:
        result = {
            "requestId": args.request_id,
            "status": "rejected",
            "error": str(exc)[:1000],
        }
    try:
        _write_json(args.result_json, result)
    except OSError as exc:
        print(f"Cannot durably write publisher result JSON: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
