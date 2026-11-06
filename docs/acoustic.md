# Acoustic fallback (lid knock via microphone)

Implemented as `wintap.sources.audio.AudioSource` (`--source audio`, also what `auto`
picks when Windows exposes no motion sensor, which is most consumer laptops —
WinRT `Accelerometer.get_default()` is None on machines without a sensor class device).

How it works:

1. The default microphone is recorded with `sounddevice` at the device sample rate,
   split into 10 ms blocks; per block the high-frequency (1–6 kHz) energy of the left
   and right mic-array channels is computed separately.
2. The energy ratio between channels gives a left/right "pan" (this is what separates
   left-half from right-half lid zones without an IMU); the energy vs. its running
   median gives a pseudo-gyro magnitude with the same adaptive-threshold shape the
   gyro trigger uses (noise ~0.5 deg/s, knock ~10 deg/s).
3. The producer emits synthetic `gyro`/`accel` rows at 800 Hz, so `detector.py`,
   `features.py`, `model.py` and the GUI run unchanged — one code path for IMU and mic.
4. `wintap calibrate --source audio` plays a short panned knock through the speakers
   (`_play`) so the user taps the matching lid zone; `wintap noise` records desk bumps
   (also audible) as negatives. Both work exactly like the IMU flow.

Hardware notes:

- No admin, no capability, no permission prompt: plain WASAPI capture of the default
  input endpoint from an unpackaged process.
- `live=False` (used by `tests/test_audio.py`) skips the hardware and injects
  synthetic knock/bump blocks into the producer, so the full calibrate -> noise ->
  train -> live pipeline is tested on any machine, including CI runners with no
  audio device.
- On this dev VM, speaker->mic acoustic coupling and Stereo Mix loopback both capture
  nothing, so the mic transducer path itself can only be validated on real hardware;
  everything downstream of the mic is covered by the test.

Windows API notes: `MediaCapture` would also work but needs the `microphone`
capability for packaged apps; `sounddevice`/PortAudio needs nothing. `pycaw` WASAPI
loopback can capture the mic without any prompt on Windows 10/11 (used for the
`--loopback` capture option).
