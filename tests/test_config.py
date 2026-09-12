import json
from pathlib import Path
import unittest

from src.blend_to_colab import (
    CUSTOM_VERSION_PRESET,
    ConfigError,
    DEFAULT_BLENDER_VERSION,
    RenderConfig,
    RenderMode,
    resolve_blender_version,
)


class RenderConfigTests(unittest.TestCase):
    def test_notebook_defaults_to_verified_gpu_without_cpu_fallback(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        notebook = json.loads(
            (repository_root / "render_blender_in_colab.ipynb").read_text(encoding="utf-8")
        )
        cells = ["".join(cell.get("source", [])) for cell in notebook["cells"]]
        primary_settings = next(cell for cell in cells if "ENABLE_CYCLES_GPU" in cell)
        advanced_settings = next(
            cell for cell in cells if "#@title Настройки — Advanced" in cell
        )

        self.assertIn("ENABLE_CYCLES_GPU = True", primary_settings)
        self.assertIn("ALLOW_CPU_FALLBACK = False", advanced_settings)
        self.assertIn("RUN_CYCLES_SMOKE_TEST = True", advanced_settings)

    def test_default_lts_preset_builds_typed_config(self) -> None:
        config = RenderConfig.from_user_values(
            blender_version_preset=DEFAULT_BLENDER_VERSION,
            custom_blender_version="",
            enable_cycles_gpu=True,
            allow_cpu_fallback=False,
            include_cpu_with_gpu=False,
            render_mode="still",
            still_frame=1,
            download_result=False,
            run_cycles_smoke_test=False,
            run_preflight_test_frame=False,
        )

        self.assertEqual(config.blender_version, DEFAULT_BLENDER_VERSION)
        self.assertEqual(config.render_mode, RenderMode.STILL)
        self.assertFalse(config.allow_cpu_fallback)
        self.assertFalse(config.enable_drive_blender_cache)

    def test_drive_blender_cache_requires_a_boolean_opt_in(self) -> None:
        config = RenderConfig.from_user_values(
            blender_version_preset=DEFAULT_BLENDER_VERSION,
            custom_blender_version="",
            enable_cycles_gpu=True,
            allow_cpu_fallback=False,
            include_cpu_with_gpu=False,
            render_mode="animation",
            still_frame=1,
            download_result=False,
            run_cycles_smoke_test=False,
            run_preflight_test_frame=False,
            enable_drive_blender_cache=True,
        )
        self.assertTrue(config.enable_drive_blender_cache)
        with self.assertRaises(ConfigError):
            RenderConfig.from_user_values(
                blender_version_preset=DEFAULT_BLENDER_VERSION,
                custom_blender_version="",
                enable_cycles_gpu=True,
                allow_cpu_fallback=False,
                include_cpu_with_gpu=False,
                render_mode="animation",
                still_frame=1,
                download_result=False,
                run_cycles_smoke_test=False,
                run_preflight_test_frame=False,
                enable_drive_blender_cache="yes",
            )

    def test_custom_version_requires_explicit_custom_preset(self) -> None:
        self.assertEqual(
            resolve_blender_version(CUSTOM_VERSION_PRESET, " 4.3.2 "), "4.3.2"
        )
        with self.assertRaises(ConfigError):
            resolve_blender_version(DEFAULT_BLENDER_VERSION, "4.3.2")
        with self.assertRaises(ConfigError):
            resolve_blender_version(CUSTOM_VERSION_PRESET, "")

    def test_invalid_values_are_rejected(self) -> None:
        with self.assertRaises(ConfigError):
            resolve_blender_version(CUSTOM_VERSION_PRESET, "5.2")
        with self.assertRaises(ConfigError):
            RenderConfig.from_user_values(
                blender_version_preset=DEFAULT_BLENDER_VERSION,
                custom_blender_version="",
                enable_cycles_gpu=True,
                allow_cpu_fallback=False,
                include_cpu_with_gpu=False,
                render_mode="animation",
                still_frame=True,
                download_result=False,
                run_cycles_smoke_test=False,
                run_preflight_test_frame=False,
            )
        with self.assertRaises(ConfigError):
            RenderConfig.from_user_values(
                blender_version_preset=DEFAULT_BLENDER_VERSION,
                custom_blender_version="",
                enable_cycles_gpu=False,
                allow_cpu_fallback=False,
                include_cpu_with_gpu=True,
                render_mode="animation",
                still_frame=1,
                download_result=False,
                run_cycles_smoke_test=False,
                run_preflight_test_frame=False,
            )
