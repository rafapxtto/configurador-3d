#!/usr/bin/env python3
import http.server
import os, json, time, mimetypes, socketserver, base64, urllib.request, urllib.error

PORT          = int(os.environ.get('PORT', 8080))
ASSET_BASE_URL = os.environ.get('ASSET_BASE_URL', '').rstrip('/')
GITHUB_TOKEN  = os.environ.get('GITHUB_TOKEN', '')
GITHUB_REPO   = os.environ.get('GITHUB_REPO', '')   # ex: rafapxtto/configurador-3d
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
EXPORTS_DIR   = os.path.join(BASE_DIR, 'exports')
os.makedirs(EXPORTS_DIR, exist_ok=True)

def _inject_base_url(catalog: dict) -> dict:
    if not ASSET_BASE_URL:
        return catalog
    import copy
    c = copy.deepcopy(catalog)
    for m in c.get('modulos', []):
        if m.get('file') and not m['file'].startswith('http'):
            m['file'] = ASSET_BASE_URL + '/' + m['file']
    for a in c.get('acabamentos', []):
        for key in ('tex_color', 'tex_normal'):
            if a.get(key) and not a[key].startswith('http'):
                a[key] = ASSET_BASE_URL + '/' + a[key]
    return c

def _push_catalog_to_github(content_bytes: bytes) -> str:
    """Commit catalog.json to GitHub. Returns '' on success or error message."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return 'GITHUB_TOKEN ou GITHUB_REPO não configurados'
    api = f'https://api.github.com/repos/{GITHUB_REPO}/contents/catalog.json'
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json',
    }
    # Get current SHA
    sha = None
    try:
        req = urllib.request.Request(api, headers=headers)
        with urllib.request.urlopen(req) as r:
            sha = json.loads(r.read())['sha']
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return f'Erro ao buscar SHA: {e.code}'
    payload = {
        'message': 'Admin: atualiza catalog.json',
        'content': base64.b64encode(content_bytes).decode(),
        'branch': 'main',
    }
    if sha:
        payload['sha'] = sha
    try:
        req = urllib.request.Request(api, data=json.dumps(payload).encode(), headers=headers, method='PUT')
        urllib.request.urlopen(req)
        return ''
    except urllib.error.HTTPError as e:
        return f'Erro GitHub: {e.code} {e.read().decode()[:200]}'

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def add_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self.add_cors()
        self.end_headers()

    def _json(self, data: dict, status=200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.add_cors()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body   = self.rfile.read(length)

        if self.path == '/admin/save-catalog':
            try:
                catalog = json.loads(body)
            except Exception as e:
                self._json({'ok': False, 'error': f'JSON inválido: {e}'}, 400)
                return
            # Salva no disco
            fpath = os.path.join(BASE_DIR, 'catalog.json')
            content = json.dumps(catalog, ensure_ascii=False, indent=2).encode('utf-8')
            with open(fpath, 'wb') as f:
                f.write(content)
            # Tenta persistir no GitHub
            gh_err = _push_catalog_to_github(content)
            self._json({'ok': True, 'github': gh_err or 'ok'})

        elif self.path == '/export/save':
            ts    = time.strftime('%Y%m%d_%H%M%S')
            fname = f'Config_{ts}.glb'
            fpath = os.path.join(EXPORTS_DIR, fname)
            with open(fpath, 'wb') as f:
                f.write(body)
            self._json({'ok': True, 'filename': fname, 'url': '/exports/' + fname})

        else:
            self.send_error(404)

    def do_GET(self):
        if self.path == '/catalog.json':
            fpath = os.path.join(BASE_DIR, 'catalog.json')
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    catalog = json.load(f)
                data = json.dumps(_inject_base_url(catalog)).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.add_cors()
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_error(500, str(e))
            return

        if self.path == '/export/list':
            files = []
            for f in sorted(os.listdir(EXPORTS_DIR), reverse=True):
                if f.endswith('.glb'):
                    fp = os.path.join(EXPORTS_DIR, f)
                    files.append({'filename': f, 'url': '/exports/'+f, 'size': os.path.getsize(fp)})
            self._json(files)
            return

        if self.path.startswith('/exports/'):
            fname = self.path[9:]
            fpath = os.path.join(EXPORTS_DIR, fname)
            if os.path.isfile(fpath):
                self.send_response(200)
                self.send_header('Content-Type', 'model/gltf-binary')
                self.send_header('Content-Length', str(os.path.getsize(fpath)))
                self.add_cors()
                self.end_headers()
                with open(fpath, 'rb') as f:
                    self.wfile.write(f.read())
                return

        super().do_GET()

    def log_message(self, fmt, *args):
        pass  # quiet

with socketserver.TCPServer(('0.0.0.0', PORT), Handler) as httpd:
    httpd.allow_reuse_address = True
    print(f'Servidor rodando na porta {PORT}')
    httpd.serve_forever()
