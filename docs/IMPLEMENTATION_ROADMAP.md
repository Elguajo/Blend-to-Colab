# ROADMAP — Blend-to-Colab

Статус на 2026-09-12: Этапы 1 и 2 завершены. Локальные unit/static checks и реальные Colab smoke tests подтверждены.

Связанные документы:

- [`ANALOG_AUDIT.md`](ANALOG_AUDIT.md) — аудит текущего notebook, аналогов и технических рисков;
- [`BLENDER_ADDON_SPEC.md`](BLENDER_ADDON_SPEC.md) — требования и архитектура будущего Blender-аддона.

## Обозначения и правила выполнения

- `[x]` — завершено и подтверждено указанным результатом;
- `[>]` — выполняется сейчас;
- `[ ]` — запланировано или ожидает предыдущую фазу.

Работа ведётся по одной фазе. Риск проверяется в той фазе, где он впервые влияет на реализацию. Следующая фаза не начинается, пока не выполнен критерий выхода предыдущей. Статус меняется только по наблюдаемым результатам: файлам, тестам, логам или реальному smoke test.

## Этап 0 — аудит, требования и архитектура

- [x] Зафиксировать текущее состояние notebook и критические дефекты.
- [x] Сравнить проект с действующими аналогами и выделить полезные возможности.
- [x] Определить целевую архитектуру notebook v2.
- [x] Определить границы бесплатного Colab и managed cloud режима.
- [x] Составить спецификацию Blender-аддона и протокола заданий.
- [x] Сделать аудит, спецификацию и этот roadmap обязательным контекстом для ИИ-агентов.

Критерий выхода выполнен: документы созданы, взаимно связаны и проходят локальную проверку ссылок и JSON-примеров.

## Этап 1 — correctness и safety notebook

- [x] Исправить обнаружение и выбор Cycles GPU backend.
- [x] Добавить явную политику CPU fallback без скрытого запуска на CPU.
- [x] Ввести типизированную конфигурацию и проверку пользовательских значений.
- [x] Реализовать безопасную распаковку ZIP с защитой от path traversal и archive bombs.
- [x] Загружать Blender только с официального источника и проверять SHA-256.
- [x] Обновить LTS presets, сохранив режим custom version.
- [x] Добавить unit tests для config, version resolution, URL construction и archive safety.
- [x] Провести реальный Cycles smoke test в Colab и сохранить подтверждающий лог: Blender 5.2.1 LTS, T4, OptiX, `Tesla T4 (OPTIX)`, маркер `CYCLES_SMOKE_TEST_PASS`.

Риск-гейт: нельзя заявлять о GPU-рендере по одному `nvidia-smi`; backend и устройство должны быть подтверждены самим Blender/Cycles.

Критерий выхода: unit tests проходят, а реальный Colab-лог содержит выбранный GPU и активный GPU backend.

## Этап 2 — read-only preflight

- [x] Добавить Blender probe, возвращающий машиночитаемый JSON.
- [x] Проверять сцену, камеру, render engine, диапазон кадров и output settings.
- [x] Находить отсутствующие textures, linked libraries, fonts, VDB и caches.
- [x] Выявлять внешние add-ons и неподдерживаемые render engines.
- [x] Показывать RAM, disk, GPU и доступную VRAM.
- [x] Добавить test-frame и оценку времени/места перед полным рендером.
- [x] Подтвердить тестами, что probe не сохраняет и не изменяет `.blend`.

Риск-гейт: исходная сцена и её dirty state не должны меняться от проверки.

Критерий выхода: ошибки проекта обнаруживаются до расходования GPU-времени, hash исходного файла остаётся прежним.

## Этап 3 — resumable job protocol

- [x] Зафиксировать JSON Schemas для `job.json`, `status.json` и `result_manifest.json`.
- [x] Ввести уникальный job id и версию протокола.
- [x] Реализовать state machine и монотонную ревизию статуса.
- [x] Планировать chunks и только отсутствующие кадры.
- [x] Записывать streaming log и итоговый summary.
- [x] Публиковать manifest и результаты атомарно.
- [x] Проверять checksum каждого подтверждённого результата.
- [x] Добавить unit/integration tests переходов состояния, resume и повреждённых результатов.
- [x] Имитировать обрыв runtime и повторный запуск в реальном Colab.

