import json
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from moge_convention import (
    ConventionError,
    GLB_FROM_MOGE,
    OFFICIAL_CODE_REVISION,
    PROVENANCE_METHOD,
    runtime_provenance_for_mode,
    validate_glb_sidecar,
    verify_canonical_orientation,
    write_frame_provenance,
    write_glb_sidecar,
    write_glb_sidecar_if_required,
)


class MogeConventionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.previous_checkpoint_hash = os.environ.get("MOGE_EXPECTED_CHECKPOINT_SHA256")
        self.previous_code_revision = os.environ.get("MOGE_EXPECTED_CODE_REVISION")
        os.environ["MOGE_EXPECTED_CHECKPOINT_SHA256"] = "a" * 64
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

    def test_only_canonical_exif_orientation_is_supported(self) -> None:
        canonical = self.root / "canonical.png"
        Image.new("RGB", (4, 3), (10, 20, 30)).save(canonical)
        orientation = verify_canonical_orientation(canonical)
        self.assertTrue(orientation["verified"])
        self.assertEqual(len(orientation["imageSha256"]), 64)

        rotated = self.root / "rotated.jpg"
        image = Image.new("RGB", (4, 3), (10, 20, 30))
        exif = Image.Exif()
        exif[274] = 6
        image.save(rotated, exif=exif)
        with self.assertRaisesRegex(ConventionError, "EXIF orientation 6"):
            verify_canonical_orientation(rotated)

    def test_writes_adjacent_fixed_metric_convention_sidecar(self) -> None:
        image = self.root / "frame.png"
        Image.new("RGB", (4, 3), (10, 20, 30)).save(image)
        provenance = {
            "modelVersion": "v3",
            "codeRevision": OFFICIAL_CODE_REVISION,
            "checkpointSha256": "a" * 64,
            "verification": PROVENANCE_METHOD,
        }
        orientation = verify_canonical_orientation(image)
        provenance_path = self.root / "frame" / "moge3.provenance.json"
        write_frame_provenance(provenance_path, provenance, orientation)

        glb_path = self.root / "frame_planes.glb"
        glb_path.write_bytes(b"synthetic glb")
        sidecar_path = write_glb_sidecar(glb_path, provenance_path)

        self.assertEqual(sidecar_path, Path(str(glb_path) + ".convention.json"))
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        self.assertEqual(sidecar["scale"], 1.0)
        self.assertEqual(sidecar["unit"], "m")
        self.assertEqual(sidecar["glbSha256"], hashlib.sha256(glb_path.read_bytes()).hexdigest())
        np.testing.assert_array_equal(
            np.asarray(sidecar["glbStoredToMogeMatrix4x4"]).reshape(4, 4),
            GLB_FROM_MOGE,
        )
        self.assertEqual(validate_glb_sidecar(sidecar_path), sidecar)

    def test_unconfigured_worker_provenance_fails_closed(self) -> None:
        sidecar = self.root / "missing.glb.convention.json"
        sidecar.write_text("{}", encoding="utf-8")
        os.environ.pop("MOGE_EXPECTED_CHECKPOINT_SHA256", None)
        with self.assertRaisesRegex(ConventionError, "MOGE_EXPECTED_CHECKPOINT_SHA256"):
            validate_glb_sidecar(sidecar)

    def test_runtime_pins_are_optional_only_when_provenance_is_not_required(self) -> None:
        os.environ.pop("MOGE_EXPECTED_CHECKPOINT_SHA256", None)
        os.environ.pop("MOGE_EXPECTED_CODE_REVISION", None)
        self.assertIsNone(runtime_provenance_for_mode(False, self.root / "unused.pt", "unused.py"))
        with self.assertRaisesRegex(ConventionError, "MOGE_EXPECTED_CODE_REVISION"):
            runtime_provenance_for_mode(True, self.root / "unused.pt", "unused.py")

    def test_sidecar_is_skipped_for_legacy_and_required_for_system_frames(self) -> None:
        glb_path = self.root / "legacy_planes.glb"
        glb_path.write_bytes(b"synthetic glb")
        provenance_path = self.root / "missing.provenance.json"

        self.assertIsNone(write_glb_sidecar_if_required(glb_path, provenance_path, required=False))
        self.assertFalse(Path(str(glb_path) + ".convention.json").exists())
        with self.assertRaisesRegex(ConventionError, "Cannot read verified frame provenance"):
            write_glb_sidecar_if_required(glb_path, provenance_path, required=True)


if __name__ == "__main__":
    unittest.main()
