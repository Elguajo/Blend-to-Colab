from pathlib import Path
import tempfile
import unittest
import zipfile

from src.blend_to_colab import (
    ArchiveSafetyError,
    ArchiveSafetyLimits,
    safe_extract_zip,
)


class ArchiveSafetyTests(unittest.TestCase):
    def _archive(self, directory: Path, members: dict[str, bytes]) -> Path:
        path = directory / "project.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in members.items():
                archive.writestr(name, content)
        return path

    def test_extracts_regular_project_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self._archive(root, {"project/scene.blend": b"blend"})

            extracted = safe_extract_zip(archive, root / "out")

            self.assertEqual(extracted, (root / "out" / "project" / "scene.blend",))
            self.assertEqual(extracted[0].read_bytes(), b"blend")

    def test_rejects_path_traversal_before_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self._archive(root, {"../outside.txt": b"escape"})

            with self.assertRaises(ArchiveSafetyError):
                safe_extract_zip(archive, root / "out")

            self.assertFalse((root / "outside.txt").exists())

    def test_rejects_zip_bomb_ratio(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self._archive(root, {"large.txt": b"0" * 4096})

            with self.assertRaises(ArchiveSafetyError):
                safe_extract_zip(
                    archive,
                    root / "out",
                    ArchiveSafetyLimits(max_compression_ratio=2),
                )

    def test_rejects_too_many_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self._archive(root, {"one.txt": b"1", "two.txt": b"2"})

            with self.assertRaises(ArchiveSafetyError):
                safe_extract_zip(
                    archive, root / "out", ArchiveSafetyLimits(max_entries=1)
                )