Риск-гейт: повторный запуск не должен перерендеривать уже подтверждённые кадры или объявлять неполный job завершённым.

Критерий выхода: прерванная анимация продолжается с missing frames, а готовые кадры сохраняются и проходят checksum validation.

## Этап 4 — источники проектов и выдача результатов

- [ ] Поддержать local upload и ручной ZIP без Google Drive.
- [ ] Поддержать Google Drive file/folder и HTTPS URL.
- [ ] При нескольких `.blend` требовать явный выбор.
- [ ] Валидировать remote input до распаковки и использования.
- [ ] Добавить result ZIP, preview и опциональную сборку MP4.
- [ ] Проверить пути с пробелами, Unicode и специальными символами.
- [ ] Убедиться, что пользовательские строки не интерполируются в shell commands.
- [ ] Провести smoke test каждого source/destination варианта.

Риск-гейт: неподтверждённые архивы и удалённые данные не должны попадать в исполняемые команды или выходить за staging directory.

Критерий выхода: все заявленные источники и назначения проходят smoke test с безопасными путями.

## Этап 5 — управляемые runtime overrides

- [ ] Оставить настройки сохранённой сцены поведением по умолчанию.
- [ ] Добавить только opt-in overrides: frames, resolution percentage, samples, camera, scene, view layer, denoiser и output.
- [ ] Показывать точный diff overrides перед запуском.
- [ ] Применять overrides только runtime-аргументами или к временной копии.
- [ ] Добавить тесты каждого override и их записи в manifest.

Риск-гейт: ни один override не должен сохраняться в исходный `.blend`.

Критерий выхода: baseline без overrides совпадает с настройками сцены; каждый override изолирован, видим пользователю и отражён в manifest.

## Этап 6 — стабилизация notebook v2 и protocol v1

- [ ] Вынести повторно используемую логику из notebook в тестируемые модули.
- [ ] Добавить воспроизводимую сборку notebook из исходников.
- [ ] Добавить CI-проверки JSON notebook, Python cells, schemas и unit tests.
- [ ] Зафиксировать protocol compatibility policy и migration notes.
- [ ] Обновить README и troubleshooting по фактическому поведению.
- [ ] Выбрать и добавить лицензию проекта до публикации сборки.
- [ ] Выполнить согласованную матрицу реальных Colab smoke tests.

Риск-гейт: API протокола нельзя замораживать, пока resume и result verification не подтверждены end-to-end.

Критерий выхода: notebook v2 автономно работает без аддона, protocol v1 стабилен, CI и smoke matrix проходят.

## Этап 7 — Blender add-on MVP: Scene Check + Manual ZIP

- [ ] Создать минимальное Blender Extension с панелью Blend-to-Colab.
- [ ] Реализовать Scene Check поверх protocol/preflight contract.
- [ ] Проверить безопасный snapshot сохранённой и несохранённой сцены.
- [ ] Найти и упаковать поддерживаемые внешние зависимости.
- [ ] Создать job package без изменения исходного `.blend`.
- [ ] Открывать notebook и показывать короткие инструкции запуска.
- [ ] Принимать result ZIP, проверять manifest/checksums.
- [ ] Импортировать still в Image Editor, sequence/video — в VSE только по команде пользователя.
- [ ] Не блокировать Blender UI: упаковка, checksums и ожидание выполняются фоново.
- [ ] Провести Manual ZIP round-trip от Blender до Colab и обратно.

Риск-гейт: тестами подтвердить поведение `save_as_mainfile(copy=True)` или выбрать другой способ snapshot; не полагаться на предположение.

Критерий выхода: supported scene проходит `Create Job -> user runs Colab -> Complete -> Import` без ручного исправления путей и без изменения исходника.

## Этап 8 — Blender add-on V1: Synced Folder

