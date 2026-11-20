"""Turn Goosechase submissions into per-day leaderboards plus a total.

Each day has a window [open, close). A submission counts toward a day if its timestamp is inside that window.
What happens to points outside every window depends on `after_close`:
  total_only  they count toward the Total only (evenings, before the event, after the last close)
  next_day    points after a day closes roll into the next day (each day then opens when the previous one closes)
Points = mission points + bonus points. Closed days are frozen: later changes in Goosechase don't alter them.
"""
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones

DEFAULTS = {
    "title": "",
    "accent": "#0a4aa6",
    "display": "team",            # team | participant
    "tiebreaker": "share",        # share | earliest | most_subs | alpha
    "after_close": "total_only",  # total_only | next_day
    "publish": {"mode": "local", "repo": "", "git_email": "", "port": 8080},
}
DISPLAY = ("team", "participant")
TIEBREAKERS = ("share", "earliest", "most_subs", "alpha")
AFTER_CLOSE = ("total_only", "next_day")
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def with_defaults(cfg):
    out = {**DEFAULTS, **cfg}
    out["publish"] = {**DEFAULTS["publish"], **cfg.get("publish", {})}
    return out


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return with_defaults(json.load(f))


def experience_id(text):
    """Accepts a Goosechase Studio link or a bare ID; returns the ID or None."""
    m = UUID.search(text or "")
    return m.group(0).lower() if m else None


def validate(cfg):
    """List of problems with a config (empty list = fine)."""
    errs = []
    if not experience_id(cfg.get("experience_id", "")):
        errs.append("Experience ID is missing or not a valid ID.")
    try:
        ZoneInfo(cfg.get("timezone", ""))
    except Exception:
        errs.append("Timezone is not recognised.")
    if cfg.get("display") not in DISPLAY:
        errs.append("Names to show must be team or participant.")
    if cfg.get("tiebreaker") not in TIEBREAKERS:
        errs.append("Unknown tiebreaker.")
    if cfg.get("after_close") not in AFTER_CLOSE:
        errs.append("Unknown 'points after a day closes' setting.")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", cfg.get("accent", "")):
        errs.append("Accent colour must look like #0a4aa6.")
    if not str(cfg.get("title", "")).strip():
        errs.append("Title is empty.")
    pub = cfg.get("publish", {})
    if pub.get("mode") not in ("local", "github"):
        errs.append("Publishing must be local or github.")
    if pub.get("mode") == "github" and not re.fullmatch(r"[\w.-]+/[\w.-]+", pub.get("repo", "")):
        errs.append("GitHub repo must look like owner/name.")
    if not isinstance(pub.get("port"), int) or not 1024 <= pub["port"] <= 65535:
        errs.append("Port must be a number from 1024 to 65535.")

    days = cfg.get("days") or []
    if not days:
        errs.append("Add at least one day.")
    names = [str(d.get("name", "")).strip() for d in days]
    if "" in names or len(set(names)) != len(names) or "Total" in names:
        errs.append("Day names must be filled in, different from each other, and not 'Total'.")
    try:
        wins = _windows(cfg)
        for name, opens, closes in wins:
            if opens >= closes:
                errs.append(f"{name}: closes before it opens.")
        for (a, _, a_close), (b, b_open, _) in zip(wins, wins[1:]):
            if b_open < a_close:
                errs.append(f"{b} opens before {a} closes.")
    except (ValueError, KeyError, TypeError):
        errs.append("A day has a date or time that can't be read.")
    return errs


def _windows(cfg):
    tz = ZoneInfo(cfg["timezone"])

    def at(text):
        return datetime.fromisoformat(text).replace(tzinfo=tz)
    wins = [[d["name"].strip(), at(d["open"]), at(d["close"])] for d in cfg["days"]]
    if cfg.get("after_close") == "next_day":
        for i in range(1, len(wins)):
            wins[i][1] = wins[i - 1][2]   # a day opens the moment the previous one closes
    return [tuple(w) for w in wins]


def windows(cfg):
    """[(day name, open, close)] as timezone-aware datetimes."""
    return _windows(cfg)


