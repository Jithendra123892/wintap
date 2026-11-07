# WinTap

[![CI](https://github.com/Jithendra123892/wintap/actions/workflows/ci.yml/badge.svg)](https://github.com/Jithendra123892/wintap/actions/workflows/ci.yml)

Tap zones on your **Windows laptop lid** — double-tap the top-left to switch virtual desktop, top-right to lock, bottom zones for media keys — using only the laptop's built-in motion sensor. No admin rights, no accessibility permissions, no extra hardware.

Based on [LidTap](https://github.com/yemcube/lidtap) by Yemcube (MIT). See `NOTICE` for credits.

```
lid, top view
┌──────────┬──────────┐
│   z0     │   z1     │   each zone runs your action
│  (e.g.  │  (e.g.  │   on tap: Win+Ctrl+Left /
│ Win+Ctrl│  Win+L   │   lock / media / shell ...)
│  +Left) │  lock)   │
├──────────┼──────────┤
│   z2     │   z3     │
│ (play/   │ (vol up) │
│  pause)  │          │
└──────────┴──────────┘
```

## How it works

1. **IMU stream** (~100–1600 Hz) from `winrt` (Windows sensors) or `hid` (raw HID)
2. **Trigger** — 5 Hz high-pass on gyro, adaptive threshold
3. **Features** — 188 per-tap features (pressure-aware, spectral, templates)
4. **Model** — kNN/centroid/SVM/logreg/RF, cross-validated per user
5. **Gating** — taps only when lid open and idle
6. **Action** — per-zone key combos, shell commands, or touch mapping

## Requirements

- Windows 10/11, Python ≥ 3.10
- `pip install .[all]` for full functionality

## Quick Start

```bat
pip install .[all]
python -m wintap sources                 :: available sensors
python -m wintap demo --source synthetic :: full demo on simulated laptop
python -m wintap serve                   :: web UI at http://127.0.0.1:8765
python -m wintap calibrate --rows 2 --cols 2 --per-zone 10
python -m wintap noise --seconds 20
python -m wintap train
python -m wintap live --enable-actions
python -m wintap status
```

Data stored in `%LOCALAPPDATA%\WinTap`.

## Touchscreen Mode

Map lid zones to screen positions: `wintap touch --rows 3 --cols 3` creates a 9-button touchpad on the lid. Actions: `play_pause`, `next_track`, `volume_up`, `desktop_left`, `lock`, `privacy_guard`, `open:<program>`, or any shell command (`{zone}` = zone number).

## Web UI

`python -m wintap serve` opens a local dashboard (127.0.0.1:8765, token-protected) to calibrate zones, watch live events, train, and assign actions.

## Feature Management

Each user can enable/disable individual features for improved accuracy:

```bat
python -m wintap features --list         :: all 22 features
python -m wintap features --enable twist_direction tap_strength
python -m wintap features --disable spectral_band_0
python -m wintap features --reset        :: restore defaults
python -m wintap features --status       :: currently enabled
```

Categories: Core (8), Spectral (12), Template (2). Enable fewer features for faster processing.

## Installation

**Option 1: PyPI**
```bat
pip install wintap
wintap quickstart
```

**Option 2: Download ZIP**
1. Download from GitHub → extract to a folder
2. `cd` to folder and run `pip install .[all]`
3. `python -m wintap serve` to start

**Option 3: Portable**
```bat
python -m wintap demo --source synthetic  # offline test
```

## Version Management

```bat
python -m wintap version        :: check version
pip install --upgrade wintap   :: update
```

See `CHANGELOG.md` for version history.

## Security

- **Local-only**: Web UI binds to 127.0.0.1
- **Token protected**: Prevents CSRF and unauthorized actions
- **No system access**: Only reads IMU data, sends keyboard/mouse inputs
- **Data stays local**: No telemetry, no cloud, no personal data collection

## Troubleshooting

- Installation fails: `pip install winsdk hidapi hid-parser`
- No sensor found: Verify laptop has IMU (most 2-in-1s, tablets, modern laptops do)
- Sensor access issues: Run Command Prompt as Administrator for `pip install`

## Development

```bat
python -m unittest discover -s tests -v   :: 26 tests, hardware-free
```

## License

MIT — see `LICENSE`.