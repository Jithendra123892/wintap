# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-11-07

### Added
- Enhanced feature extraction with 188 features (up from 70)
  - Pressure-aware features: peak acceleration, direction
  - Rise time analysis for better temporal discrimination
  - Asymmetry features (rise vs decay shape)
  - Extended spectral bands (8 frequency bands vs 4)
  - 12 spectrogram frequency peaks for bump discrimination
  - Combined gyro+accel templates for richer characterization
- Feature visualization tab in web UI
- Feature toggle controls (enable/disable individual features)
- Gesture detection support (double-tap, swipe patterns)
- Version info accessible via CLI and web UI
- Reset and save buttons for feature settings

### Changed
- N_FEATURES now dynamically computed from extract() output
- WEIGHTS array computed at runtime to match feature count
- Updated test assertions to match new feature count

### Fixed
- Feature count mismatch between WEIGHTS and actual features

## [0.1.0] - 2024-01-01

### Added
- Initial release
- Zone tap detection from laptop lid IMU
- Calibration workflow
- Model training and evaluation
- Web-based monitoring UI
- Actions system for zone-based keyboard shortcuts
- Noise recording for rejection training