import os
import subprocess
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from cougstival_lb.cycle import cycle, event_over, publish, sane
from cougstival_lb.goosechase import LoginError
from tests.test_engine import cfg

CFG = cfg()
MT = ZoneInfo("America/Denver")
T0 = datetime(2026, 11, 9, 10, 0, tzinfo=MT)


def good_fetch():
    return ([{"teamName": "a", "missionPoints": 10, "bonusPoints": 0, "submissionCreatedAt": "2026-11-09T17:00:00.000Z"}], {"a": 10})


def failing(exc):
    def f():
        raise exc
    return f


def titles(alerts):
    return [a[0] for a in alerts]


def test_alert_rules():
    state = {}
    data, alerts = cycle(CFG, T0, None, state, good_fetch)
    assert data and alerts == [] and state["last_success"]
    data, alerts = cycle(CFG, T0 + timedelta(minutes=20), None, state, failing(LoginError("expired")))
    assert data is None and titles(alerts) == ["Goosechase login needed"] and alerts[0][2] == "urgent"
    _, alerts = cycle(CFG, T0 + timedelta(minutes=40), None, state, failing(LoginError("expired")))
    assert alerts == []
    _, alerts = cycle(CFG, T0 + timedelta(minutes=85), None, state, failing(LoginError("expired")))
    assert titles(alerts) == ["Goosechase login needed"]
    _, alerts = cycle(CFG, T0 + timedelta(minutes=105), None, state, good_fetch)
    assert titles(alerts) == ["Goosechase login recovered"]
    state = {}
    cycle(CFG, T0, None, state, good_fetch)
    for m, expect in [(20, []), (40, []), (60, ["Leaderboard not updating"]), (80, []), (125, ["Leaderboard not updating"])]:
        _, alerts = cycle(CFG, T0 + timedelta(minutes=m), None, state, failing(RuntimeError("boom")))
        assert titles(alerts) == expect, (m, alerts)


def test_sanity_and_mismatch_and_output_failure():
    state = {"sub_count": 1000}
    data, _ = cycle(CFG, T0, None, state, good_fetch)
    assert data is None and "not publishing" in state["last_error"]
    assert sane(900, 1000) and not sane(100, 1000) and sane(5, None)
    state = {}
    off = lambda: (good_fetch()[0], {"a": 11})
    _, alerts = cycle(CFG, T0, None, state, off)
    assert titles(alerts) == ["Leaderboard totals do not reconcile"]
    _, alerts = cycle(CFG, T0 + timedelta(minutes=20), None, state, off)
    assert alerts == []

    def boom(data):
        raise RuntimeError("push rejected")
    state = {}
    data, _ = cycle(CFG, T0, None, state, good_fetch, output=boom)
    assert data is None and "push rejected" in state["last_error"] and "last_success" not in state


def test_event_over():
    close = datetime(2026, 11, 14, 14, 0, tzinfo=MT)
    before, _ = cycle(CFG, close - timedelta(minutes=10), None, {}, good_fetch)
    assert not event_over(CFG, close + timedelta(hours=1), before)
    done, _ = cycle(CFG, close + timedelta(minutes=5), before, {}, good_fetch)
    assert all(d["frozen"] for d in done["days"])
    assert not event_over(CFG, close + timedelta(minutes=20), done)
    assert event_over(CFG, close + timedelta(minutes=31), done)


def sh(*a, cwd=None):
    return subprocess.run(a, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def test_publish():
    with tempfile.TemporaryDirectory() as tmp:
        remote, a, b = (os.path.join(tmp, n) for n in ("remote.git", "a", "b"))
        sh("git", "init", "--bare", "-b", "main", remote)
        sh("git", "clone", remote, a)
        sh("git", "clone", remote, b)
        for repo in (a, b):
            sh("git", "config", "user.name", "Someone", cwd=repo)
            sh("git", "config", "user.email", "x@example.com", cwd=repo)
        open(os.path.join(a, "index.html"), "w").write("page")
        open(os.path.join(a, "data.json"), "w").write("1")
        sh("git", "add", ".", cwd=a)
        sh("git", "commit", "-m", "init", cwd=a)
        sh("git", "push", "-u", "origin", "main", cwd=a)
        now = datetime(2026, 11, 9, 17, 0)
        open(os.path.join(a, "data.json"), "w").write("2")
        publish(a, now, "me@example.com")
        log = sh("git", "log", "-1", "--format=%an|%ae|%B", cwd=remote)
        assert log.startswith("Cougstival Leaderboard|me@example.com|Update leaderboard Mon 17:00"), log
        publish(a, now)                                          # nothing changed: no commit
        assert sh("git", "rev-list", "--count", "main", cwd=remote) == "2"
        sh("git", "pull", "origin", "main", cwd=b)
        open(os.path.join(b, "other"), "w").write("x")
        sh("git", "add", "other", cwd=b)
        sh("git", "commit", "-m", "other work", cwd=b)
        sh("git", "push", cwd=b)                                 # remote moved on
        open(os.path.join(a, "data.json"), "w").write("3")
        publish(a, now)
        assert sh("git", "show", "main:data.json", cwd=remote) == "3"
