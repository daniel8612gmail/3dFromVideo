import hashlib
import json
import os
import shutil
import sys
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from geom_aggregate_glb import AggregationError, aggregate_manifest
from geom_publish_glb import (
    PublicationPending,
    PublisherError,
    publish_request,
)
from moge_convention import (
    OFFICIAL_CODE_REVISION,
    PROVENANCE_METHOD,
    make_glb_sidecar,
)


SESSION_A = "a" * 32
SESSION_B = "c" * 32


class InjectedCrash(BaseException):
    pass


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.calls = []
        self.aggregate = self.make_aggregator()
        self.previous_checkpoint_hash = os.environ.get("MOGE_EXPECTED_CHECKPOINT_SHA256")
        self.previous_code_revision = os.environ.get("MOGE_EXPECTED_CODE_REVISION")
        os.environ["MOGE_EXPECTED_CHECKPOINT_SHA256"] = "a" * 64
        os.environ["MOGE_EXPECTED_CODE_REVISION"] = OFFICIAL_CODE_REVISION

    def tearDown(self):
        self.temp.cleanup()
        if self.previous_checkpoint_hash is None:
            os.environ.pop("MOGE_EXPECTED_CHECKPOINT_SHA256", None)
        else:
            os.environ["MOGE_EXPECTED_CHECKPOINT_SHA256"] = self.previous_checkpoint_hash
        if self.previous_code_revision is None:
            os.environ.pop("MOGE_EXPECTED_CODE_REVISION", None)
        else:
            os.environ["MOGE_EXPECTED_CODE_REVISION"] = self.previous_code_revision

    @staticmethod
    def write_valid_convention_sidecar(glb_path):
        provenance = {
            "schemaVersion": 1,
            "modelVersion": "v3",
            "codeRevision": OFFICIAL_CODE_REVISION,
            "checkpointSha256": "a" * 64,
            "verification": PROVENANCE_METHOD,
            "canonicalOrientation": {
                "verified": True,
                "method": "EXIF orientation absent or 1; source pixels used without rotation or mirroring",
                "exifOrientation": None,
                "imageSha256": "b" * 64,
            },
        }
        sidecar = make_glb_sidecar(provenance)
        sidecar["glbSha256"] = hashlib.sha256(glb_path.read_bytes()).hexdigest()
        Path(str(glb_path) + ".convention.json").write_text(
            json.dumps(sidecar), encoding="utf-8"
        )

    def make_aggregator(self, barrier=None, fail=False):
        calls = self.calls

        def aggregate(manifest_path, output_path, require_base_frame=False):
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            calls.append((manifest["systemSessionId"], manifest["targetVersion"],
                          [frame["frameId"] for frame in manifest["frames"]]))
            if barrier is not None:
                barrier.wait(timeout=5)
            if fail:
                Path(output_path).write_bytes(b"not-a-glb")
                return {}
            source = Path(manifest["frames"][0]["glbPath"])
            shutil.copyfile(source, output_path)
            return {"frameCount": len(manifest["frames"])}

        return aggregate

    def make_session(self, session_id=SESSION_A):
        session = self.data / "system-sessions" / session_id
        (session / "aggregator-inbox").mkdir(parents=True, exist_ok=True)
        return session

    def add_request(
        self,
        frame_id,
        sequence,
        request_id,
        session_id=SESSION_A,
        translation=None,
        quaternion=None,
    ):
        session = self.make_session(session_id)
        inbox = session / "aggregator-inbox" / request_id
        inbox.mkdir(parents=True, exist_ok=True)
        input_path = inbox / "input.glb"
        mesh = trimesh.creation.box(extents=[1.0, 1.0, 1.0])
        trimesh.Scene(mesh).export(input_path, file_type="glb")
        glb_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
        sidecar_path = Path(str(input_path) + ".convention.json")
        sidecar_path.write_text(json.dumps({"glbSha256": glb_hash}), encoding="utf-8")
        relative_glb = input_path.relative_to(self.data).as_posix()
        record = {
            "frameId": frame_id,
            "sequence": sequence,
            "glbPath": relative_glb,
            "conventionSidecarPath": relative_glb + ".convention.json",
            "cameraToFirstFrame": {
                "translationM": translation if translation is not None else [0.0, 0.0, 0.0],
                "rotationQuaternionXyzw": (
                    quaternion if quaternion is not None else [0.0, 0.0, 0.0, 1.0]
                ),
            },
        }
        metadata = {
            "schemaVersion": 1,
            "requestId": request_id,
            "systemSessionId": session_id,
            "frameId": frame_id,
            "sequence": sequence,
            "inputGlbSha256": glb_hash,
            "inputGlbPath": relative_glb,
            "frames": [record],
        }
        metadata_path = inbox / "publisher-metadata.json"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        return {
            "requestId": request_id,
            "sessionId": session_id,
            "frameId": frame_id,
            "input": input_path,
            "metadata": metadata_path,
        }

    def publish(self, request, aggregate=None, fault_hook=None):
        return publish_request(
            request["requestId"],
            request["sessionId"],
            request["frameId"],
            request["input"],
            request["metadata"],
            self.data,
            aggregate_fn=aggregate or self.aggregate,
            fault_hook=fault_hook,
        )

    def cli_command(self, request, result_path):
        script = Path(__file__).resolve().parents[1] / "geom_publish_glb.py"
        return [
            sys.executable, str(script),
            "--request-id", request["requestId"],
            "--system-session-id", request["sessionId"],
            "--frame-id", request["frameId"],
            "--input-glb", str(request["input"]),
            "--metadata-json", str(request["metadata"]),
            "--data-dir", str(self.data),
            "--result-json", str(result_path),
        ]

    def test_late_sequence_zero_publishes_all_durable_frames(self):
        later = self.add_request("frame-later", 1, "1" * 32, translation=[1, 0, 0])
        with self.assertRaises(PublicationPending):
            self.publish(later)
        session = self.make_session()
        self.assertEqual(json.loads((session / "current-version.json").read_text())["currentVersion"], 0)
        self.assertFalse((session / "model.v1.glb").exists())

        base = self.add_request("frame-base", 0, "2" * 32)
        result = self.publish(base)
        self.assertEqual(result, {"requestId": base["requestId"], "status": "committed", "version": 1})
        self.assertEqual(self.calls[-1][2], ["frame-base", "frame-later"])
        self.assertEqual(self.publish(later)["version"], 1)

    def test_same_session_concurrent_publishers_rebuild_without_lost_frames(self):
        base = self.add_request("base", 0, "3" * 32)
        self.assertEqual(self.publish(base)["version"], 1)
        second = self.add_request("second", 1, "4" * 32, translation=[1, 0, 0])
        third = self.add_request("third", 2, "5" * 32, translation=[2, 0, 0])
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.publish, [second, third]))
        self.assertEqual({result["version"] for result in results}, {2, 3})
        session = self.make_session()
        state = json.loads((session / "publisher-state.json").read_text())
        self.assertEqual(set(state["frames"]), {"base", "second", "third"})
        self.assertEqual(json.loads((session / "current-version.json").read_text())["currentVersion"], 3)
        self.assertEqual(sorted(path.name for path in session.glob("model.v*.glb")),
                         ["model.v1.glb", "model.v2.glb", "model.v3.glb"])

    def test_same_session_concurrent_cli_processes_use_os_lock(self):
        base = self.add_request("base", 0, "31" * 16)
        self.write_valid_convention_sidecar(base["input"])
        self.assertEqual(self.publish(base, aggregate=aggregate_manifest)["version"], 1)

        requests = [
            self.add_request("process-one", 1, "32" * 16, translation=[1, 0, 0]),
            self.add_request("process-two", 2, "33" * 16, translation=[2, 0, 0]),
        ]
        result_paths = [
            request["metadata"].parent / "publisher-result.json"
            for request in requests
        ]
        for request, result_path in zip(requests, result_paths):
            self.write_valid_convention_sidecar(request["input"])
        processes = [
            subprocess.Popen(
                self.cli_command(request, result_path),
                cwd=self.data,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for request, result_path in zip(requests, result_paths)
        ]
        outputs = [process.communicate(timeout=60) for process in processes]
        self.assertEqual([process.returncode for process in processes], [0, 0], outputs)
        results = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in result_paths
        ]
        self.assertEqual({result["version"] for result in results}, {2, 3})
        session = self.make_session()
        state = json.loads((session / "publisher-state.json").read_text())
        self.assertEqual(set(state["frames"]), {"base", "process-one", "process-two"})
        self.assertEqual(json.loads((session / "current-version.json").read_text())["currentVersion"], 3)

    def test_independent_sessions_publish_concurrently(self):
        barrier = threading.Barrier(2)
        aggregator = self.make_aggregator(barrier=barrier)
        first = self.add_request("base-a", 0, "6" * 32, session_id=SESSION_A)
        second = self.add_request("base-b", 0, "7" * 32, session_id=SESSION_B)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda item: self.publish(item, aggregator), [first, second]))
        self.assertEqual([result["version"] for result in results], [1, 1])
        self.assertEqual(len(self.calls), 2)

    def test_duplicate_request_and_duplicate_frame_do_not_republish(self):
        original = self.add_request("base", 0, "8" * 32)
        self.assertEqual(self.publish(original)["version"], 1)
        call_count = len(self.calls)
        self.assertEqual(self.publish(original)["version"], 1)
        self.assertEqual(len(self.calls), call_count)

        duplicate = self.add_request("base", 0, "9" * 32)
        self.assertEqual(self.publish(duplicate)["version"], 1)
        self.assertEqual(len(self.calls), call_count)
        session = self.make_session()
        state = json.loads((session / "publisher-state.json").read_text())
        self.assertEqual(len(state["frames"]), 1)
        self.assertEqual(json.loads((session / "current-version.json").read_text())["currentVersion"], 1)

    def test_recovers_crashes_after_model_rename_and_after_pointer(self):
        for request_id, crash_stage in (("a1" * 16, "after-model-rename"),
                                        ("a2" * 16, "after-pointer")):
            with self.subTest(stage=crash_stage):
                session_id = "b" * 32 if crash_stage == "after-model-rename" else "d" * 32
                request = self.add_request(
                    f"base-{crash_stage}", 0, request_id, session_id=session_id
                )

                def crash(stage):
                    if stage == crash_stage:
                        raise InjectedCrash(stage)

                with self.assertRaises(InjectedCrash):
                    self.publish(request, fault_hook=crash)
                recovered = self.publish(request)
                self.assertEqual(recovered["status"], "committed")
                self.assertEqual(recovered["version"], 1)
                session = self.make_session(session_id)
                self.assertEqual(
                    json.loads((session / "current-version.json").read_text())["currentVersion"],
                    1,
                )
                self.assertTrue((session / "model.v1.glb").is_file())

    def test_candidate_failure_does_not_advance_version_or_keep_bad_frame(self):
        request = self.add_request("base", 0, "c1" * 16)
        result = self.publish(request, aggregate=self.make_aggregator(fail=True))
        self.assertEqual(result["status"], "rejected")
        session = self.make_session()
        self.assertEqual(json.loads((session / "current-version.json").read_text())["currentVersion"], 0)
        self.assertFalse((session / "model.v1.glb").exists())
        state = json.loads((session / "publisher-state.json").read_text())
        self.assertEqual(state["frames"], {})
        self.assertEqual(state["requests"][request["requestId"]]["status"], "rejected")

    def test_publishes_valid_candidate_through_legacy_geometry_aggregator(self):
        request = self.add_request("base", 0, "cc" * 16)
        self.write_valid_convention_sidecar(request["input"])
        result = self.publish(request, aggregate=aggregate_manifest)
        self.assertEqual(result["status"], "committed")
        model = self.make_session() / "model.v1.glb"
        loaded = trimesh.load(model, force="scene", process=False)
        self.assertTrue(loaded.geometry)
        self.assertTrue((self.make_session() / "current-version.json").is_file())

    def test_cli_matches_aggregator_adapter_arguments_and_result_file(self):
        request = self.add_request("base", 0, "ce" * 16)
        self.write_valid_convention_sidecar(request["input"])
        result_path = request["metadata"].parent / "publisher-result.json"
        completed = subprocess.run(
            self.cli_command(request, result_path),
            cwd=self.data,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(result, {
            "requestId": request["requestId"],
            "status": "committed",
            "version": 1,
        })

    def test_rejects_nonidentity_base_and_mixed_pose_reference(self):
        bad_base = self.add_request(
            "bad-base", 0, "d1" * 16, translation=[0.1, 0, 0]
        )
        with self.assertRaises(PublisherError):
            self.publish(bad_base)

        mixed = self.add_request("mixed", 0, "d2" * 16)
        metadata = json.loads(mixed["metadata"].read_text())
        metadata["frames"][0]["poseReference"] = "cameraToSession"
        mixed["metadata"].write_text(json.dumps(metadata), encoding="utf-8")
        with self.assertRaises(PublisherError):
            self.publish(mixed)

    def test_accepts_both_identity_quaternion_signs_for_sequence_zero(self):
        for index, quaternion in enumerate((
            [0.0, 0.0, 0.0, 1.0],
            [0.0, 0.0, 0.0, -1.0],
        )):
            with self.subTest(quaternion=quaternion):
                request = self.add_request(
                    f"base-{index}", 0, f"{index + 1:x}" * 32,
                    session_id=(f"{index + 1:x}" * 32),
                    quaternion=quaternion,
                )
                self.assertEqual(self.publish(request)["status"], "committed")

    def test_rejects_malformed_near_identity_sequence_zero_poses(self):
        malformed = (
            ([0.0, 0.0, 0.0, -0.5], [0.0, 0.0, 0.0]),
            ([0.01, 0.0, 0.0, (1.0 - 0.01 ** 2) ** 0.5], [0.0, 0.0, 0.0]),
            ([0.0, 0.0, 0.0, -1.0], [0.01, 0.0, 0.0]),
        )
        for index, (quaternion, translation) in enumerate(malformed):
            with self.subTest(quaternion=quaternion, translation=translation):
                request = self.add_request(
                    f"bad-base-{index}", 0, f"{index + 10:x}" * 32,
                    quaternion=quaternion, translation=translation,
                )
                with self.assertRaises(PublisherError):
                    self.publish(request)


if __name__ == "__main__":
    unittest.main()
