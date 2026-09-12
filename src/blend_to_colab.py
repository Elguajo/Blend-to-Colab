"""Safe, testable helpers embedded by the self-contained Colab notebook.

This module intentionally depends only on the Python standard library so it can
also run in a newly created Google Colab runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
import tempfile
from typing import Callable
from urllib.request import Request, urlopen
import zipfile


OFFICIAL_BLENDER_RELEASE_BASE_URL = "https://download.blender.org/release"
OFFICIAL_DOWNLOAD_USER_AGENT = "Blender-to-GoogleColab/phase-1"
CUSTOM_VERSION_PRESET = "custom"
LTS_VERSION_PRESETS = ("5.2.1", "4.5.13")
DEFAULT_BLENDER_VERSION = LTS_VERSION_PRESETS[0]
_VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class ConfigError(ValueError):
    """A notebook value is unsupported or unsafe."""


class ArchiveSafetyError(ValueError):
    """A ZIP archive cannot be safely extracted."""


class BlenderDownloadError(RuntimeError):
    """An official Blender archive or its checksum could not be verified."""


class BlenderCacheError(BlenderDownloadError):
    """A Blender archive cache entry is malformed or cannot be trusted."""


class BlenderProbeError(RuntimeError):
    """A Blender preflight report is missing, malformed, or unsafe to trust."""


class SourceBlendChangedError(BlenderProbeError):
    """A read-only operation changed the source ``.blend`` file."""


class RenderMode(str, Enum):
    STILL = "STILL"
    ANIMATION = "ANIMATION"


def validate_blender_version(version: str) -> str:
    """Return a normalized Blender release version accepted by official URLs."""
    if not isinstance(version, str):
        raise ConfigError("Blender version must be a string in X.Y.Z format.")
    normalized = version.strip()
    if not _VERSION_RE.fullmatch(normalized):
        raise ConfigError(
            "Blender version must use the exact X.Y.Z format, for example 5.2.1."
        )
    return normalized


def resolve_blender_version(preset: str, custom_version: str) -> str:
    """Resolve an LTS preset or an explicit custom version without ambiguity."""
    if not isinstance(preset, str) or not isinstance(custom_version, str):
        raise ConfigError("Blender version preset and custom version must be strings.")
    normalized_preset = preset.strip()
    if normalized_preset == CUSTOM_VERSION_PRESET:
        if not custom_version.strip():
            raise ConfigError("Set CUSTOM_BLENDER_VERSION when BLENDER_VERSION_PRESET is custom.")
        return validate_blender_version(custom_version)
    if normalized_preset not in LTS_VERSION_PRESETS:
        raise ConfigError(
            "BLENDER_VERSION_PRESET must be one of the documented LTS presets or custom."
        )
    if custom_version.strip():
        raise ConfigError(
            "CUSTOM_BLENDER_VERSION is only allowed when BLENDER_VERSION_PRESET is custom."
        )
    return normalized_preset


@dataclass(frozen=True)
class RenderConfig:
    """Validated values accepted from the notebook's configuration cell."""

    blender_version: str
    enable_cycles_gpu: bool
    allow_cpu_fallback: bool
    include_cpu_with_gpu: bool
    render_mode: RenderMode
    still_frame: int
    download_result: bool
    run_cycles_smoke_test: bool
    run_preflight_test_frame: bool
    enable_drive_blender_cache: bool

    @classmethod
    def from_user_values(
        cls,
        *,
        blender_version_preset: str,
        custom_blender_version: str,
        enable_cycles_gpu: bool,
        allow_cpu_fallback: bool,
        include_cpu_with_gpu: bool,
        render_mode: str,
        still_frame: int,
        download_result: bool,
        run_cycles_smoke_test: bool,
        run_preflight_test_frame: bool,
        enable_drive_blender_cache: bool = False,
    ) -> "RenderConfig":
        boolean_values = {
            "ENABLE_CYCLES_GPU": enable_cycles_gpu,
            "ALLOW_CPU_FALLBACK": allow_cpu_fallback,
            "INCLUDE_CPU_WITH_GPU": include_cpu_with_gpu,
            "DOWNLOAD_RESULT": download_result,
            "RUN_CYCLES_SMOKE_TEST": run_cycles_smoke_test,
            "RUN_PREFLIGHT_TEST_FRAME": run_preflight_test_frame,
            "ENABLE_DRIVE_BLENDER_CACHE": enable_drive_blender_cache,
        }
        for name, value in boolean_values.items():
            if not isinstance(value, bool):
                raise ConfigError(f"{name} must be True or False.")
        if isinstance(still_frame, bool) or not isinstance(still_frame, int) or still_frame < 0:
            raise ConfigError("STILL_FRAME must be a non-negative integer.")
        try:
            normalized_render_mode = RenderMode(render_mode.strip().upper())
        except (AttributeError, ValueError) as error:
            raise ConfigError("RENDER_MODE must be STILL or ANIMATION.") from error
        if include_cpu_with_gpu and not enable_cycles_gpu:
            raise ConfigError("INCLUDE_CPU_WITH_GPU requires ENABLE_CYCLES_GPU=True.")
        return cls(
            blender_version=resolve_blender_version(
                blender_version_preset, custom_blender_version
            ),
            enable_cycles_gpu=enable_cycles_gpu,
            allow_cpu_fallback=allow_cpu_fallback,
            include_cpu_with_gpu=include_cpu_with_gpu,
            render_mode=normalized_render_mode,
            still_frame=still_frame,
            download_result=download_result,
            run_cycles_smoke_test=run_cycles_smoke_test,
            run_preflight_test_frame=run_preflight_test_frame,
            enable_drive_blender_cache=enable_drive_blender_cache,
        )


