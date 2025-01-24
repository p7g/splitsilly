import errno
import fcntl
import hashlib
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

lock_dir = Path(__file__).parent.parent.parent / "_locks"
lock_dir.mkdir(exist_ok=True)


class LockNotAcquired(Exception):
    pass


@contextmanager
def _timeout(seconds: int | float) -> Iterator[None]:
    def timeout_handler(signum, frame):
        raise InterruptedError

    original_handler = signal.signal(signal.SIGALRM, timeout_handler)

    try:
        signal.alarm(seconds)
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, original_handler)


class Lock:
    def __init__(self, key: str) -> None:
        hashed_key = hashlib.new("md5", key.encode()).hexdigest()
        self.file = open(lock_dir / hashed_key, "wb")

    def __del__(self) -> None:
        self.file.close()

    def __enter__(self) -> None:
        self.acquire()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()

    def acquire(self, blocking: bool = True, timeout: int | float = None) -> "Lock":
        if timeout is None:
            return self._acquire(blocking=blocking)

        assert blocking
        with _timeout(timeout):
            return self._acquire(blocking=True)

    def _acquire(self, blocking: bool = True) -> "Lock":
        cmd = fcntl.LOCK_EX
        if not blocking:
            cmd |= fcntl.LOCK_NB
        while True:
            try:
                fcntl.lockf(self.file, cmd)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                elif blocking:
                    continue
                else:
                    raise LockNotAcquired(self.key)
        return self

    def release(self) -> None:
        fcntl.lockf(self.file, fcntl.LOCK_UN)