def config_key(cfg):
    """Identifies an event setup, so data from another setup (or a changed rule) is never reused."""
    return json.dumps([cfg["experience_id"], cfg["timezone"], cfg["days"], cfg["display"],
                       cfg["tiebreaker"], cfg["after_close"]], sort_keys=True)


def parse_utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def ranked(points, stats=None, tiebreaker="share"):
    """Rows sorted by points. Teams tied on points AND the tiebreaker share a rank (1, 2, 2, 4).

    stats: {name: {"last": datetime of last submission, "n": submission count}}
    """
    stats = stats or {}

    def tb(name):
        s = stats.get(name)
        if tiebreaker == "earliest":
            return (s["last"].timestamp() if s else float("inf"),)
        if tiebreaker == "most_subs":
            return (-(s["n"] if s else 0),)
        return ()      # share / alpha: a tie stays a tie (alpha only orders the display)

    items = sorted(points.items(), key=lambda kv: (-kv[1], tb(kv[0]), kv[0].lower(), kv[0]))
    rows, prev, rank = [], None, 0
    for i, (name, pts) in enumerate(items, 1):
        mark = (pts, tb(name))
        if mark != prev:
            rank, prev = i, mark
        rows.append({"rank": rank, "name": name, "points": pts})
    return rows


class Board:
    """Points and tiebreak stats for one leaderboard."""
    def __init__(self):
        self.points, self.stats = {}, {}

    def add(self, name, pts, when):
        self.points[name] = self.points.get(name, 0) + pts
        s = self.stats.setdefault(name, {"last": when, "n": 0})
        s["n"] += 1
        s["last"] = max(s["last"], when)


def build(subs, official, cfg, now, previous=None):
    """Return (data for the website, list of teams whose numbers don't reconcile).

    subs:     dicts with teamName, participantName, missionPoints, bonusPoints, submissionCreatedAt
    official: {teamName: Goosechase's overall points}
    now:      timezone-aware datetime
    previous: last published data, used to keep closed days frozen
    """
    key = config_key(cfg)
    if previous and previous.get("config_key") != key:
        previous = None
    wins = windows(cfg)
    by_participant = cfg["display"] == "participant"
    daily = {name: Board() for name, _, _ in wins}
    total = Board()
    team_sum = {}      # Σ points per team, always by team: this is what reconciles with Goosechase
    outside = {}

    for s in subs:
        t = parse_utc(s["submissionCreatedAt"])
        team = s["teamName"]
        name = (s.get("participantName") or team) if by_participant else team
        pts = (s["missionPoints"] or 0) + (s["bonusPoints"] or 0)
        total.add(name, pts, t)
        team_sum[team] = team_sum.get(team, 0) + pts
        for dname, opens, closes in wins:
            if opens <= t < closes:
                daily[dname].add(name, pts, t)
                break
        else:
            outside[name] = outside.get(name, 0) + pts

    prev_days = {d["name"]: d for d in (previous or {}).get("days", [])}
    days = []
    for name, opens, closes in wins:
        status = "upcoming" if now < opens else "closed" if now >= closes else "open"
        old = prev_days.get(name)
        if status == "closed" and old and old.get("frozen"):
            days.append(old)
            continue
        days.append({
            "name": name, "status": status, "opens": opens.isoformat(), "closes": closes.isoformat(),
            "frozen": status == "closed",
            "rows": ranked(daily[name].points, daily[name].stats, cfg["tiebreaker"]),
        })

    # Reconcile by team: the sum of everything we counted must equal Goosechase's overall number.
    mismatches = []
    for team in set(official) | set(team_sum):
        if team_sum.get(team, 0) != official.get(team, 0):
            mismatches.append({"team": team, "computed": team_sum.get(team, 0), "official": official.get(team, 0)})

    # The Total is Goosechase's own number when showing teams; per participant it can only be our sum.
    total_points = total.points if by_participant else official
    data = {
        "updated": now.isoformat(),
        "config_key": key,
        "title": cfg["title"], "accent": cfg["accent"], "timezone": cfg["timezone"],
        "after_close": cfg["after_close"], "tiebreaker": cfg["tiebreaker"],
        "days": days,
        "total": {
            "rows": ranked({n: p for n, p in total_points.items() if p != 0}, total.stats, cfg["tiebreaker"]),
            "outside_points": sum(outside.values()),
        },
    }
    return data, mismatches
