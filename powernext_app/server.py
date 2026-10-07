from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
import json,mimetypes,re,base64,binascii,socket,os
from .common import PACKAGE,safe_child,read_json
from powernext_config import UI, HOST, PORT
from .reports import html_report,bundle_zip

def make_server(app,port=PORT):
    class LocalServer(ThreadingHTTPServer):
        # Windows SO_REUSEADDR permits two HTTP listeners on the same endpoint;
        # clients can then reach an older app even though startup reports success.
        allow_reuse_address=False
        def server_bind(self):
            if os.name=='nt':self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            super().server_bind()
    class Handler(BaseHTTPRequestHandler):
        server_version='PowerNextLocal/0.1'
        def log_message(self,fmt,*args):pass
        def reply(self,body,status=200,content_type='application/json; charset=utf-8',filename=None):
            if not isinstance(body,bytes):body=(json.dumps(body,allow_nan=False) if content_type.startswith('application/json') else body).encode('utf-8')
            self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            if filename:self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
            self.end_headers();self.wfile.write(body)
        def check_origin(self):
            allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
            if self.headers.get('Host') not in allowed:raise ValueError('This service is available only on its local origin')
            origin=self.headers.get('Origin')
            if origin and origin not in {'http://'+host for host in allowed}:raise ValueError('Cross-origin request rejected')
        def do_GET(self):
            try:
                self.check_origin();url=urlparse(self.path);parts=url.path.strip('/').split('/');query=parse_qs(url.query)
                if url.path=='/api/meta':return self.reply(app.metadata())
                if url.path=='/api/runs':return self.reply(app.store.list())
                if len(parts)>=3 and parts[:2]==['api','runs']:
                    rid=parts[2]
                    if len(parts)==3:return self.reply(app.get_run(rid))
                    if parts[3]=='waveform':return self.reply(app.waveform(rid,query['candidate'][0]))
                    if parts[3]=='evidence':return self.reply(app.evidence(rid,query['candidate'][0]))
                    if parts[3]=='compare':return self.reply(app.compare(rid,query['left'][0],query['right'][0]))
                    if parts[3]=='measurement' and len(parts)==5:return self.reply(app.measured_waveform(rid,parts[4]))
                    if parts[3]=='measurements':return self.reply(app.measurements(rid))
                    if parts[3]=='export':
                        kind=query.get('format',['json'])[0]
                        if kind=='json':return self.reply(app.store.result_path(rid).read_bytes(),filename=rid+'.json')
                        if kind=='html':return self.reply(html_report(app,rid),content_type='text/html; charset=utf-8',filename=rid+'.html')
                        if kind=='zip':return self.reply(bundle_zip(app,rid),content_type='application/zip',filename=rid+'.zip')
                        raise ValueError('Unknown export format')
                if url.path.startswith('/api/'):raise FileNotFoundError('Unknown endpoint')
                p=safe_child(UI,'index.html' if url.path=='/' else url.path.lstrip('/'))
                if not p.is_file():raise FileNotFoundError('Page not found')
                return self.reply(p.read_bytes(),content_type=mimetypes.guess_type(p.name)[0] or 'application/octet-stream')
            except (ValueError,KeyError,TypeError) as exc:self.reply(dict(error=str(exc)),400)
            except FileNotFoundError as exc:self.reply(dict(error=str(exc)),404)
            except Exception as exc:self.reply(dict(error='Local application error',detail=str(exc)),500)
        def do_POST(self):
            try:
                self.check_origin()
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('Use application/json')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=20_000_000:raise ValueError('Request body is empty or too large')
                def bad(value):raise ValueError('Nonfinite JSON value: '+value)
                data=json.loads(self.rfile.read(length),parse_constant=bad);parts=urlparse(self.path).path.strip('/').split('/')
                if parts==['api','validate']:return self.reply(app.validate(data['request'],data.get('annotations')))
                if parts==['api','screen']:return self.reply(app.screen_scenarios(data['scenarios']))
                if parts==['api','runs']:return self.reply(app.optimize(data['request'],data.get('annotations')),202)
                if len(parts)==3 and parts[:2]==['api','demos']:return self.reply(app.load_demo(parts[2]),201)
                if len(parts)==4 and parts[:2]==['api','runs'] and parts[3]=='measurements':
                    raw=base64.b64decode(data['csv_base64'],validate=True) if 'csv_base64' in data else data['csv_text']
                    return self.reply(app.import_measurement(parts[2],raw,data['metadata']),201)
                raise FileNotFoundError('Unknown endpoint')
            except (ValueError,KeyError,TypeError) as exc:self.reply(dict(error=str(exc)),400)
            except FileNotFoundError as exc:self.reply(dict(error=str(exc)),404)
            except Exception as exc:self.reply(dict(error='Local application error',detail=str(exc)),500)
    server=LocalServer((HOST,port),Handler)
    server.daemon_threads=True
    return server
