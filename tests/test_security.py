#!/usr/bin/env python3
"""
Security Test Suite for Claude Code Changelog Observatory Server
Verifies:
1. Path traversal attacks (/data/../README.md, %2e%2e, ..%2f..%2f) return 403 or 404, NEVER 200
2. Legitimate data files return 200
3. GET /api/update returns 405 Method Not Allowed
4. Server is strictly bound to 127.0.0.1 (loopback)
5. Static directory web/ traversal returns 403/404, never 200
"""

import unittest
import threading
import http.client
import socket
import os
import sys

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import server

class TestServerSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start server on 127.0.0.1 with ephemeral port (0)
        cls.httpd = server.create_server(host="127.0.0.1", port=0)
        cls.host, cls.port = cls.httpd.server_address
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def make_raw_request(self, method, path):
        """Send raw HTTP request without automatic client path normalization"""
        conn = http.client.HTTPConnection(self.host, self.port, timeout=5)
        conn.request(method, path)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, resp.headers, body

    def test_binding_address_is_loopback(self):
        """Verify the server binds exclusively to 127.0.0.1 (not 0.0.0.0 or wildcard)"""
        self.assertEqual(
            self.host, "127.0.0.1",
            f"Server must bind strictly to 127.0.0.1, got {self.host}"
        )
        # Verify it cannot be accessed on a wild bind if 127.0.0.1 is specified
        self.assertNotEqual(self.host, "0.0.0.0")
        self.assertNotEqual(self.host, "")

    def test_path_traversal_raw_parent(self):
        """Verify /data/../README.md returns 403 or 404, NEVER 200"""
        status, _, body = self.make_raw_request("GET", "/data/../README.md")
        self.assertIn(
            status, [403, 404],
            f"Expected 403 or 404 on /data/../README.md, got {status}. Body snippet: {body[:100]}"
        )
        self.assertNotEqual(status, 200, "VULNERABILITY: /data/../README.md returned HTTP 200!")

    def test_path_traversal_encoded_dots(self):
        """Verify /data/%2e%2e/README.md returns 403 or 404, NEVER 200"""
        status, _, body = self.make_raw_request("GET", "/data/%2e%2e/README.md")
        self.assertIn(
            status, [403, 404],
            f"Expected 403 or 404 on /data/%2e%2e/README.md, got {status}. Body snippet: {body[:100]}"
        )
        self.assertNotEqual(status, 200, "VULNERABILITY: /data/%2e%2e/README.md returned HTTP 200!")

    def test_path_traversal_encoded_slashes(self):
        """Verify /data/..%2f..%2fREADME.md returns 403 or 404, NEVER 200"""
        status, _, body = self.make_raw_request("GET", "/data/..%2f..%2fREADME.md")
        self.assertIn(
            status, [403, 404],
            f"Expected 403 or 404 on /data/..%2f..%2fREADME.md, got {status}. Body snippet: {body[:100]}"
        )
        self.assertNotEqual(status, 200, "VULNERABILITY: /data/..%2f..%2fREADME.md returned HTTP 200!")

    def test_path_traversal_web_root(self):
        """Verify /../server.py and /%2e%2e/server.py return 403 or 404, NEVER 200"""
        status, _, _ = self.make_raw_request("GET", "/../server.py")
        self.assertIn(status, [403, 404], f"Expected 403/404 for /../server.py, got {status}")
        self.assertNotEqual(status, 200)

        status_enc, _, _ = self.make_raw_request("GET", "/%2e%2e/server.py")
        self.assertIn(status_enc, [403, 404], f"Expected 403/404 for /%2e%2e/server.py, got {status_enc}")
        self.assertNotEqual(status_enc, 200)

    def test_legitimate_data_file_returns_200(self):
        """Verify a legitimate file inside data/ returns HTTP 200"""
        status, _, body = self.make_raw_request("GET", "/data/insights.json")
        self.assertEqual(status, 200, f"Expected 200 on legitimate file /data/insights.json, got {status}")
        self.assertTrue(len(body) > 0, "Response body should not be empty")

        status_raw, _, _ = self.make_raw_request("GET", "/data/raw_changelog.md")
        self.assertEqual(status_raw, 200, f"Expected 200 on /data/raw_changelog.md, got {status_raw}")

    def test_get_api_update_returns_405(self):
        """Verify GET /api/update is rejected with 405 Method Not Allowed"""
        status, headers, body = self.make_raw_request("GET", "/api/update")
        self.assertEqual(
            status, 405,
            f"GET /api/update must return 405 Method Not Allowed, got {status}. Body: {body}"
        )
        allow_header = headers.get("Allow", "")
        self.assertIn("POST", allow_header, f"Expected Allow: POST header, got {allow_header}")

    def test_single_update_lock_concurrency(self):
        """Verify only one update can run at a time (returns 409 Conflict if locked)"""
        # Acquire the lock manually to simulate an ongoing update
        acquired = server.UPDATE_LOCK.acquire(blocking=False)
        self.assertTrue(acquired, "Should be able to acquire lock")
        try:
            status, _, body = self.make_raw_request("POST", "/api/update")
            self.assertEqual(status, 409, f"Expected 409 Conflict when update is running, got {status}")
        finally:
            server.UPDATE_LOCK.release()

    def test_null_byte_in_url_returns_400(self):
        """Verify embedded null byte (%00) in URL is intercepted and returns HTTP 400 Bad Request"""
        status_data, _, body_data = self.make_raw_request("GET", "/data/insights.json%00.json")
        self.assertEqual(
            status_data, 400,
            f"Expected HTTP 400 for /data/insights.json%00.json, got {status_data}. Body: {body_data}"
        )

        status_root, _, body_root = self.make_raw_request("GET", "/index.html%00test")
        self.assertEqual(
            status_root, 400,
            f"Expected HTTP 400 for /index.html%00test, got {status_root}. Body: {body_root}"
        )

if __name__ == "__main__":
    unittest.main(verbosity=2)
