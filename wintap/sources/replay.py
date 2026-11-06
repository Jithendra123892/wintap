"""Replay a recording made with `wintap monitor --record FILE` (JSONL, one sample per line:
{"k": "gyro"|"accel", "t": seconds, "x": .., "y": .., "z": ..}). Timestamps are re-based onto
the monotonic clock so the detector's windowing and gating behave as live."""
import json
import threading
import time

from .base import Source


class ReplaySource(Source):
    kind = "replay"

    def __init__(self, path, realtime=True):
        super().__init__()
        self.path = path
        self.realtime = realtime

    def start(self):
        def run():
            rows = []
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            rows.append(json.loads(line))
            except OSError as e:
                self.error = f"cannot read recording: {e}"
                return
            if not rows:
                self.error = "empty recording"
                return
            self.found["accel"] = any(r["k"] == "accel" for r in rows)
            self.found["gyro"] = any(r["k"] == "gyro" for r in rows)
            base = rows[0]["t"]
            wall0 = time.monotonic()
            for r in rows:
                t_emit = wall0 + (r["t"] - base)
                if self.realtime:
                    while time.monotonic() < t_emit:
                        time.sleep(0.001)
                self.put(r["k"], t_emit, r["x"], r["y"], r["z"])
                if not self.realtime:
                    self.throttle()

        threading.Thread(target=run, daemon=True, name="wintap-replay").start()
