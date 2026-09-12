"""Validation helpers shared by the notebook's project-source cell."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit


MAX_PROJECT_FILE_BYTES = 25 * 1024**3
PROJECT_SOURCE_MODES = ("upload", "drive_file", "drive_folder", "url")
BLEND_CONTAINER_MAGICS = (
    b"BLENDER",  # Uncompressed blend-file.
    b"\x28\xb5\x2f\xfd",  # Zstandard, used by Blender 3.0 and later.
    b"\x1f\x8b",  # Gzip, used by earlier compressed blend-files.
)


class ProjectInputError(ValueError):
    """A project source is unsafe, malformed, or ambiguous."""


def validate_project_source_mode(value: str) -> str:
    if not isinstance(value, str) or value not in PROJECT_SOURCE_MODES:
        raise ProjectInputError(f"PROJECT_SOURCE must be one of {PROJECT_SOURCE_MODES}.")
    return value


def validate_https_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectInputError("PROJECT_URL must be a non-empty HTTPS URL.")
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ProjectInputError("PROJECT_URL must be an HTTPS URL without embedded credentials.")
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise ProjectInputError("PROJECT_URL must not contain control characters or whitespace.")
    return value.strip()


def validate_project_relative_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise ProjectInputError("SELECTED_BLEND_PATH must be a project-relative path.")
    candidate = PurePosixPath(value.replace("\\", "/"))
    windows_candidate = PureWindowsPath(value)
    if candidate.is_absolute() or windows_candidate.is_absolute() or windows_candidate.drive or ".." in candidate.parts:
        raise ProjectInputError("SELECTED_BLEND_PATH must stay inside the staged project.")
    if candidate.name in {"", "."}:
        raise ProjectInputError("SELECTED_BLEND_PATH must name a .blend file.")
    return candidate


def resolve_path_under(root: Path, relative_path: str, *, field_name: str) -> Path:
    """Resolve a user-supplied relative path without allowing an escape from root."""
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ProjectInputError(f"{field_name} must be a non-empty path inside its root.")
    windows_path = PureWindowsPath(relative_path)
    if windows_path.is_absolute() or windows_path.drive:
        raise ProjectInputError(f"{field_name} must stay inside its root.")
    base = Path(root).resolve()
    candidate = (base / relative_path.strip()).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as error:
        raise ProjectInputError(f"{field_name} must stay inside its root.") from error
    return candidate


def validate_blend_file(path: Path, *, max_bytes: int = MAX_PROJECT_FILE_BYTES) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise ProjectInputError("Project .blend must be a regular file.")
    if candidate.suffix.lower() != ".blend":
        raise ProjectInputError("Project source must be a .blend file or a ZIP project.")
    size = candidate.stat().st_size
    if not 12 <= size <= max_bytes:
        raise ProjectInputError("Project .blend size is outside the allowed limit.")
    with candidate.open("rb") as source:
        container_magic = source.read(7)
        if not any(container_magic.startswith(magic) for magic in BLEND_CONTAINER_MAGICS):
            raise ProjectInputError("Project .blend does not have a supported Blender container header.")
    return candidate


def select_blend_file(project_root: Path, selected_path: str = "") -> Path:
    root = Path(project_root).resolve()
    candidates = tuple(sorted(path for path in root.rglob("*.blend") if path.is_file() and not path.is_symlink()))
    if len(candidates) == 1 and not selected_path.strip():
        return candidates[0]
    if not selected_path.strip():
        choices = ", ".join(path.relative_to(root).as_posix() for path in candidates) or "none"
        raise ProjectInputError(f"Found {len(candidates)} .blend files; set SELECTED_BLEND_PATH explicitly: {choices}")
    relative = validate_project_relative_path(selected_path)
    candidate = root.joinpath(*relative.parts).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ProjectInputError("SELECTED_BLEND_PATH must stay inside the staged project.") from error
    if candidate not in candidates:
        raise ProjectInputError("SELECTED_BLEND_PATH does not name a staged .blend file.")
    return candidate
