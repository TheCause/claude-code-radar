#!/usr/bin/env python3
"""
Vulnerable server implementation (Exact reproduction of original state before security fixes)
Used specifically by tests to prove test failure on the unpatched codebase.
"""

import http.server
import socketserver
import os
import sys
import json
import subprocess
import urllib.parse

PORT = 3333
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, "web")
DATA_DIR = os.path.join(BASE_DIR, "data")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")

class VulnerableObservatoryHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/insights":
            insights_path = os.path.join(DATA_DIR, "insights.json")
            if os.path.exists(insights_path):
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                with open(insights_path, "rb") as f:
                    self.wfile.write(f.read())
            return

        # VULN 1: /api/update triggered on GET!
        if path in ["/api/update", "/api/refresh"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'{"success": true, "message": "update triggered"}')
            return

        # VULN 2: Path traversal without realpath/sandbox check!
        if path.startswith("/data/"):
            rel_path = path.replace("/data/", "", 1)
            file_path = os.path.join(DATA_DIR, rel_path)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
                return

        return super().do_GET()

# VULN 3: Bound to "" (all interfaces 0.0.0.0)
def create_vulnerable_server(host="", port=0):
    socketserver.TCPServer.allow_reuse_address = True
    return socketserver.TCPServer((host, port), VulnerableObservatoryHandler)