@dataclass(frozen=True)
class BlenderRelease:
    version: str
    archive_name: str
    archive_url: str
    checksum_url: str


@dataclass(frozen=True)
class BlenderArchiveAcquisition:
    """A verified local archive and the cache outcome used to obtain it."""

    archive_path: Path
    cache_status: str


def official_blender_release(version: str) -> BlenderRelease:
    """Build URLs only for official Linux x64 Blender release artifacts."""
    normalized_version = validate_blender_version(version)
    major, minor, _patch = normalized_version.split(".")
    series = f"{major}.{minor}"
    archive_name = f"blender-{normalized_version}-linux-x64.tar.xz"
    release_url = f"{OFFICIAL_BLENDER_RELEASE_BASE_URL}/Blender{series}"
    return BlenderRelease(
        version=normalized_version,
        archive_name=archive_name,
        archive_url=f"{release_url}/{archive_name}",
        checksum_url=f"{release_url}/blender-{normalized_version}.sha256",
    )


def _assert_official_blender_release(release: BlenderRelease) -> None:
    """Reject descriptors that could redirect an installer to a third-party URL."""
    if release != official_blender_release(release.version):
        raise BlenderDownloadError(
            "Blender archive URLs must come from download.blender.org."
        )


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


PROBE_REPORT_VERSION = 1
_PROBE_REQUIRED_KEYS = frozenset(
    {
        "report_version",
        "source_file",
        "blender",
        "scenes",
        "assets",
        "issues",
        "environment",
    }
)


def build_blender_probe_command(
    blender_binary: Path, blend_file: Path, probe_script: Path, report_path: Path
) -> tuple[str, ...]:
    """Build a shell-free, non-autoexecuting Blender preflight invocation.

    The report path is deliberately passed after Blender's ``--`` separator, so
    a user-controlled path never becomes a Blender command-line option.
    """
    return (
        str(Path(blender_binary)),
        "--background",
        "--factory-startup",
        "--disable-autoexec",
        str(Path(blend_file)),
        "--python",
        str(Path(probe_script)),
        "--",
        str(Path(report_path)),
    )


def assert_source_blend_unchanged(blend_file: Path, expected_sha256: str) -> None:
    """Raise if a supposedly read-only Blender operation changed its input."""
    actual_sha256 = sha256_file(Path(blend_file))
    if actual_sha256 != expected_sha256:
        raise SourceBlendChangedError(
            "Blender preflight changed the source .blend file; rendering is blocked."
        )


