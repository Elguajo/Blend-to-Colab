import json
from pathlib import Path
import tempfile
import unittest

from src.job_protocol import (
    JobProtocolError,
    JobState,
    JobStateError,
    JobStore,
    ResumableJobRunner,
    make_job_document,
    plan_chunks,
    validate_job_document,
    validate_result_manifest,
    validate_status_document,
)


class JobProtocolTests(unittest.TestCase):
    def _job(self, root: Path, *, start: int = 1, end: int = 4) -> JobStore:
        source = root / "scene.blend"
        source.write_bytes(b"source blend fixture")
        store = JobStore(root / "job")
        store.create_job(
            make_job_document(
                project_name="fixture",
                project_path=source,
                source_blender_version="5.2.1",
                requested_blender_version="5.2.1",
                start=start,
                end=end,
                step=1,
            )
        )
        return store

    def _renderer(self, calls: list[tuple[int, ...]], *, interrupt_at: int | None = None):
        def render(chunk, staging):
            calls.append(chunk.frames)
            if interrupt_at == chunk.start:
                raise KeyboardInterrupt()
            result = {}
            for frame in chunk.frames:
                output = staging / f"render_{frame:04d}.png"
                output.write_bytes(f"frame {frame}".encode())
                result[frame] = output
            return result

        return render

    def test_schemas_are_valid_json_and_core_documents_match_contract(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        for name in ("job.schema.json", "status.schema.json", "result_manifest.schema.json"):
            schema = json.loads((repository_root / "protocol" / name).read_text(encoding="utf-8"))
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")

        with tempfile.TemporaryDirectory() as temporary:
            store = self._job(Path(temporary))
            job = validate_job_document(store.job())
            status = store.publish_status(
                JobState.PREFLIGHT,
                completed_frames=0,
                total_frames=4,
                message="Planning.",
                worker_version="test",
            )
            manifest = store.publish_manifest([], complete=False)
            self.assertEqual(job["protocol_version"], "1.0")
            self.assertEqual(validate_status_document(status)["revision"], 1)
            self.assertEqual(validate_result_manifest(manifest)["artifacts"], [])

    def test_state_revision_is_monotonic_and_invalid_transition_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = self._job(Path(temporary), end=1)
            first = store.publish_status(
                JobState.PREFLIGHT, completed_frames=0, total_frames=1, message="preflight", worker_version="test"
            )
            second = store.publish_status(
                JobState.RENDERING, completed_frames=0, total_frames=1, message="rendering", worker_version="test"
            )
            self.assertEqual((first["revision"], second["revision"]), (1, 2))
            with self.assertRaises(JobStateError):
                store.publish_status(
                    JobState.PREFLIGHT, completed_frames=0, total_frames=1, message="backward", worker_version="test"
                )

    def test_plan_chunks_never_includes_confirmed_frame_gaps(self) -> None:
        chunks = plan_chunks((1, 2, 4, 5, 7), step=1, chunk_size=3)
        self.assertEqual([chunk.frames for chunk in chunks], [(1, 2), (4, 5), (7,)])

    def test_interrupted_job_resumes_only_missing_frames_and_keeps_checksums(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = self._job(Path(temporary))
            initial_calls: list[tuple[int, ...]] = []
            runner = ResumableJobRunner(store, worker_version="test", chunk_size=2)
            with self.assertRaises(KeyboardInterrupt):
                runner.run(self._renderer(initial_calls, interrupt_at=3))
            self.assertEqual(initial_calls, [(1, 2), (3, 4)])
            self.assertEqual(store.status()["state"], "PARTIAL")
            self.assertEqual(sorted(store.valid_artifacts()), [1, 2])

            resumed_calls: list[tuple[int, ...]] = []
            manifest = ResumableJobRunner(store, worker_version="test", chunk_size=2).run(
                self._renderer(resumed_calls)
            )
            self.assertEqual(resumed_calls, [(3, 4)])
            self.assertEqual(manifest["state"], "COMPLETE")
            self.assertEqual(sorted(store.valid_artifacts()), [1, 2, 3, 4])
            self.assertEqual(store.status()["state"], "COMPLETE")
            self.assertFalse(list((store.paths.result_dir / "frames").glob("*.tmp")))
            self.assertEqual(
                json.loads(store.paths.summary_path.read_text(encoding="utf-8"))["state"],
                "COMPLETE",
            )
            self.assertIn("CHUNK_COMPLETE frames=3,4", store.paths.log_path.read_text(encoding="utf-8"))

    def test_corrupt_confirmed_result_is_not_reused_and_is_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = self._job(Path(temporary), end=2)
            calls: list[tuple[int, ...]] = []
            ResumableJobRunner(store, worker_version="test", chunk_size=2).run(self._renderer(calls))
            frame_one = store.paths.result_dir / "frames" / "frame_000001.png"
            frame_one.write_bytes(b"corrupted")
            self.assertEqual(sorted(store.valid_artifacts()), [2])

            repair_calls: list[tuple[int, ...]] = []
            manifest = ResumableJobRunner(store, worker_version="test", chunk_size=2).run(
                self._renderer(repair_calls)
            )
            self.assertEqual(repair_calls, [(1,)])
            self.assertEqual(manifest["state"], "COMPLETE")
            self.assertEqual(sorted(store.valid_artifacts()), [1, 2])

    def test_rejects_non_uuid_and_unsafe_result_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = self._job(Path(temporary), end=1)
            job = store.job()
            job["job_id"] = "not-a-uuid"
            with self.assertRaises(JobProtocolError):
                validate_job_document(job)
            job["job_id"] = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
            with self.assertRaises(JobProtocolError):
                validate_job_document(job)
            manifest = {
                "protocol_version": "1.0",
                "job_id": store.job()["job_id"],
                "published_at": "2026-01-01T00:00:00Z",
                "state": "PARTIAL",
                "artifacts": [{"frame": 1, "path": "../secret.png", "sha256": "0" * 64, "size_bytes": 0}],
            }
            with self.assertRaises(JobProtocolError):
                validate_result_manifest(manifest)

    def test_notebook_has_a_shell_free_resumable_render_cell(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        notebook = json.loads(
            (repository_root / "render_blender_in_colab.ipynb").read_text(encoding="utf-8")
        )
        cell_source = next(
            "".join(cell["source"])
            for cell in notebook["cells"]
            if "Protocol v1" in "".join(cell.get("source", []))
        )
        compile(cell_source, "resumable render cell", "exec")
        self.assertIn("JOB_ID", cell_source)
        self.assertIn("result_manifest.json", cell_source)
        self.assertIn("subprocess.Popen", cell_source)
        self.assertNotIn("shell=True", cell_source)
