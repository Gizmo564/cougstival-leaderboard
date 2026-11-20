"""Where this app keeps its files. One folder per user; COUGSTIVAL_HOME overrides it (used by tests).

    config.json   event settings (no secrets)
    secrets.json  Goosechase login, alert URLs (only readable by you)
    state.json    alert bookkeeping
    site/         the website: index.html + data.json (a git repo when publishing to GitHub)
    browser-profile/, browsers/   the headless browser's saved login and the browser itself
    logs/         app.log
"""
import os


def home():
    custom = os.environ.get("COUGSTIVAL_HOME")
    if custom:
        base = custom
    elif os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "CougstivalLeaderboard")
    else:
        base = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"),
                            "cougstival-leaderboard")
    os.makedirs(base, exist_ok=True)
    return base


def path(*parts):
    return os.path.join(home(), *parts)
