#!/usr/bin/env python3
"""
Fuga Vocabs local server — serves index.html and provides /api/db for the external vocab database.
Usage: python3 server.py [port]   (default port: 8765)
"""
import http.server
import json
import os
import sys
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
BASE_DIR = Path(__file__).parent.resolve()
DB_PATH = BASE_DIR / 'vocab_db.json'


class FugaHandler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    # ── CORS helper ──────────────────────────────────────────────────────────
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    # ── GET /api/db ───────────────────────────────────────────────────────────
    def do_GET(self):
        if self.path == '/api/db':
            if DB_PATH.exists():
                data = DB_PATH.read_bytes()
            else:
                data = b'{"version":"1.0","vocab":{}}'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self._cors()
            self.end_headers()
            self.wfile.write(data)
        else:
            super().do_GET()

    # ── POST /api/db ──────────────────────────────────────────────────────────
    def do_POST(self):
        if self.path == '/api/db':
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode('utf-8'))
            # Load existing DB
            if DB_PATH.exists():
                db = json.loads(DB_PATH.read_text('utf-8'))
            else:
                db = {'version': '1.0', 'vocab': {}}
            # Merge incoming vocab entries
            db['vocab'].update(body.get('vocab', {}))
            DB_PATH.write_text(
                json.dumps(db, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        print(f'  {self.address_string()}  {fmt % args}')


if __name__ == '__main__':
    os.chdir(BASE_DIR)
    print(f'Fuga Vocabs  →  http://localhost:{PORT}')
    print(f'Vocab DB     →  {DB_PATH}')
    print('Ctrl-C to stop.\n')
    with http.server.HTTPServer(('', PORT), FugaHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nServer stopped.')
