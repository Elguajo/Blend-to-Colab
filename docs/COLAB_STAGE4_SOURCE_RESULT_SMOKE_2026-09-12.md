# Colab Stage 4 source/result smoke — 2026-09-12

Scope: real standard Colab Python 3 runtime running notebook revision
`59c1804`, Blender `5.2.1`, and a temporary Google Drive fixture.  This is
an observation record, not a completion record for roadmap stage 4.

## Observed source and job paths

- A Google Drive file named `file source.blend` was staged under
  `/content/blender_project/project/`.  Preflight completed with `0 error(s),
  0 warning(s)`.  A two-frame EEVEE job wrote its results to Drive, completed
  with `frames=2/2`, and a second invocation of the same job completed in
  `0.23` seconds without starting a replacement render.
- A Google Drive folder containing `first.blend` and `nested/second.blend`
  required the explicit selection `nested/second.blend`; the notebook reported
  that staged file as the render target.
- HTTPS input
  `https://raw.githubusercontent.com/whitemoonstone/blender/master/untitled.blend`
  was staged as `/content/blender_project/project/untitled.blend` after the
  single-file selection regression was fixed in revision `59c1804`.
- The browser upload control uploaded `test-scene-2.blend` (`413101` bytes)
  and the notebook staged it as
  `/content/blender_project/project/test-scene-2.blend`.  Its preflight
  completed with `0 error(s), 0 warning(s)`.
- With `RESULT_DESTINATION=local_download`, the notebook selected
  `/content/blender_local_results` as the result root.  The subsequent
  CPU still render was intentionally interrupted before completion, so this
  run has no observed local ZIP/download artifact.

The separate opt-in Blender Drive-cache miss, hit, corrupted-cache fallback,
fresh checksum validation, and local `/content` startup observations are
recorded in [COLAB_DRIVE_CACHE_SMOKE_2026-09-12.md](COLAB_DRIVE_CACHE_SMOKE_2026-09-12.md).

## Not established by this smoke

- a completed manual ZIP upload;
- a completed local-download delivery, including its ZIP and preview;
- MP4 assembly;
- Unicode or special-character paths (the exercised Drive filename contained
  a space only).

Consequently, the stage 4 checkbox and its exit criterion remain incomplete.
