# Спецификация Blender-аддона для Blend-to-Colab

Рабочее название: **Blend-to-Colab Connector**

Статус: спецификация будущей функции, реализация не начата

Версия документа: 1.0

Дата: 2026-09-12
Связанный документ: [`ANALOG_AUDIT.md`](ANALOG_AUDIT.md)

## 1. Краткое объяснение без технических терминов

Идея пользователя правильная: в Blender должна появиться панель, из которой можно подготовить сцену к облачному рендеру, передать её в Colab, дождаться результата и вернуть готовые изображения или видео обратно на компьютер и, при желании, в Blender.

Но бесплатный Google Colab нельзя надёжно использовать как полностью автоматическую render-farm API:

- у обычного managed Colab нет документированного публичного API для запуска произвольного бесплатного notebook job из Blender;
- пользователь должен сам открыть notebook, подключить runtime, выдать доступ к Drive и запустить ячейки;
- GPU, длительность runtime и доступность ресурсов не гарантируются;
- обход UI, anti-idle механизмы, remote control и обход лимитов не должны использоваться.

Документированный программный запуск notebook jobs существует у **Colab Enterprise**, но это отдельный платный Google Cloud продукт с проектом, IAM, квотами и биллингом. Поэтому продукт разделяется на два режима:

1. **Free Colab Bridge** — основной режим: аддон автоматизирует подготовку, передачу, наблюдение и импорт, но запуск Colab остаётся одним явным действием пользователя.
2. **Managed Cloud Provider** — будущий режим: полностью автоматический запуск через Colab Enterprise/GCP или другого GPU-провайдера.

Под «вернуть в Blender» понимается:

- скачать готовые кадры/видео в выбранную локальную папку;
- показать preview;
- опционально добавить image sequence или MP4 в Video Sequence Editor;
- опционально загрузить отдельный кадр как Blender Image datablock.

Рендер не превращается обратно в редактируемую 3D-сцену: результат рендера — изображения, EXR-последовательность или видео.

## 2. Проблема и цель

### Проблема

Пользователю без мощной GPU приходится вручную:

1. сохранять и упаковывать Blender-проект;
2. искать внешние текстуры, библиотеки и caches;
3. открывать Colab;
4. загружать проект и настраивать notebook;
5. отслеживать результат в Drive;
6. скачивать кадры;
7. вручную загружать их в Blender или видеоредактор;
8. повторять процесс после обрыва runtime.

Это сложно для человека без опыта разработки и создаёт риск потерянных ресурсов, несовпавших версий Blender и повторного рендера уже готовых кадров.

### Цель

Дать пользователю понятный пошаговый процесс внутри Blender:

`Проверить сцену -> Создать задание -> Открыть Colab -> Запустить -> Дождаться -> Получить результат`

При этом исходный `.blend` не изменяется, передача возобновляется после сетевых ошибок, а рендер продолжается с отсутствующих кадров.

## 3. Целевые пользователи

- начинающий Blender-пользователь без мощной GPU;
- художник, которому неудобно работать с Python и Colab paths;
- пользователь, рендерящий небольшие и средние Cycles/EEVEE-анимации;
- автор проекта, которому важны сохранённые настройки сцены и воспроизводимость;
- технический пользователь, которому позже понадобится полностью управляемый GPU backend.

## 4. Основные сценарии

### Сценарий A: один кадр

1. Пользователь открывает сохранённую сцену.
2. В панели Blend-to-Colab нажимает **Проверить сцену**.
3. Аддон показывает камеру, движок, разрешение, Blender version и проблемы ресурсов.
4. Пользователь нажимает **Создать задание**.
5. Аддон создаёт snapshot-копию и job package.
6. Аддон открывает официальный notebook проекта в браузере.
7. Пользователь нажимает **Run all** и подтверждает Drive/GPU.
8. После завершения результат синхронизируется обратно.
9. Пользователь нажимает **Загрузить результат**.

### Сценарий B: анимация с обрывом Colab

1. Аддон создаёт job для frame range.
2. Notebook рендерит кадры chunks и обновляет status/manifest.
3. Runtime завершается до конца.
4. Аддон показывает `Частично: 84/240 кадров`.
5. Пользователь снова открывает notebook и запускает тот же job.
6. Notebook пропускает подтверждённые кадры и рендерит только отсутствующие.

### Сценарий C: ручной режим без Google Drive for Desktop

