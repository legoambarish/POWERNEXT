"""OS-held single-writer lock, released automatically even after a crash."""
from pathlib import Path
import os

class InstanceLock:
    def __init__(self,data_dir):
        folder=Path(data_dir).resolve();folder.mkdir(parents=True,exist_ok=True)
        self.stream=(folder/'.instance.lock').open('a+b')
        self.stream.seek(0,2)
        if self.stream.tell()==0:self.stream.write(b'0');self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:
            self.stream.close()
            raise RuntimeError('This data directory is already open in another PowerNext instance. Close that instance or choose a different --data-dir.') from exc
    def close(self):
        self.stream.close()
