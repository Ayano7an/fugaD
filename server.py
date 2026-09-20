#!/usr/bin/env python3
"""
Fuga Vocabs local server — serves index.html and provides /api/db for the external vocab database.
Usage: python3 server.py [port]   (default port: 8765)
"""
import http.server
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
BASE_DIR = Path(__file__).parent.resolve()
DB_PATH = BASE_DIR / 'vocab_db.json'
QUEUE_PATH = BASE_DIR / 'pending_queue.json'
FREQ_PATH = BASE_DIR / 'freq_cache.json'
# ── Config hooks: every one of these can be overridden by an environment
# variable, so no machine-specific path has to live in the repository. ────────
OLLAMA_MODEL = os.environ.get('FUGA_OLLAMA_MODEL', 'qwen2.5:7b')
OLLAMA_URL = os.environ.get('FUGA_OLLAMA_URL', 'http://localhost:11434/api/generate')

# Interpreter used for the Tolino/Kobo dictionary build. pyglossary needs pyicu,
# which often lives in one specific environment (e.g. Anaconda) rather than the
# system python. Defaults to whichever interpreter is running this server, so
# launching server.py with that environment's python is enough.
DICT_PYTHON = os.environ.get('FUGA_DICT_PYTHON', sys.executable)

# ── German article stripping for lemma matching ──────────────────────────────
ARTICLES = ('der ', 'die ', 'das ', 'den ', 'dem ', 'des ')

_lemma_index = {'mtime': None, 'map': {}}
_queue_lock = threading.Lock()


def load_db():
    if DB_PATH.exists():
        try:
            return json.loads(DB_PATH.read_text('utf-8'))
        except json.JSONDecodeError:
            pass
    return {'version': '1.0', 'vocab': {}}


def strip_article(s):
    low = s.strip().lower()
    for a in ARTICLES:
        if low.startswith(a):
            return low[len(a):].strip()
    return low


def lemma_index(vocab):
    """word-key lookup table built from stored lemmas; rebuilt when the DB file changes."""
    mtime = DB_PATH.stat().st_mtime if DB_PATH.exists() else 0
    if _lemma_index['mtime'] == mtime:
        return _lemma_index['map']
    m = {}
    for word, entry in vocab.items():
        lemma = (entry or {}).get('lemma') or ''
        for key in (lemma.strip().lower(), strip_article(lemma)):
            if key and key not in m:
                m[key] = word
    _lemma_index['mtime'] = mtime
    _lemma_index['map'] = m
    return m


def clean_selection(raw):
    """Trim punctuation/quotes around a browser text selection."""
    s = (raw or '').strip()
    s = re.sub(r'^[^\wÄÖÜäöüß]+', '', s)
    s = re.sub(r'[^\wÄÖÜäöüß]+$', '', s)
    return s.strip()


def lookup_word(raw):
    """Return (matched_key, entry) or (None, None). Tries case variants, then lemmas."""
    w = clean_selection(raw)
    if not w:
        return None, None
    vocab = load_db().get('vocab', {})
    seen, candidates = set(), []
    for c in (w, w.lower(), w.capitalize(), w.upper(), w.title()):
        if c and c not in seen:
            seen.add(c)
            candidates.append(c)
    for c in candidates:
        if c in vocab:
            return c, vocab[c]
    idx = lemma_index(vocab)
    for c in candidates:
        for key in (c.lower(), strip_article(c)):
            if key in idx:
                hit = idx[key]
                return hit, vocab[hit]
    return None, None


def merge_into_db(vocab_patch):
    db = load_db()
    db.setdefault('vocab', {}).update(vocab_patch)
    DB_PATH.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding='utf-8')


# ── Source priority, mirrors index.html's SOURCE_PRIORITY ────────────────────
SOURCE_PRIORITY = {'llm': 2, 'gemma': 1}


def source_can_overwrite(incoming, existing):
    return SOURCE_PRIORITY.get(incoming, 1) >= SOURCE_PRIORITY.get((existing or {}).get('source'), 0)


# ── Pending queue: words looked up in the browser extension ──────────────────
def queue_load():
    if QUEUE_PATH.exists():
        try:
            return json.loads(QUEUE_PATH.read_text('utf-8'))
        except json.JSONDecodeError:
            pass
    return {'words': []}


def queue_push(words):
    if not words:
        return 0
    with _queue_lock:
        q = queue_load()
        now = int(time.time())
        q['words'].extend({'w': w, 't': now} for w in words)
        q['words'] = q['words'][-5000:]
        QUEUE_PATH.write_text(json.dumps(q, ensure_ascii=False), encoding='utf-8')
        # Keep the frequency cache in lockstep with the queue: every word that
        # will eventually be counted by the app is counted here immediately, so
        # the extension can show the same number the Lesen panel shows.
        freq_bump(words)
        return len(q['words'])


# ── Frequency cache ──────────────────────────────────────────────────────────
# index.html owns the real per-decade tally in its localStorage and pushes a
# flat word → total map here. The server only has to serve it back and keep it
# current between pushes, so an extension lookup and the web UI agree.
def freq_load():
    if FREQ_PATH.exists():
        try:
            return json.loads(FREQ_PATH.read_text('utf-8'))
        except json.JSONDecodeError:
            pass
    return {}