1. Аддон создаёт ZIP job package локально.
2. Пользователь загружает ZIP в notebook через браузер.
3. Notebook предлагает скачать result ZIP.
4. Пользователь выбирает result ZIP в аддоне.
5. Аддон проверяет manifest, распаковывает и импортирует результат.

### Сценарий D: полностью автоматический платный backend

1. Пользователь заранее настраивает Google Cloud project и billing.
2. Аддон отправляет job через provider adapter.
3. Colab Enterprise/GCP выполняет notebook execution job.
4. Аддон получает статус и результат через официальные API.

Этот сценарий не входит в первую версию.

## 5. Объём версий продукта

### MVP — Local Package Bridge

Обязательно:

- панель Blender;
- анализ текущей сцены;
- создание snapshot-копии без изменения исходного `.blend`;
- сбор зависимостей и ZIP;
- `job.json` с версионированным протоколом;
- открытие Colab notebook;
- ручная передача ZIP;
- импорт result ZIP;
- preview и импорт в Video Sequence Editor;
- понятные ошибки для неподдерживаемых ресурсов.

MVP не требует Google OAuth и может работать как полностью локальный Blender extension до момента ручной загрузки.

### V1 — Synced Folder Bridge

Добавляется:

- выбранная пользователем локальная папка, синхронизируемая Google Drive for Desktop;
- автоматическая запись job package в sync-folder;
- наблюдение за `status.json` и `result_manifest.json`;
- автоматическое обнаружение готовых результатов после синхронизации;
- продолжение прерванного job;
- отмена локального ожидания без удаления удалённых результатов.

Это рекомендуемый основной режим: он не хранит Google OAuth tokens внутри Blender и не требует Drive API в аддоне.

### V1.5 — Direct Google Drive API

Опционально после отдельного security/privacy review:

- OAuth desktop flow;
- минимальный scope `drive.file`;
- resumable upload/download;
- восстановление передачи;
- progress и retry;
- безопасное хранение refresh token либо session-only авторизация;
- проверка поведения `drive.file` для файлов, созданных notebook внутри выбранной папки.

Этот режим сначала должен пройти технический spike. Нельзя заранее считать, что folder permission автоматически даст доступ ко всем дочерним файлам, созданным другим клиентом.

### V2 — Managed Cloud Provider

Опционально:

- Colab Enterprise notebook execution jobs;
- GCP GPU VM/Batch adapter;
- другие GPU-провайдеры за общим provider interface;
- полностью автоматический запуск;
- стоимость и лимиты до подтверждения пользователем.

V2 не должна усложнять бесплатный основной сценарий.

### Архитектурное решение по способу обмена

| Вариант | Пользовательский опыт | Сложность и риски | Решение |
| --- | --- | --- | --- |
| Manual ZIP | Дополнительные upload/download действия | Минимальная реализация, нет OAuth, легко проверить | Выбран для MVP и остаётся fallback |
| Google Drive for Desktop sync-folder | Почти автоматическая передача туда и обратно | Требует установленный Drive client, нужно учитывать задержки/partial sync | Выбран для V1 как самый простой надёжный bridge |
| Direct Google Drive API | Не требует Drive desktop, есть точный progress | OAuth consent, token storage, API verification, resumable transfer, неясность доступа к worker-created files | Только V1.5 после spike и security/privacy review |
| Colab Enterprise/GCP | Полностью автоматический job submission | Платный проект, IAM, billing, provider lifecycle | Отдельный V2 для пользователей, которым нужна автоматизация |

Synced-folder выигрывает для первой удобной версии, потому что выполняет реальное требование «отправить и вернуть», но не заставляет сразу строить OAuth-продукт. Manual ZIP сохраняется, чтобы аддон работал у пользователей без Google Drive for Desktop. Direct API и managed backend добавляются через transport interface и не требуют переписывать упаковку, protocol или импорт результатов.

## 6. Что не входит в продукт

- автоматический запуск бесплатного Colab через недокументированные endpoints;
- browser automation для нажатия `Run all`;
- anti-idle JavaScript;
- SSH, remote desktop, web server или reverse proxy внутри Colab;
- обход лимитов через несколько аккаунтов;
- распределение одного job между несколькими бесплатными Colab-аккаунтами;
- изменение или сохранение исходного `.blend`;
- автоматическая покупка GPU/кредитов;
- гарантии времени рендера или конкретной модели GPU;
- загрузка секретов, OAuth tokens или локальных путей в job package;
- произвольное выполнение пользовательских скриптов на недоверенной инфраструктуре без предупреждения.

