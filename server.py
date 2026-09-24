#!/usr/bin/env python3
"""
Claude Code Changelog Observatory - Hardened Local Server
Serves the web dashboard and provides secured live update API endpoints.
Security properties:
- Binds strictly to 127.0.0.1 (loopback only)
- Strict path traversal prevention using os.path.realpath on /data/ and web/
- /api/update strictly requires POST (405 on GET)
- Thread-safe concurrency control ensuring single update execution at a time (409 Conflict)
"""

import http.server
import socketserver
import os
import sys
import json
import subprocess
import urllib.parse
import threading

DEFAULT_HOST = "127.0.0.1"
PORT = 3333

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
DATA_DIR = os.path.join(BASE_DIR, "data")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")

REAL_DATA_DIR = os.path.realpath(DATA_DIR)
REAL_WEB_DIR = os.path.realpath(WEB_DIR)

UPDATE_LOCK = threading.Lock()

class ObservatoryHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def translate_path(self, path):
        """
        Translate URL path to local filesystem path inside WEB_DIR.
        Strictly prevents directory traversal out of REAL_WEB_DIR and handles null bytes.
        """
        if "\x00" in path:
            return None
        parsed = urllib.parse.urlsplit(path)
        if "\x00" in parsed.path:
            return None
            
        decoded_path = urllib.parse.unquote(parsed.path)
        if "\x00" in decoded_path:
            return None
        
        # Clean path segments
        clean_parts = []
        for part in decoded_path.split('/'):
            if not part or part == '.':
                continue
            if part == '..':
                # Attempt to traverse up
                return None
            clean_parts.append(part)
            
        try:
            target = os.path.realpath(os.path.join(REAL_WEB_DIR, *clean_parts))
            if os.path.commonpath([target, REAL_WEB_DIR]) != REAL_WEB_DIR:
                return None
            return target
        except ValueError:
            return None

    def send_error_json(self, code, message):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        payload = json.dumps({"error": message, "code": code})
        self.wfile.write(payload.encode("utf-8"))

    def do_GET(self):
        # SECURITY RULE: Intercept embedded null characters (%00) and return 400 Bad Request
        if "\x00" in self.path:
            self.send_error_json(400, "Bad Request: Embedded null character detected.")
            return

        parsed = urllib.parse.urlparse(self.path)
        raw_path = parsed.path
        if "\x00" in raw_path:
            self.send_error_json(400, "Bad Request: Embedded null character detected.")
            return

        try:
            decoded_path = urllib.parse.unquote(raw_path)
        except Exception:
            self.send_error_json(400, "Bad Request: Invalid URL encoding.")
            return

        if "\x00" in decoded_path:
            self.send_error_json(400, "Bad Request: Embedded null character detected.")
            return

        # SECURITY RULE: /api/update is POST ONLY. Return 405 on GET
        if decoded_path in ["/api/update", "/api/refresh"]:
            self.send_response(405)
            self.send_header("Allow", "POST")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "Method Not Allowed. Use POST.",
                "code": 405
            }).encode("utf-8"))
            return

        # API: Get Insights
        if decoded_path == "/api/insights":
            insights_path = os.path.join(REAL_DATA_DIR, "insights.json")
            if os.path.exists(insights_path) and os.path.isfile(insights_path):
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with open(insights_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error_json(404, "Insights data not found.")
            return

        # API: Get Changelog
        if decoded_path == "/api/changelog":
            changelog_path = os.path.join(REAL_DATA_DIR, "changelog.json")
            if os.path.exists(changelog_path) and os.path.isfile(changelog_path):
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with open(changelog_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error_json(404, "Changelog data not found.")
            return

        # ROUTE: /data/*
        # Must resolve strictly within REAL_DATA_DIR using os.path.realpath
        if raw_path.startswith("/data/") or decoded_path.startswith("/data/"):
            # Strip /data/ prefix from decoded path
            rel_path = decoded_path[6:].lstrip("/\\")
            try:
                target_path = os.path.realpath(os.path.join(REAL_DATA_DIR, rel_path))
            except ValueError:
                self.send_error_json(400, "Bad Request: Embedded null character in path.")
                return

            # Security verification: commonpath must equal REAL_DATA_DIR
            try:
                is_inside = (
                    os.path.commonpath([target_path, REAL_DATA_DIR]) == REAL_DATA_DIR
                    and target_path.startswith(REAL_DATA_DIR + os.sep)
                )
            except ValueError:
                is_inside = False

            if not is_inside:
                # Return 403 Forbidden on directory traversal attempt
                self.send_error_json(403, "Access Forbidden: Path traversal detected.")
                return

            try:
                if not os.path.exists(target_path) or not os.path.isfile(target_path):
                    self.send_error_json(404, "File not found.")
                    return
            except ValueError:
                self.send_error_json(400, "Bad Request: Embedded null character in path.")
                return

            # File is legitimate and strictly within DATA_DIR
            self.send_response(200)
            if target_path.endswith(".json"):
                self.send_header("Content-Type", "application/json; charset=utf-8")
            elif target_path.endswith(".md"):
                self.send_header("Content-Type", "text/markdown; charset=utf-8")
            else:
                self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with open(target_path, "rb") as f:
                self.wfile.write(f.read())
            return

        # Static files from web/
        translated = self.translate_path(self.path)
        if translated is None:
            self.send_error_json(403, "Access Forbidden.")
            return

        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        decoded_path = urllib.parse.unquote(parsed.path)

        if decoded_path in ["/api/update", "/api/refresh"]:
            self.handle_update()
            return

        self.send_error_json(404, "Not Found")

    def handle_update(self):
        # Concurrency control: Single update at a time
        acquired = UPDATE_LOCK.acquire(blocking=False)
        if not acquired:
            self.send_error_json(409, "Une mise à jour est déjà en cours d'exécution.")
            return

        try:
            print("[*] Received live update request via API POST...")
            update_script = os.path.join(SCRIPTS_DIR, "update_changelog.py")
            res = subprocess.run(
                [sys.executable, update_script],
                capture_output=True,
                text=True,
                check=True
            )
            print("[+] Update script finished successfully.")

            insights_path = os.path.join(REAL_DATA_DIR, "insights.json")
            meta = {}
            if os.path.exists(insights_path):
                with open(insights_path, "r", encoding="utf-8") as f:
                    meta = json.load(f).get("metadata", {})

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            response_payload = {
                "success": True,
                "message": "Changelog mis à jour avec succès !",
                "metadata": meta,
                "logs": res.stdout
            }
            self.wfile.write(json.dumps(response_payload).encode("utf-8"))
        except Exception as e:
            print(f"[-] Update failed: {e}")
            self.send_error_json(500, f"Update failed: {str(e)}")
        finally:
            UPDATE_LOCK.release()

def create_server(host=DEFAULT_HOST, port=PORT):
    socketserver.TCPServer.allow_reuse_address = True
    return socketserver.TCPServer((host, port), ObservatoryHandler)

def run_server():
    with create_server(DEFAULT_HOST, PORT) as httpd:
        print(f"============================================================")
        print(f"🔒 Claude Code Strategic Observatory running SECURELY at:")
        print(f"👉 http://{DEFAULT_HOST}:{PORT}")
        print(f"Bound to: {DEFAULT_HOST} (Loopback only)")
        print(f"============================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")

if __name__ == "__main__":
    run_server()
