import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from src.blend_to_colab import (
    BlenderRelease,
    BlenderDownloadError,
    OFFICIAL_DOWNLOAD_USER_AGENT,
    acquire_verified_blender_archive,
    checksum_from_manifest,
    download_verified_blender_archive,
    official_blender_release,
)


class BlenderVersioningTests(unittest.TestCase):
    def test_official_urls_use_release_series_and_checksum_manifest(self) -> None:
        release = official_blender_release("5.2.1")

        self.assertEqual(release.archive_name, "blender-5.2.1-linux-x64.tar.xz")
        self.assertEqual(
            release.archive_url,
            "https://download.blender.org/release/Blender5.2/blender-5.2.1-linux-x64.tar.xz",
        )
        self.assertEqual(
            release.checksum_url,
            "https://download.blender.org/release/Blender5.2/blender-5.2.1.sha256",
        )

    def test_checksum_manifest_selects_exact_archive(self) -> None:
        digest = hashlib.sha256(b"archive").hexdigest()
        manifest = f"{digest}  blender-5.2.1-linux-x64.tar.xz\n"

        self.assertEqual(
            checksum_from_manifest(manifest, "blender-5.2.1-linux-x64.tar.xz"), digest
        )
        with self.assertRaises(BlenderDownloadError):
            checksum_from_manifest(manifest, "blender-5.2.1-linux-arm64.tar.xz")

    def test_verified_download_keeps_only_matching_archive(self) -> None:
        release = official_blender_release("5.2.1")
        archive_bytes = b"verified Blender archive fixture"
        digest = hashlib.sha256(archive_bytes).hexdigest()
        manifest = f"{digest}  {release.archive_name}\n".encode()

        opened_requests = []

        def opener(request) -> io.BytesIO:
            opened_requests.append(request)
            return io.BytesIO(
                manifest if request.full_url == release.checksum_url else archive_bytes
            )

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / release.archive_name
            self.assertEqual(
                download_verified_blender_archive(release, destination, opener=opener),
                destination,
            )
            self.assertEqual(destination.read_bytes(), archive_bytes)
        self.assertEqual(
            [request.get_header("User-agent") for request in opened_requests],
            [OFFICIAL_DOWNLOAD_USER_AGENT, OFFICIAL_DOWNLOAD_USER_AGENT],
        )

    def test_failed_checksum_does_not_leave_archive(self) -> None:
        release = official_blender_release("5.2.1")
        manifest = f"{'0' * 64}  {release.archive_name}\n".encode()

        def opener(request) -> io.BytesIO:
            return io.BytesIO(
                manifest if request.full_url == release.checksum_url else b"wrong data"
            )

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / release.archive_name
            with self.assertRaises(BlenderDownloadError):
                download_verified_blender_archive(release, destination, opener=opener)
            self.assertFalse(destination.exists())

    def test_verified_cache_hit_is_rechecked_against_official_checksum(self) -> None:
        release = official_blender_release("5.2.1")
        archive_bytes = b"verified cached Blender archive"
        manifest = (
            f"{hashlib.sha256(archive_bytes).hexdigest()}  {release.archive_name}\n"
        ).encode()
        opened_requests = []

        def opener(request) -> io.BytesIO:
            opened_requests.append(request.full_url)
            return io.BytesIO(manifest)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_path = root / "drive-cache" / release.archive_name
            cache_path.parent.mkdir()
            cache_path.write_bytes(archive_bytes)
            acquired = acquire_verified_blender_archive(
                release, root / "content" / release.archive_name,
                cache_path=cache_path, opener=opener,
            )

            self.assertEqual(acquired.cache_status, "hit")
            self.assertEqual(acquired.archive_path.read_bytes(), archive_bytes)
            self.assertEqual(opened_requests, [release.checksum_url])

    def test_cache_miss_downloads_from_official_source_then_publishes_cache(self) -> None:
        release = official_blender_release("5.2.1")
        archive_bytes = b"official Blender archive after cache miss"
        manifest = (
            f"{hashlib.sha256(archive_bytes).hexdigest()}  {release.archive_name}\n"
        ).encode()
        opened_requests = []

        def opener(request) -> io.BytesIO:
            opened_requests.append(request.full_url)
            return io.BytesIO(
                manifest if request.full_url == release.checksum_url else archive_bytes
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_path = root / "drive-cache" / release.archive_name
            acquired = acquire_verified_blender_archive(
                release, root / "content" / release.archive_name,
                cache_path=cache_path, opener=opener,
            )

            self.assertEqual(acquired.cache_status, "miss")
            self.assertEqual(cache_path.read_bytes(), archive_bytes)
            self.assertEqual(
                opened_requests, [release.checksum_url, release.archive_url]
            )

    def test_corrupt_cache_falls_back_to_official_archive_and_replaces_cache(self) -> None:
        release = official_blender_release("5.2.1")
        archive_bytes = b"fresh official Blender archive"
        manifest = (
            f"{hashlib.sha256(archive_bytes).hexdigest()}  {release.archive_name}\n"
        ).encode()
        opened_requests = []

        def opener(request) -> io.BytesIO:
            opened_requests.append(request.full_url)
            return io.BytesIO(
                manifest if request.full_url == release.checksum_url else archive_bytes
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache_path = root / "drive-cache" / release.archive_name
            cache_path.parent.mkdir()
            cache_path.write_bytes(b"corrupted cache entry")
            acquired = acquire_verified_blender_archive(
                release, root / "content" / release.archive_name,
                cache_path=cache_path, opener=opener,
            )

            self.assertEqual(acquired.cache_status, "corrupt")
            self.assertEqual(acquired.archive_path.read_bytes(), archive_bytes)
            self.assertEqual(cache_path.read_bytes(), archive_bytes)
            self.assertEqual(opened_requests, [release.checksum_url, release.archive_url])

    def test_rejects_non_official_release_descriptor_before_network_access(self) -> None:
        release = official_blender_release("5.2.1")
        untrusted_release = BlenderRelease(
            version=release.version,
            archive_name=release.archive_name,
            archive_url="https://example.invalid/blender.tar.xz",
            checksum_url="https://example.invalid/blender.sha256",
        )
        opened_requests = []

        def opener(request) -> io.BytesIO:
            opened_requests.append(request.full_url)
            return io.BytesIO(b"")

        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(BlenderDownloadError):
                acquire_verified_blender_archive(
                    untrusted_release,
                    Path(temporary) / "blender.tar.xz",
                    opener=opener,
                )
        self.assertEqual(opened_requests, [])

    def test_notebook_embeds_the_opt_in_local_staging_cache_flow(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        notebook = json.loads(
            (repository_root / "render_blender_in_colab.ipynb").read_text(encoding="utf-8")
        )
        installer = next(
            "".join(cell["source"])
            for cell in notebook["cells"]
            if "Установка Blender с официальной SHA-256 проверкой" in "".join(
                cell.get("source", [])
            )
        )

        compile(installer, "notebook Blender installer", "exec")
        self.assertIn("CONFIG.enable_drive_blender_cache", installer)
        self.assertIn("https://download.blender.org/release", installer)
        self.assertIn("atomic_copy_verified_archive(cache_path, archive_path", installer)
        self.assertIn("atomic_copy_verified_archive(archive_path, cache_path", installer)
        self.assertIn("Path('/content/blender')", installer)
        self.assertNotIn("shell=True", installer)
