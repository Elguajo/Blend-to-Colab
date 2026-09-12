# Запись завершения — Этап 3

Работаем в `D:\01_DEV\Blender-to-GoogleColab`. Этап 3 из
`docs/IMPLEMENTATION_ROADMAP.md` завершён. Этот документ сохраняет контекст и
доказательства его выполнения; он не является указанием повторно запускать
Этап 3 или автоматически начинать Этапы 4+.

Перед изменениями полностью прочитай `AGENTS.md`, `README.md`,
`docs/ANALOG_AUDIT.md`, `docs/BLENDER_ADDON_SPEC.md` и
`docs/IMPLEMENTATION_ROADMAP.md`; проверь `git status` и сохрани все
незакоммиченные изменения.

## Подтверждённый статус

- Этапы 0–2 завершены. Не изменяй и не откатывай их результаты.
- Этап 3 реализован, локально проверен и **завершён**.
- Прошли локальные unit/integration tests: state transitions и monotonic
  revision; missing-only chunk planning; simulated interruption с сохранением
  frames 1–2 и resume только frames 3–4; checksum detection и repair
  повреждённого кадра; atomic publication без временных файлов.
- Прошли static checks: все Python-ячейки notebook и JSON Schemas парсятся.
- Реальный Colab interrupted-animation smoke test выполнен 2026-09-12. Job
  `2e839139-d767-4d74-b873-dd4f2870318b` после `Disconnect and delete runtime`
  восстановился в чистой T4-среде из Drive: сохранены кадры 1–2, отрендерены
  только 3–4 через `OPTIX` на Tesla T4. SHA-256 исходного `.blend` не изменился;
  независимая проверка Drive подтвердила кадры 1–4 и `COMPLETE`/revision 3.

## Реализованный protocol v1

- Schemas: `protocol/job.schema.json`, `protocol/status.schema.json`,
  `protocol/result_manifest.schema.json`.
- Reusable stdlib-only core: `src/job_protocol.py`.
- Notebook render cell: `render_blender_in_colab.ipynb`, раздел `Protocol v1`.
- Tests: `tests/test_job_protocol.py`.
- Job id — UUID v4. `job.json` immutable; resume с иным SHA-256 проекта или
  иным сохранённым frame range блокируется.
- Job folder: `<DRIVE_OUTPUT_DIR>/jobs/<job-id>/request`, `worker`, `result`.
  Worker публикует `status.json` с монотонной revision, `render.log`,
  `summary.json`, frames и `result_manifest.json`.
- Frames сначала рендерятся в local staging, затем публикуются временным файлом
  с `os.replace`; в manifest попадают только файлы с вычисленным SHA-256.
- При resume подтверждённым считается только file, у которого совпадают path,
  size и SHA-256 из manifest. Missing и corrupted frames планируются заново;
  подтверждённые не перерендериваются.

## Зафиксированные решения и риски

1. Resumable animation поддерживает только image sequence. FFMPEG/direct video
   output блокируется: отдельные кадры нельзя надёжно checksum-validate и
   возобновить.
2. Output path — единственный runtime-only override для local staging и
   checksum-verified delivery. Он явно выводится перед рендером; остальные
   saved scene settings остаются default source of truth.
3. Source `.blend` нельзя сохранять или менять. Его SHA-256 проверяется до и
   после каждого Blender render process; несовпадение блокирует публикацию.
4. `COMPLETE -> PREFLIGHT` разрешён только как recovery path после обнаружения
   повреждённого результата; это не означает доверие к старому manifest.
5. Notebook остаётся self-contained, поэтому содержит небольшой runtime слой;
   полный protocol contract и тестируемая логика находятся в `src/job_protocol.py`.
6. Не интерполируй пользовательские значения в shell. Blender запускается
   списком аргументов, без `shell=True`.

## Подтверждённый критерий выхода

Реальный Colab GPU runtime подтвердил все условия: resume запускает только
missing frames, подтверждённые кадры не перерендерены, checksum валидны для
кадров 1–4, а `status.json` и `summary.json` имеют `COMPLETE`.
