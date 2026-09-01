"""Cross-process atomic run lock with explicit stale recovery."""
import json
import os
from datetime import UTC, datetime
from pathlib import Path


class RunLock:
    def __init__(self,path='data/.run.lock',run_key='run',ttl_seconds=3600): self.path=Path(path); self.run_key=run_key; self.ttl_seconds=ttl_seconds; self.acquired=False
    def acquire(self):
        self.path.parent.mkdir(parents=True,exist_ok=True); payload={'run_key':self.run_key,'pid':os.getpid(),'started_at':datetime.now(UTC).isoformat(),'ttl_seconds':self.ttl_seconds}
        try:
            fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY); os.write(fd,json.dumps(payload).encode()); os.close(fd); self.acquired=True; return True
        except FileExistsError: raise RuntimeError(f'run lock already held: {self.path}')
    def release(self):
        if self.acquired:
            try: self.path.unlink()
            except FileNotFoundError: pass
            self.acquired=False
    def recover(self,force=False):
        if not self.path.exists(): return False
        data=json.loads(self.path.read_text(encoding='utf-8')); started=datetime.fromisoformat(data['started_at']); stale=(datetime.now(UTC)-started).total_seconds()>float(data.get('ttl_seconds',self.ttl_seconds))
        if not (force or stale): raise RuntimeError('lock is not stale; explicit force required')
        self.path.unlink(); return True
    def __enter__(self): self.acquire(); return self
    def __exit__(self,*_): self.release()
