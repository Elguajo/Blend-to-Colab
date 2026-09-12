# Stage 4 local delivery and Unicode-path Colab smoke — 2026-09-12

## Scope

This record covers an observed Google Colab run for the remaining result-delivery
paths. It does not claim browser upload of a ZIP: the `files.upload()` chooser
did not expose a usable upload event to the automation interface and was
cancelled before a file was selected.

## Environment and configuration

- Google Colab connected GPU runtime: T4 (Python 3).
- Blender: `5.2.1 LTS`.
- Notebook settings retained `ENABLE_CYCLES_GPU=True` and
  `ALLOW_CPU_FALLBACK=False`.
- `RESULT_DESTINATION='local_download'`, `CREATE_RESULT_ZIP=True`,
  `BUILD_RESULT_MP4=True`, `MP4_FPS=24`.
- The notebook tab was opened at Git revision `9208214`, which is an ancestor
  of the local tested `origin/main` tip `3c389fc`; the Stage 4 source and result
  cells exercised here are unchanged by the later default-smoke label commit.

## Test project and commands

In the runtime, an isolated factory-startup Blender script created a two-frame,
64x64 Cycles scene, then wrote a ZIP with these Unicode/special-character paths:

```text
Этап 4 & smoke #1.zip
проект & кадры #1/сцена & кадры #1.blend
```

The generated archive was `87,977` bytes and was downloaded to the local
machine. To exercise the actual safety/staging, render, and delivery code after
the inaccessible browser file chooser, the same archive was copied into the
notebook's `/content/blender_project/uploads/` staging input and passed to its
existing `safe_extract_zip`, `select_blend`, and `validate_blend` functions.

Observed staging result:

```text
LOCAL_STAGING_ZIP_PASS blend=проект & кадры #1/сцена & кадры #1.blend bytes=87790
```

The stock-Blender preflight reported zero errors and warnings; it preserved the
source SHA-256. It reported the path with Unicode and special characters,
Cycles, frames `1..2`, and 64x64 PNG output.

## Observed results

The render completed as protocol-v1 job
`56b3b80b-6f71-4314-9c51-eee421cb1ffc`:

```text
JOB_COMPLETE ... frames=2/2
GPU_RENDER_LOG_PASS=... CYCLES_DEVICE: backend=OPTIX; active=['Tesla T4 (OPTIX)']
```

The Results cell displayed `frame_0002.png` as its preview, created
`frames.zip` and `frames.mp4`, and invoked the local download of `frames.mp4`.
The downloaded file was observed at `C:\Users\Elguajo\Downloads\frames.mp4`
with size `1,707` bytes.

The final runtime verification asserted all of the following:

```json
{
  "RESULT_ARTIFACTS_PASS": true,
  "frames": ["frame_0001.png", "frame_0002.png"],
  "mp4_bytes": 1707,
  "source_sha256_unchanged": true,
  "zip_bytes": 6256,
  "zip_members": ["frame_0001.png", "frame_0002.png"],
  "ffprobe": {
    "format": {
      "duration": "0.083333",
      "format_name": "mov,mp4,m4a,3gp,3g2,mj2"
    }
  }
}
```

## Limits

- The result path, ZIP, preview, MP4 assembly, download, non-CPU Cycles render,
  and Unicode/special-character source path above are observed facts.
- This is not evidence of a completed browser `files.upload()` ZIP handoff. The
  manual ZIP smoke remains open, so this record does not satisfy the Stage 4
  exit criterion by itself and no roadmap checkbox was changed.
