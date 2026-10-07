"""Real-browser RT-08 fixture: delay the prior SI POST, retain the actual API/UI."""
import time,sys,threading
from pathlib import Path
import powernext_config as config
from powernext_app.service import Application
from powernext_app.server import make_server

app=Application(config.ROOT/'evidence/race_browser_data')
original=app.load_demo
def delayed(identifier):
    print(f'START {identifier} {time.monotonic()}',flush=True)
    time.sleep(2 if identifier=='si' else .05)
    result=original(identifier)
    print(f'END {identifier} {time.monotonic()}',flush=True)
    return result
app.load_demo=delayed
server=make_server(app,8776)
print('Race fixture ready on http://127.0.0.1:8776/',flush=True)
try:server.serve_forever()
finally:server.server_close();app.close()
