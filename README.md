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

WinTap extracts 188 features per tap, organized into 22 manageable features across three categories:

| Category | Features | Default | Use Case |
|----------|----------|---------|----------|
| Core | 8 (essential) | ON | Basic tap classification |
| Spectral | 12 (useful/experimental) | selective | Frequency-domain analysis |
| Template | 2 (experimental) | OFF | Raw waveform patterns |

### CLI Usage

```bat
python -m wintap features --list           :: show all features with importance
python -m wintap features --enable NAME     :: enable one or more features
python -m wintap features --disable NAME    :: disable one or more features
python -m wintap features --default         :: reset to smart defaults
python -m wintap features --status          :: show currently enabled features
python -m wintap features --info NAME       :: detailed info for a feature
```

### Web UI Usage

Open `http://127.0.0.1:8765/features` in your browser. Features are grouped by category with:
- **ON/OFF toggle** - Enable or disable individual features
- **Importance level** - Essential (green), Useful (blue), Experimental (yellow)
- **Default state** - Shown as tag, helps identify recommended configuration
- **Save Settings** - Persists changes for the current user

### Best Practices

- **Minimal configuration**: Enable only Core features for fastest processing
- **Balanced**: Core + Essential Spectral for most accuracy
- **Full**: All features enabled for maximum accuracy (slower processing)
- Test different configurations to find the best speed/accuracy tradeoff

## Version Management

### Check Version

```bat
python -m wintap version    # outputs: wintap X.Y.Z
```

### Update

```bat
pip install --upgrade wintap   # upgrade to latest release
```

### Version History

See [`CHANGELOG.md`](CHANGELOG.md) for version history and breaking changes.

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

**Option 3: Portable/Testing**
```bat
python -m wintap demo --source synthetic  # offline test, no IMU needed
```

### Safe Multi-User Installation

When installing on a shared laptop:

1. Install once per user with `pip install --user wintap`
2. Each user can have independent configurations (stored in `%LOCALAPPDATA%\WinTap`)
3. Use `wintap status` to verify installation
4. Run `wintap quickstart` to set up per-user calibration and model

⚠️ **Each user must run their own calibration** — models are trained per-user from recorded taps.

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