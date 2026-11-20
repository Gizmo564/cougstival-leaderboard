from datetime import datetime
from zoneinfo import ZoneInfo

from cougstival_lb.engine import build, experience_id, ranked, validate, windows, with_defaults

MT = ZoneInfo("America/Denver")
NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
DATES = ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13", "2026-11-14"]
EXP = "32d9bad8-74f8-4481-bc72-18163ad5b47f"


def cfg(**kw):
    days = [{"name": n, "open": f"{d}T00:00", "close": f"{d}T{'14:00' if n == 'Saturday' else '17:00'}"}
            for n, d in zip(NAMES, DATES)]
    return with_defaults({"experience_id": EXP, "timezone": "America/Denver", "title": "Test Event", "days": days, **kw})


def sub(team, pts, utc, bonus=0, who=None):
    return {"teamName": team, "participantName": who, "missionPoints": pts, "bonusPoints": bonus, "submissionCreatedAt": utc}


def day(data, name):
    return next(d for d in data["days"] if d["name"] == name)


def rows(d):
    return {r["name"]: r["points"] for r in d["rows"]}


def test_windows_and_total_only():
    w = windows(cfg())
    utc = ZoneInfo("UTC")
    assert w[0][1].astimezone(utc).isoformat() == "2026-11-09T07:00:00+00:00"
    assert w[0][2].astimezone(utc).isoformat() == "2026-11-10T00:00:00+00:00"
    assert w[5][2].astimezone(utc).isoformat() == "2026-11-14T21:00:00+00:00"
    now = datetime(2026, 11, 14, 22, 0, tzinfo=MT)
    subs = [
        sub("a", 100, "2026-11-09T06:59:59.999Z"),   # before the event
        sub("a", 10, "2026-11-09T07:00:00.000Z"),    # Mon 12:00 AM: open edge included
        sub("a", 20, "2026-11-09T23:59:59.999Z"),    # Mon 4:59:59 PM
        sub("a", 30, "2026-11-10T00:00:00.000Z"),    # Mon 5:00 PM: evening, total only
        sub("a", 40, "2026-11-10T06:59:59.999Z"),    # Mon 11:59 PM: total only, NOT Tuesday
        sub("b", 50, "2026-11-10T07:00:00.000Z", bonus=-50),
        sub("b", 5, "2026-11-14T21:00:00.000Z"),     # after the last close
    ]
    data, bad = build(subs, {"a": 200, "b": 5}, cfg(), now)
    assert bad == []
    assert rows(day(data, "Monday")) == {"a": 30}
    assert rows(day(data, "Tuesday")) == {"b": 0}
    assert data["total"]["outside_points"] == 175
    assert rows({"rows": data["total"]["rows"]}) == {"a": 200, "b": 5}
    assert all(d["status"] == "closed" for d in data["days"])
    _, bad = build(subs, {"a": 200, "b": 6}, cfg(), now)
    assert bad == [{"team": "b", "computed": 5, "official": 6}]


def test_next_day_rollover():
    c = cfg(after_close="next_day")
    now = datetime(2026, 11, 14, 22, 0, tzinfo=MT)
    subs = [sub("a", 30, "2026-11-10T00:00:00.000Z"),     # Mon 5:00 PM -> now counts for Tuesday
            sub("a", 40, "2026-11-10T06:59:59.999Z"),     # Mon 11:59 PM -> Tuesday
            sub("a", 5, "2026-11-10T07:00:00.000Z")]      # Tue 12:00 AM -> Tuesday
    data, bad = build(subs, {"a": 75}, c, now)
    assert bad == [] and rows(day(data, "Tuesday")) == {"a": 75} and day(data, "Monday")["rows"] == []
    assert windows(c)[1][1] == windows(c)[0][2]


def test_status_by_time():
    def st(h, m=0, d=9):
        return [x["status"] for x in build([], {}, cfg(), datetime(2026, 11, d, h, m, tzinfo=MT))[0]["days"]]
    assert st(9) == ["open"] + ["upcoming"] * 5
    assert st(20) == ["closed"] + ["upcoming"] * 5
    assert st(16, 59)[0] == "open" and st(17, 0)[0] == "closed"


def test_freeze_and_config_change():
    now = datetime(2026, 11, 14, 22, 0, tzinfo=MT)
    prev, _ = build([sub("a", 10, "2026-11-09T18:00:00.000Z")], {"a": 10}, cfg(), now)
    later = [sub("a", 999, "2026-11-09T18:00:00.000Z")]
    d2, _ = build(later, {"a": 999}, cfg(), now, previous=prev)
    assert rows(day(d2, "Monday")) == {"a": 10}                     # frozen
    d3, _ = build(later, {"a": 999}, cfg(tiebreaker="earliest"), now, previous=prev)
    assert rows(day(d3, "Monday")) == {"a": 999}                    # rule changed: recomputed


def test_ranking_and_tiebreakers():
    assert [r["rank"] for r in ranked({"x": 5, "y": 5, "z": 1})] == [1, 1, 3]
    t = lambda h: datetime(2026, 11, 9, h, tzinfo=MT)
    stats = {"x": {"last": t(12), "n": 1}, "y": {"last": t(9), "n": 3}, "z": {"last": t(9), "n": 3}}
    pts = {"x": 5, "y": 5, "z": 5}
    r = ranked(pts, stats, "earliest")
    assert [(x["name"], x["rank"]) for x in r] == [("y", 1), ("z", 1), ("x", 3)]   # y,z fully tied
    r = ranked(pts, stats, "most_subs")
    assert [(x["name"], x["rank"]) for x in r] == [("y", 1), ("z", 1), ("x", 3)]
    assert [x["rank"] for x in ranked(pts, stats, "alpha")] == [1, 1, 1]


def test_participant_display():
    c = cfg(display="participant")
    now = datetime(2026, 11, 9, 12, 0, tzinfo=MT)
    subs = [sub("T", 10, "2026-11-09T18:00:00.000Z", who="Ann"), sub("T", 5, "2026-11-09T18:30:00.000Z", who="Bo")]
    data, bad = build(subs, {"T": 15}, c, now)
    assert bad == [] and rows(day(data, "Monday")) == {"Ann": 10, "Bo": 5}
    assert rows({"rows": data["total"]["rows"]}) == {"Ann": 10, "Bo": 5}


def test_validation_and_ids():
    assert validate(cfg()) == []
    bad = cfg()
    bad["days"][1]["open"] = "2026-11-09T12:00"       # Tuesday opens before Monday closes
    assert any("opens before" in e for e in validate(bad))
    bad = cfg()
    bad["days"][0]["close"] = "2026-11-09T00:00"
    assert any("closes before" in e for e in validate(bad))
    assert validate(cfg(accent="red")) and validate(cfg(timezone="Nope/Zone"))
    assert validate(with_defaults({"experience_id": "", "timezone": "UTC", "days": []}))
    assert experience_id("https://studio.goosechase.com/experience/32D9BAD8-74F8-4481-BC72-18163AD5B47F/x") == EXP
    assert experience_id("nothing") is None
