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
3. **Features** — 188 per-tap features (pressure-aware, spectral, templates)
   for superior tap detection accuracy.
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

## Installation (for another user)

### Quick Installer (Recommended for Friends)

**Option 1: Run from PyPI (when published)**
```bat
pip install wintap
wintap quickstart  # guides you through calibration
```

**Option 2: Download & Run (No Git needed)**
1. Click "Code" → "Download ZIP" on GitHub
2. Extract to a folder (e.g., `C:\Users\YourName\Applications\wintap`)
3. Open Command Prompt and run:
```bat
cd C:\Users\YourName\Applications\wintap
pip install .[all]
python -m wintap version
```

**Option 3: Portable Mode (No installation needed)**
```bat
cd path\to\wintap
python -m wintap demo --source synthetic  # test without IMU
```

### Verify Installation

```bat
python -m wintap version
python -m wintap sources  # check available sensors
python -m wintap serve    # start the web UI
```

### First-Time Setup for Your Friend

1. **Start the web dashboard**: `python -m wintap serve`
2. **Open browser**: Go to `http://127.0.0.1:8765`
3. **Go to Calibrate tab** and:
   - Record 30 seconds of noise (desk knocks, lid movement)
   - Do 2×2 grid calibration with 5-10 taps per zone
4. **Go to Model tab** and click "Retrain"
5. **Go to Live tab** and enable "Run the zone's command on each accepted tap"

### Enabling/Disabling Features

**Via Web UI (tab 4: Features)**:
- Toggle individual features on/off
- Click "Reset to Default" to restore all
- Click "Save Feature Settings" to persist

**Via CLI**:
```bat
# List all available features
python -m wintap features --list

# Enable specific features
python -m wintap features --enable twist_direction tap_strength

# Disable specific features
python -m wintap features --disable spectral_band_0

# Reset to defaults
python -m wintap features --reset

# Show current status
python -m wintap features --status
```

### Enable / disable WinTap itself

```bat
:: run it manually (stops with Ctrl+C)
wintap serve --open

:: start automatically at every Windows login (no console window)
wintap autostart on

:: check whether autostart is set
wintap autostart status

:: disable autostart (a running instance keeps running until you stop it)
wintap autostart off
```

- **Pause actions without stopping detection**: in the web UI Live tab, uncheck
  "Run the zone's command on each accepted tap" (same as
  `POST /api/config {"actions_enabled": false}`).
- **Stop a running instance**: Ctrl+C in its terminal, or close the window it
  opened; with autostart, run `wintap autostart off` for the next boots.
- **Uninstall**: `pip uninstall wintap`

### On a laptop that has a motion sensor (2-in-1s, some ultrabooks)

`wintap sources` will show `winrt_accel: true` / `winrt_gyro: true` and the
`auto` source uses the built-in IMU directly — no microphone involved, and
touchscreen taps get full 2D position from the gyro vector. If Windows exposes
no IMU but a USB one is plugged in: `pip install "wintap[hid]"`.
On machines with no sensor at all, `auto` falls back to the microphone
(acoustic knock detection) — see `docs/acoustic.md`.

### Version Management

```bat
# Check current version
python -m wintap version

# Check for updates
pip list | findstr wintap

# Upgrade (when published)
pip install --upgrade wintap
```

**Version History**: See `CHANGELOG.md` for details.

### Security

**WinTap is designed with security and isolation:**

1. **Local-only access**: Web UI only binds to `127.0.0.1` (localhost). No remote access is possible.

2. **Token protection**: All API endpoints require a per-run token embedded in the HTML page. This prevents:
   - Cross-site request forgery (CSRF)
   - Unauthorized command injection

3. **No system access**: The tool only reads IMU sensor data and sends keyboard/mouse inputs. It:
   - Does NOT read/write files outside `%LOCALAPPDATA%\WinTap`
   - Does NOT execute arbitrary code without explicit user-configured actions
   - Uses `SendInput` only for predefined key combinations or shell commands you configure

4. **No privilege escalation**: WinTap runs as a regular user. It never requires:
   - Administrator rights
   - Accessibility permissions (unlike macOS)
   - Kernel drivers or hardware access beyond IMU

5. **Privacy**: 
   - Data stays local (no telemetry, no cloud)
   - No personal data collection
   - Your tap patterns never leave your machine

### For Your Friend: Safe Installation Steps

**Before giving to your friend**:
1. Read this README completely yourself first
2. Test the full workflow: calibrate → train → live mode

**To share with your friend**:
1. **Package it**: Zip the entire wintap folder
2. **Include README.md**: Your friend needs this file
3. **Include requirements**: The `[all]` extras need `winsdk` and `hidapi`

**Your friend should**:
1. Extract to a location they can access (e.g., Desktop)
2. Open Command Prompt (NOT PowerShell)
3. Run: `pip install .[all]` from inside the folder
4. Run: `python -m wintap serve`
5. Open browser to `http://127.0.0.1:8765`
6. Follow the web UI setup wizard

**Troubleshooting for your friend**:
- If `pip install .[all]` fails, try: `pip install winsdk hidapi hid-parser`
- If sensor not found, check that laptop has an IMU (most 2-in-1s, tablets, modern laptops do)
- If permissions error, they may need to run Command Prompt as Administrator for `pip install` only

**If you suspect malicious activity**:
- Check your `config.json` and `dataset.json` in `%LOCALAPPDATA%\WinTap`
- Review configured actions in the web UI
- The tool only activates when you run it manually

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