## 7. Пользовательский интерфейс Blender

### Расположение

Рекомендуемая первая версия: `Properties -> Render -> Blend to Colab`.

Дополнительная компактная панель в `3D View -> Sidebar` возможна позже, но не должна дублировать всю логику.

### Блоки панели

#### 1. Scene Check

Показывает:

- имя текущего `.blend`;
- сохранён ли файл;
- локальную версию Blender;
- active scene, camera и render engine;
- frame range и FPS;
- resolution и output format;
- количество найденных внешних файлов;
- missing files, linked libraries, caches и подозрительные add-ons;
- приблизительный размер package;
- итог `Ready`, `Warnings` или `Blocked`.

Кнопка: **Check Scene**.

#### 2. Render Job

Поля:

- mode: `Saved Range`, `Single Frame`, `Custom Range`, `Preview`;
- start/end/step для custom range;
- output: `Use Scene Settings` по умолчанию;
- advanced overrides, выключенные по умолчанию;
- destination: `Manual ZIP` или `Synced Folder`;
- job name;
- overwrite policy: `Skip Existing` по умолчанию.

Кнопка: **Create Render Job**.

#### 3. Colab Handoff

Показывает:

- job id;
- package path;
- upload/sync state;
- короткую инструкцию из трёх действий.

Кнопки:

- **Open Colab**;
- **Copy Job ID**;
- **Open Job Folder**;
- **Refresh Status**.

#### 4. Progress

Показывает:

- состояние job;
- completed/total frames;
- active frame/chunk, если доступно;
- backend и имя GPU;
- elapsed time;
- последнее сообщение worker;
- ошибку и путь к log.

Кнопки:

- **Refresh**;
- **Open Log**;
- **Stop Watching**.

Остановка наблюдения не должна притворяться удалённой отменой Colab job.

#### 5. Results

Кнопки:

- **Download/Locate Results**;
- **Load Preview**;
- **Add Image Sequence to VSE**;
- **Add Movie to VSE**;
- **Open Output Folder**.

Любой импорт должен быть opt-in и не заменять существующие strips/images без подтверждения.

## 8. Функциональные требования

### FR-1. Snapshot исходной сцены

- Аддон создаёт отдельную snapshot-копию.
- Путь текущего `.blend` и dirty state не должны меняться.
- Исходный файл не открывается на запись.
- Snapshot получает fingerprint: SHA-256, размер, Blender version и timestamp.
- Если безопасный snapshot несохранённых изменений не подтверждён тестами, первая версия блокирует job и просит сохранить сцену.

Рекомендуемая реализация после проверки Blender API: `save_as_mainfile(copy=True)` во временный путь, затем упаковка snapshot в отдельном background Blender process. Если этот оператор меняет пользовательское состояние, fallback — требовать сохранённый файл и копировать его.

### FR-2. Сбор зависимостей

Аддон должен обнаруживать и классифицировать:

- images и UDIM tiles;
- fonts;
- movie clips и sounds;
- linked `.blend` libraries;
- volumes/VDB;
- Alembic/USD caches;
- simulation/point caches;
- Geometry Nodes bake directories;
- custom color management/OCIO, если используется;
- add-ons и custom render engines, необходимые сцене.

Статусы ресурса:

- `included`;
- `packed_in_blend`;
- `missing`;
- `unsupported`;
- `external_manual_action_required`.

Missing обязательный ресурс блокирует full render, но может разрешать test render после явного подтверждения.

### FR-3. Безопасная упаковка

- Все файлы копируются в staging directory.
- Архив содержит только файлы staging directory.
- Запрещены абсолютные пути, `..`, symlinks и special files.
- Устанавливаются лимиты числа файлов, общего размера и compression ratio.
- Создаётся `package_manifest.json` с относительными путями, размерами и SHA-256.
- ZIP строится background worker, чтобы Blender UI не зависал.
- Отмена упаковки удаляет только временный staging текущего job.

### FR-4. Job protocol

- Протокол имеет `protocol_version`.
- `job.json` после публикации неизменяем.
- Credentials и токены никогда не входят в manifest.
- Notebook отклоняет неизвестную major-версию протокола.
- Add-on показывает понятное сообщение при несовместимости.

### FR-5. Передача

Manual mode:

