import json
import os
import threading
import urllib.error
import urllib.request

import pytest

from cougstival_lb import cycle, setup_server
from tests.test_engine import cfg


@pytest.fixture()
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("COUGSTIVAL_HOME", str(tmp_path))
    from http.server import ThreadingHTTPServer
    job = setup_server.Job()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), setup_server.make_handler("tok", job))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", tmp_path
    srv.shutdown()


def call(base, path, body=None, token="tok", host=None):
    h = {"X-Token": token, "Content-Type": "application/json"}
    if host:
        h["Host"] = host
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


def payload(**over):
    c = cfg()
    c = {k: c[k] for k in ("experience_id", "timezone", "days", "title", "accent", "display", "tiebreaker", "after_close", "publish")}
    c["experience_id"] = "https://studio.goosechase.com/experience/32d9bad8-74f8-4481-bc72-18163ad5b47f/participants"
    c.update(over)
    return {"config": c, "secrets": {"gc_email": "me@example.com", "gc_password": "p@ss'word\"1", "ntfy_topic": "secret-topic"}}


def test_token_and_host_required(server):
    base, _ = server
    assert call(base, "/api/state", token="wrong")[0] == 403
    assert call(base, "/api/state", host="evil.example.com")[0] == 403
    assert call(base, "/api/state")[0] == 200
    with urllib.request.urlopen(base + "/") as r:           # the page itself loads
        assert b"Leaderboard Setup" in r.read()


def test_save_never_echoes_secrets(server):
    base, home = server
    code, r = call(base, "/api/save", payload())
    assert r["ok"], r
    code, st = call(base, "/api/state")
    text = json.dumps(st)
    assert "p@ss" not in text and "secret-topic" not in text
    assert st["email"] == "me@example.com" and st["has"] == {"password": True, "ntfy": True, "ping": False}
    assert st["config"]["experience_id"] == "32d9bad8-74f8-4481-bc72-18163ad5b47f"     # link reduced to the ID
    secrets = json.load(open(home / "secrets.json"))
    assert secrets["gc_password"] == "p@ss'word\"1"
    if os.name != "nt":
        assert oct(os.stat(home / "secrets.json").st_mode)[-3:] == "600"
    assert (home / "site" / "index.html").exists()
    # Blank secrets on a later save keep the saved values.
    body = payload()
    body["secrets"] = {"gc_email": "me@example.com", "gc_password": "", "ntfy_topic": ""}
    assert call(base, "/api/save", body)[1]["ok"]
    assert json.load(open(home / "secrets.json"))["ntfy_topic"] == "secret-topic"


def test_save_rejects_bad_settings(server):
    base, _ = server
    code, r = call(base, "/api/save", payload(experience_id="nope"))
    assert not r["ok"] and any("Experience" in e for e in r["errors"])
    body = payload()
    body["secrets"] = {}
    assert not call(base, "/api/save", body)[1]["ok"]       # no login saved yet
    code, r = call(base, "/api/save", payload(publish={"mode": "github", "repo": "bad", "port": 8080}))
    assert not r["ok"] and any("owner/name" in e for e in r["errors"])


def test_unknown_job_rejected(server):
    base, _ = server
    assert call(base, "/api/job", {"name": "rm -rf"})[0] == 400


def test_run_once_local_with_fake_fetch(server):
    base, home = server
    call(base, "/api/save", payload())
    subs = [{"teamName": "a", "participantName": None, "missionPoints": 10, "bonusPoints": 0,
             "submissionCreatedAt": "2026-11-09T18:00:00.000Z"}]
    from datetime import datetime
    from zoneinfo import ZoneInfo
    assert cycle.run_once(fetch=lambda: (subs, {"a": 10}), now=datetime(2026, 11, 9, 12, 0, tzinfo=ZoneInfo("America/Denver"))) == 0
    data = json.load(open(home / "site" / "data.json"))
    assert data["title"] == "Test Event" and data["days"][0]["rows"][0]["points"] == 10
