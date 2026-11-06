# Acoustic fallback (lid knock via microphone)

On machines with no IMU exposed to Windows, the lid tap is still audible: a
short broadband knock on the lid shell couples into the built-in mic.

Sketch of a fallback trigger (not wired in yet — contribution welcome):

1. Record the default microphone (`Windows.Media.Capture.MediaCapture` or
   `pycaw`/`sounddevice` loopback) at 16 kHz mono.
2. Band-pass 1–6 kHz (the knock's energy band), compute short-time energy.
3. Trigger when energy crosses `max(8x median, floor)` for 5–20 ms — the same
   adaptive-threshold shape the gyro trigger uses.
4. Feed the 200 ms audio window into the same feature extractor with the
   gyro features zeroed, and train a separate model, or fuse with the gyro
   model when both are available.

Desk bumps are also audible, so negatives recorded during `wintap noise`
(while you bump the desk) transfer directly to the acoustic model.

Windows API notes: `MediaCapture` needs the `microphone` capability for
packaged apps but **not** for unpackaged Python; `pycaw` (WASAPI loopback) can
capture the mic without any permission prompt on Windows 10/11.
