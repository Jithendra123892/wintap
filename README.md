# WinTap

[![CI](https://github.com/Jithendra123892/wintap/actions/workflows/ci.yml/badge.svg)](https://github.com/Jithendra123892/wintap/actions/workflows/ci.yml)

Tap zones on your **Windows laptop lid** — double-tap the top-left of the lid to
switch virtual desktop, top-right to lock, bottom zones for media keys — using
only the laptop's built-in motion sensor. No admin, no accessibility
permissions, no extra hardware.

WinTap is a Windows port of [LidTap](https://github.com/yemcube/lidtap) by
Yemcube (MIT). **Based on LidTap by Yemcube (https://github.com/yemcube/lidtap)**
— see `NOTICE`.

```
lid, top view
┌──────────┬──────────┐
│   z0     │   z1     │   each zone runs your action
│  (e.g.   │  (e.g.   │   on tap: Win+Ctrl+Left /
│ Win+Ctrl │  Win+L   │   lock / media / shell ...)
│  +Left)  │  lock)   │
├──────────┼──────────┤
│   z2     │   z3     │
│ (play/   │ (vol up) │
│  pause)  │          │
└──────────┴──────────┘
```

## How it works

Same pipeline as LidTap, retargeted to Windows:

1. **IMU stream** (~100–1600 Hz) from one of three sources, auto-selected:
   - `winrt` — `Windows.Devices.Sensors` (Accelerometer + Gyrometer) via
     `winsdk`, 60–100 Hz, managed. Present on most 2-in-1s, convertibles,
     tablets and modern-standby laptops.
   - `hid` — raw HID input reports (usage page `0x20`, Accelerometer3D `0x73`,
     Gyrometer3D `0x76`) read at the device's full rate (up to ~1600 Hz on
     Bosch BMI260 / STM parts) via `hidapi`. No admin required.
   - `synthetic` / `replay:FILE.jsonl` — physics-simulated laptop / recorded
     sessions, so everything (including the tests) runs on machines with no IMU.
2. **Trigger** — 5 Hz high-pass on the gyro, adaptive threshold
   `max(1.0, 6·σ_noise)` on |twist|; a 200 ms window is cut per tap.
3. **Features** — 70 per-tap features (onset/decay/peak timing, signed peak
   gyro direction, gyro/accel energy ratio, spectral peaks, …).
4. **Model** — kNN / centroid / SVM / logreg / RF, cross-validated per user,
   plus open-set novelty rejection ("unfamiliar tap"), trained from your own
   calibration taps + recorded desk-bump negatives.
5. **Gating** — taps only fire when the lid is open (lid state via
   `RegisterPowerSettingNotification`, GUID `BA3E0F4D-…`) and when you have not
   typed/clicked in the last 0.3 s (low-level `WH_KEYBOARD_LL` / `WH_MOUSE_LL`
   hooks — in-process, no admin, no accessibility permission on Windows).
6. **Action** — per-zone: `SendInput` key combos (virtual desktops
   `Win+Ctrl+←/→`, media `VK_MEDIA_*`, volume `VK_VOLUME_*`, lock `Win+L`),
   `open:<program>`, or any shell command with `{zone}`; `privacy_guard` locks
   and mutes mic + camera.

## Requirements

- Windows 10/11, Python ≥ 3.10
- A laptop that exposes its IMU to Windows (check with `python -m wintap sources`)
- `pip install .[winrt]` and/or `.[hid]` for real sensors
- On IMU-less machines: `python -m wintap demo --source synthetic` works fully
  offline (simulated laptop), or plug in a ~$5 USB IMU breakout (BMI160/BNO055)
  and use `--source hid`

## Quick start

```bat
pip install .[all]
python -m wintap sources                 :: what sensors this machine has
python -m wintap demo --source synthetic :: full calibrate->train->live on a simulated laptop
python -m wintap serve                   :: real laptop: web UI at http://127.0.0.1:8765
python -m wintap calibrate --rows 2 --cols 2 --per-zone 10
python -m wintap noise --seconds 20
python -m wintap train
python -m wintap live --enable-actions   :: actions fire on tap (dry-run without the flag)
python -m wintap touch --rows 3 --cols 3 :: lid becomes a touchscreen: every zone taps the same spot on the display
python -m wintap status
```

Data (config, dataset, model) lives in `%LOCALAPPDATA%\WinTap`.

## Touchscreen mode

Lid zones map onto the screen: a knock on a lid zone left-clicks the same relative
spot on the display (`tap` action; `click:fx,fy` / `move:fx,fy` for explicit screen
fractions). So `wintap touch --rows 3 --cols 3`, calibrate the 3x3 grid, train, then
`wintap live --enable-actions` gives you a 9-button touchscreen on the lid. Other
actions per zone: `play_pause`, `next_track`, `volume_up`, `desktop_left`, `lock`,
`privacy_guard`, `open:<program>`, or any shell command (`{zone}` = zone number).

## Web UI

`python -m wintap serve` opens a local dashboard (loopback-only, token
protected, no framing) to calibrate zones, watch live events, train, and assign
actions per zone — the same UI as LidTap.

## Development

```bat
python -m unittest discover -s tests -v   :: 26 tests, hardware-free (synthetic IMU)
```

Layout: `wintap/` package — `detector.py`, `features.py`, `model.py`,
`server.py`, `app.py`, `static/` are portable LidTap core (verbatim);
`wintap/sensors.py`, `wintap/inputmon.py`, `wintap/actions.py`,
`wintap/sources/` are the Windows-specific layer.

## Why gyro, not accel?

A tap twists the lid about the hinge; a desk bump mostly translates the whole
chassis. Triggering on gyro twist and using the gyro/accel energy ratio as a
feature rejects bumps that an accelerometer-only trigger would fire on
(TapPrints, MobiSys 2012, ~90% with accel+gyro fusion; see `docs/`).

## License

MIT — see `LICENSE`. Based on LidTap by Yemcube (https://github.com/yemcube/lidtap).
