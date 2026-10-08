import argparse,os,webbrowser,threading,json,secrets
import powernext_config as config
from pathlib import Path
from .common import PACKAGE

def main():
    parser=argparse.ArgumentParser(description='Offline PowerNext engineering application')
    parser.add_argument('--port',type=int,default=config.PORT)
    parser.add_argument('--data-dir',type=Path,default=config.DATA)
    parser.add_argument('--workers',type=int,default=config.WORKERS)
    parser.add_argument('--timeout-seconds',type=float,default=config.TIMEOUT_SECONDS,help='Stop an unfinished search after this wall-clock budget; never return a partial ranking')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--adapter',default='provisional')
    parser.add_argument('--registry',type=Path)
    parser.add_argument('--selection',type=Path)
    args=parser.parse_args()
    if not 1<=args.workers<=16:parser.error('Workers must be 1 through 16')
    if not 1<=args.port<=65535:parser.error('Port must be 1 through 65535')
    os.environ.setdefault('OMP_NUM_THREADS','1');os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
    from .service import Application
    from .server import make_server
    from .instance import InstanceLock
    app=None
    lock=None
    try:
        print('[START] Validating local profiles, models and interface assets...',flush=True)
        config.validate_assets()
        lock=InstanceLock(args.data_dir)
        app=Application(args.data_dir,adapter=args.adapter,registry=args.registry,selection=args.selection,workers=args.workers,timeout_seconds=args.timeout_seconds)
        config.validate_models(app)
        print('[READY] Physics, all four ML routes, Optimizer and local database loaded.',flush=True)
        server=make_server(app,args.port)
        app.shutdown_token=secrets.token_hex(32)
        (app.store.root/'server_connection.json').write_text(json.dumps(dict(port=server.server_port,token=app.shutdown_token,pid=os.getpid())),encoding='utf-8')
    except Exception as exc:
        if app is not None:app.close()
        if lock is not None:lock.close()
        parser.exit(1,f'PowerNext could not start: {exc}\nRun .\\runtime\\python.exe -m powernext_app from the release folder.\n')
    url=f'http://{config.HOST}:{server.server_port}/'
    print(f'PowerNext local application: {url}\nSaved runs: {args.data_dir.resolve()}\nOffline processing. Provisional recipes; no hardware control. Ctrl+C to stop.',flush=True)
    if not args.no_browser:
        opener=threading.Timer(.5,lambda:webbrowser.open(url));opener.daemon=True;opener.start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.server_close();app.close()
        connection=app.store.root/'server_connection.json'
        if connection.exists():connection.unlink()
        lock.close()

if __name__=='__main__':main()