- показывает готовый ZIP и его checksum;
- открывает notebook;
- принимает result ZIP через file picker.

Synced folder mode:

- пишет job atomically через временное имя;
- считает job опубликованным только после появления marker `READY`;
- не полагается только на размер файла во время синхронизации;
- проверяет checksum после обратной синхронизации.

Direct Drive API mode:

- использует resumable upload для больших файлов;
- не запрашивает полный `drive` scope без отдельного решения;
- retries имеют exponential backoff и не создают дубликаты job;
- пользователь видит объём и прогресс передачи.

### FR-6. Colab handoff

- Аддон открывает только официальный URL notebook из этого репозитория.
- Job package не должен передаваться через query string.
- Пользователь явно запускает notebook и выдаёт Google permissions.
- Notebook находит job по folder/job id либо принимает ZIP вручную.
- Версия notebook worker записывается в status.

### FR-7. Статусы и восстановление

Обязательные состояния:

```text
DRAFT
  -> CHECKING
  -> BLOCKED | READY_TO_PACKAGE
  -> PACKAGING
  -> READY_TO_TRANSFER
  -> TRANSFERRING
  -> WAITING_FOR_COLAB
  -> PREFLIGHT
  -> RENDERING
  -> PARTIAL | COMPLETE | FAILED
```

Дополнительные локальные состояния: `IMPORTING`, `IMPORTED`, `STOPPED_WATCHING`.

- Add-on владеет request/package файлами.
- Colab worker владеет status/log/result файлами.
- Два процесса не изменяют один и тот же manifest.
- `status.json` содержит монотонный `revision`.
- После reconnect add-on восстанавливает job list из локального index и job folders.
- `PARTIAL` считается нормальным восстанавливаемым состоянием.

### FR-8. Получение результатов

- Проверяется `result_manifest.json` и checksum каждого скачанного файла.
- Неполная последовательность не объявляется завершённой.
- Existing local files не перезаписываются без выбранной политики.
- Image sequence сортируется по frame number из manifest, а не только по имени.
- FPS VSE strip берётся из job metadata.
- EXR/multilayer EXR сохраняются без преобразования.
- MP4 является дополнительным artifact; source image sequence не удаляется автоматически.

### FR-9. Логи и поддержка

- Локальный log не содержит tokens.
- Пользователь может экспортировать support bundle.
- Support bundle содержит версии, manifest, статусы и очищенный log, но не `.blend` и не assets по умолчанию.
- Любая отправка support bundle наружу выполняется только после явного действия пользователя.

## 9. Job protocol v1

### Структура папки

```text
BlendToColab/
└── jobs/
    └── <job-id>/
        ├── request/
        │   ├── job.json
        │   ├── package_manifest.json
        │   ├── project.zip
        │   └── READY
        ├── worker/
        │   ├── status.json
        │   ├── preflight.json
        │   └── render.log
        └── result/
            ├── result_manifest.json
            ├── frames/
            ├── preview/
            └── video/
```

### Минимальный `job.json`

```json
{
  "protocol_version": "1.0",
  "job_id": "uuid",
  "created_at": "RFC3339 timestamp",
  "addon_version": "0.1.0",
  "project": {
    "display_name": "scene-name",
    "archive": "project.zip",
    "sha256": "hex",
    "size_bytes": 0
  },
  "blender": {
    "source_version": "5.2.1",
    "requested_version": "5.2.1"
  },
  "render": {
    "mode": "saved_range",
    "start": 1,
    "end": 250,
    "step": 1,
    "overwrite": false,
    "use_saved_settings": true,
    "overrides": {}
  },
  "destination": {
    "mode": "synced_folder"
  }
}
```

Полная JSON Schema должна быть создана перед реализацией аддона. Поля добавляются обратно совместимо внутри minor-версии; удаление или изменение смысла требует новой major-версии.

### Минимальный `status.json`

```json
{
  "protocol_version": "1.0",
  "job_id": "uuid",
  "revision": 1,
  "state": "RENDERING",
  "updated_at": "RFC3339 timestamp",
  "worker_version": "0.1.0",
  "progress": {
    "completed_frames": 84,
    "total_frames": 250,
    "current_frame": 85
  },
  "device": {
    "backend": "OPTIX",
    "name": "Tesla T4"
  },
  "message": "Rendering frame 85",
  "error": null
}
```

## 10. Техническая архитектура

### Компоненты Blender extension

