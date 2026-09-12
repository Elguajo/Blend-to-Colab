import hashlib
import io
from pathlib import Path
import tempfile
import unittest

from src.blend_to_colab import (
    BlenderDownloadError,
    OFFICIAL_DOWNLOAD_USER_AGENT,
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
