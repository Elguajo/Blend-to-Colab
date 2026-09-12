"""Versioned, resumable render-job protocol shared by notebook clients.

The module deliberately uses only the standard library.  It owns worker-side
files (status, log and results); request/job.json is treated as immutable once
published.  A transport may copy the resulting job directory elsewhere, but
does not need to understand frame planning or result integrity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Callable, Iterable, Mapping
from uuid import UUID, uuid4

from .blend_to_colab import sha256_file


PROTOCOL_VERSION = "1.0"
PROTOCOL_MAJOR_VERSION = 1


class JobProtocolError(ValueError):
    """A persisted protocol document is malformed or incompatible."""


class JobStateError(JobProtocolError):
    """A status transition is not permitted by the worker state machine."""


class ResultValidationError(JobProtocolError):
    """A published result cannot be trusted as a completed frame."""


class JobState(str, Enum):
    PREFLIGHT = "PREFLIGHT"
    RENDERING = "RENDERING"
    PARTIAL = "PARTIAL"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.PREFLIGHT: frozenset({JobState.RENDERING, JobState.FAILED}),
    JobState.RENDERING: frozenset(
        {JobState.RENDERING, JobState.PARTIAL, JobState.COMPLETE, JobState.FAILED}
    ),
    # A fresh Colab runtime may re-run preflight before it resumes a partial
    # job; that restart does not invalidate any checksum-confirmed frame.
    JobState.PARTIAL: frozenset({JobState.PREFLIGHT, JobState.RENDERING, JobState.FAILED}),
    JobState.FAILED: frozenset({JobState.PREFLIGHT}),
    # COMPLETE is terminal while its manifest remains valid.  If a later
    # checksum audit finds damage, a new preflight starts an explicit repair
    # attempt rather than trusting the stale terminal status.
    JobState.COMPLETE: frozenset({JobState.PREFLIGHT}),
}


def utc_now() -> str:
    """Return an RFC3339 UTC timestamp with a stable ``Z`` suffix."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_job_id() -> str:
    """Create a UUID v4 suitable for an isolated protocol job directory."""
    return str(uuid4())


