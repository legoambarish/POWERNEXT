"""Bound local optimizer work without accepting a partial search as a result."""
import os,signal,subprocess,threading

def stream_process(command,*,cwd,env,output,on_progress,timeout_seconds):
    options=dict(cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',env=env)
    if os.name=='nt':options['creationflags']=subprocess.CREATE_NO_WINDOW
    else:options['start_new_session']=True
    proc=subprocess.Popen(command,**options)
    def drain():
        for line in proc.stdout:
            output.write(line);output.flush();on_progress(line)
    reader=threading.Thread(target=drain,daemon=True);reader.start()
    try:
        code=proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        # The optimizer owns child workers. Stop that entire process tree so
        # an extreme circuit cannot leave background solves running forever.
        if os.name=='nt':
            subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW,timeout=15)
        else:os.killpg(proc.pid,signal.SIGKILL)
        proc.wait(timeout=15);reader.join(timeout=5)
        raise TimeoutError(f'Optimization exceeded {timeout_seconds:g} seconds; stopped the worker tree. No partial recommendation was accepted. Review extreme circuit parameters or configure a longer local timeout.')
    reader.join(timeout=5)
    return code
