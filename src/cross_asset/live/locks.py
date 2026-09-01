"""Cross-process atomic run lock with explicit stale recovery."""
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path


class RunLock:
    def __init__(
        self,
        path="data/.run.lock",
        run_key="run",
        ttl_seconds=3600,
        clock: Callable[[], datetime] | None = None,
    ):
        self.path = Path(path)
        self.run_key = run_key
        self.ttl_seconds = ttl_seconds
        self.clock = clock or (lambda: datetime.now(UTC))
        self.acquired = False

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("RunLock clock must return a timezone-aware datetime")
        return value.astimezone(UTC)

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_key": self.run_key,
            "pid": os.getpid(),
            "started_at": self._now().isoformat(),
            "ttl_seconds": self.ttl_seconds,
        }
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, json.dumps(payload).encode())
            finally:
                os.close(fd)
            self.acquired = True
            return True
        except FileExistsError as exc:
            raise RuntimeError(f"run lock already held: {self.path}") from exc

    def release(self):
        if self.acquired:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            self.acquired = False

    def recover(self, force=False):
        if not self.path.exists():
            return False
        data = json.loads(self.path.read_text(encoding="utf-8"))
        started = datetime.fromisoformat(data["started_at"])
        if started.tzinfo is None:
            raise ValueError("stored RunLock timestamp must be timezone-aware")
        age = (self._now() - started.astimezone(UTC)).total_seconds()
        stale = age >= float(data.get("ttl_seconds", self.ttl_seconds))
        if not (force or stale):
            raise RuntimeError("lock is not stale; explicit force required")
        self.path.unlink()
        return True

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_):
        self.release()
