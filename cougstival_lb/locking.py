"""A lock file so only one copy of something runs at a time."""
import os

try:
    import fcntl
except ImportError:      # Windows
    fcntl = None
    import msvcrt


def try_lock(path):
    """Return an open file that holds the lock (keep it referenced), or None if someone else has it."""
    f = open(path, "a+")
    try:
        if fcntl:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        f.close()
        return None
    return f
