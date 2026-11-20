from datetime import datetime
from zoneinfo import ZoneInfo

from cougstival_lb.scheduler import close_name, next_tick
from tests.test_engine import cfg

MT = ZoneInfo("America/Denver")
CFG = cfg()


def at(day, h, m, s=0):
    return datetime(2026, 11, day, h, m, s, tzinfo=MT)


def test_ticks_and_closes():
    assert next_tick(CFG, at(9, 10, 5)) == at(9, 10, 20)
    assert next_tick(CFG, at(9, 23, 50)) == at(10, 0, 0)
    assert next_tick(CFG, at(9, 16, 59, 59)) == at(9, 17, 0)
    assert close_name(CFG, at(9, 17, 0)) == "Monday" and close_name(CFG, at(9, 16, 40)) is None
    assert next_tick(CFG, at(9, 17, 0)) == at(9, 17, 20)
    assert close_name(CFG, at(14, 14, 0)) == "Saturday"
    odd = dict(CFG, days=[dict(CFG["days"][0], close="2026-11-09T17:10")] + CFG["days"][1:])
    assert next_tick(odd, at(9, 17, 0)) == at(9, 17, 10) and close_name(odd, at(9, 17, 10)) == "Monday"
