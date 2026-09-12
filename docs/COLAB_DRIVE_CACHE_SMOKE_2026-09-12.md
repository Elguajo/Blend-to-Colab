# Colab Drive cache smoke — 2026-09-12

Scope: `render_blender_in_colab.ipynb`, Blender `5.2.1`, standard Colab Python 3 runtime with `ENABLE_DRIVE_BLENDER_CACHE=True`. The runtime used for this check had no NVIDIA GPU (`nvidia-smi` was unavailable); GPU rendering was not part of this cache smoke test.

## Observed cache scenarios

1. After explicitly deleting the Colab runtime and allocating a clean one, the installer mounted Drive and reported `Blender archive cache: miss`. It then completed `/content/blender/blender-5.2.1-linux-x64/blender --version` successfully.
2. After deleting that runtime and allocating another clean one, the installer reported `Blender archive cache: hit` and completed the same local `/content` Blender version command successfully.
3. The Drive cache archive was deliberately replaced with 38 bytes (its previous size was `383688088` bytes). In a new clean runtime the installer reported `Blender archive cache: corrupt; downloading a fresh official archive` and completed the local version command. The subsequent probe reported `cache size after recovery: 383688088` and `cache SHA-256 matches fresh official manifest: True`.

The Colab UI does not expose a separate observation of filesystem atomicity; this record therefore only establishes the exercised corrupt-cache recovery branch and the final checksum-valid cache archive.

## Preflight, render, and resume observation

A temporary local two-frame EEVEE scene (`64x64` PNG) produced a preflight report with `0 error(s), 0 warning(s)` and `SHA-256 source сохранён.` Its standard render completed with `frames=2/2`.

The first normal resume attempt exposed a defect: with no missing frames it attempted `PREFLIGHT -> COMPLETE` and failed the status transition. The notebook and reusable protocol helper were corrected to reuse an existing `COMPLETE` result without a Blender process; when a recovery attempt has all verified frames but is not already `COMPLETE`, it records `PREFLIGHT -> RENDERING -> COMPLETE`. A runtime reproduction of the corrected recovery branch reported `RESUME_RECOVERY_PASS frames=2 state=COMPLETE revision=8` and `RENDER_PROCESS_STARTED=False; all existing frame checksums were reused.`

This smoke does not complete roadmap stage 4: other input and destination scenarios remain outside its scope.