- [ ] Добавить transport interface без изменения package/protocol/import слоёв.
- [ ] Реализовать transport для локальной папки Google Drive for Desktop.
- [ ] Публиковать marker `READY` только после полной записи package.
- [ ] Отслеживать status/result без чтения частично синхронизированных файлов.
- [ ] Сохранять локальный job index и восстанавливать его после перезапуска Blender.
- [ ] Добавить cancel waiting без удаления remote job и результатов.
- [ ] Проверить большие ZIP, задержки синхронизации и конфликтные копии.
- [ ] Провести round-trip на Windows; затем проверить macOS/Linux перед заявлением поддержки.

Риск-гейт: Drive sync не является транзакцией; готовность файлов определяется markers, revision и checksums, а не только их появлением.

Критерий выхода: после ручного запуска Colab статус и результат автоматически появляются в Blender, включая восстановление после обрыва и перезапуска.

## Этап 9 — Blender add-on V1.5: Direct Drive API

- [ ] Провести отдельный spike доступности result files через `drive.file`.
- [ ] Утвердить OAuth client lifecycle, consent UX и способ безопасного хранения tokens.
- [ ] Запрашивать только минимальный разрешённый scope.
- [ ] Реализовать resumable upload/download и идемпотентные retry.
- [ ] Реализовать logout/revoke и удаление локальных credentials.
- [ ] Исключить tokens и персональные данные из `.blend`, packages, manifests и logs.
- [ ] Пройти security и privacy review до публикации.
- [ ] Проверить требования Google OAuth verification.

Риск-гейт: эта фаза не начинается, пока spike не подтвердит выполнимость минимального scope и безопасный credential lifecycle.

Критерий выхода: сетевой обрыв восстанавливается без дубликатов, утечки credentials и расширения OAuth scope.

## Этап 10 — V2 Managed Cloud Provider

- [ ] Подтвердить реальную потребность в полностью автоматическом запуске и допустимую стоимость.
- [ ] Определить provider contract отдельно от notebook и transports.
- [ ] Реализовать Colab Enterprise/GCP job submission, IAM, quotas и billing errors.
- [ ] Добавить cancellation, retry, idempotency и cost visibility.
- [ ] Провести security, reliability и cost review.
- [ ] Выполнить end-to-end тест в отдельном тестовом cloud project.

Риск-гейт: создание или изменение cloud project, IAM, billing и production resources требует отдельного подтверждения пользователя.

Критерий выхода: job запускается и завершается без ручного открытия notebook, а стоимость, ошибки и отмена видимы пользователю.

## Этап 11 — release gate

- [ ] Выполнить полный набор unit, integration и end-to-end тестов.
- [ ] Проверить Blender/OS compatibility matrix только на реально протестированных версиях.
- [ ] Проверить установку, обновление и удаление аддона.
- [ ] Выполнить security, privacy, reliability, accessibility и usability review в применимом объёме.
- [ ] Подготовить release notes, migration notes и recovery instructions.
- [ ] Собрать подписанный или checksum-подтверждённый release artifact.
- [ ] Принять ship/no-ship решение по наблюдаемым результатам.

Риск-гейт: непроверенные платформы, Blender versions и cloud modes не указываются как поддерживаемые.

Критерий выхода: release checklist закрыт без критических дефектов; известные ограничения явно опубликованы.

## Текущий статус

Этапы 0–3 завершены. Этап 1 подтверждён локальными проверками и реальным Colab GPU smoke test: Blender 5.2.1 LTS выбрал OptiX на `Tesla T4 (OPTIX)` и завершил рендер временной сцены с маркером `CYCLES_SMOKE_TEST_PASS`. Этап 2 подтверждён реальным Colab T4 smoke test: stock Blender 5.2.1 сохранил SHA-256 двух временных `.blend` до и после probe, обнаружил `missing_asset` до рендера и отрендерил opt-in test-frame за 1.33 с; Cycles обнаружил CUDA и OptiX для Tesla T4. Этап 3 подтверждён реальным прерыванием и удалением runtime Colab: job `2e839139-d767-4d74-b873-dd4f2870318b` сохранил проверенные кадры 1–2 в Drive, в новой чистой T4-среде отрендерил только 3–4 через `OPTIX`, не изменив SHA-256 исходного `.blend`; независимая проверка Drive подтвердила кадры 1–4, `COMPLETE` и revision 3.
