# Аудит аналогов и план развития Blend-to-Colab

Статус: архитектурная база до начала интеграции

Дата проверки: 2026-09-12
Область: `render_blender_in_colab.ipynb`, открытые Colab-ноутбуки для Blender и действующие render-farm сервисы

## 1. Краткий вывод

Проект уже имеет хорошее и редкое базовое правило: он использует подготовленный `.blend` как источник истины и не сохраняет изменения обратно в исходный файл. Эту модель нужно сохранить.

Главный технический дефект текущей версии — проверка `device.type == "GPU"`. Cycles обозначает вычислительные устройства типами бэкендов (`CUDA`, `OPTIX`, `HIP`, `METAL`, `ONEAPI`, `CPU`), поэтому существующая проверка может не найти доступную NVIDIA GPU и перевести рендер на CPU. Это приоритет P0.

Самый сильный прямой аналог — `ynshung/blender-colab`: он актуализирован под Blender 5.2 и предоставляет несколько источников проекта и способов выдачи результата. Однако он принудительно выбирает Cycles, использует хрупкие shell-команды и не решает восстановление после обрыва runtime. Его функции стоит воспроизвести независимо, но его архитектуру целиком переносить не следует.

Целевая версия проекта должна объединить:

- простой Colab-интерфейс и несколько источников проекта;
- автоматический preflight сцены, оборудования, ресурсов и выходных настроек;
- корректный выбор GPU с доказательным отчётом;
- рендер по диапазонам с продолжением по уже готовым кадрам;
- безопасную работу с ZIP и загрузками;
- локальный staging и контролируемую синхронизацию с Drive;
- журнал, manifest и итоговый отчёт;
- сохранение исходной сцены как default-поведения;
- тестируемое ядро при сохранении самодостаточного ноутбука.

## 2. Проверенные источники

### Локальный проект

- `README.md`
- `render_blender_in_colab.ipynb`
- Git history: `50e7344`, `b242c1f`, `386e705`

### Прямые кодовые аналоги

