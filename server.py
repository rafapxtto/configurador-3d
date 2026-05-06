#!/usr/bin/env python3
import http.server
import os, json, time, mimetypes, socketserver

PORT = int(os.environ.get('PORT', 8080))
ASSET_BASE_URL = os.environ.get('ASSET_BASE_URL', '').rstrip('/')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORTS_DIR = os.path.join(BASE_DIR, 'exports')
os.makedirs(EXPORTS_DIR, exist_ok=True)

def _inject_base_url(catalog: dict) -> dict:
    """Prefix relative file/tex paths with ASSET_BASE_URL when set."""
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

    def do_POST(self):
        if self.path == '/export/save':
            length = int(self.headers.get('Content-Length', 0))
            body   = self.rfile.read(length)
            ts     = time.strftime('%Y%m%d_%H%M%S')
            fname  = f'Config_{ts}.glb'
            fpath  = os.path.join(EXPORTS_DIR, fname)
            with open(fpath, 'wb') as f:
                f.write(body)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.add_cors()
            self.end_headers()
            self.wfile.write(json.dumps({
                'ok': True,
                'filename': fname,
                'url': '/exports/' + fname
            }).encode())
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
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.add_cors()
            self.end_headers()
            self.wfile.write(json.dumps(files).encode())
            return
        # Serve exports folder
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