```text
addon/blend_to_colab/
├── blender_manifest.toml
├── __init__.py
├── preferences.py
├── properties.py
├── operators/
│   ├── check_scene.py
│   ├── create_job.py
│   ├── open_colab.py
│   ├── refresh_status.py
│   └── import_results.py
├── services/
│   ├── scene_probe.py
│   ├── snapshot.py
│   ├── packager.py
│   ├── job_store.py
│   ├── transport.py
│   └── result_importer.py
├── ui/
│   └── render_panel.py
└── workers/
    ├── package_worker.py
    └── transfer_worker.py
```

### Общий protocol layer

```text
protocol/
├── job.schema.json
├── status.schema.json
├── result.schema.json
└── README.md
```

Notebook и add-on используют одинаковые schemas и fixtures. Protocol layer не импортирует `bpy` или `google.colab`.

### Почему нужны background workers

ZIP больших сцен, hashing и network transfer не должны блокировать Blender UI. Долгие операции запускаются отдельным процессом. Основной Blender process:

- создаёт команду;
- читает progress file через timer;
- обновляет UI;
- не обращается к `bpy` из background thread.

Для максимальной совместимости worker можно запускать отдельным Blender background process через `bpy.app.binary_path --background --factory-startup --python ...`. Это тяжелее отдельного Python, но не зависит от системного Python пользователя.

### Transport interface

```text
prepare(job)
publish(job)
poll(job) -> status
fetch(job) -> result paths
cancel_local(job)
```

Реализации:

- `ManualZipTransport` — MVP;
- `SyncedFolderTransport` — V1;
- `GoogleDriveTransport` — V1.5;
- `ColabEnterpriseTransport` — V2.

## 11. Безопасность, приватность и разрешения

### Исходный проект

- Аддон никогда не отправляет данные без нажатия **Create/Send Job**.
- До отправки показываются список и общий объём включённых файлов.
- Пользователь может исключить необязательный ресурс.
- Secrets-подобные файлы (`.env`, credentials, SSH keys) блокируются или требуют отдельного явного подтверждения.
- Абсолютные локальные пути не попадают в публичные логи.

### Blender permissions

Для Blender Extension manifest потребуется:

```toml
[permissions]
files = "Package project assets and import rendered results"
```

`network` добавляется только в Direct Drive API/managed provider сборку:

```toml
network = "Transfer user-approved render jobs and results"
```

Перед каждой сетевой операцией проверяется `bpy.app.online_access`.

### OAuth

- Preferred scope: `https://www.googleapis.com/auth/drive.file`.
- Полный `drive` или `drive.readonly` scope запрещён без отдельного privacy/security решения.
- Client secret desktop application не считается серверным секретом, но OAuth configuration и verification всё равно нужны для публичного распространения.
- Refresh token нельзя хранить в `.blend`, preferences, job package или plaintext log.
- Session-only auth предпочтительна для первого Direct API prototype.

### Colab

- Notebook выполняет код с доступом к файлам пользователя; UI должен объяснять разрешение Drive.
- Job не должен содержать access/refresh tokens.
- Не использовать недокументированные Colab APIs.
- Не использовать методы обхода timeout/anti-abuse.

## 12. Совместимость и распространение

### Blender

Рекомендуемая начальная поддержка:

- Blender 4.5 LTS;
- Blender 5.2 LTS;
- Windows x64 как первый проверенный desktop target;
- macOS/Linux после прохождения packaging/sync tests.

`blender_manifest.toml`:

- schema `1.0.0`;
- type `add-on`;
- `blender_version_min = "4.5.0"`;
- semantic versioning;
- SPDX license;
- объявленные `files`/`network` permissions.

### Распространение

Основной реалистичный канал первой версии — GitHub Releases с установкой ZIP через Blender Extensions preferences.

Публикация на официальной Blender Extensions Platform не гарантируется: правила требуют self-contained extension и могут не принять продукт, основная функция которого зависит от внешнего Colab/Drive сервиса. Перед публикацией нужен отдельный moderation preflight.

### Лицензия

До реализации необходимо выбрать лицензию всего репозитория. Для открытого распространения проекта рекомендована MIT, но Blender Extension Platform может иметь дополнительные требования к лицензии пакета и зависимостей; это нужно перепроверить перед публикацией.

## 13. Состояния ошибок и ожидаемое поведение

