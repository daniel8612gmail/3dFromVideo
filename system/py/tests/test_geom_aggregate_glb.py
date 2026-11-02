import json
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from geom_aggregate_glb import AggregationError, aggregate_manifest
from moge_convention import (
    OFFICIAL_CODE_REVISION,
    PROVENANCE_METHOD,
    make_glb_sidecar,
)


FLIP = np.diag([1.0, -1.0, -1.0, 1.0])
TEST_CHECKPOINT_SHA256 = "a" * 64


def write_convention_sidecar(path: Path) -> None:
    provenance = {
        "schemaVersion": 1,
        "modelVersion": "v3",
        "codeRevision": OFFICIAL_CODE_REVISION,
        "checkpointSha256": TEST_CHECKPOINT_SHA256,
        "verification": PROVENANCE_METHOD,
        "canonicalOrientation": {
            "verified": True,
            "method": "EXIF orientation absent or 1; source pixels used without rotation or mirroring",
            "exifOrientation": None,
            "imageSha256": "b" * 64,
        },
    }
    sidecar = make_glb_sidecar(provenance)
    sidecar["glbSha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    Path(str(path) + ".convention.json").write_text(
        json.dumps(sidecar),
        encoding="utf-8",
    )


def make_textured_glb(path: Path, moge_vertices: np.ndarray, color: tuple[int, int, int, int]) -> None:
    # Emulate geom_save_glb.py: it writes MoGe vertices after Y/Z sign flips.
    glb_vertices = (FLIP @ np.c_[moge_vertices, np.ones(len(moge_vertices))].T).T[:, :3]
    material = PBRMaterial(
        baseColorTexture=Image.new("RGBA", (2, 2), color),
        metallicFactor=0.0,
        roughnessFactor=1.0,
        doubleSided=True,
        alphaMode="BLEND",
    )
    mesh = trimesh.Trimesh(
        vertices=glb_vertices,
        faces=np.array([[0, 1, 2]]),
        visual=TextureVisuals(
            uv=np.array([[0, 0], [1, 0], [0, 1]], dtype=float),
            material=material,
        ),
        process=False,
    )
    trimesh.Scene(mesh).export(path, file_type="glb")
    write_convention_sidecar(path)


def make_textured_rectangle_glb(
    path: Path,
    bounds: tuple[float, float, float, float],
    z: float,
    color: tuple[int, int, int, int],
) -> None:
    x0, y0, x1, y1 = bounds
    vertices = np.array([
        [x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z],
    ], dtype=float)
    glb_vertices = (FLIP @ np.c_[vertices, np.ones(len(vertices))].T).T[:, :3]
    material = PBRMaterial(
        baseColorTexture=Image.new("RGBA", (2, 2), color),
        metallicFactor=0.0,
        roughnessFactor=1.0,
        doubleSided=True,
        alphaMode="BLEND",
    )
    mesh = trimesh.Trimesh(
        vertices=glb_vertices,
        faces=np.array([[0, 1, 2], [0, 2, 3]]),
        visual=TextureVisuals(
            uv=np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float),
            material=material,
        ),
        process=False,
    )
    trimesh.Scene(mesh).export(path, file_type="glb")
    write_convention_sidecar(path)


def frame(frame_id: str, sequence: int, glb: str) -> dict:
    return {
        "frameId": frame_id,
        "sequence": sequence,
        "glbPath": glb,
        "translationM": [10.0, 20.0, 30.0],
        "rotationQuaternionXyzw": [0.0, 0.0, 0.0, 1.0],
    }


class AggregateGlbTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.previous_checkpoint_hash = os.environ.get("MOGE_EXPECTED_CHECKPOINT_SHA256")
        self.previous_code_revision = os.environ.get("MOGE_EXPECTED_CODE_REVISION")
        os.environ["MOGE_EXPECTED_CHECKPOINT_SHA256"] = TEST_CHECKPOINT_SHA256
        os.environ["MOGE_EXPECTED_CODE_REVISION"] = OFFICIAL_CODE_REVISION

    def tearDown(self) -> None:
        self.temp.cleanup()
        if self.previous_checkpoint_hash is None:
            os.environ.pop("MOGE_EXPECTED_CHECKPOINT_SHA256", None)
        else:
            os.environ["MOGE_EXPECTED_CHECKPOINT_SHA256"] = self.previous_checkpoint_hash
        if self.previous_code_revision is None:
            os.environ.pop("MOGE_EXPECTED_CODE_REVISION", None)
        else:
            os.environ["MOGE_EXPECTED_CODE_REVISION"] = self.previous_code_revision

    def write_manifest(self, frames: list[dict]) -> Path:
        manifest_path = self.root / "manifest.json"
        manifest_path.write_text(json.dumps({
            "schemaVersion": 1,
            "systemSessionId": "synthetic-session",
            "targetVersion": 4,
            "frames": frames,
        }), encoding="utf-8")
        return manifest_path

    def test_uses_metric_scale_once_and_keeps_textures(self) -> None:
        vertices = np.array([[1.0, 2.0, 3.0], [2.0, 2.0, 3.0], [1.0, 3.0, 3.0]])
        source = self.root / "frame.glb"
        make_textured_glb(source, vertices, (240, 20, 10, 255))
        manifest = self.write_manifest([frame("roof-east", 1, source.name)])

        output = self.root / "combined.glb"
        info = aggregate_manifest(manifest, output)

        loaded = trimesh.load(output, force="scene", process=False)
        mesh = next(iter(loaded.geometry.values()))
        expected = vertices * np.array([1.0, -1.0, -1.0]) + np.array([10.0, 20.0, 30.0])
        np.testing.assert_allclose(np.sort(mesh.vertices, axis=0), np.sort(expected, axis=0), atol=1e-5)
        self.assertIsNotNone(mesh.visual.uv)
        self.assertIsNotNone(mesh.visual.material.baseColorTexture)
        self.assertEqual(info["frameCount"], 1)
        self.assertEqual(info["meshCount"], 1)
        self.assertEqual(info["boundsM"], [expected.min(axis=0).tolist(), expected.max(axis=0).tolist()])
        self.assertIn("roof-east", next(iter(loaded.graph.nodes_geometry)))

    def test_applies_full_camera_rotation_quaternion_to_frame_geometry(self) -> None:
        vertices = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ])
        source = self.root / "rotated-frame.glb"
        make_textured_glb(source, vertices, (240, 20, 10, 255))
        rotated_frame = frame("camera-turned", 1, source.name)
        rotated_frame["translationM"] = [0.0, 0.0, 0.0]
        rotated_frame["rotationQuaternionXyzw"] = [
            0.0, 0.0, np.sqrt(0.5), np.sqrt(0.5),
        ]

        output = self.root / "rotated-combined.glb"
        aggregate_manifest(self.write_manifest([rotated_frame]), output)

        loaded = trimesh.load(output, force="scene", process=False)
        mesh = next(iter(loaded.geometry.values()))
        expected = np.array([
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 0.0, -1.0],
        ])
        np.testing.assert_allclose(
            np.asarray(mesh.vertices),
            expected,
            atol=1e-5,
        )

    def test_separately_retains_textures_from_multiple_registered_frames(self) -> None:
        points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
        paths = []
        frames = []
        for index, color in enumerate(((255, 0, 0, 255), (0, 0, 255, 255)), 1):
            path = self.root / f"frame{index}.glb"
            make_textured_glb(path, points + [index, 0, 0], color)
            paths.append(path)
            frames.append(frame(f"f{index}", index, path.name))
        output = self.root / "combined.glb"
        aggregate_manifest(self.write_manifest(frames), output)

        loaded = trimesh.load(output, force="scene", process=False)
        self.assertEqual(len(loaded.geometry), 2)
        self.assertEqual(len(loaded.graph.nodes_geometry), 2)
        for mesh in loaded.geometry.values():
            self.assertIsNotNone(mesh.visual.material.baseColorTexture)

    def test_fuses_near_duplicate_rectangles_and_later_sequence_texture_wins(self) -> None:
        first_path = self.root / "first.glb"
        second_path = self.root / "second.glb"
        make_textured_rectangle_glb(first_path, (0, 0, 2, 1), 0.0, (240, 20, 10, 255))
        make_textured_rectangle_glb(second_path, (0.001, 0, 2.001, 1), 0.001, (10, 20, 240, 255))
        records = [
            frame("later", 2, second_path.name),
            frame("stable-winner", 1, first_path.name),
        ]

        output = self.root / "deduplicated.glb"
        info = aggregate_manifest(self.write_manifest(records), output)
        loaded = trimesh.load(output, force="scene", process=False)

        self.assertEqual(info["meshCount"], 1)
        self.assertEqual(len(loaded.geometry), 1)
        self.assertIn("frame_000001_stable-winner", next(iter(loaded.graph.nodes_geometry)))
        mesh = next(iter(loaded.geometry.values()))
        self.assertIsNotNone(mesh.visual.uv)
        texture = mesh.visual.material.baseColorTexture
        self.assertIsNotNone(texture)
        atlas = np.asarray(texture.convert("RGBA"))
        np.testing.assert_array_equal(atlas[atlas.shape[0] // 2, atlas.shape[1] // 2],
                                      [10, 20, 240, 255])
        sources = mesh.metadata.get("merged_patch_sources", [])
        self.assertEqual([source["frame_id"] for source in sources], ["stable-winner", "later"])
        suppressed = mesh.metadata.get("suppressed_duplicate_sources", [])
        self.assertEqual(suppressed[0]["frame_id"], "later")
        self.assertEqual(mesh.metadata.get("texture_merge_policy"), "sequence_order_alpha_over")

    def test_merges_meaningfully_overlapping_patches_but_keeps_distinct_surfaces(self) -> None:
        cases = [
            ((0, 0, 1, 1), 0.0, (3, 0, 4, 1), 0.0, 2),
            ((0, 0, 1, 1), 0.0, (0, 0, 1, 1), 0.1, 2),
            ((0, 0, 1, 1), 0.0, (0.5, 0, 1.5, 1), 0.0, 1),
            ((0, 0, 1, 1), 0.0, (0.85, 0, 1.85, 1), 0.0, 2),
        ]
        for case_index, (first_bounds, first_z, second_bounds, second_z, expected_count) in enumerate(cases):
            with self.subTest(case=case_index):
                first_path = self.root / f"first-{case_index}.glb"
                second_path = self.root / f"second-{case_index}.glb"
                make_textured_rectangle_glb(first_path, first_bounds, first_z, (240, 20, 10, 255))
                make_textured_rectangle_glb(second_path, second_bounds, second_z, (10, 20, 240, 255))
                output = self.root / f"kept-{case_index}.glb"
                info = aggregate_manifest(self.write_manifest([
                    frame("first", 1, first_path.name),
                    frame("second", 2, second_path.name),
                ]), output)
                loaded = trimesh.load(output, force="scene", process=False)
                self.assertEqual(info["meshCount"], expected_count)
                self.assertEqual(len(loaded.geometry), expected_count)
                self.assertTrue(all(mesh.visual.material.baseColorTexture is not None
                                    for mesh in loaded.geometry.values()))
                if expected_count == 1:
                    mesh = next(iter(loaded.geometry.values()))
                    atlas = np.asarray(mesh.visual.material.baseColorTexture.convert("RGBA"))
                    # The non-overlap portions from both images survive the
                    # projected atlas composition.
                    self.assertGreater(np.count_nonzero(np.all(atlas == [240, 20, 10, 255], axis=2)), 0)
                    self.assertGreater(np.count_nonzero(np.all(atlas == [10, 20, 240, 255], axis=2)), 0)
                    uv = np.asarray(mesh.visual.uv)
                    self.assertTrue(np.all(uv >= 0.0))
                    self.assertTrue(np.all(uv <= 1.0))
                    texture_height, texture_width = atlas.shape[:2]
                    uv_pixels = np.column_stack((
                        np.rint(uv[:, 0] * (texture_width - 1)).astype(int),
                        np.rint((1.0 - uv[:, 1]) * (texture_height - 1)).astype(int),
                    ))
                    sampled_at_vertices = atlas[uv_pixels[:, 1], uv_pixels[:, 0]]
                    self.assertGreater(np.count_nonzero(np.all(
                        sampled_at_vertices == [240, 20, 10, 255], axis=1
                    )), 0)
                    self.assertGreater(np.count_nonzero(np.all(
                        sampled_at_vertices == [10, 20, 240, 255], axis=1
                    )), 0)

    def test_overlap_uses_sequence_order_alpha_compositing(self) -> None:
        first_path = self.root / "opaque-red.glb"
        second_path = self.root / "half-blue.glb"
        make_textured_rectangle_glb(first_path, (0, 0, 1, 1), 0.0, (255, 0, 0, 255))
        make_textured_rectangle_glb(second_path, (0, 0, 1, 1), 0.0, (0, 0, 255, 128))
        output = self.root / "blended.glb"

        info = aggregate_manifest(self.write_manifest([
            frame("red", 1, first_path.name),
            frame("blue", 2, second_path.name),
        ]), output)
        loaded = trimesh.load(output, force="scene", process=False)
        self.assertEqual(info["meshCount"], 1)
        mesh = next(iter(loaded.geometry.values()))
        atlas = np.asarray(mesh.visual.material.baseColorTexture.convert("RGBA"))
        np.testing.assert_array_equal(atlas[atlas.shape[0] // 2, atlas.shape[1] // 2],
                                      [127, 0, 128, 255])
        self.assertTrue(np.all(np.asarray(mesh.visual.uv) >= 0.0))

    def test_keeps_slightly_angled_planes_that_diverge_at_their_edges(self) -> None:
        first_path = self.root / "flat.glb"
        second_path = self.root / "tilted.glb"
        make_textured_rectangle_glb(first_path, (0, 0, 1, 1), 0.0, (240, 20, 10, 255))
        make_textured_rectangle_glb(second_path, (0, 0, 1, 1), 0.0, (10, 20, 240, 255))
        tilted = frame("tilted", 2, second_path.name)
        angle = np.deg2rad(0.6)
        rotation = np.array([
            [np.cos(angle), 0.0, np.sin(angle)],
            [0.0, 1.0, 0.0],
            [-np.sin(angle), 0.0, np.cos(angle)],
        ])
        # Rotate about the scaled footprint center so the planes meet there.
        center = np.array([0.5, 0.5, 0.0])
        tilted["rotationQuaternionXyzw"] = [
            0.0, np.sin(angle / 2.0), 0.0, np.cos(angle / 2.0),
        ]
        tilted["translationM"] = (center - rotation @ center).tolist()
        output = self.root / "slightly-tilted.glb"

        info = aggregate_manifest(self.write_manifest([
            frame("flat", 1, first_path.name),
            tilted,
        ]), output)
        loaded = trimesh.load(output, force="scene", process=False)

        self.assertEqual(info["meshCount"], 2)
        self.assertEqual(len(loaded.geometry), 2)

    def test_texture_merge_is_independent_of_manifest_order(self) -> None:
        paths = []
        records = []
        for sequence, color in ((1, (240, 20, 10, 255)), (2, (10, 20, 240, 255))):
            path = self.root / f"stable-{sequence}.glb"
            make_textured_rectangle_glb(path, (0, 0, 1, 1), 0.0, color)
            paths.append(path)
            records.append(frame(f"f{sequence}", sequence, path.name))
        for suffix, ordered in (("forward", records), ("reverse", list(reversed(records)))):
            output = self.root / f"{suffix}.glb"
            aggregate_manifest(self.write_manifest(ordered), output)
            loaded = trimesh.load(output, force="scene", process=False)
            self.assertEqual(list(loaded.graph.nodes_geometry), [
                "frame_000001_f1_mesh_0000_geometry_0",
            ])
            mesh = next(iter(loaded.geometry.values()))
            np.testing.assert_array_equal(
                np.asarray(mesh.visual.material.baseColorTexture.convert("RGBA"))[0, 0],
                [10, 20, 240, 255],
            )
            self.assertEqual(
                [source["frame_id"] for source in mesh.metadata["merged_patch_sources"]],
                ["f1", "f2"],
            )

    def test_composes_verified_camera_basis_with_session_pose(self) -> None:
        vertices = np.array([[1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [1.0, 1.0, 0.0]])
        source = self.root / "rotated.glb"
        make_textured_glb(source, vertices, (10, 20, 30, 255))
        item = frame("rotated", 1, source.name)
        item["translationM"] = [0.0, 2.0, 0.0]
        item["rotationQuaternionXyzw"] = [0.0, 0.0, np.sqrt(0.5), np.sqrt(0.5)]
        aggregate_manifest(self.write_manifest([item]), self.root / "rotated-out.glb")

        loaded = trimesh.load(self.root / "rotated-out.glb", force="scene", process=False)
        actual = np.asarray(next(iter(loaded.geometry.values())).vertices)
        expected = np.array([[0.0, 3.0, 0.0], [0.0, 4.0, 0.0], [1.0, 3.0, 0.0]])
        np.testing.assert_allclose(
            np.sort(actual, axis=0),
            np.sort(expected, axis=0),
            atol=1e-5,
        )

    def test_rejects_client_mapping_and_invalid_worker_sidecar(self) -> None:
        source = self.root / "frame.glb"
        make_textured_glb(source, np.eye(3), (255, 255, 255, 255))
        bad = frame("f", 1, source.name)
        bad["mogeToCameraMatrix4x4"] = np.eye(4).reshape(-1).tolist()
        with self.assertRaisesRegex(AggregationError, "client-supplied"):
            aggregate_manifest(self.write_manifest([bad]), self.root / "out.glb")
        sidecar_path = Path(str(source) + ".convention.json")
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        sidecar["glbStoredToMogeMatrix4x4"][0] = 2.0
        sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
        bad = frame("f", 1, source.name)
        with self.assertRaisesRegex(AggregationError, "sidecar"):
            aggregate_manifest(self.write_manifest([bad]), self.root / "out.glb")
        sidecar["glbStoredToMogeMatrix4x4"] = FLIP.reshape(-1).tolist()
        sidecar["scale"] = 1.01
        sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
        with self.assertRaisesRegex(AggregationError, "sidecar"):
            aggregate_manifest(self.write_manifest([bad]), self.root / "out.glb")

    def test_requires_sidecar_even_when_frame_glb_is_readable(self) -> None:
        source = self.root / "frame.glb"
        make_textured_glb(source, np.eye(3), (255, 255, 255, 255))
        Path(str(source) + ".convention.json").unlink()
        with self.assertRaisesRegex(AggregationError, "convention sidecar"):
            aggregate_manifest(
                self.write_manifest([frame("f", 1, source.name)]),
                self.root / "out.glb",
            )

    def test_rejects_wrong_world_and_non_normalized_quaternion(self) -> None:
        source = self.root / "frame.glb"
        make_textured_glb(source, np.eye(3), (255, 255, 255, 255))
        bad = frame("f", 1, source.name)
        bad["axes"] = {"world": "unknown"}
        with self.assertRaisesRegex(AggregationError, "client-supplied"):
            aggregate_manifest(self.write_manifest([bad]), self.root / "out.glb")
        bad = frame("f", 1, source.name)
        bad["rotationQuaternionXyzw"] = [0, 0, 0, 2]
        with self.assertRaisesRegex(AggregationError, "unit length"):
            aggregate_manifest(self.write_manifest([bad]), self.root / "out.glb")

    def test_sequence_zero_accepts_both_identity_quaternion_signs(self) -> None:
        source = self.root / "base.glb"
        make_textured_glb(source, np.eye(3), (255, 255, 255, 255))
        for index, quaternion in enumerate((
            [0.0, 0.0, 0.0, 1.0],
            [0.0, 0.0, 0.0, -1.0],
        )):
            with self.subTest(quaternion=quaternion):
                base = frame(f"base-{index}", 0, source.name)
                base["translationM"] = [0.0, 0.0, 0.0]
                base["rotationQuaternionXyzw"] = quaternion
                output = self.root / f"base-{index}.glb"
                aggregate_manifest(
                    self.write_manifest([base]), output, require_base_frame=True
                )
                self.assertTrue(output.is_file())

    def test_sequence_zero_rejects_malformed_near_identity_transforms(self) -> None:
        source = self.root / "base.glb"
        make_textured_glb(source, np.eye(3), (255, 255, 255, 255))
        malformed = (
            ([0.0, 0.0, 0.0, -0.5], [0.0, 0.0, 0.0], "unit length"),
            ([0.01, 0.0, 0.0, (1.0 - 0.01 ** 2) ** 0.5],
             [0.0, 0.0, 0.0], "identity"),
            ([0.0, 0.0, 0.0, -1.0], [0.01, 0.0, 0.0], "identity"),
            ([0.0, 0.0, 0.0, float("nan")], [0.0, 0.0, 0.0], "finite"),
        )
        for index, (quaternion, translation, error) in enumerate(malformed):
            with self.subTest(quaternion=quaternion, translation=translation):
                base = frame(f"bad-base-{index}", 0, source.name)
                base["translationM"] = translation
                base["rotationQuaternionXyzw"] = quaternion
                with self.assertRaisesRegex(AggregationError, error):
                    aggregate_manifest(
                        self.write_manifest([base]),
                        self.root / f"bad-base-{index}.glb",
                        require_base_frame=True,
                    )

    def test_failed_aggregation_does_not_replace_existing_output(self) -> None:
        output = self.root / "existing.glb"
        output.write_bytes(b"keep existing")
        manifest = self.write_manifest([frame("missing", 1, "no-file.glb")])
        with self.assertRaises(AggregationError):
            aggregate_manifest(manifest, output)
        self.assertEqual(output.read_bytes(), b"keep existing")


if __name__ == "__main__":
    unittest.main()
