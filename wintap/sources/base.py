"""Sensor sources. A source fills a queue with (kind, t, x, y, z) samples:
kind in {"accel", "gyro"}, t on the monotonic clock, accel in g, gyro in deg/s."""
import queue
import time


class Source:
    kind = "base"

    def __init__(self):
        self.samples = queue.SimpleQueue()
        self.found = {"accel": False, "gyro": False, "lid": False}
        self.error = None

    def start(self):
        raise NotImplementedError

    def put(self, kind, t, x, y, z):
        self.samples.put((kind, t, x, y, z))

    def throttle(self, max_q=400):
        """Backpressure: block while the consumer is more than max_q rows behind.

        The detector keeps a 4000-entry ring buffer and cuts its 0.5 s window from what
        is still in it, so a fast-forward producer must not run far ahead of the
        detector; 400 rows = 200 samples = 0.25 s of sensor time at 800 Hz."""
        while self.samples.qsize() > max_q:
            time.sleep(0.002)