| Ситуация | Поведение |
| --- | --- |
| Сцена не сохранена | Блокировать job или создавать доказанно безопасный snapshot-copy |
| Нет active camera | Блокировать camera render, предложить исправить сцену |
| Missing texture/cache | Показать точный путь и уровень критичности до упаковки |
| Custom engine/add-on не поддерживается Colab | Блокировать full render, не подменять engine молча |
| Недостаточно локального места | Остановиться до snapshot/ZIP |
| Sync-folder не найден | Сохранить job локально, предложить выбрать папку заново |
| Package ещё синхронизируется | Не публиковать `READY` преждевременно |
| Colab не запущен | Состояние `WAITING_FOR_COLAB`, без ложной ошибки |
| Runtime оборвался | `PARTIAL`, сохранить готовые кадры и дать Restart instructions |
| Версия protocol несовместима | Показать требуемые версии notebook/add-on |
| Result checksum неверен | Не импортировать повреждённый файл |
| Кадры неполные | Показать missing frame list, не объявлять `COMPLETE` |
| Blender закрывается во время worker | Worker корректно завершить или оставить recoverable job |
| Пользователь отменил ожидание | Не удалять remote job/result |
| Existing VSE strip | Создать новый strip с уникальным именем, не заменять существующий |

## 14. Критерии приёмки

### MVP

- [ ] Add-on устанавливается ZIP-пакетом в поддерживаемых Blender versions.
- [ ] Scene Check не изменяет dirty state и содержимое сцены.
- [ ] Создание job не изменяет и не перезаписывает source `.blend`.
- [ ] Package включает все поддерживаемые найденные зависимости.
- [ ] Missing обязательные assets обнаруживаются до ZIP.
- [ ] `job.json` проходит JSON Schema validation.
- [ ] Notebook принимает созданный package без ручного редактирования paths.
- [ ] Result ZIP проверяется по manifest/checksums.
- [ ] Still загружается как Image datablock.
- [ ] Image sequence добавляется в VSE с правильным порядком и FPS.
- [ ] Ошибка не оставляет Blender UI заблокированным.

### V1 Synced Folder

- [ ] Add-on публикует job только после полной локальной записи package.
- [ ] Notebook видит опубликованный job после Drive sync.
- [ ] Add-on видит `PREFLIGHT`, `RENDERING`, `PARTIAL`, `COMPLETE`, `FAILED`.
- [ ] После перезапуска Blender job остаётся в локальном списке.
- [ ] После обрыва Colab повторный запуск рендерит только missing frames.
- [ ] Complete result автоматически обнаруживается после локальной синхронизации.
- [ ] Повреждённый или частично синхронизированный result не импортируется.

### V1.5 Direct Drive API

- [ ] Запрашивается только утверждённый минимальный OAuth scope.
- [ ] Upload большого ZIP возобновляется после сетевого обрыва.
- [ ] Retry не создаёт дубликаты job.
- [ ] Tokens отсутствуют в `.blend`, ZIP, manifest и logs.
- [ ] Logout/revoke удаляет локальные credentials.
- [ ] Проверено, какие result files доступны через `drive.file` после создания notebook worker.

## 15. Стратегия проверки

### Unit tests без Blender

- schemas и protocol compatibility;
- job state transitions;
- ZIP path safety;
- checksums;
- frame ordering и missing-frame detection;
- filename/path normalization;
- support bundle redaction;
- sync marker rules.

### Blender integration tests

- temporary snapshot и неизменность source file hash;
- dirty state до/после Scene Check/Create Job;
- dependency discovery fixtures;
- panel/operator registration;
- cancel packaging;
- Image/VSE import;
- восстановление job index после restart.

### End-to-end tests

- Blender 4.5 LTS + notebook + Cycles still;
- Blender 5.2 LTS + notebook + EEVEE sequence;
- texture/UDIM/linked library/VDB/cache projects;
- Unicode и пробелы в путях;
- manual ZIP round-trip;
- Drive sync round-trip;
- runtime interruption/resume;
- partial/corrupted package/result;
- Windows first, затем macOS/Linux.

## 16. Метрики успеха без телеметрии

Телеметрия по умолчанию не добавляется. Метрики получают из контролируемых тестовых прогонов и локального job history, который остаётся у пользователя.

### Основная метрика

Доля тестовых job, прошедших полный путь `Create Job -> Complete -> Import` без ручного исправления файлов или путей.