| Проект | Проверенная ревизия | Последнее изменение | Лицензия | Оценка |
| --- | --- | --- | --- | --- |
| [ynshung/blender-colab](https://github.com/ynshung/blender-colab) | `91ea6be` | 2026-08-04 | MIT | Актуальный главный аналог |
| [fastass-ez/cloud_rendering_gc](https://github.com/fastass-ez/cloud_rendering_gc) | `8705ef5` | 2024-01-27 | Лицензия не найдена | Источник UX-идей, код не копировать |
| [drmichaeldouglass/blenderGoogleGPU](https://github.com/drmichaeldouglass/blenderGoogleGPU) | `0bd60bb` | 2022-11-02 | MIT | Исторический пример, технически устарел |
| [methsilusenavirathne/Blender_Cloud_Rendering](https://github.com/methsilusenavirathne/Blender_Cloud_Rendering) | `f2a166d` | 2022-05-31 | Лицензия не найдена | Полезен только preflight ресурсов |

Ревизии проверены локальным shallow clone. Это статический аудит исходников; запуск этих ноутбуков в Colab не выполнялся.

### Сервисы-аналоги по пользовательскому результату

- [SheepIt](https://www.sheepit-renderfarm.com/home): бесплатная распределённая ферма, браузерное наблюдение, Cycles/EEVEE/Workbench, актуальные версии Blender.
- [Drop & Render](https://blendercloudrender.com/blender-render-farm): проверка сцены, подбор версий Blender и add-on, сбор ресурсов, мониторинг, повторная отправка отдельных кадров, возобновляемая доставка результатов.
- [RenderJuice](https://www.renderjuice.com/blender): `.blend`/ZIP, автоматическое сопоставление версии, проверка проекта, runtime-overrides без изменения оригинала, crash recovery, выбор кадров/камер/view layers и подготовка MP4.
- [Google Colab FAQ](https://research.google.com/colaboratory/faq.html): ресурсы, GPU и длительность runtime не гарантированы; Drive рекомендуют использовать с уменьшением количества мелких операций ввода-вывода.
- [Blender LTS](https://www.blender.org/download/lts/): на дату аудита поддерживаются Blender 5.2 LTS и 4.5 LTS; 4.2 LTS уже относится к предыдущим выпускам.

Возможности коммерческих сервисов зафиксированы по их публичной документации и являются заявлениями поставщиков, а не результатом нашего независимого нагрузочного теста.

## 3. Текущее устройство проекта

### Точка входа

Вся логика находится в `render_blender_in_colab.ipynb`. Ноутбук содержит шесть исполняемых ячеек:

1. пользовательские настройки;
2. скачивание и распаковка точной версии Blender;
3. загрузка `.blend` или ZIP в `/content/blender_project`;
4. подключение Google Drive;
5. создание Blender Python-скрипта для GPU и запуск рендера;
6. проверка результатов и необязательное скачивание файла/ZIP.

### Текущий поток данных

`браузерная загрузка -> /content/blender_project -> Blender background process -> Google Drive/<timestamp> -> необязательное скачивание`

### Сильные стороны

- Малый объём и понятный линейный сценарий.
- Точная версия Blender задаётся явно.
- Поддерживаются `.blend` и ZIP с относительной структурой ресурсов.
- Выход каждого запуска изолирован timestamp-папкой.
- Настройки камеры, качества, формата и движка не переопределяются командой рендера.
- `subprocess.run(..., check=True)` не маскирует ненулевой exit code Blender.
- Ноутбук и все шесть Python-ячеек синтаксически корректны.

## 4. Матрица возможностей

Обозначения: `да` — реализовано; `частично` — есть ограниченная или хрупкая реализация; `нет` — отсутствует.

| Возможность | Наш проект | ynshung | fastass | drmichael | Render farms |
| --- | --- | --- | --- | --- | --- |
| Прямая загрузка `.blend` | да | да | нет | нет | да |
| ZIP с ресурсами | да | да | нет | нет | да |
| Проект из Google Drive | нет | да | да | да | не применимо |
| Проект по URL | нет | да | нет | нет | обычно нет |
| Проект-папка без ZIP | нет | да | да | да | через упаковщик/add-on |
| Произвольная версия Blender | да | да | частично | нет | авто/каталог |
| Автоопределение версии `.blend` | нет | нет | нет | нет | да |
| Preflight RAM/disk/GPU | нет | GPU | GPU | частично | да |
| Preflight сцены и ассетов | нет | нет | нет | нет | да |
| Сохранение движка из `.blend` по умолчанию | да | нет, принудительно Cycles | по выбору | нет, Cycles | да |
| Корректный авто-выбор GPU | нет, дефект | частично | вручную | вручную | да |
| Пользовательский диапазон кадров | нет | да | да | вручную | да |
| Продолжение после обрыва | нет | нет | нет | нет | да |
| Пропуск готовых кадров | нет | нет | нет | нет | да |
| Сохранённый лог/manifest | нет | нет | нет | нет | да |
| Локальный staging перед Drive | нет | да для части режимов | нет | нет | внутренний staging |
| ZIP/прямое скачивание | да | да | нет | нет | да |
| Preview/test frame | нет | нет | нет | вручную | да |
| Runtime-overrides без изменения оригинала | только GPU/output | нет | нет | нет | да |
| Камера/view layer | из сцены | из сцены | из сцены | из сцены | выбор |
| Сборка видео из кадров | только если сцена сама пишет видео | нет | нет | нет | частично |

## 5. Находки аудита текущего ноутбука

### P0 — исправить до расширения функциональности

#### P0.1. GPU может никогда не активироваться

Текущий код отбирает устройства выражением `device.type == "GPU"`. В Cycles `scene.cycles.device` принимает общее значение `GPU`, но `CyclesDeviceSettings.type` содержит вычислительный бэкенд — например `CUDA` или `OPTIX`. Эти два уровня нельзя смешивать.

Последствие: ноутбук может написать `No Cycles GPU detected` и запустить дорогой CPU-рендер при доступной T4/L4/A100.

Требуемое исправление:

- выполнить `refresh_devices()` или совместимый fallback;
- по очереди проверить `OPTIX`, затем `CUDA` для Colab NVIDIA;
- получить устройства выбранного типа;
- включить только выбранные GPU и, опционально, CPU;
- установить `scene.cycles.device = "GPU"` для всех Cycles-сцен;
- вывести имена и типы реально активированных устройств;
- завершать preflight ошибкой либо требовать явного разрешения перед CPU fallback.

#### P0.2. Нет восстановления после завершения runtime

Рендер всей анимации запускается одной командой `-a`, а новый запуск всегда создаёт новую timestamp-папку. При обрыве Colab готовые кадры могут сохраниться, но штатного способа продолжить тот же job и пропустить их нет.

Требуемое исправление:

- стабильный `JOB_NAME`/job id, задаваемый пользователем или вычисляемый из проекта и конфигурации;
- manifest в Drive;
- вычисление отсутствующих кадров перед рендером;
- разбиение последовательности на непрерывные диапазоны/chunks;
- повторный запуск только отсутствующих диапазонов;
- режим `OVERWRITE_EXISTING = False` по умолчанию.

### P1 — надёжность, безопасность и соответствие среде

#### P1.1. Нет безопасной проверки ZIP

`extractall()` вызывается без проверки числа файлов, суммарного распакованного размера, подозрительных путей и доступного места. Риск особенно возрастёт после добавления URL.

Нужно проверять:

- отсутствие абсолютных путей и выхода через `..`;
- отсутствие специальных/символьных файлов;
- лимит количества entries;
- лимит общего uncompressed size и коэффициента сжатия;
- свободное место до распаковки;
- ровно выбранный `.blend`, а не обязательно ровно один во всём архиве.

#### P1.2. Не проверяется целостность Blender

Архив скачивается с официального HTTPS-домена, но checksum не сверяется. В официальных каталогах Blender присутствуют version-specific `.sha256` файлы.

Нужно скачать checksum, проверить SHA-256 до распаковки и не использовать частичный архив после неудачной загрузки.

#### P1.3. Нет preflight сцены

До длинного рендера не проверяются:

- версия файла и совместимость выбранного Blender;
- render engine, активная сцена, камера и frame range;
- разрешение, samples, формат и ожидаемый шаблон файлов;
- отсутствующие внешние ресурсы и linked libraries;
- simulation caches;
- File Output nodes и дополнительные выходы;
- add-ons/engine, недоступные в официальной сборке;
- приблизительный объём результата и свободное место.

Preflight должен запускать Blender в background-режиме отдельным read-only probe script и писать JSON-отчёт.

#### P1.4. Google Drive обязателен и используется как render target

Обязательный `drive.mount()` делает весь сценарий зависимым от OAuth/Drive. Рендер непосредственно в mounted Drive создаёт множество мелких записей; Colab рекомендует минимизировать такие операции.

Рекомендуемая модель:

- Drive остаётся рекомендуемым durable storage;
- рендерить chunk локально в `/content/output/<job>`;
- после успешного chunk атомарно копировать готовые кадры и обновлять manifest в Drive;
- разрешить режим без Drive с прямым скачиванием;
- не удалять уже подтверждённые результаты при повторном запуске.

#### P1.5. Нет устойчивого журнала и диагностики

Лог Blender виден только в выводе ячейки. После runtime termination он теряется, а факт наличия файлов не доказывает полноту рендера.

Нужно сохранять:

- `preflight.json`;
- `job.json` с конфигурацией и fingerprint проекта;
- `render.log` с потоковым выводом subprocess;
- `frames.json` или manifest со статусом каждого диапазона;
- `summary.json` с устройством, временем, exit code и найденными результатами.

#### P1.6. Default Blender устарел

По состоянию на дату аудита default — `4.2.0`, тогда как поддерживаемые LTS — 5.2.x и 4.5.x. При этом всегда использовать самый новый Blender тоже неправильно: воспроизводимость требует совпадения с версией проекта.

Нужно:

- попытаться прочитать версию из заголовка `.blend`, включая сжатый файл;
- предложить соответствующий активный LTS/точную версию;
- оставить ручной override;
- не открывать файл более старым Blender;
- показывать предупреждение при version drift.

### P2 — улучшение UX и производительности

- Colab Forms (`#@param`) вместо ручного редактирования нескольких ячеек.
- Источники `upload`, `drive_file`, `drive_folder`, `url`.
- Режимы `saved_range`, `single`, `custom_range`, `missing_only`, `preview`.
- Настраиваемые `start`, `end`, `step`, `chunk_size`.
- Default `USE_SAVED_SETTINGS = True`; advanced overrides только при явном включении.
- Опциональные overrides: resolution percentage, samples, camera, scene, view layer, output format и denoiser.
- Предварительный test frame перед полной анимацией.
- Preview последнего изображения в ноутбуке.
- Сборка MP4 из готовой image sequence через `ffmpeg` как отдельный post-process; не рендерить длинную анимацию напрямую в MP4 по умолчанию.
- Оценка времени после test frame и оценка требуемого места.
- Кэш архива Blender в Drive как opt-in; локальный runtime cache остаётся первым выбором.
- Понятное итоговое резюме: что рендерилось, на каком устройстве, какие кадры готовы и где лежат результаты.

## 6. Что заимствовать у каждого аналога

### ynshung/blender-colab

Воспроизвести независимо:

- четыре источника проекта;
- Colab Forms;
- custom frame range;
- несколько вариантов выдачи результата;
- ZIP нескольких кадров;
- видимую информацию о выделенной GPU;
- список стабильных/LTS-версий плюс custom input.

Не переносить:

- принудительный `-E CYCLES`;
- shell interpolation пользовательских путей и URL;
- `rm`, `cp`, `wget`, `unzip` через notebook magics для основной логики;
- устаревший перебор `CUDA`, `OPENCL`, `NONE`;
- удаление/переустановку `libtcmalloc` без доказанной необходимости;
- удаление output-папок без job-aware защиты.

### fastass-ez/cloud_rendering_gc

Воспроизвести независимо:

- интерактивный выбор single/animation;
- явный start/end;
- возможность использовать уже установленный Blender;
- понятный GPU information step.

Не переносить:

- длинные `input()`-меню;
- жёсткий устаревший каталог версий;
- `sudo` и непроверенные shell-переменные;
- принудительную смену движка;
- общую папку Output с риском коллизий.

### drmichaeldouglass/blenderGoogleGPU

Воспроизвести независимо:

- диагностический `nvidia-smi`;
- идею кэшировать Blender между runtime;
- отдельные понятные примеры Cycles/EEVEE в документации.

Не переносить:

- несовпадающие версии URL/папки архива;
- закомментированные команды как пользовательский интерфейс;
- фиксированные пути и frame range;
- старый `GPU.py`, рассчитанный на прежний API Blender.

### methsilusenavirathne/Blender_Cloud_Rendering

Воспроизвести независимо:

- отчёт RAM, disk и GPU перед работой;
- явное напоминание о baked simulation data.

Не переносить:

- двойное монтирование Drive;
- массивные embedded outputs notebook;
- установку полного набора dev-библиотек;
- старые Blender 2.x/3.x presets как default.

### SheepIt, Drop & Render, RenderJuice

Адаптировать к одному Colab runtime:

- preflight и project validation;
- source-of-truth проект плюс runtime-only overrides;
- job manifest и повторная отправка пропущенных кадров;
- version matching;
- диагностика add-ons, assets, caches, cameras и view layers;
- test frame, estimation и итоговый job report;
- наблюдаемость по кадрам/chunks;
- crash recovery;
- безопасная упаковка проекта как возможный будущий Blender add-on.

Не обещать и не имитировать:

- параллельную ферму из сотен GPU;
- гарантированное оборудование;
- фоновую работу вне ограничений Colab;
- точное совпадение коммерческой инфраструктуры и поддержки add-ons.

## 7. Рекомендуемая архитектура версии 2

### Репозиторий

```text
.
├── AGENTS.md
├── README.md
├── render_blender_in_colab.ipynb   # самодостаточный пользовательский интерфейс
├── src/
│   └── blend_to_colab.py           # тестируемое ядро без обязательного google.colab import
├── tools/
│   └── build_notebook.py           # воспроизводимо встраивает ядро в notebook
├── tests/
│   ├── test_archive_safety.py
│   ├── test_config.py
│   ├── test_frame_plan.py
│   ├── test_manifest.py
│   └── test_versioning.py
└── docs/
    └── ANALOG_AUDIT.md
```

Notebook должен оставаться самостоятельным: пользователь открывает его из GitHub и не обязан клонировать пакет. При этом committed notebook генерируется из тестируемого Python-источника, а CI проверяет отсутствие расхождения.

### Runtime-компоненты

- `RenderConfig`: нормализованная конфигурация Colab Forms.
- `ProjectSource`: direct upload, Drive file/folder или HTTPS URL.
- `ProjectWorkspace`: безопасный staging и выбор `.blend`.
- `BlenderInstaller`: версия, официальный URL, checksum, cache.
- `BlenderProbe`: read-only JSON-инспекция сцены и ресурсов.
- `DeviceSelector`: Blender/Cycles discovery, backend selection и подтверждение.
- `FramePlanner`: диапазоны, chunks, missing frames, overwrite policy.
- `JobStore`: Drive/local manifest, logs и atomic updates.
- `RenderRunner`: subprocess без shell, streaming log, cancellation-safe state.
- `ResultCollector`: проверка ожидаемых выходов, sync, ZIP, preview, MP4.

### Поток управления

```text
Config
  -> acquire project
  -> validate/unpack locally
  -> detect/select Blender version
  -> download + verify Blender
  -> probe scene + resources + devices
  -> show preflight and require explicit run cell
  -> calculate missing frame chunks
  -> render each chunk locally
  -> sync successful outputs + manifest to durable storage
  -> verify completeness
  -> optional ZIP/MP4/preview
  -> final report
```

Preflight и запуск рендера должны оставаться разными ячейками: пользователь видит движок, GPU, кадры, разрешение, missing assets и ожидаемое место до расходования GPU-времени.

## 8. Последовательность интеграции

### Фаза 1 — correctness и safety

1. Исправить Cycles device discovery.
2. Добавить проверку GPU/CPU fallback policy.
3. Ввести безопасную конфигурацию и валидацию значений.
4. Добавить безопасную распаковку ZIP.
5. Проверять SHA-256 Blender.
6. Обновить default/presets до действующих LTS, сохранив custom version.

Критерий выхода: test Cycles scene в реальном Colab подтверждает имя GPU и GPU backend в Blender log; unit tests покрывают config/archive/version logic.

### Фаза 2 — preflight

1. Добавить Blender probe JSON.
2. Проверять сцену, камеру, диапазон, output, внешние файлы, add-ons и caches.
3. Выводить RAM/disk/GPU/VRAM.
4. Добавить test frame и оценку времени/места.

Критерий выхода: проблемы проекта выявляются до full render; probe не сохраняет `.blend`.

### Фаза 3 — resumable jobs

1. Добавить job id и manifest.
2. Планировать missing frames и chunks.
3. Рендерить локально и синхронизировать подтверждённые результаты.
4. Сохранять streaming log и summary.
5. Возобновлять тот же job после нового runtime.

Критерий выхода: искусственно прерванная анимация продолжает работу без повторного рендера готовых кадров.

### Фаза 4 — источники и результаты

1. Добавить Drive file/folder и HTTPS URL.
2. Добавить режим без Drive.
3. Добавить ZIP, preview и MP4 post-process.
4. Поддержать несколько `.blend` через явный выбор.

Критерий выхода: каждый источник и destination проходят smoke test; пользовательские строки не исполняются shell.

### Фаза 5 — advanced runtime overrides

1. Оставить saved settings default.
2. Добавить opt-in overrides для кадров, resolution percentage, samples, camera, scene, view layer, denoiser и output.
3. Печатать diff overrides до запуска.
4. Никогда не сохранять изменённый исходный `.blend`.

Критерий выхода: одинаковый проект даёт baseline без overrides; каждый override изолирован и отражён в manifest.

### Фаза 6 — упаковка, документация и release gate

1. Реализовывать Blender add-on только после стабилизации resumable job protocol; продуктовые требования и архитектура зафиксированы в [`BLENDER_ADDON_SPEC.md`](BLENDER_ADDON_SPEC.md).
2. Обновить README и troubleshooting.
3. Добавить лицензию проекта.
4. Добавить notebook build/check и unit tests в CI.
5. Выполнить матрицу реального Colab smoke testing.

## 9. Проверка и release gate

### Локальные автоматические проверки

- notebook — валидный JSON;
- все обычные Python cells парсятся;
- generated notebook совпадает с `src`;
- archive safety tests;
- version parser и URL construction tests;
- manifest atomicity и resume planning tests;
- пути с пробелами, Unicode и спецсимволами;
- отсутствие `shell=True` и shell interpolation пользовательских данных.

### Реальный Colab smoke matrix

Минимум:

| Сценарий | Проверка |
| --- | --- |
| Cycles + T4/L4 | Blender log показывает OPTIX/CUDA GPU |
| Cycles без GPU | понятный stop или подтверждённый CPU fallback |
| EEVEE | сохранённый engine не заменён |
| Still | ровно ожидаемые output-файлы |
| Animation image sequence | все кадры и manifest complete |
| Interrupted animation | missing-only resume |
| ZIP с текстурами | ресурсы найдены |
| Missing texture | preflight предупреждает до full render |
| Drive unavailable | local/direct-download path работает |
| Blender 4.5 LTS и 5.2 LTS | установка, probe и test frame |
| Compressed `.blend` | version detection/fallback работает |
| Несколько `.blend` | пользователь получает список для выбора |

### Негативные проверки

- ZIP traversal/zip bomb отклоняются до распаковки;
- неверная версия и несуществующий URL не оставляют partial install;
- недостаток disk space обнаруживается заранее;
- ненулевой exit code Blender сохраняется в summary;
- неполная последовательность не объявляется успешной;
- повторный запуск не перезаписывает готовые кадры без opt-in.

## 10. Лицензирование

Текущий проект не содержит LICENSE, что уже отражено в README. До интеграции стороннего кода нужно выбрать лицензию проекта.

- Код `ynshung/blender-colab` и `drmichaeldouglass/blenderGoogleGPU` имеет MIT-лицензию, но копирование требует сохранения copyright/license notices.
- У `fastass-ez/cloud_rendering_gc` и `methsilusenavirathne/Blender_Cloud_Rendering` лицензия в проверенных деревьях не найдена: код копировать нельзя.
- Реализации коммерческих render farms проприетарны; допустимо независимо реализовывать общие продуктовые идеи.

Рекомендация: реализовать функции самостоятельно на стандартной библиотеке Python и Blender API. Это уменьшит технический долг и лицензионную неопределённость.

## 11. Решения, которые следует сохранить

- Один понятный notebook остаётся главным пользовательским артефактом.
- Исходный `.blend` не изменяется и не сохраняется.
- Saved settings используются по умолчанию.
- Image sequence предпочтительнее прямого MP4 для длинной анимации.
- Drive — durable destination, но не единственный режим и не обязательный hot render filesystem.
- Результат считается успешным только после проверки ожидаемых файлов и manifest.
- Anti-idle JavaScript, SSH, remote desktop и обход ограничений Colab не входят в проект.
- Несколько аккаунтов или другие способы обхода лимитов Colab не поддерживаются.
- Бесплатный Colab остаётся user-started runtime; полностью автоматический запуск относится к отдельному платному provider mode.

## 12. Открытые продуктовые решения перед фазой 5

Они не блокируют фазы 1–4:

- Разрешать ли CPU fallback автоматически или только после явного opt-in. Рекомендация: явный opt-in.
- Нужны ли advanced overrides всем пользователям или отдельный «Advanced» блок. Рекомендация: отдельный блок, выключенный по умолчанию.
- Добавлять ли Blender-side Project Packer в этот репозиторий. Рекомендация: отдельный этап после notebook v2.
- Какую лицензию выбрать для проекта. Рекомендация для максимально простого открытого распространения: MIT.

## 13. Verification record

Выполнено 2026-09-12:

- просмотрены все ячейки локального notebook и README;
- проверен чистый Git status и история проекта;
- notebook успешно разобран как JSON;
- шесть code cells успешно разобраны Python AST;
- локально получены и просмотрены указанные ревизии четырёх публичных аналогов;
- проверены публичные страницы SheepIt, Drop & Render, RenderJuice, Blender LTS и Google Colab FAQ;
- подтверждено наличие официальных `.sha256` файлов рядом с Linux-архивами Blender 5.2.0/5.2.1.

Не выполнено:

- проверка больших файлов;
- сравнительный benchmark GPU.

Реально подтверждено в Google Colab T4 после аудита:

- Cycles GPU smoke test на Blender 5.2.1: `OPTIX` на `Tesla T4`;
- Drive OAuth и сохранение промежуточных/итоговых результатов;
- interrupted-animation для job `2e839139-d767-4d74-b873-dd4f2870318b`: после явного `Disconnect and delete runtime` чистая среда не содержала прежних Blender, source или staging-файлов, но восстановила job из Drive;
- missing-only resume: проверенные кадры 1–2 сохранены, отрендерены только кадры 3–4, SHA-256 исходного `.blend` не изменился;
- независимая проверка Drive: все кадры 1–4 существуют, совпадают по size/SHA-256, manifest/status/summary имеют `COMPLETE`, status revision равна 3.

Локально реализовано после аудита (Этап 3):

- protocol v1 с JSON Schemas для request, worker status и result manifest;
- immutable `job.json`, UUID v4, монотонная revision и recovery-переходы;
- chunked missing-only plan, atomic publication кадров/manifest/status, SHA-256 и streaming log/summary;
- unit/integration simulation interruption, resume и corruption repair.

Resume-поток подтверждён end-to-end для короткой временной Cycles-анимации; это не заменяет smoke matrix для крупных проектов, других движков и вариантов хранения.

Эти ограничения запрещают утверждать, что текущий notebook или любой сторонний notebook полностью работает в актуальном Colab только на основании статического аудита.
