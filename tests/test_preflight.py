import ast
import json
from pathlib import Path
import tempfile
import unittest

from src.blend_to_colab import (
    BLENDER_PREFLIGHT_SCRIPT,
    BlenderProbeError,
    ConfigError,
    PROBE_REPORT_VERSION,
    SourceBlendChangedError,
    assert_source_blend_unchanged,
    build_blender_probe_command,
    estimate_from_test_frame,
    load_probe_report,
    sha256_file,
)


class BlenderPreflightTests(unittest.TestCase):
    def test_probe_script_is_valid_python_and_never_uses_blender_operators(self) -> None:
        ast.parse(BLENDER_PREFLIGHT_SCRIPT)
        self.assertNotIn("bpy.ops", BLENDER_PREFLIGHT_SCRIPT)
        self.assertNotIn("save_mainfile", BLENDER_PREFLIGHT_SCRIPT)
        self.assertNotIn("save_as_mainfile", BLENDER_PREFLIGHT_SCRIPT)

    def test_notebook_embeds_a_parseable_read_only_preflight_script(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        notebook = json.loads(
            (repository_root / "render_blender_in_colab.ipynb").read_text(encoding="utf-8")
        )
        cell_source = next(
            "".join(cell["source"])
            for cell in notebook["cells"]
            if "Read-only preflight" in "".join(cell.get("source", []))
        )
        cell_tree = ast.parse(cell_source)
        script = next(
            ast.literal_eval(node.value)
            for node in cell_tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "PREFLIGHT_SCRIPT"
                for target in node.targets
            )
        )

        ast.parse(script)
        self.assertNotIn("bpy.ops", script)
        self.assertNotIn("save_mainfile", script)
        self.assertIn("--factory-startup", cell_source)
        self.assertIn("--disable-autoexec", cell_source)
        self.assertIn("test_command += ['-o', str(test_prefix), '-f', str(test_frame)]", cell_source)
        self.assertNotIn("'--render-frame'", cell_source)
        self.assertIn("missing_asset", script)
        self.assertIn("unsupported_render_engine", script)
        self.assertIn("vram_free_mib", script)

    def test_probe_command_keeps_paths_as_distinct_arguments_after_separator(self) -> None:
        command = build_blender_probe_command(
            Path("/opt/blender/blender"),
            Path("/work/project scene.blend"),
            Path("/work/probe.py"),
            Path("/work/-report.json"),
        )

        self.assertEqual(
            command[:3],
            (str(Path("/opt/blender/blender")), "--background", "--factory-startup"),
        )
        self.assertIn("--disable-autoexec", command)
        self.assertEqual(command[-2:], ("--", str(Path("/work/-report.json"))))
        self.assertNotIn("shell", " ".join(command).lower())

    def test_source_hash_guard_detects_any_probe_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            blend_file = Path(temporary) / "source.blend"
            blend_file.write_bytes(b"original blend bytes")
            source_hash = sha256_file(blend_file)

            assert_source_blend_unchanged(blend_file, source_hash)
            blend_file.write_bytes(b"modified blend bytes")
            with self.assertRaises(SourceBlendChangedError):
                assert_source_blend_unchanged(blend_file, source_hash)

    def test_loads_only_the_versioned_minimum_report_contract(self) -> None:
        report = {
            "report_version": PROBE_REPORT_VERSION,
            "source_file": "/project/scene.blend",
            "blender": {},
            "scenes": [],
            "assets": [],
            "issues": {"errors": [], "warnings": []},
            "environment": {},
        }
        with tempfile.TemporaryDirectory() as temporary:
            report_path = Path(temporary) / "preflight.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(load_probe_report(report_path), report)

            report.pop("assets")
            report_path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaises(BlenderProbeError):
                load_probe_report(report_path)

    def test_test_frame_estimate_scales_known_time_and_output_size(self) -> None:
        estimate = estimate_from_test_frame(
            frame_count=120,
            test_frame_seconds=2.5,
            test_frame_output_bytes=1024,
        )

        self.assertEqual(estimate.estimated_render_seconds, 300)
        self.assertEqual(estimate.estimated_output_bytes, 122_880)
        with self.assertRaises(ConfigError):
            estimate_from_test_frame(
                frame_count=0, test_frame_seconds=1, test_frame_output_bytes=1
            )
