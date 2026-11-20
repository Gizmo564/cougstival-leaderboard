"""Command line entry. With no arguments it opens the setup app."""
import argparse
import os
import sys

from . import __version__, paths


def _log_to_file_if_no_console():
    """A packaged Windows app has no console; send prints to a log file instead of crashing."""
    if sys.stdout is None or sys.stderr is None:
        os.makedirs(paths.path("logs"), exist_ok=True)
        f = open(paths.path("logs", "app.log"), "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f


def main(argv=None):
    _log_to_file_if_no_console()
    p = argparse.ArgumentParser(prog="cougstival-lb", description="Cougstival leaderboard")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("setup", help="open the setup app (default)")
    s.add_argument("--no-browser", action="store_true", help="don't open a browser window, just print the address")
    sub.add_parser("run", help="run the scheduler (leave running)")
    sub.add_parser("once", help="do one update")
    c = sub.add_parser("check-login", help="test the Goosechase login")
    c.add_argument("--headed", action="store_true", help="show the browser window")
    sub.add_parser("install-browser", help="download the headless browser")
    sub.add_parser("test-alert")
    sub.add_parser("test-ping")
    g = sub.add_parser("github-check", help="connect the GitHub repo and test publishing")
    g.add_argument("repo")
    sub.add_parser("version")
    a = p.parse_args(argv)

    if a.cmd in (None, "setup"):
        from .setup_server import serve_setup
        return serve_setup(open_browser=not getattr(a, "no_browser", False))
    if a.cmd == "version":
        print(__version__)
        return 0
    if a.cmd == "run":
        from .scheduler import main as run_scheduler
        return run_scheduler()
    if a.cmd == "once":
        from .cycle import run_once
        return run_once()
    if a.cmd == "install-browser":
        from .goosechase import install_browser
        return install_browser()
    if a.cmd == "test-alert":
        from .cycle import notify
        from .settings import load_secrets
        notify(load_secrets(), "Leaderboard test alert", "If you can read this, alerts work.", "default")
        return 0
    if a.cmd == "test-ping":
        from .cycle import ping
        from .settings import load_secrets
        ping(load_secrets(), True)
        return 0
    if a.cmd == "github-check":
        from .gitpub import check
        return check(a.repo)
    if a.cmd == "check-login":
        from .goosechase import fetch_all, session
        from .settings import load_config, load_secrets
        cfg, sec = load_config(), load_secrets()
        if not cfg:
            print("Save your settings first.")
            return 1
        try:
            with session(cfg["experience_id"], sec.get("gc_email"), sec.get("gc_password"), headed=a.headed) as gql:
                subs, official = fetch_all(gql, cfg["experience_id"])
        except Exception as e:
            print(f"Login test failed: {e}")
            return 1
        print(f"Login works. Found {len(official)} teams/players and {len(subs)} submissions so far.")
        return 0
    return 1
