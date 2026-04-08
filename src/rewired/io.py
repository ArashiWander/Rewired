"""Safe I/O utilities — atomic writes and file locking.

Atomic writes prevent data corruption when a crash or power loss occurs
mid-write.  The pattern: write to a temp file in the same directory,
fsync, then ``os.replace()`` (atomic on NTFS and POSIX filesystems).

File locking prevents concurrent CLI + GUI/monitor processes from
corrupting shared state files like ``regime_state.json``.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)


def atomic_write(path: Path | str, data: str, encoding: str = "utf-8") -> None:
    """Write *data* to *path* atomically.

    1. Write to ``<path>.tmp`` in the same directory.
    2. ``fsync`` to flush OS buffers to disk.
    3. ``os.replace`` to atomically swap the temp file into place.

    If the process crashes between steps 1 and 3, only the ``.tmp`` file
    is left behind — the original file remains intact.
    """
    path = Path(path)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp_path, "w", encoding=encoding) as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp_path), str(path))
    except OSError:
        # Clean up temp file on failure
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


@contextmanager
def file_lock(path: Path | str, timeout: float = 10.0) -> Generator[None, None, None]:
    """Acquire an exclusive advisory lock on *path*.

    Uses ``portalocker`` for cross-platform file locking.  Falls back to
    a no-op if ``portalocker`` is not installed (graceful degradation for
    development environments without the optional dependency).

    Parameters
    ----------
    path : Path
        The file to lock.  A ``.lock`` sibling is created/used.
    timeout : float
        Seconds to wait for the lock before raising.
    """
    lock_path = Path(path).with_suffix(Path(path).suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import portalocker

        lock_file = open(lock_path, "w")  # noqa: SIM115
        try:
            portalocker.lock(lock_file, portalocker.LOCK_EX, timeout=timeout)
            yield
        finally:
            try:
                portalocker.unlock(lock_file)
            except Exception:
                pass
            lock_file.close()
    except ImportError:
        logger.debug("portalocker not installed — file locking disabled")
        yield
