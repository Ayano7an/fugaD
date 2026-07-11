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
        if self.path == '/api/llm':
            import urllib.request, urllib.error
            body = b''
            try:
                length = int(self.headers.get('Content-Length', 0))
                req_body = json.loads(self.rfile.read(length).decode('utf-8'))
                prompt = req_body.get('prompt', '')
                ollama_req = json.dumps({
                    'model': 'gemma3:4b',
                    'prompt': prompt,
                    'stream': False,
                    'think': False
                }).encode('utf-8')
                with urllib.request.urlopen(
                    urllib.request.Request(
                        'http://localhost:11434/api/generate',
                        data=ollama_req,
                        headers={'Content-Type': 'application/json'},
                        method='POST'
                    ), timeout=180
                ) as ollama_resp:
                    raw = ollama_resp.read().decode('utf-8')
                print(f'  [llm] ollama raw ({len(raw)} chars): {raw[:200]}')
                # Ollama may return newline-delimited JSON when stream=False but outputs chunks
                # Take the last non-empty line that has "response" key
                result_text = ''
                for line in raw.strip().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        if 'response' in chunk:
                            result_text += chunk['response']
                        if chunk.get('done'):
                            break
                    except json.JSONDecodeError:
                        continue
                body = json.dumps({'result': result_text}, ensure_ascii=False).encode('utf-8')
            except urllib.error.URLError as e:
                print(f'  [llm] URLError: {e}')
                body = json.dumps({'error': f'Ollama 連接失敗: {e.reason}'}).encode('utf-8')
            except Exception as e:
                import traceback; traceback.print_exc()
                body = json.dumps({'error': str(e)}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == '/api/build-dict':
            import subprocess
            try:
                result = subprocess.run(
                    ['/opt/anaconda3/bin/python', str(BASE_DIR / 'build_quickdic.py')],
                    capture_output=True, text=True, timeout=60
                )
                ok = result.returncode == 0
                msg = (result.stdout + result.stderr).strip()
                body = json.dumps({'ok': ok, 'msg': msg}, ensure_ascii=False).encode('utf-8')
            except Exception as e:
                body = json.dumps({'ok': False, 'msg': str(e)}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return

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
