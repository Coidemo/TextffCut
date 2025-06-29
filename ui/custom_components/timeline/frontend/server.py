#!/usr/bin/env python3
"""簡易開発サーバー for Streamlit component"""

import http.server
import os
import socketserver

PORT = 3001
DIRECTORY = os.path.dirname(os.path.abspath(__file__))


class CORSRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()


print(f"Serving at http://localhost:{PORT}")
print(f"Directory: {DIRECTORY}")

with socketserver.TCPServer(("", PORT), CORSRequestHandler) as httpd:
    httpd.serve_forever()
