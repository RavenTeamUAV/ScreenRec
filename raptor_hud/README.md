# NextVision Raptor 360 — HUD оператора

Інтерфейс оператора у стилі NextVision OmniViewerHD: відеопотік на весь екран,
нижня телеметрична панель та компас курсу. Телеметрія — через **MavLink**.

## Запуск макета (тестові дані)

**Windows** (з кореня репозиторію):
```bat
raptor_hud\setup_windows.bat   :: один раз — створює .venv і ставить залежності
raptor_hud\run_windows.bat     :: запуск
```

**macOS / Linux**:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r raptor_hud/requirements.txt
python -m raptor_hud.main
```

`F11` — повноекранний режим, `Esc`/`Q` — вихід. Налаштування підключення —
кнопка ⚙ у вікні. Потрібен Python 3.10–3.13.

## Запис відео на ПК

Кнопка **⏺** (праворуч угорі) або клавіша **`R`** — старт/стоп запису. Під час
запису згори по центру світиться індикатор **● REC mm:ss**.

- За замовчуванням — **чистий відеопотік без HUD**. У ⚙ можна увімкнути
  «Накладати HUD-оверлей на запис» — тоді час, координати цілі, АКБ та кути
  гімбала «вшиваються» у кадр (зручно для розбору польоту). Вибір зберігається.
- Кнопки та індикатори статусу в кадр **не потрапляють** у жодному режимі.
- Формат: **MP4** (кодек `mp4v`), 25 fps. Файли — у теці
  `Відео/RaptorHUD/raptor_РРРРММДД_ГГХХСС.mp4`.
- Кодування йде у фоновому потоці; за перевантаження диска/CPU кадри
  відкидаються, інтерфейс лишається плавним.

## Запуск з реальною камерою/автопілотом

```bash
python -m raptor_hud.main \
    --rtsp rtsp://192.168.1.10:554/stream \
    --mavlink udpin:0.0.0.0:14550
```

- `--rtsp` — RTSP URL відеопотоку Raptor 360 (H.264/H.265).
- `--mavlink` — рядок підключення pymavlink (`udpin:…`, `udp:…`, `/dev/ttyUSB0,57600`).

## Структура

| Файл | Призначення |
|------|-------------|
| `main.py` | Точка входу, складає відео + оверлей, вибір джерел. |
| `theme.py` | Кольори, шрифти, геометрія у фірмовому стилі. |
| `telemetry.py` | `TelemetryState` + `MockSource` (макет) + `MavlinkSource` (реальне MavLink). |
| `hud_overlay.py` | Малювання нижньої панелі та компаса (QPainter). |
| `video_view.py` | Фон-відео: статичний кадр (макет) або `RtspFrameSource`. |
| `recorder.py` | Запис композита (відео+HUD) у MP4 через OpenCV. |

## Поля телеметрії (нижня панель)

Курс • ВИСОТА (ASL+WGS) • Ground speed • Airspeed • Струм • Дист. до точки •
Таймер • ARM-статус • Режим польоту • Батарея (% / V) • Статус лінку.

Поверх відео: **рамка автотрекінгу** (TRIP 5), дата/час (ліворуч зверху),
кут камери PAN/TILT (ліворуч по центру).

MavLink-повідомлення: `HEARTBEAT`, `VFR_HUD`, `ATTITUDE`, `SYS_STATUS`,
`GLOBAL_POSITION_INT`, `GPS_RAW_INT`, `NAV_CONTROLLER_OUTPUT`, `MOUNT_STATUS`,
`GIMBAL_DEVICE_ATTITUDE_STATUS` (Gimbal v2), `CAMERA_TRACKING_IMAGE_STATUS`.

## Залізо

- Автопілот **ArduPlane**.
- **NextVision TRIP 5** — пейлоад-процесор: RTSP H.264/H.265, EO/IR-трекінг,
  геолокація цілей. Кути гімбала — Gimbal Protocol v2; трекінг — Camera v2.

## Що далі (TODO для бойової версії)

- **Геолокація цілі** (`CAMERA_TRACKING_GEO_STATUS`) — координати/дальність у HUD.
- Авіагоризонт (pitch/roll) — дані вже є у `TelemetryState`.
- ~~Запис відео з оверлеєм~~ — готово (`recorder.py`, кнопка ⏺ / клавіша `R`).
