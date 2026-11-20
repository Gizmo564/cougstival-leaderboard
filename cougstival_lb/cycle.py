"""One update cycle: log in, fetch, build, write site/data.json (and publish it), alert if something is wrong."""
import os
import subprocess
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import paths, settings
from .engine import build, windows
from .goosechase import LoginError, fetch_all, session
from .locking import try_lock

STALE = timedelta(minutes=60)    # no successful update for this long -> alert
REPEAT = timedelta(hours=1)      # repeat an unresolved alert this often


def site_dir():
    return paths.path("site")


def sane(new_count, old_count):
    """Refuse to publish if the submission count suddenly drops a lot (a bad fetch, not real removals)."""
    return old_count is None or new_count >= old_count * 0.8


def event_over(cfg, now, previous):
    last_close = windows(cfg)[-1][2]
    return bool(previous) and now > last_close + timedelta(minutes=30) and all(d.get("frozen") for d in previous["days"])


def update_state(state, now, ok, auth_failed, err, mismatches):
    """Update state in place; return the alerts to send as (title, message, priority)."""
    alerts, t = [], now.isoformat()
    state.setdefault("first_seen", t)

    def due(key):
        last = state.get(key)
        return not last or now - datetime.fromisoformat(last) >= REPEAT

    if ok:
        if state.get("auth_failing"):
            alerts.append(("Goosechase login recovered", "Leaderboard updates are working again.", "default"))
        state.update(last_success=t, auth_failing=False, last_error=None)
        key = ",".join(sorted(m["team"] for m in mismatches))
        if key and key != state.get("mismatch_key"):
            m = mismatches[0]
            alerts.append(("Leaderboard totals do not reconcile",
                           f"{len(mismatches)} team(s) differ from Goosechase totals, e.g. {m['team']}: "
                           f"computed {m['computed']} vs official {m['official']}.", "low"))
        state["mismatch_key"] = key
        return alerts

    state["last_error"] = err
    if auth_failed:
        if not state.get("auth_failing") or due("last_auth_alert"):
            alerts.append(("Goosechase login needed",
                           f"The leaderboard cannot log in ({err}). Open the setup app and test the login.", "urgent"))
            state["last_auth_alert"] = t
        state["auth_failing"] = True
    else:
        since = datetime.fromisoformat(state.get("last_success") or state["first_seen"])
        if now - since >= STALE and due("last_stale_alert"):
            alerts.append(("Leaderboard not updating",
                           f"No successful update since {since.isoformat()}. Last error: {err}", "high"))
            state["last_stale_alert"] = t
    return alerts


def cycle(cfg, now, previous, state, fetch, output=None):
    """Returns (new data or None, alerts). fetch() -> (submissions, official totals).
    output(data) saves/publishes the result; if it raises, the update counts as failed."""
    data, mismatches, err, auth_failed, ok = None, [], None, False, False
    try:
        subs, official = fetch()
        if not sane(len(subs), state.get("sub_count")):
            raise RuntimeError(f"fetched {len(subs)} submissions but had {state.get('sub_count')}; not publishing")
        data, mismatches = build(subs, official, cfg, now, previous)
        if output:
            output(data)
        state["sub_count"] = len(subs)
        ok = True
    except LoginError as e:
        auth_failed, err = True, str(e)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    return (data if ok else None), update_state(state, now, ok, auth_failed, err, mismatches)


def publish(directory, now, git_email=""):
    """Commit the site files and push them (GitHub Pages serves them)."""
    def git(*args):
        return subprocess.run(["git", "-C", directory, *args], check=True, capture_output=True, text=True,
                              timeout=90, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    git("add", "index.html", "data.json")
    if subprocess.run(["git", "-C", directory, "diff", "--cached", "--quiet"]).returncode == 0:
        return  # nothing changed
    email = git_email or "leaderboard-bot@users.noreply.github.com"
    git("-c", "user.name=Cougstival Leaderboard", "-c", f"user.email={email}",
        "commit", "-m", f"Update leaderboard {now:%a %H:%M}")
    try:
        git("push", "-u", "origin", "main")
    except subprocess.CalledProcessError:
        git("pull", "--rebase", "origin", "main")  # something else pushed to the repo meanwhile
        git("push", "-u", "origin", "main")


def notify(secrets, title, message, priority):
    topic = secrets.get("ntfy_topic")
    print(f"ALERT [{priority}] {title}: {message}")
    if not topic:
        print("  not sent: no ntfy topic is saved")
        return
    try:
        req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=message.encode(),
                                     headers={"Title": title, "Priority": priority})
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"  sent to ntfy (HTTP {r.status})")
    except Exception as e:
        print("  could not send alert:", e)


def ping(secrets, ok=True):
    """Tell healthchecks.io we're alive (or failed). It alerts you if the pings stop."""
    url = secrets.get("ping_url")
    if not url:
        return
    try:
        with urllib.request.urlopen(url if ok else url.rstrip("/") + "/fail", timeout=10) as r:
            print(f"  pinged healthchecks ({'ok' if ok else 'fail'}, HTTP {r.status})")
    except Exception as e:
        print("  ping failed:", e)


def run_once(fetch=None, now=None):
    """Do one update. Returns 0 ok, 1 failed, 2 another run was in progress."""
    cfg, secrets = settings.load_config(), settings.load_secrets()
    if not cfg:
        print("No settings saved yet. Open the setup app first.")
        return 1
    now = now or datetime.now(ZoneInfo(cfg["timezone"]))

    lock = try_lock(paths.path("once.lock"))
    if lock is None:
        print("previous run still going; skipping")
        return 2

    out = os.path.join(site_dir(), "data.json")
    previous, state = settings.read_json(out, None), settings.read_json(paths.path("state.json"), {})
    if event_over(cfg, now, previous):
        print("event is over and every day is frozen; nothing to do")
        ping(secrets, True)
        return 0

    if fetch is None:
        def fetch():
            with session(cfg["experience_id"], secrets.get("gc_email"), secrets.get("gc_password")) as gql:
                return fetch_all(gql, cfg["experience_id"])

    def output(data):
        os.makedirs(site_dir(), exist_ok=True)
        install_site_page()
        settings.write_json(out, data)
        if cfg["publish"]["mode"] == "github":
            publish(site_dir(), now, cfg["publish"].get("git_email", ""))

    data, alerts = cycle(cfg, now, previous, state, fetch, output)
    if data:
        print(f"{now:%a %H:%M:%S} updated: " + ", ".join(f"{d['name']} {d['status']}" for d in data["days"]))
    else:
        print(f"{now:%a %H:%M:%S} update FAILED: {state.get('last_error')}")
    settings.write_json(paths.path("state.json"), state)
    for a in alerts:
        notify(secrets, *a)
    ping(secrets, bool(data))
    lock.close()
    return 0 if data else 1


def install_site_page():
    """Copy the packaged leaderboard page into the site folder (kept current with the app version)."""
    import shutil
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "index.html")
    os.makedirs(site_dir(), exist_ok=True)
    shutil.copyfile(src, os.path.join(site_dir(), "index.html"))
