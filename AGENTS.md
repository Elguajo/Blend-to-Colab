# Project instructions

Before any analysis, planning, review, or implementation in this repository:

1. Read `README.md`.
2. Read `docs/ANALOG_AUDIT.md` completely.
3. Read `docs/BLENDER_ADDON_SPEC.md` completely.
4. Read `docs/IMPLEMENTATION_ROADMAP.md` completely.
5. Revalidate time-sensitive external facts before relying on them, especially the current Blender LTS versions, Google Colab limits/policies, and third-party project activity.

## Product invariants

- The source `.blend` file must never be saved back or modified in place.
- Saved scene settings are the default source of truth. Any render override must be optional, explicit, runtime-only, and reported before rendering.
- A long animation must be resumable after a Colab runtime interruption without rerendering completed frames by default.
- GPU selection must be verified from Blender/Cycles device discovery, not inferred only from `nvidia-smi`.
- Project archives and remote inputs must be validated before extraction or use.
- Do not copy code from repositories without a compatible license. Feature ideas may be reimplemented independently.
- Keep the Google Colab notebook self-contained for end users and keep its reusable logic testable from the repository.
- Keep the notebook job protocol compatible with the Blender add-on specification. Breaking protocol changes require a version bump and migration notes.

## Change workflow

- Treat `docs/ANALOG_AUDIT.md` as the current architecture and product baseline until an approved implementation changes it.
- Treat `docs/BLENDER_ADDON_SPEC.md` as the product and architecture baseline for Blender-to-Colab integration.
- Treat `docs/IMPLEMENTATION_ROADMAP.md` as the canonical execution order and status source.
- Update the audit when a decision, risk, competitor capability, or implementation boundary materially changes.
- Update roadmap checkboxes only when completion is supported by files, tests, logs, or a real environment check. Work on one phase at a time and satisfy its exit criterion before starting the next phase.
- For implementation, follow the ordered phases and acceptance criteria in the audit; do not combine all phases into an unreviewable rewrite.
- Do not claim Colab, GPU rendering, Google Drive integration, or Blender compatibility was validated unless it was actually exercised in that environment.
