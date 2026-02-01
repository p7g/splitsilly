import errno
import fcntl
import hashlib
import signal
import types
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Never

lock_dir = Path(__file__).parent.parent.parent / "_locks"
lock_dir.mkdir(exist_ok=True)


class LockNotAcquired(Exception):
    pass


class LockTimeout(Exception):
    pass


@contextmanager
def _timeout(seconds: int) -> Iterator[None]:
    def timeout_handler(signum: int, frame: types.FrameType | None) -> Never:
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
        self.key = key
        hashed_key = hashlib.new("md5", key.encode()).hexdigest()
        self.file = open(lock_dir / hashed_key, "wb")

    def __del__(self) -> None:
        self.file.close()

    def __enter__(self) -> None:
        self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        self.release()

    def acquire(self, blocking: bool = True, timeout: int | None = None) -> "Lock":
        if timeout is None:
            return self._acquire(blocking=blocking)

        assert blocking
        try:
            with _timeout(timeout):
                return self._acquire(blocking=True)
        except InterruptedError as e:
            raise LockTimeout(self.key) from e

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
                    raise LockNotAcquired(self.key) from exc
        return self

    def release(self) -> None:
        fcntl.lockf(self.file, fcntl.LOCK_UN)
