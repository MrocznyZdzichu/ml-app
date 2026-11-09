from collections.abc import Iterator
from contextlib import contextmanager
import errno
import os
from pathlib import Path
from time import sleep


@contextmanager
def exclusive_file_lock(path: Path) -> Iterator[None]:
    """Serialize processes using the same lock file on the shared filesystem."""
    # Keep the file in place so that all waiters lock the same filesystem object.
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt

            stream.seek(0)
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EDEADLK}:
                        raise
                    sleep(0.1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield
