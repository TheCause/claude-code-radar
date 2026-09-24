#!/usr/bin/env python3
"""
Vulnerability Demonstration Test:
Runs the security test checks against tests/server_vulnerable.py
to demonstrate and document that the unpatched version FAILS these tests.
"""

import unittest
import threading
import http.client
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from tests import server_vulnerable

class TestVulnerableServerFails(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start the old vulnerable server on wildcard bind "" and ephemeral port
        cls.httpd = server_vulnerable.create_vulnerable_server(host="", port=0)
        cls.host, cls.port = cls.httpd.server_address
        # When bound to "", socket address may be "0.0.0.0"
        cls.connect_host = "127.0.0.1"
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def make_raw_request(self, method, path):
        conn = http.client.HTTPConnection(self.connect_host, self.port, timeout=5)
        conn.request(method, path)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, resp.headers, body

    def test_binding_address_is_loopback(self):
        # Should fail: vulnerable server binds to "0.0.0.0" / ""
        self.assertEqual(
            self.host, "127.0.0.1",
            f"VULNERABILITY CONFIRMED: Server binds to wildcard address '{self.host}' instead of 127.0.0.1"
        )

    def test_path_traversal_raw_parent(self):
        # Should fail: vulnerable server returns 200 with README.md contents
        status, _, body = self.make_raw_request("GET", "/data/../README.md")
        self.assertIn(
            status, [403, 404],
            f"VULNERABILITY CONFIRMED: /data/../README.md returned HTTP {status} (leaking {len(body)} bytes!)"
        )

    def test_get_api_update_returns_405(self):
        # Should fail: vulnerable server triggers on GET and returns 200
        status, _, body = self.make_raw_request("GET", "/api/update")
        self.assertEqual(
            status, 405,
            f"VULNERABILITY CONFIRMED: GET /api/update returned HTTP {status} instead of 405"
        )

if __name__ == "__main__":
    unittest.main(verbosity=2)