def _require_mapping(value: object, description: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise JobProtocolError(f"{description} must be a JSON object.")
    return value


def _require_string(value: object, description: str) -> str:
    if not isinstance(value, str) or not value:
        raise JobProtocolError(f"{description} must be a non-empty string.")
    return value


def _require_non_negative_int(value: object, description: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise JobProtocolError(f"{description} must be a non-negative integer.")
    return value


def _validate_protocol_version(value: object) -> str:
    version = _require_string(value, "protocol_version")
    try:
        major_text, minor_text = version.split(".", maxsplit=1)
        major, minor = int(major_text), int(minor_text)
    except (ValueError, TypeError) as error:
        raise JobProtocolError("protocol_version must use MAJOR.MINOR format.") from error
    if major != PROTOCOL_MAJOR_VERSION or minor < 0:
        raise JobProtocolError(
            f"Unsupported protocol_version {version!r}; expected major {PROTOCOL_MAJOR_VERSION}."
        )
    return version


def _validate_job_id(value: object) -> str:
    job_id = _require_string(value, "job_id")
    try:
        parsed = UUID(job_id)
    except (ValueError, AttributeError) as error:
        raise JobProtocolError("job_id must be a UUID v4.") from error
    if parsed.version != 4:
        raise JobProtocolError("job_id must be a UUID v4.")
    return job_id


def expected_frames(render: Mapping[str, object]) -> tuple[int, ...]:
    start = _require_non_negative_int(render.get("start"), "render.start")
    end = _require_non_negative_int(render.get("end"), "render.end")
    step = _require_non_negative_int(render.get("step"), "render.step")
    if step < 1 or end < start:
        raise JobProtocolError("render requires end >= start and step >= 1.")
    return tuple(range(start, end + 1, step))


def validate_job_document(document: object) -> dict[str, object]:
    """Validate the portable v1 job contract without a third-party validator."""
    job = _require_mapping(document, "job.json")
    _validate_protocol_version(job.get("protocol_version"))
    _validate_job_id(job.get("job_id"))
    _require_string(job.get("created_at"), "created_at")
    _require_string(job.get("addon_version"), "addon_version")
    project = _require_mapping(job.get("project"), "project")
    _require_string(project.get("display_name"), "project.display_name")
    _require_string(project.get("archive"), "project.archive")
    digest = _require_string(project.get("sha256"), "project.sha256")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest.lower()):
        raise JobProtocolError("project.sha256 must be a SHA-256 hex digest.")
    _require_non_negative_int(project.get("size_bytes"), "project.size_bytes")
    blender = _require_mapping(job.get("blender"), "blender")
    _require_string(blender.get("source_version"), "blender.source_version")
    _require_string(blender.get("requested_version"), "blender.requested_version")
    render = _require_mapping(job.get("render"), "render")
    if render.get("mode") not in {"saved_range", "single_frame"}:
        raise JobProtocolError("render.mode must be saved_range or single_frame.")
    expected_frames(render)
    if not isinstance(render.get("overwrite"), bool):
        raise JobProtocolError("render.overwrite must be a boolean.")
    if not isinstance(render.get("use_saved_settings"), bool):
        raise JobProtocolError("render.use_saved_settings must be a boolean.")
    if not isinstance(render.get("overrides"), dict):
        raise JobProtocolError("render.overrides must be an object.")
    destination = _require_mapping(job.get("destination"), "destination")
    if destination.get("mode") not in {"local", "manual_zip", "synced_folder"}:
        raise JobProtocolError("destination.mode is unsupported.")
    return job


def validate_status_document(document: object) -> dict[str, object]:
    status = _require_mapping(document, "status.json")
    _validate_protocol_version(status.get("protocol_version"))
    _validate_job_id(status.get("job_id"))
    revision = _require_non_negative_int(status.get("revision"), "revision")
    if revision < 1:
        raise JobProtocolError("revision must be at least 1.")
    try:
        JobState(status.get("state"))
    except (TypeError, ValueError) as error:
        raise JobProtocolError("state is unknown.") from error
    _require_string(status.get("updated_at"), "updated_at")
    _require_string(status.get("worker_version"), "worker_version")
    progress = _require_mapping(status.get("progress"), "progress")
    completed = _require_non_negative_int(progress.get("completed_frames"), "progress.completed_frames")
    total = _require_non_negative_int(progress.get("total_frames"), "progress.total_frames")
    if completed > total:
        raise JobProtocolError("progress.completed_frames cannot exceed progress.total_frames.")
    current = progress.get("current_frame")
    if current is not None:
        _require_non_negative_int(current, "progress.current_frame")
    _require_string(status.get("message"), "message")
    if status.get("error") is not None and not isinstance(status["error"], dict):
        raise JobProtocolError("error must be null or an object.")
    return status


def _safe_result_path(value: object) -> str:
    path = _require_string(value, "artifact.path")
    relative = PurePosixPath(path)
    if relative.is_absolute() or ".." in relative.parts or path.startswith("/"):
        raise ResultValidationError("artifact.path must be a safe relative result path.")
    return relative.as_posix()


def validate_result_manifest(document: object) -> dict[str, object]:
    manifest = _require_mapping(document, "result_manifest.json")
    _validate_protocol_version(manifest.get("protocol_version"))
    _validate_job_id(manifest.get("job_id"))
    _require_string(manifest.get("published_at"), "published_at")
    if manifest.get("state") not in {JobState.PARTIAL.value, JobState.COMPLETE.value}:
        raise ResultValidationError("result manifest state must be PARTIAL or COMPLETE.")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ResultValidationError("artifacts must be an array.")
    frames: set[int] = set()
    for artifact in artifacts:
        record = _require_mapping(artifact, "artifact")
        frame = _require_non_negative_int(record.get("frame"), "artifact.frame")
        if frame in frames:
            raise ResultValidationError(f"Duplicate result artifact for frame {frame}.")
        frames.add(frame)
        _safe_result_path(record.get("path"))
        digest = _require_string(record.get("sha256"), "artifact.sha256")
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest.lower()):
            raise ResultValidationError("artifact.sha256 must be a SHA-256 hex digest.")
        _require_non_negative_int(record.get("size_bytes"), "artifact.size_bytes")
    return manifest


