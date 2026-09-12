# Colab GPU-default smoke — 2026-09-12

Scope: notebook revision `9208214` in a newly allocated standard Colab T4
runtime. The notebook defaults used for the check were
`ENABLE_CYCLES_GPU=True`, `ALLOW_CPU_FALLBACK=False`, and
`RUN_CYCLES_SMOKE_TEST=True`.

The installer completed its local `/content/blender/.../blender --version`
check for Blender `5.2.1 LTS` in `38.199s`. The default 64x64 Cycles smoke
completed in `6.073s` and reported:

```text
CYCLES_SMOKE_TEST_PASS backend=OPTIX; devices=['Tesla T4 (OPTIX)']
```

No project source, preflight, or full render was started in this check.