def load_probe_report(report_path: Path) -> dict[str, object]:
    """Load the minimum machine-readable contract produced by the Blender probe."""
    try:
        loaded = json.loads(Path(report_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BlenderProbeError(f"Could not read Blender preflight report: {error}") from error
    if not isinstance(loaded, dict):
        raise BlenderProbeError("Blender preflight report must be a JSON object.")
    missing = _PROBE_REQUIRED_KEYS.difference(loaded)
    if missing:
        raise BlenderProbeError(
            "Blender preflight report is missing required fields: "
            + ", ".join(sorted(missing))
        )
    if loaded["report_version"] != PROBE_REPORT_VERSION:
        raise BlenderProbeError(
            f"Unsupported Blender preflight report version: {loaded['report_version']!r}."
        )
    return loaded


@dataclass(frozen=True)
class TestFrameEstimate:
    """A transparent linear estimate derived from one rendered test frame."""

    frame_count: int
    test_frame_seconds: float
    test_frame_output_bytes: int
    estimated_render_seconds: float
    estimated_output_bytes: int


def estimate_from_test_frame(
    *, frame_count: int, test_frame_seconds: float, test_frame_output_bytes: int
) -> TestFrameEstimate:
    """Scale one test-frame measurement to the saved animation range.

    This is intentionally an estimate, not a promise: later frames may have
    different render complexity and Blender start-up time is included.
    """
    if isinstance(frame_count, bool) or not isinstance(frame_count, int) or frame_count < 1:
        raise ConfigError("frame_count must be a positive integer.")
    if test_frame_seconds < 0:
        raise ConfigError("test_frame_seconds must be non-negative.")
    if (
        isinstance(test_frame_output_bytes, bool)
        or not isinstance(test_frame_output_bytes, int)
        or test_frame_output_bytes < 0
    ):
        raise ConfigError("test_frame_output_bytes must be a non-negative integer.")
    return TestFrameEstimate(
        frame_count=frame_count,
        test_frame_seconds=test_frame_seconds,
        test_frame_output_bytes=test_frame_output_bytes,
        estimated_render_seconds=test_frame_seconds * frame_count,
        estimated_output_bytes=test_frame_output_bytes * frame_count,
    )


# This script is embedded in the self-contained notebook.  Keep it free of
# ``bpy.ops`` calls: the probe must inspect an already-loaded source file and
# never save it or alter its scene data.
BLENDER_PREFLIGHT_SCRIPT = r'''import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import bpy

REPORT_VERSION = 1
SUPPORTED_RENDER_ENGINES = {
    "BLENDER_EEVEE",
    "BLENDER_EEVEE_NEXT",
    "BLENDER_WORKBENCH",
    "CYCLES",
}
BUILTIN_ADDONS = {"cycles"}


def issue(report, severity, code, message, **details):
    entry = {"code": code, "message": message}
    if details:
        entry["details"] = details
    report["issues"][severity].append(entry)


def absolute_path(filepath, library=None):
    if not filepath:
        return ""
    try:
        return bpy.path.abspath(filepath, library=library)
    except TypeError:
        return bpy.path.abspath(filepath)


def add_asset(report, kind, name, filepath, *, library=None, packed=False):
    if packed:
        report["assets"].append(
            {"kind": kind, "name": name, "status": "packed_in_blend", "path": None}
        )
        return
    resolved_path = absolute_path(filepath, library)
    if not resolved_path:
        report["assets"].append(
            {"kind": kind, "name": name, "status": "not_applicable", "path": None}
        )
        return
    exists = os.path.exists(resolved_path)
    record = {
        "kind": kind,
        "name": name,
        "status": "available" if exists else "missing",
        "path": resolved_path,
    }
    report["assets"].append(record)
    if not exists:
        issue(
            report,
            "errors",
            "missing_asset",
            f"Missing {kind}: {name}",
            path=resolved_path,
        )


def collect_assets(report):
    for image in bpy.data.images:
        if image.source in {"GENERATED", "VIEWER"}:
            continue
        packed = bool(getattr(image, "packed_file", None)) or bool(
            getattr(image, "packed_files", ())
        )
        add_asset(
            report,
            "image",
            image.name,
            image.filepath,
            library=image.library,
            packed=packed,
        )
    for library in bpy.data.libraries:
        add_asset(report, "linked_library", library.name, library.filepath)
    for font in bpy.data.fonts:
        add_asset(report, "font", font.name, font.filepath, library=font.library)
    for volume in bpy.data.volumes:
        add_asset(report, "vdb", volume.name, volume.filepath, library=volume.library)
    for cache_file in bpy.data.cache_files:
        add_asset(report, "cache", cache_file.name, cache_file.filepath)
    for clip in bpy.data.movieclips:
        add_asset(report, "movie_clip", clip.name, clip.filepath, library=clip.library)
    for sound in bpy.data.sounds:
        add_asset(report, "sound", sound.name, sound.filepath, library=sound.library)
    for obj in bpy.data.objects:
        for modifier in obj.modifiers:
            if modifier.type != "FLUID":
                continue
            domain = getattr(modifier, "domain_settings", None)
            cache_directory = getattr(domain, "cache_directory", "")
            if cache_directory:
                add_asset(
                    report,
                    "fluid_cache",
                    f"{obj.name}/{modifier.name}",
                    cache_directory,
                    library=obj.library,
                )


def scene_record(scene):
    render = scene.render
    image_settings = render.image_settings
    return {
        "name": scene.name,
        "camera": scene.camera.name if scene.camera else None,
        "render_engine": render.engine,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_step": scene.frame_step,
        "fps": render.fps / render.fps_base,
        "resolution": {
            "x": render.resolution_x,
            "y": render.resolution_y,
            "percentage": render.resolution_percentage,
        },
        "output": {
            "filepath": absolute_path(render.filepath),
            "file_format": image_settings.file_format,
            "color_mode": image_settings.color_mode,
            "film_transparent": render.film_transparent,
        },
    }


def collect_scenes(report):
    for scene in bpy.data.scenes:
        record = scene_record(scene)
        report["scenes"].append(record)
        if not record["camera"]:
            issue(report, "errors", "missing_camera", f"Scene {scene.name!r} has no active camera.")
        if record["render_engine"] not in SUPPORTED_RENDER_ENGINES:
            issue(
                report,
                "errors",
                "unsupported_render_engine",
                f"Scene {scene.name!r} uses unsupported render engine {record['render_engine']!r}.",
            )
        if record["frame_end"] < record["frame_start"] or record["frame_step"] < 1:
            issue(report, "errors", "invalid_frame_range", f"Scene {scene.name!r} has an invalid frame range.")


def collect_cycles_devices():
    addon = bpy.context.preferences.addons.get("cycles")
    if addon is None:
        return {"available": False, "devices": []}
    preferences = addon.preferences
    try:
        refresh = getattr(preferences, "refresh_devices", None)
        if refresh is not None:
            refresh()
        else:
            preferences.get_devices()
        devices = [
            {"name": device.name, "type": str(device.type), "enabled": bool(device.use)}
            for device in preferences.devices
        ]
        return {"available": True, "devices": devices}
    except Exception as error:
        return {"available": True, "devices": [], "error": str(error)}


def collect_gpu_info():
    command = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.free",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as error:
        return {"available": False, "devices": [], "error": str(error)}
    if result.returncode:
        return {"available": False, "devices": [], "error": result.stderr.strip()}
    devices = []
    for line in result.stdout.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) == 3:
            devices.append({"name": fields[0], "vram_total_mib": fields[1], "vram_free_mib": fields[2]})
    return {"available": bool(devices), "devices": devices}


def collect_environment(report_path):
    try:
        ram_total_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, ValueError, OSError):
        ram_total_bytes = None
    disk = shutil.disk_usage(report_path.parent)
    system_root = Path(bpy.app.binary_path).resolve().parent
    enabled_addons = []
    for addon in bpy.context.preferences.addons:
        if addon.module in BUILTIN_ADDONS:
            continue
        module = sys.modules.get(addon.module)
        module_path = getattr(module, "__file__", None)
        if not module_path:
            continue
        try:
            Path(module_path).resolve().relative_to(system_root)
            continue
        except ValueError:
            pass
        enabled_addons.append(addon.module)
    return {
        "ram_total_bytes": ram_total_bytes,
        "disk_total_bytes": disk.total,
        "disk_free_bytes": disk.free,
        "gpu": collect_gpu_info(),
        "cycles_device_discovery": collect_cycles_devices(),
        "enabled_external_addons": sorted(enabled_addons),
    }


def empty_report():
    scenes = tuple(bpy.data.scenes)
    context_scene_name = getattr(getattr(bpy.context, "scene", None), "name", "")
    scene_names = {scene.name for scene in scenes}
    active_scene_name = (
        context_scene_name if context_scene_name in scene_names else scenes[0].name
    )
    return {
        "report_version": REPORT_VERSION,
        "source_file": bpy.data.filepath,
        "blender": {"version": bpy.app.version_string, "version_file": list(bpy.data.version)},
        "active_scene": active_scene_name,
        "scenes": [],
        "assets": [],
        "issues": {"errors": [], "warnings": []},
        "environment": {},
    }


def build_report(report_path):
    report = empty_report()
    collect_scenes(report)
    collect_assets(report)
    report["environment"] = collect_environment(report_path)
    external_addons = report["environment"]["enabled_external_addons"]
    if external_addons:
        issue(
            report,
            "warnings",
            "external_addons_enabled",
            "Enabled add-ons may be unavailable in a stock Colab Blender installation.",
            modules=external_addons,
        )
    return report


def report_path_from_arguments():
    try:
        separator = sys.argv.index("--")
        return Path(sys.argv[separator + 1])
    except (ValueError, IndexError) as error:
        raise RuntimeError("Expected a preflight report path after --.") from error


report_path = report_path_from_arguments()
try:
    report = build_report(report_path)
except Exception as error:
    report = empty_report()
    issue(report, "errors", "probe_failure", str(error))
report_path.parent.mkdir(parents=True, exist_ok=True)
temporary_path = report_path.with_suffix(report_path.suffix + ".tmp")
temporary_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
temporary_path.replace(report_path)
print(f"BLENDER_PREFLIGHT_REPORT={report_path}")
'''


def checksum_from_manifest(manifest: str, archive_name: str) -> str:
    """Find an archive checksum in Blender's official ``.sha256`` manifest."""
    for line in manifest.splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) != 2:
            continue
        digest, listed_name = fields
        listed_name = listed_name.lstrip("*")
        if listed_name == archive_name and re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            return digest.lower()
    raise BlenderDownloadError(
        f"Official checksum manifest does not contain {archive_name!r}."
    )


def official_blender_checksum(
    release: BlenderRelease, *, opener: Callable[..., object] = urlopen
) -> str:
    """Fetch the expected SHA-256 only from Blender's official manifest."""
    _assert_official_blender_release(release)
    request = Request(
        release.checksum_url, headers={"User-Agent": OFFICIAL_DOWNLOAD_USER_AGENT}
    )
    try:
        with opener(request) as response:
            manifest = response.read().decode("utf-8")
        return checksum_from_manifest(manifest, release.archive_name)
    except BlenderDownloadError:
        raise
    except Exception as error:
        raise BlenderDownloadError(
            f"Could not download the official Blender checksum manifest: {error}"
        ) from error


def _atomic_copy_verified_archive(
    source: Path, destination: Path, expected_digest: str
) -> Path:
    """Copy a verified archive using a same-directory temporary file and replace."""
    source = Path(source)
    destination = Path(destination)
    if not source.is_file():
        raise BlenderCacheError(f"Blender archive does not exist: {source}")
    if sha256_file(source) != expected_digest:
        raise BlenderCacheError("Blender archive SHA-256 does not match the official manifest.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        shutil.copyfile(source, temporary_path)
        if sha256_file(temporary_path) != expected_digest:
            raise BlenderCacheError("Blender archive changed while it was being copied.")
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    return destination


def download_verified_blender_archive(
    release: BlenderRelease,
    destination: Path,
    *,
    opener: Callable[..., object] = urlopen,
    expected_digest: str | None = None,
) -> Path:
    """Download an official Blender archive and atomically retain it after SHA-256 verification."""
    _assert_official_blender_release(release)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    def open_official_url(url: str) -> object:
        return opener(Request(url, headers={"User-Agent": OFFICIAL_DOWNLOAD_USER_AGENT}))

    try:
        expected_digest = expected_digest or official_blender_checksum(release, opener=opener)
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=f".{destination.name}.", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            with open_official_url(release.archive_url) as response:
                shutil.copyfileobj(response, temporary)
        actual_digest = sha256_file(temporary_path)
        if actual_digest != expected_digest:
            temporary_path.unlink(missing_ok=True)
            raise BlenderDownloadError(
                "Downloaded Blender archive failed SHA-256 verification; it was discarded."
            )
        temporary_path.replace(destination)
        return destination
    except BlenderDownloadError:
        raise
    except Exception as error:
        raise BlenderDownloadError(f"Could not download verified Blender archive: {error}") from error


def acquire_verified_blender_archive(
    release: BlenderRelease,
    destination: Path,
    *,
    cache_path: Path | None = None,
    opener: Callable[..., object] = urlopen,
) -> BlenderArchiveAcquisition:
    """Acquire a locally staged Blender archive from an opt-in verified cache.

    A cache is only an optimization: its content is checked against a newly
    fetched official SHA-256 manifest on every use.  A miss or mismatch falls
    back to ``download.blender.org`` and only a verified local archive is
    atomically copied back into the cache.
    """
    _assert_official_blender_release(release)
    destination = Path(destination)
    expected_digest = official_blender_checksum(release, opener=opener)
    if cache_path is not None:
        cache_path = Path(cache_path)
        if not cache_path.exists():
            cache_status = "miss"
        else:
            try:
                _atomic_copy_verified_archive(cache_path, destination, expected_digest)
                return BlenderArchiveAcquisition(destination, "hit")
            except (BlenderCacheError, OSError):
                cache_status = "corrupt"
    else:
        cache_status = "disabled"

    download_verified_blender_archive(
        release, destination, opener=opener, expected_digest=expected_digest
    )
    if cache_path is not None:
        try:
            _atomic_copy_verified_archive(destination, Path(cache_path), expected_digest)
        except (BlenderCacheError, OSError):
            cache_status = "write_failed"
    return BlenderArchiveAcquisition(destination, cache_status)


@dataclass(frozen=True)
class ArchiveSafetyLimits:
    max_entries: int = 10_000
    max_uncompressed_bytes: int = 25 * 1024**3
    max_compression_ratio: float = 100.0

    def __post_init__(self) -> None:
        if self.max_entries < 1 or self.max_uncompressed_bytes < 1:
            raise ValueError("Archive limits must be positive.")
        if self.max_compression_ratio < 1:
            raise ValueError("max_compression_ratio must be at least 1.")


def _validate_archive_member(info: zipfile.ZipInfo) -> None:
    name = info.filename
    if not name or "\x00" in name:
        raise ArchiveSafetyError("ZIP contains an empty or NUL-containing entry name.")
    posix_path = PurePosixPath(name)
    windows_path = PureWindowsPath(name)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ArchiveSafetyError(f"ZIP contains an absolute path: {name!r}")
    if any(part == ".." for part in posix_path.parts):
        raise ArchiveSafetyError(f"ZIP contains a path traversal entry: {name!r}")
    mode = info.external_attr >> 16
    file_type = stat.S_IFMT(mode)
    if file_type and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
        raise ArchiveSafetyError(f"ZIP contains a non-regular entry: {name!r}")


def inspect_zip_archive(
    archive_path: Path, destination: Path, limits: ArchiveSafetyLimits = ArchiveSafetyLimits()
) -> tuple[zipfile.ZipInfo, ...]:
    """Validate ZIP members and ensure enough free space before extracting anything."""
    archive_path = Path(archive_path)
    destination = Path(destination)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = tuple(archive.infolist())
    except (OSError, zipfile.BadZipFile) as error:
        raise ArchiveSafetyError(f"Invalid ZIP archive: {error}") from error
    if len(infos) > limits.max_entries:
        raise ArchiveSafetyError(
            f"ZIP has {len(infos)} entries; the limit is {limits.max_entries}."
        )
    total_uncompressed = 0
    for info in infos:
        _validate_archive_member(info)
        if info.is_dir():
            continue
        if info.file_size and info.compress_size == 0:
            raise ArchiveSafetyError(f"ZIP entry has an invalid compression size: {info.filename!r}")
        compression_ratio = info.file_size / max(info.compress_size, 1)
        if compression_ratio > limits.max_compression_ratio:
            raise ArchiveSafetyError(
                f"ZIP entry exceeds the compression-ratio limit: {info.filename!r}"
            )
        total_uncompressed += info.file_size
        if total_uncompressed > limits.max_uncompressed_bytes:
            raise ArchiveSafetyError(
                "ZIP uncompressed size exceeds the configured safety limit."
            )
    destination.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ArchiveSafetyError("ZIP destination must not be a symbolic link.")
    free_bytes = shutil.disk_usage(destination).free
    if total_uncompressed > free_bytes:
        raise ArchiveSafetyError(
            "Insufficient free disk space to extract the ZIP archive safely."
        )
    return infos


def safe_extract_zip(
    archive_path: Path, destination: Path, limits: ArchiveSafetyLimits = ArchiveSafetyLimits()
) -> tuple[Path, ...]:
    """Extract a previously untrusted ZIP without ``extractall`` or path traversal."""
    destination = Path(destination)
    infos = inspect_zip_archive(archive_path, destination, limits)
    destination_root = destination.resolve()
    extracted: list[Path] = []
    with zipfile.ZipFile(archive_path) as archive:
        for info in infos:
            relative_path = PurePosixPath(info.filename)
            target = destination_root.joinpath(*relative_path.parts)
            try:
                target.resolve().relative_to(destination_root)
            except ValueError as error:
                raise ArchiveSafetyError(
                    f"ZIP entry escapes its destination: {info.filename!r}"
                ) from error
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            extracted.append(target)
    return tuple(extracted)
