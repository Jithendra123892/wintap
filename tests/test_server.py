"""Local HTTP server tests (ported from the LidTap prototype): token auth, host check,
security headers, path traversal, JSON state."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from wintap import server
from wintap.app import App
from wintap.sources.synthetic import SyntheticSource


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        app = App(Path(cls.tmp.name) / "data", source=SyntheticSource(realtime=False))
        cls.httpd = server.serve(app, 0)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r, data

    def test_page_cannot_be_framed(self):
        r, _ = self.request("GET", "/")
        self.assertEqual(r.status, 200)
        self.assertEqual(r.getheader("X-Frame-Options"), "DENY")
        self.assertIn("frame-ancestors 'none'", r.getheader("Content-Security-Policy"))

    def test_foreign_host_is_refused(self):
        r, _ = self.request("GET", "/", headers={"Host": "attacker.example"})
        self.assertEqual(r.status, 403)

    def test_post_needs_the_token(self):
        r, _ = self.request("POST", "/api/stop", "{}", {"X-Token": "wrong"})
        self.assertEqual(r.status, 403)
        r, _ = self.request("POST", "/api/stop", "{}", {"X-Token": server.TOKEN})
        self.assertEqual(r.status, 200)

    def test_bad_bodies_are_400_not_crashes(self):
        for body in ("not json", "[1, 2]"):
            r, data = self.request("POST", "/api/stop", body, {"X-Token": server.TOKEN})
            self.assertEqual(r.status, 400, data)

    def test_static_paths_cannot_escape(self):
        r, _ = self.request("GET", "/static/../app.py")
        self.assertEqual(r.status, 404)

    def test_state_is_json(self):
        r, data = self.request("GET", "/api/state")
        self.assertEqual(r.status, 200)
        self.assertIn("status", json.loads(data))


if __name__ == "__main__":
    unittest.main()