def freq_bump(words):
    m = freq_load()
    for w in words:
        m[w] = m.get(w, 0) + 1
    FREQ_PATH.write_text(json.dumps(m, ensure_ascii=False), encoding='utf-8')


def freq_replace(m):
    """The app's tally is authoritative; replacing (not merging) is what keeps
    the two from drifting apart after the queue is drained."""
    with _queue_lock:
        clean = {str(k): int(v) for k, v in (m or {}).items() if v}
        FREQ_PATH.write_text(json.dumps(clean, ensure_ascii=False), encoding='utf-8')
        return len(clean)


def queue_drain():
    with _queue_lock:
        q = queue_load()
        QUEUE_PATH.write_text(json.dumps({'words': []}, ensure_ascii=False), encoding='utf-8')
        return q.get('words', [])


# ── Single-word Ollama annotation ────────────────────────────────────────────
SINGLE_PROMPT = """对下面这一个德语词做注释，只输出一行，格式固定为五个斜线分隔的栏位：
词汇/原型或词性/繁體中文翻譯/English/词根词缀说明

规则：
1. 只输出一行，不要输出任何解释、编号、前言、结尾或空行
2. 第三栏必须是繁體中文，第四栏必须是英文，两者都不可留空
3. 名词的第二栏写冠词+单数（如 die Entwicklung），动词写不定式（如 laufen）
4. 第五栏说明词根词缀的组合方式，不超过15字；若无明显词根词缀则留空
5. 第一栏必须原样重复所给的词，不可改写

示例：
Entwicklung/die Entwicklung/發展/development/ent（去除）+Wicklung（繞組）
lief/laufen/跑/run/
Hinweis/der Hinweis/提示/hint/

词汇：{word}
"""


def ollama_single(word, context=''):
    """Run one word through Ollama and return a parsed entry dict, or raise."""
    import urllib.request

    prompt = SINGLE_PROMPT.format(word=word)
    if context:
        prompt += f'\n该词出现在这个句子中，请据此选择正确的义项：{context[:300]}\n'
    body = json.dumps({
        'model': OLLAMA_MODEL,
        'prompt': prompt,
        'stream': True,
        'think': False,
        'options': {'num_ctx': 4096, 'temperature': 0.2},
    }).encode('utf-8')
    req = urllib.request.Request(
        OLLAMA_URL, data=body,
        headers={'Content-Type': 'application/json'}, method='POST')
    text = ''
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw_line in resp:
            line = raw_line.decode('utf-8').strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            text += chunk.get('response', '')
            if chunk.get('done'):
                break
    return parse_single(word, text)


def parse_single(word, text):
    """Pick the best '/'-delimited line out of a possibly chatty model reply."""
    best = None
    for line in text.split('\n'):
        line = line.strip()
        if '/' not in line:
            continue
        parts = [p.strip() for p in line.split('/')]
        if len(parts) < 2 or not parts[0]:
            continue
        if best is None or parts[0].lower() == word.lower():
            best = parts
            if parts[0].lower() == word.lower():
                break
    if not best:
        raise ValueError(f'模型输出无法解析: {text[:120]!r}')
    return {
        'word': word,
        'lemma': best[1] if len(best) > 1 and best[1] else word,
        'zh': best[2] if len(best) > 2 else '',
        'en': best[3] if len(best) > 3 else '',
        'etym': best[4] if len(best) > 4 else '',
        'source': 'gemma',
    }


