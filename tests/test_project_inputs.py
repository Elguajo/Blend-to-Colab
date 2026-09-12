from pathlib import Path
import ast
import json
import tempfile
import unittest

from src.project_inputs import (
    ProjectInputError,
    resolve_path_under,
    select_blend_file,
    validate_blend_file,
    validate_https_url,
    validate_project_source_mode,
)


class ProjectInputTests(unittest.TestCase):
    def _blend(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"BLENDER-v500")
        return path

    def test_only_known_source_modes_and_https_urls_are_accepted(self) -> None:
        self.assertEqual(validate_project_source_mode("drive_folder"), "drive_folder")
        self.assertEqual(validate_https_url("https://example.test/project.blend"), "https://example.test/project.blend")
        for value in ("ftp://example.test/a.blend", "https://user@example.test/a.blend", "https://example.test/a blend"):
            with self.assertRaises(ProjectInputError):
                validate_https_url(value)

    def test_rejects_invalid_blend_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "scene.blend"
            path.write_bytes(b"not blender")
            with self.assertRaises(ProjectInputError):
                validate_blend_file(path)

    def test_accepts_zstandard_and_gzip_compressed_blend_containers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, magic in (("zstandard.blend", b"\x28\xb5\x2f\xfd"), ("gzip.blend", b"\x1f\x8b")):
                path = root / name
                path.write_bytes(magic + b"x" * 16)
                self.assertEqual(validate_blend_file(path), path)

    def test_multiple_blends_require_an_explicit_safe_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._blend(root / "first.blend")
            expected = self._blend(root / "nested" / "second.blend")
            with self.assertRaises(ProjectInputError):
                select_blend_file(root)
            self.assertEqual(select_blend_file(root, "nested/second.blend"), expected)
            with self.assertRaises(ProjectInputError):
                select_blend_file(root, "../first.blend")

    def test_stale_selection_does_not_block_a_single_blend_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = self._blend(root / "scene.blend")
            self.assertEqual(select_blend_file(root, "nested/previous.blend"), expected)

    def test_result_path_stays_inside_drive_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "MyDrive"
            self.assertEqual(resolve_path_under(root, "Рендеры / final", field_name="DRIVE_RESULT_PATH"), root.resolve() / "Рендеры " / " final")
            for value in ("../outside", "/outside", "C:\\outside"):
                with self.assertRaises(ProjectInputError):
                    resolve_path_under(root, value, field_name="DRIVE_RESULT_PATH")

    def test_notebook_embeds_all_project_sources_and_result_delivery(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        notebook = json.loads((repository_root / "render_blender_in_colab.ipynb").read_text(encoding="utf-8"))
        cells = ["".join(cell.get("source", [])) for cell in notebook["cells"] if cell.get("cell_type") == "code"]
        source_cell = next(cell for cell in cells if "PROJECT_SOURCE" in cell)
        result_cell = next(cell for cell in cells if "CREATE_RESULT_ZIP" in cell)
        ast.parse(source_cell, "project source cell", "exec")
        ast.parse(result_cell, "result delivery cell", "exec")
        for source in ("'upload'", "'drive_file'", "'drive_folder'", "'url'", "SELECTED_BLEND_PATH", "require_https_url"):
            self.assertIn(source, source_cell)
        for feature in ("RESULT_DESTINATION", "CREATE_RESULT_ZIP", "BUILD_RESULT_MP4", "files.download", "ffmpeg"):
            self.assertIn(feature, result_cell)
