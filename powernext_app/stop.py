"""Stop only the locally recorded application instance; never kill other Python."""
import argparse,json,time
from pathlib import Path
from urllib.request import Request,urlopen
import powernext_config as config

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path,default=config.DATA);args=parser.parse_args()
    path=args.data_dir.resolve()/'server_connection.json'
    if not path.exists():print('No running PowerNext instance recorded in this data folder.');return
    info=json.loads(path.read_text(encoding='utf-8'))
    req=Request(f"http://127.0.0.1:{int(info['port'])}/api/shutdown",data=json.dumps({'token':info['token']}).encode(),headers={'Content-Type':'application/json'})
    with urlopen(req,timeout=10) as response:print(json.load(response)['detail'],flush=True)
    start=time.monotonic()
    while path.exists() and time.monotonic()-start<400:
        time.sleep(.25)
        if int((time.monotonic()-start)*4)%100==0:print('Waiting for current work to finish…',flush=True)
    if path.exists():raise RuntimeError('Shutdown did not finish within 400 seconds; inspect the server console')
    print('PowerNext stopped; saved evidence retained.',flush=True)
if __name__=='__main__':main()