def atomic_write_json(path: Path, document: Mapping[str, object]) -> None:
    """Publish JSON with replace semantics; readers never see partial JSON."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=destination.parent, prefix=f".{destination.name}.",
        suffix=".tmp", delete=False,
    ) as temporary:
        json.dump(document, temporary, ensure_ascii=False, indent=2, sort_keys=True)
        temporary.write("\n")
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    temporary_path.replace(destination)


def load_json(path: Path, description: str) -> dict[str, object]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise JobProtocolError(f"Could not read {description}: {error}") from error
    return _require_mapping(value, description)


@dataclass(frozen=True)
class FrameChunk:
    frames: tuple[int, ...]

    @property
    def start(self) -> int:
        return self.frames[0]

    @property
    def end(self) -> int:
        return self.frames[-1]


def plan_chunks(frames: Iterable[int], *, step: int, chunk_size: int) -> tuple[FrameChunk, ...]:
    """Split missing frames into contiguous, bounded render ranges.

    A completed frame creates a hard boundary: chunks never include it merely
    because Blender can render a wider numeric range.
    """
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size < 1:
        raise JobProtocolError("chunk_size must be a positive integer.")
    sequence = tuple(frames)
    if len(sequence) != len(set(sequence)) or tuple(sorted(sequence)) != sequence:
        raise JobProtocolError("frames must be sorted and unique.")
    groups: list[FrameChunk] = []
    current: list[int] = []
    for frame in sequence:
        if not current or (frame == current[-1] + step and len(current) < chunk_size):
            current.append(frame)
            continue
        groups.append(FrameChunk(tuple(current)))
        current = [frame]
    if current:
        groups.append(FrameChunk(tuple(current)))
    return tuple(groups)


@dataclass(frozen=True)
class JobPaths:
    root: Path

    @property
    def request_dir(self) -> Path:
        return self.root / "request"

    @property
    def worker_dir(self) -> Path:
        return self.root / "worker"

    @property
    def result_dir(self) -> Path:
        return self.root / "result"

    @property
    def job_path(self) -> Path:
        return self.request_dir / "job.json"

    @property
    def status_path(self) -> Path:
        return self.worker_dir / "status.json"

    @property
    def log_path(self) -> Path:
        return self.worker_dir / "render.log"

    @property
    def summary_path(self) -> Path:
        return self.worker_dir / "summary.json"

    @property
    def manifest_path(self) -> Path:
        return self.result_dir / "result_manifest.json"


class JobStore:
    """Atomic worker-side persistence for one immutable job request."""

    def __init__(self, root: Path) -> None:
        self.paths = JobPaths(Path(root))

    def create_job(self, document: Mapping[str, object]) -> dict[str, object]:
        job = validate_job_document(dict(document))
        if self.paths.job_path.exists():
            existing = validate_job_document(load_json(self.paths.job_path, "job.json"))
            if existing != job:
                raise JobProtocolError("job.json is immutable and already exists with different data.")
            return existing
        atomic_write_json(self.paths.job_path, job)
        return job

    def job(self) -> dict[str, object]:
        return validate_job_document(load_json(self.paths.job_path, "job.json"))

    def status(self) -> dict[str, object] | None:
        if not self.paths.status_path.exists():
            return None
        return validate_status_document(load_json(self.paths.status_path, "status.json"))

    def publish_status(
        self,
        state: JobState,
        *,
        completed_frames: int,
        total_frames: int,
        message: str,
        worker_version: str,
        current_frame: int | None = None,
        device: Mapping[str, object] | None = None,
        error: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        job = self.job()
        previous = self.status()
        if previous is not None:
            old_state = JobState(previous["state"])
            if state not in _TRANSITIONS[old_state]:
                raise JobStateError(f"Cannot transition from {old_state.value} to {state.value}.")
            revision = int(previous["revision"]) + 1
        else:
            if state is not JobState.PREFLIGHT:
                raise JobStateError("The first worker status must be PREFLIGHT.")
            revision = 1
        progress: dict[str, object] = {
            "completed_frames": completed_frames,
            "total_frames": total_frames,
            "current_frame": current_frame,
        }
        status: dict[str, object] = {
            "protocol_version": PROTOCOL_VERSION,
            "job_id": job["job_id"],
            "revision": revision,
            "state": state.value,
            "updated_at": utc_now(),
            "worker_version": worker_version,
            "progress": progress,
            "device": dict(device or {}),
            "message": message,
            "error": dict(error) if error is not None else None,
        }
        validate_status_document(status)
        atomic_write_json(self.paths.status_path, status)
        return status

    def append_log(self, message: str) -> None:
        self.paths.worker_dir.mkdir(parents=True, exist_ok=True)
        with self.paths.log_path.open("a", encoding="utf-8", newline="\n") as log:
            log.write(f"{utc_now()} {message}\n")
            log.flush()
            os.fsync(log.fileno())

    def publish_summary(
        self,
        *,
        state: JobState,
        verified_frames: int,
        total_frames: int,
        error: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """Publish the durable end-of-attempt summary referenced by the log."""
        job = self.job()
        summary: dict[str, object] = {
            "protocol_version": PROTOCOL_VERSION,
            "job_id": job["job_id"],
            "published_at": utc_now(),
            "state": state.value,
            "verified_frames": verified_frames,
            "total_frames": total_frames,
            "result_manifest": "../result/result_manifest.json",
            "error": dict(error) if error is not None else None,
        }
        atomic_write_json(self.paths.summary_path, summary)
        return summary

    def _manifest_or_empty(self) -> dict[str, object]:
        if not self.paths.manifest_path.exists():
            job = self.job()
            return {
                "protocol_version": PROTOCOL_VERSION,
                "job_id": job["job_id"],
                "published_at": utc_now(),
                "state": JobState.PARTIAL.value,
                "artifacts": [],
            }
        return validate_result_manifest(load_json(self.paths.manifest_path, "result_manifest.json"))

    def publish_frame(self, frame: int, source: Path, *, filename: str | None = None) -> dict[str, object]:
        """Atomically publish one rendered file and record its checksum later."""
        _require_non_negative_int(frame, "frame")
        source = Path(source)
        if not source.is_file():
            raise ResultValidationError(f"Rendered frame source does not exist: {source}")
        safe_name = filename or f"frame_{frame:06d}{source.suffix.lower()}"
        relative = _safe_result_path(f"frames/{safe_name}")
        target = self.paths.result_dir / Path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False) as temporary:
            temporary_path = Path(temporary.name)
        try:
            shutil.copyfile(source, temporary_path)
            digest = sha256_file(temporary_path)
            size = temporary_path.stat().st_size
            temporary_path.replace(target)
        finally:
            temporary_path.unlink(missing_ok=True)
        return {"frame": frame, "path": relative, "sha256": digest, "size_bytes": size}

    def publish_manifest(self, artifacts: Iterable[Mapping[str, object]], *, complete: bool) -> dict[str, object]:
        job = self.job()
        records = sorted((dict(artifact) for artifact in artifacts), key=lambda item: int(item["frame"]))
        manifest: dict[str, object] = {
            "protocol_version": PROTOCOL_VERSION,
            "job_id": job["job_id"],
            "published_at": utc_now(),
            "state": JobState.COMPLETE.value if complete else JobState.PARTIAL.value,
            "artifacts": records,
        }
        validate_result_manifest(manifest)
        atomic_write_json(self.paths.manifest_path, manifest)
        return manifest

    def valid_artifacts(self) -> dict[int, dict[str, object]]:
        manifest = self._manifest_or_empty()
        valid: dict[int, dict[str, object]] = {}
        for artifact in manifest["artifacts"]:
            record = dict(_require_mapping(artifact, "artifact"))
            target = self.paths.result_dir / Path(_safe_result_path(record["path"]))
            if not target.is_file() or target.stat().st_size != record["size_bytes"]:
                continue
            if sha256_file(target) != record["sha256"]:
                continue
            valid[int(record["frame"])] = record
        return valid


def make_job_document(
    *,
    project_name: str,
    project_path: Path,
    source_blender_version: str,
    requested_blender_version: str,
    start: int,
    end: int,
    step: int,
    mode: str = "saved_range",
    destination_mode: str = "local",
    addon_version: str = "notebook-0.1.0",
    job_id: str | None = None,
) -> dict[str, object]:
    """Create the immutable notebook-side request for an existing project file."""
    project_path = Path(project_path)
    document: dict[str, object] = {
        "protocol_version": PROTOCOL_VERSION,
        "job_id": job_id or new_job_id(),
        "created_at": utc_now(),
        "addon_version": addon_version,
        "project": {
            "display_name": project_name,
            # The protocol calls this input an archive.  In direct-upload mode
            # it is the already validated .blend file; later package modes use
            # the same field for project.zip without a protocol break.
            "archive": project_path.name,
            "sha256": sha256_file(project_path),
            "size_bytes": project_path.stat().st_size,
        },
        "blender": {
            "source_version": source_blender_version,
            "requested_version": requested_blender_version,
        },
        "render": {
            "mode": mode,
            "start": start,
            "end": end,
            "step": step,
            "overwrite": False,
            "use_saved_settings": True,
            "overrides": {},
        },
        "destination": {"mode": destination_mode},
    }
    return validate_job_document(document)


RenderChunk = Callable[[FrameChunk, Path], Mapping[int, Path]]


class ResumableJobRunner:
    """Run a deterministic render callback while persisting recoverable state."""

    def __init__(self, store: JobStore, *, worker_version: str, chunk_size: int) -> None:
        self.store = store
        self.worker_version = worker_version
        self.chunk_size = chunk_size

    def plan(self) -> tuple[tuple[int, ...], tuple[FrameChunk, ...], dict[int, dict[str, object]]]:
        job = self.store.job()
        render = _require_mapping(job["render"], "render")
        all_frames = expected_frames(render)
        valid = self.store.valid_artifacts()
        missing = tuple(frame for frame in all_frames if frame not in valid)
        return all_frames, plan_chunks(missing, step=int(render["step"]), chunk_size=self.chunk_size), valid

    def run(self, render_chunk: RenderChunk, *, device: Mapping[str, object] | None = None) -> dict[str, object]:
        all_frames, chunks, valid = self.plan()
        self.store.append_log(f"JOB_START total_frames={len(all_frames)} missing_frames={len(chunks and tuple(frame for chunk in chunks for frame in chunk.frames) or ())}")
        previous = self.store.status()
        if not chunks and previous is not None and previous["state"] == JobState.COMPLETE.value:
            self.store.append_log("JOB_COMPLETE reused_verified_frames=true")
            return self.store._manifest_or_empty()
        self.store.publish_status(
            JobState.PREFLIGHT,
            completed_frames=len(valid), total_frames=len(all_frames), message="Planning missing frames.",
            worker_version=self.worker_version, device=device,
        )
        if not chunks:
            manifest = self.store.publish_manifest(valid.values(), complete=True)
            self.store.publish_status(JobState.RENDERING, completed_frames=len(all_frames), total_frames=len(all_frames), message="Verified frames need no new render process.", worker_version=self.worker_version, device=device)
            self.store.publish_status(JobState.COMPLETE, completed_frames=len(all_frames), total_frames=len(all_frames), message="All frames already verified.", worker_version=self.worker_version, device=device)
            self.store.publish_summary(state=JobState.COMPLETE, verified_frames=len(all_frames), total_frames=len(all_frames))
            self.store.append_log("JOB_COMPLETE reused_verified_frames=true")
            return manifest
        try:
            for chunk in chunks:
                self.store.publish_status(JobState.RENDERING, completed_frames=len(valid), total_frames=len(all_frames), current_frame=chunk.start, message=f"Rendering frames {chunk.start}-{chunk.end}.", worker_version=self.worker_version, device=device)
                self.store.append_log(f"CHUNK_START frames={','.join(map(str, chunk.frames))}")
                staging = self.store.paths.root / ".staging" / f"{chunk.start}-{chunk.end}"
                staging.mkdir(parents=True, exist_ok=True)
                rendered = dict(render_chunk(chunk, staging))
                if set(rendered) != set(chunk.frames):
                    raise ResultValidationError("Renderer did not return exactly the requested chunk frames.")
                for frame in chunk.frames:
                    valid[frame] = self.store.publish_frame(frame, rendered[frame])
                self.store.publish_manifest(valid.values(), complete=False)
                self.store.append_log(f"CHUNK_COMPLETE frames={','.join(map(str, chunk.frames))}")
            manifest = self.store.publish_manifest(valid.values(), complete=True)
            self.store.publish_status(JobState.COMPLETE, completed_frames=len(all_frames), total_frames=len(all_frames), message="All frames rendered and checksum-verified.", worker_version=self.worker_version, device=device)
            self.store.publish_summary(state=JobState.COMPLETE, verified_frames=len(all_frames), total_frames=len(all_frames))
            self.store.append_log("JOB_COMPLETE reused_verified_frames=false")
            return manifest
        except KeyboardInterrupt:
            self.store.publish_manifest(valid.values(), complete=False)
            self.store.publish_status(JobState.PARTIAL, completed_frames=len(valid), total_frames=len(all_frames), message="Render interrupted; verified frames can be resumed.", worker_version=self.worker_version, device=device)
            self.store.publish_summary(state=JobState.PARTIAL, verified_frames=len(valid), total_frames=len(all_frames), error={"type": "KeyboardInterrupt", "message": "Render interrupted."})
            self.store.append_log("JOB_PARTIAL reason=interrupted")
            raise
        except Exception as error:
            self.store.publish_manifest(valid.values(), complete=False)
            self.store.publish_status(JobState.FAILED, completed_frames=len(valid), total_frames=len(all_frames), message="Render failed; verified frames are retained.", worker_version=self.worker_version, device=device, error={"type": type(error).__name__, "message": str(error)})
            self.store.publish_summary(state=JobState.FAILED, verified_frames=len(valid), total_frames=len(all_frames), error={"type": type(error).__name__, "message": str(error)})
            self.store.append_log(f"JOB_FAILED type={type(error).__name__} message={error}")
            raise
