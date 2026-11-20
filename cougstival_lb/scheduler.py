"""Runs the update cycle on schedule. Leave this running all week.

Runs every 20 minutes on the :00 / :20 / :40 marks, and ALWAYS exactly at each day's close time from the config
(for example 5:00 PM), even if the close time isn't on a 20-minute mark. A close-time run that fails is retried
every minute (up to 5 tries) and raises an urgent alert if it never works.
"""
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import paths, settings
from .cycle import notify
from .engine import windows
from .locking import try_lock

STEP = 20            # minutes between regular runs
CLOSE_TRIES = 5
RUN_TIMEOUT = 300    # seconds; a stuck run is killed


def self_cmd(*args):
    """Command line that starts this app again with the given arguments (works packaged or not)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, "-m", "cougstival_lb", *args]


def next_tick(cfg, after):
    """Next run time strictly after `after`: the next 20-minute mark, or an earlier day close."""
    mark = after.replace(minute=after.minute // STEP * STEP, second=0, microsecond=0) + timedelta(minutes=STEP)
    return min([mark] + [close for _, _, close in windows(cfg) if close > after])


def close_name(cfg, tick):
    """The day that closes exactly at `tick`, or None."""
    return next((name for name, _, close in windows(cfg) if abs((close - tick).total_seconds()) < 1), None)


def run_once():
    """Run one update in its own process, so a hang or crash can't take the scheduler down."""
    try:
        return subprocess.run(self_cmd("once"), timeout=RUN_TIMEOUT).returncode
    except subprocess.TimeoutExpired:
        print("run timed out and was killed")
        return 1


def run_close(day):
    for attempt in range(1, CLOSE_TRIES + 1):
        if run_once() == 0:
            return
        if attempt < CLOSE_TRIES:
            time.sleep(60)
    notify(settings.load_secrets(), f"{day} closing run FAILED",
           f"{day} closed but the final update failed {CLOSE_TRIES} times. The board is not frozen yet. Check the machine.",
           "urgent")


def sleep_until(t, tz):
    while True:
        left = (t - datetime.now(tz)).total_seconds()
        if left <= 0:
            return
        time.sleep(min(left, 20))  # short sleeps, so a computer waking from sleep notices at once


def keep_awake_windows():
    """Ask Windows not to sleep while we run (no admin needed)."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # CONTINUOUS | SYSTEM_REQUIRED
    except Exception:
        pass


def main():
    lock = try_lock(paths.path("scheduler.lock"))
    if lock is None:
        print("The scheduler is already running. Not starting a second one.")
        return 1
    cfg = settings.load_config()
    if not cfg:
        print("No settings saved yet. Open the setup app first.")
        return 1
    if sys.platform == "win32":
        keep_awake_windows()
    if cfg["publish"]["mode"] == "local":
        from .localserve import serve
        serve(paths.path("site"), cfg["publish"]["port"])
    print("scheduler started")
    run_once()  # don't wait for the next mark after a (re)start
    while True:
        cfg = settings.load_config() or cfg           # picks up settings saved while we run
        tz = ZoneInfo(cfg["timezone"])
        tick = next_tick(cfg, datetime.now(tz))
        print(f"next run at {tick:%a %H:%M:%S}")
        sleep_until(tick, tz)
        day = close_name(cfg, tick)
        run_close(day) if day else run_once()
