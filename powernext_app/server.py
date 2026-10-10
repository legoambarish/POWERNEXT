from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
import json,mimetypes,re,base64,binascii,socket,os
import secrets,threading
from .common import PACKAGE,safe_child,read_json
from powernext_config import UI, HOST, PORT
from .reports import html_report,bundle_zip
from .engineering import predict_configuration,discover,verify_discovery,load_discovery,next_adjustment,informative_measurement
from .evidence import reopen_bundle
from .bench import predict_bench,compare_bench

def make_server(app,port=PORT):
    # The v3 network workspace is deliberately lazy and versioned.  The
    # legacy service keeps ownership of its existing executor, database, and
    # model routes; a v3 request creates a separate facade below
    # ``<data-root>/v3`` only when that API is used.
    v3_holder={'application':None,'lock':threading.RLock()}
    def v3_application():
        with v3_holder['lock']:
            if v3_holder['application'] is None:
                from powernext_v3.application import V3Application
                workers=min(4,max(1,int(getattr(app,'workers',1))))
                v3_holder['application']=V3Application(
                    app.store.root/'v3', workers=workers,
                    timeout_seconds=float(getattr(app,'timeout_seconds',90.0)),
                )
            return v3_holder['application']
    class LocalServer(ThreadingHTTPServer):
        # Windows SO_REUSEADDR permits two HTTP listeners on the same endpoint;
        # clients can then reach an older app even though startup reports success.
        allow_reuse_address=False
        def server_bind(self):
            if os.name=='nt':self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            super().server_bind()
        def server_close(self):
            with v3_holder['lock']:
                current=v3_holder['application']
                v3_holder['application']=None
            if current is not None:
                current.close()
            super().server_close()
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
                if url.path=='/api/v3/meta':return self.reply(v3_application().metadata())
                if url.path=='/api/v3/runs':return self.reply(v3_application().list_runs())
                if len(parts)==4 and parts[:3]==['api','v3','runs']:
                    return self.reply(v3_application().get_run(parts[3]))
                if len(parts)==5 and parts[:4]==['api','v3','runs',parts[3]] and parts[4]=='waveform':
                    candidate=query.get('candidate',[None])[0]
                    if not candidate:raise ValueError('candidate query parameter is required')
                    return self.reply(v3_application().waveform(parts[3],candidate))
                if len(parts)==4 and parts[:3]==['api','v3','predictions']:
                    return self.reply(v3_application().get_prediction(parts[3]))
                if len(parts)==5 and parts[:4]==['api','v3','predictions',parts[3]] and parts[4]=='waveform':
                    return self.reply(v3_application().prediction_waveform(parts[3]))
                if len(parts)==6 and parts[:3]==['api','v3','predictions'] and parts[4]=='reference':
                    return self.reply(v3_application().get_reference(parts[3],parts[5]))
                if len(parts)==3 and parts[:2]==['api','technical'] and parts[2] in app.metadata()['technical_documents']:
                    return self.reply((PACKAGE/'docs/integration'/parts[2]).read_text(encoding='utf-8'),content_type='text/plain; charset=utf-8')
                if url.path=='/api/runs':return self.reply(app.store.list())
                if url.path=='/api/discoveries':
                    root=app.store.root/'discoveries'
                    return self.reply([dict(discovery_id=p.parent.name,created_at=r['created_at'],policy=r['policy'],scenario_count=len(r['scenarios'])) for p in sorted(root.glob('explore_*/record.json'),reverse=True) for r in [read_json(p)]])
                if len(parts)==3 and parts[:2]==['api','discoveries']:return self.reply(load_discovery(app,parts[2]))
                if len(parts)>=3 and parts[:2]==['api','runs']:
                    rid=parts[2]
                    if len(parts)==3:return self.reply(app.get_run(rid))
                    if parts[3]=='waveform':return self.reply(app.waveform(rid,query['candidate'][0]))
                    if parts[3]=='evidence':return self.reply(app.evidence(rid,query['candidate'][0]))
                    if parts[3]=='compare':return self.reply(app.compare(rid,query['left'][0],query['right'][0]))
                    if parts[3]=='measurement' and len(parts)==5:return self.reply(app.measured_waveform(rid,parts[4]))
                    if parts[3]=='measurements':return self.reply(app.measurements(rid))
                    if parts[3]=='next-measurement':return self.reply(informative_measurement(app,rid))
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
                if urlparse(self.path).path=='/api/reopen' and self.headers.get('Content-Type')=='application/zip':
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=200_000_000:raise ValueError('ZIP exceeds 200 MB')
                    return self.reply(reopen_bundle(app,self.rfile.read(length)),201)
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('Use application/json')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=20_000_000:raise ValueError('Request body is empty or too large')
                def bad(value):raise ValueError('Nonfinite JSON value: '+value)
                data=json.loads(self.rfile.read(length),parse_constant=bad);parts=urlparse(self.path).path.strip('/').split('/')
                if parts==['api','shutdown']:
                    expected=getattr(app,'shutdown_token',None)
                    if not expected or not isinstance(data.get('token'),str) or not secrets.compare_digest(data['token'],expected):raise ValueError('Invalid local shutdown token')
                    self.reply(dict(status='STOPPING',detail='Current optimization, if any, completes before data lock is released'))
                    threading.Thread(target=self.server.shutdown,daemon=True).start();return
                if parts==['api','validate']:return self.reply(app.validate(data['request'],data.get('annotations')))
                if parts==['api','v3','validate']:
                    request=data.get('request',data) if isinstance(data,dict) else data
                    return self.reply(v3_application().validate(request))
                if parts==['api','v3','runs']:
                    request=data.get('request',data) if isinstance(data,dict) else data
                    return self.reply(v3_application().start_search(request),202)
                if parts==['api','v3','predict']:
                    return self.reply(v3_application().predict_fixed(data),201)
                if len(parts)==5 and parts[:3]==['api','v3','predictions'] and parts[4]=='reference':
                    if not isinstance(data,dict):raise ValueError('Reference request must be an object')
                    metadata=data.get('metadata',{})
                    metadata_text=data.get('metadata_text')
                    metadata_bytes=metadata_text.encode('utf-8') if isinstance(metadata_text,str) else None
                    if 'metrics' in data:
                        return self.reply(v3_application().attach_reference_metrics(parts[3],data['metrics'],metadata,metadata_bytes=metadata_bytes),201)
                    if 'csv_base64' in data:
                        raw=base64.b64decode(data['csv_base64'],validate=True)
                    elif 'csv_text' in data:
                        raw=data['csv_text']
                    else:
                        raise ValueError('Reference request requires csv_text or csv_base64')
                    return self.reply(v3_application().attach_reference(parts[3],raw,metadata,metadata_bytes=metadata_bytes),201)
                if len(parts)==5 and parts[:3]==['api','v3','predictions'] and parts[4]=='reference-metrics':
                    if not isinstance(data,dict):raise ValueError('Reference request must be an object')
                    metadata=data.get('metadata',{})
                    metadata_text=data.get('metadata_text')
                    metadata_bytes=metadata_text.encode('utf-8') if isinstance(metadata_text,str) else None
                    return self.reply(v3_application().attach_reference_metrics(parts[3],data.get('metrics',{}),metadata,metadata_bytes=metadata_bytes),201)
                if parts==['api','screen']:return self.reply(app.screen_scenarios(data['scenarios']))
                if parts==['api','predict']:return self.reply(predict_configuration(app,data))
                if parts==['api','discoveries']:return self.reply(discover(app,data),201)
                if len(parts)==4 and parts[:2]==['api','discoveries'] and parts[3]=='verify':return self.reply(verify_discovery(app,parts[2],data['indices']))
                if parts==['api','bench']:return self.reply(predict_bench(data['parameters']))
                if parts==['api','bench','compare']:return self.reply(compare_bench(data['parameters'],data['csv_text'],data.get('source_filename','unnamed.csv')))
                if len(parts)==4 and parts[:2]==['api','runs'] and parts[3]=='next-adjustment':return self.reply(next_adjustment(app,parts[2],data['configuration']))
                if parts==['api','runs']:return self.reply(app.optimize(data['request'],data.get('annotations')),202)
                if len(parts)==3 and parts[:2]==['api','demos']:return self.reply(app.load_demo(parts[2]),201)
                if len(parts)==4 and parts[:2]==['api','runs'] and parts[3]=='measurements':
                    raw=base64.b64decode(data['csv_base64'],validate=True) if 'csv_base64' in data else data['csv_text']
                    return self.reply(app.import_measurement(parts[2],raw,data['metadata'],data.get('metadata_text')),201)
                raise FileNotFoundError('Unknown endpoint')
            except (ValueError,KeyError,TypeError) as exc:self.reply(dict(error=str(exc)),400)
            except FileNotFoundError as exc:self.reply(dict(error=str(exc)),404)
            except Exception as exc:self.reply(dict(error='Local application error',detail=str(exc)),500)
    server=LocalServer((HOST,port),Handler)
    # Close waits for active evidence imports/predictions as well as the
    # application's optimizer executor, so a stop cannot truncate a record.
    server.daemon_threads=False
    return server