Baseline отсутствует; первые end-to-end прогоны формируют baseline.

### Контрметрики

- число случаев изменения source `.blend`: допустимое значение `0`;
- число повторно отрендеренных подтверждённых кадров после resume: допустимое значение `0` по default policy;
- число job, ошибочно объявленных `COMPLETE`: допустимое значение `0`;
- количество обязательных ручных действий в Free Colab flow;
- размер и длительность упаковки относительно исходного проекта.

### Локальные события job history

Минимально:

| Событие | Когда записывается | Поля без персональных данных |
| --- | --- | --- |
| `scene_check_finished` | завершён анализ | result, warning/error counts, duration |
| `package_finished` | ZIP готов | result, size, file count, duration |
| `job_published` | появился READY | transport, package size |
| `job_status_changed` | изменилось состояние | old/new state, revision |
| `result_verified` | checksums проверены | result, file count, total size |
| `result_imported` | выполнен импорт | artifact type, frame count |

Имена сцен, пути, Google account, содержимое `.blend` и asset names в аналитику не отправляются. Если позже появится внешняя telemetry, перед ней обязателен отдельный privacy review и явный opt-in.

## 17. Порядок реализации относительно notebook v2

Аддон нельзя начинать с upload UI до стабилизации notebook job model. Правильный порядок:

1. Исправить P0/P1 notebook из `ANALOG_AUDIT.md`.
2. Реализовать notebook resumable jobs и manifest.
3. Зафиксировать protocol v1 и JSON Schemas.
4. Создать минимальный Blender extension: Scene Check + Manual ZIP.
5. Провести end-to-end round-trip.
6. Добавить Synced Folder transport.
7. После стабильной V1 отдельно решить OAuth/Direct Drive API.
8. Managed provider добавлять только при подтверждённой потребности.

Так notebook остаётся самостоятельным продуктом, а аддон становится удобным клиентом того же стабильного протокола, а не второй несовместимой реализацией.

## 18. Открытые решения

Не блокируют текущую доработку notebook, но должны быть решены до соответствующей фазы:

1. **Snapshot несохранённой сцены.** Подтвердить тестами, что `save_as_mainfile(copy=True)` не меняет пользовательский filepath, dirty state и данные.
2. **Google Drive for Desktop как основная V1-зависимость.** Проверить UX на Windows/macOS и поведение больших ZIP.
3. **Direct Drive access.** Провести spike для `drive.file`, folder access и notebook-created files.
4. **Официальная Blender Extensions Platform.** Получить подтверждение допустимости внешнего Colab/Drive dependency или распространять extension самостоятельно.
5. **Лицензия проекта.** Выбрать до публикации первой сборки.
6. **Import default.** Рекомендация: download-only по умолчанию, VSE/Image import только по кнопке.
7. **CPU fallback.** Рекомендация: не запускать автоматически, требовать явное подтверждение.

## 19. Источники и ограничения анализа

- [Google Colab FAQ](https://research.google.com/colaboratory/faq.html) — ограничения managed runtime, GPU, lifetime и запрещённые сценарии.
- [Colab Enterprise documentation](https://docs.cloud.google.com/colab/docs) — документированный API/managed execution относится к Enterprise-продукту.
- [Colab Enterprise notebook executions](https://docs.cloud.google.com/colab/docs/schedule-notebook-run) — программное управление execution jobs и результатами.
- [Google Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth) — минимальный `drive.file` scope и требования OAuth verification.
- [Google Drive resumable uploads](https://developers.google.com/workspace/drive/api/guides/manage-uploads) — восстановление больших передач.
- [Blender Extension schema](https://developer.blender.org/docs/features/extensions/schema/1.0.0/) — manifest, versions и permissions.
- [Blender add-on guidelines](https://developer.blender.org/docs/handbook/extensions/addon_guidelines/) — online access, self-contained package и local storage.
- [Blender extension moderation guidelines](https://developer.blender.org/docs/features/extensions/moderation/guidelines/) — network permission, `bpy.app.online_access`, I/O и background-work ограничения.

На дату документа не выполнялись:

- prototype Blender add-on;
- эксперимент с snapshot несохранённой сцены;
- Google Drive for Desktop round-trip;
- OAuth/Drive API spike;
- Colab Enterprise execution;
- публикация в Blender Extensions Platform.

Любые утверждения об этих интеграциях до реального теста считаются архитектурными предположениями, а не подтверждённым поведением.
