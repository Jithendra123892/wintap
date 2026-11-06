# Windows sensor sources

WinTap reads the laptop IMU through one of three sources (auto-selected by
`python -m wintap sources`, overridable with `--source`):

## 1. WinRT managed sensors (`winrt`) — 60–100 Hz

`Windows.Devices.Sensors.Accelerometer` / `Gyrometer` via the `winsdk` package.

- Accelerometer reports in **g**, gyrometer in **deg/s** — the units the
  detector expects, so no rescaling is needed.
- Set `report_interval_ms = 12` (~83 Hz) as a compromise between latency and
  USB HID interrupt load.
- Availability: 2-in-1s, convertibles, tablets, modern-standby laptops.
  Plain clamshells often expose **no** sensor to Windows even when the IMU is
  physically present — check `python -m wintap sources`; if `winrt_sensor` is
  false, try `hid`.

Install: `pip install .[winrt]`

## 2. Raw HID (`hid`) — up to ~1600 Hz

Many laptop IMUs (Bosch BMI160/BMI260, STM LIS3MDL+LSM6DSO, etc.) sit on the
internal HID bus with usage page `0x20` (Sensors):

- Accelerometer3D usage `0x73`, Gyrometer3D usage `0x76`.
- Read input reports at the device's full report rate with `hidapi`
  (`pip install .[hid]`). No admin rights needed for read-only HID.
- `wintap/sources/hidraw.py` parses the report descriptor with `hidparser` and
  maps fields by usage; scale defaults (16384 LSB/g, 16.4 LSB per deg/s) cover
  common 16-bit parts and are overridable.

If your model is not covered, record raw reports (`python -m wintap monitor
--source hid --record raw.jsonl`) and open an issue with the descriptor.

## 3. Synthetic / replay — no hardware

- `synthetic` simulates a laptop: idle gyro noise ~0.15 deg/s per axis, taps as
  a damped ~40 Hz twist of 5–12 deg/s with a left/right sign flip and a
  top/bottom accel-shake difference, desk bumps as accel-dominated 25–40 Hz
  shakes of 2.8–4.2 deg/s. Used by `python -m wintap demo` and the test suite.
- `replay:FILE.jsonl` replays a recording (`{"k","t","x","y","z"}` rows, as
  written by `--record`).

## No IMU at all?

Two fallbacks:

1. **USB IMU breakout** (~$5, BMI160 or BNO055 over USB-HID) — use `--source hid`.
2. **Microphone knock sensing** — the lid tap is audible; a band-passed energy
   detector on the default recording device can substitute for the IMU trigger
   (contributions welcome; see `docs/acoustic.md`).

## Lid state and input gating

- Lid open/closed: `RegisterPowerSettingNotification` with
  `GUID_LIDSWITCH_STATE_CHANGE = BA3E0F4D-B817-4094-A2D1-D56379E6A0F3` on a
  message-only window (`HWND_MESSAGE`), mapped to 130°/0° so the detector's
  lid-moved gate works unchanged.
- "User is typing" gate: `WH_KEYBOARD_LL` (13) / `WH_MOUSE_LL` (14) low-level
  hooks, installed in-process with `hMod = NULL`. On Windows these need **no
  admin and no accessibility permission** (unlike macOS Input Monitoring).
