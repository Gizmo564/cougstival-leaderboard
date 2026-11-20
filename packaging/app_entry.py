"""Entry point for the packaged apps (PyInstaller)."""
import multiprocessing

from cougstival_lb.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
