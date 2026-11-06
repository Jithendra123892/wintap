"""Sensor sources. A source fills a queue with (kind, t, x, y, z) samples:
kind in {"accel", "gyro"}, t on the monotonic clock, accel in g, gyro in deg/s."""
import queue


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