class FugaHandler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    # ── CORS helper ──────────────────────────────────────────────────────────
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get('Content-Length', 0))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    # ── GET ───────────────────────────────────────────────────────────────────
    def do_GET(self):
        route = urlparse(self.path)
        query = parse_qs(route.query)

        if route.path == '/api/db':
            if DB_PATH.exists():
                data = DB_PATH.read_bytes()
            else:
                data = b'{"version":"1.0","vocab":{}}'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self._cors()
            self.end_headers()
            self.wfile.write(data)
            return

        # ── GET /api/lookup?w=Wort — single-word lookup for the extension ────
        if route.path == '/api/lookup':
            raw = (query.get('w') or [''])[0]
            word = clean_selection(raw)
            if not word:
                self._json({'found': False, 'word': '', 'error': 'empty'})
                return
            key, entry = lookup_word(word)
            if entry is None:
                self._json({'found': False, 'word': word})
                return
            # count=1 records the encounter (queue for the app + bump the cache)
            # before reading the tally back, so the number returned includes this
            # lookup — matching what the web UI shows after recordFrequencies().
            if (query.get('count') or ['0'])[0] in ('1', 'true'):
                queue_push([key])
            self._json({
                'found': True,
                'word': word,
                'key': key,
                'freq': freq_load().get(key, 0),
                'entry': {
                    'word': key,
                    'lemma': entry.get('lemma') or key,
                    'zh': entry.get('zh', ''),
                    'en': entry.get('en', ''),
                    'etym': entry.get('etym', ''),
                    'source': entry.get('source', ''),
                },
            })
            return

        # ── GET /api/pending[?drain=1] — main app drains extension lookups ───
        if route.path == '/api/pending':
            if (query.get('drain') or ['0'])[0] in ('1', 'true'):
                words = queue_drain()
            else:
                words = queue_load().get('words', [])
            self._json({'words': words, 'count': len(words)})
            return

        super().do_GET()

    # ── POST ──────────────────────────────────────────────────────────────────
    def do_POST(self):
        route = urlparse(self.path)

        if route.path == '/api/llm':
            import urllib.request, urllib.error
            try:
                req_body = self._read_json()
                prompt = req_body.get('prompt', '')
                ollama_req = json.dumps({
                    'model': OLLAMA_MODEL,
                    'prompt': prompt,
                    'stream': True,
                    'think': False,
                    'options': {'num_ctx': 8192}
                }).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('X-Accel-Buffering', 'no')
                self._cors()
                self.end_headers()
                result_text = ''
                with urllib.request.urlopen(
                    urllib.request.Request(
                        OLLAMA_URL,
                        data=ollama_req,
                        headers={'Content-Type': 'application/json'},
                        method='POST'
                    ), timeout=180
                ) as ollama_resp:
                    for raw_line in ollama_resp:
                        line = raw_line.decode('utf-8').strip()
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        token = chunk.get('response', '')
                        result_text += token
                        done = chunk.get('done', False)
                        event = json.dumps({'token': token, 'done': done}, ensure_ascii=False)
                        self.wfile.write(f'data: {event}\n\n'.encode('utf-8'))
                        self.wfile.flush()
                        if done:
                            break
                print(f'  [llm] done ({len(result_text)} chars)')
            except urllib.error.URLError as e:
                print(f'  [llm] URLError: {e}')
                err = json.dumps({'error': f'Ollama 連接失敗: {e.reason}'})
                self.wfile.write(f'data: {err}\n\n'.encode('utf-8'))
                self.wfile.flush()
            except Exception as e:
                import traceback; traceback.print_exc()
                err = json.dumps({'error': str(e)})
                try:
                    self.wfile.write(f'data: {err}\n\n'.encode('utf-8'))
                    self.wfile.flush()
                except Exception:
                    pass
            return

        # ── POST /api/translate — one word through Ollama, saved to the DB ───
        if route.path == '/api/translate':
            import urllib.error
            try:
                body = self._read_json()
                word = clean_selection(body.get('word', ''))
                context = (body.get('context') or '').strip()
                if not word:
                    self._json({'ok': False, 'error': 'empty word'}, 400)
                    return
                entry = ollama_single(word, context)
                existing = load_db().get('vocab', {}).get(entry['word'])
                if source_can_overwrite('gemma', existing):
                    merge_into_db({entry['word']: {
                        'zh': entry['zh'], 'en': entry['en'],
                        'lemma': entry['lemma'], 'etym': entry['etym'],
                        'source': 'gemma',
                    }})
                    saved = True
                else:
                    entry = {**entry, **existing, 'word': entry['word'],
                             'etym': existing.get('etym', '')}
                    saved = False
                if body.get('count'):
                    queue_push([entry['word']])
                entry['freq'] = freq_load().get(entry['word'], 0)
                print(f'  [translate] {word} → {entry["zh"]} / {entry["en"]}')
                self._json({'ok': True, 'entry': entry, 'saved': saved})
            except urllib.error.URLError as e:
                self._json({'ok': False, 'error': f'Ollama 連接失敗: {e.reason}'}, 502)
            except Exception as e:
                self._json({'ok': False, 'error': str(e)}, 500)
            return

        # ── POST /api/pending — extension enqueues encountered words ─────────
        if route.path == '/api/pending':
            try:
                body = self._read_json()
                words = [w for w in (body.get('words') or []) if w]
                total = queue_push(words)
                self._json({'ok': True, 'queued': len(words), 'total': total})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)}, 500)
            return

        # ── POST /api/freq — index.html pushes its authoritative tally ──────
        if route.path == '/api/freq':
            try:
                n = freq_replace(self._read_json().get('freq'))
                self._json({'ok': True, 'words': n})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)}, 500)
            return

        if route.path == '/api/build-dict':
            import subprocess
            try:
                result = subprocess.run(
                    [DICT_PYTHON, str(BASE_DIR / 'build_quickdic.py')],
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

        if route.path == '/api/db':
            body = self._read_json()
            db = load_db()
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


class ThreadedHTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True


if __name__ == '__main__':
    os.chdir(BASE_DIR)
    print(f'Fuga Vocabs  →  http://localhost:{PORT}')
    print(f'Vocab DB     →  {DB_PATH}')
    print(f'Ollama       →  {OLLAMA_MODEL}')
    print(f'Dict python  →  {DICT_PYTHON}')
    print('Ctrl-C to stop.\n')
    with ThreadedHTTPServer(('', PORT), FugaHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nServer stopped.')
