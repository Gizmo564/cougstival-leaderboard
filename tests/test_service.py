from cougstival_lb import service


def test_unit_and_powershell_text():
    u = service.unit_text()
    assert "systemd-inhibit" in u and "Restart=always" in u and "WantedBy=default.target" in u and '"run"' in u
    p = service.powershell_install_script()
    assert "Register-ScheduledTask" in p and "-AtLogOn" in p and "-RestartCount" in p and "CougstivalLeaderboard" in p


def test_plist_text():
    import plistlib
    d = plistlib.loads(service.plist_text().encode())
    assert d["Label"] == service.LABEL and d["KeepAlive"] is True and d["RunAtLoad"] is True
    assert d["ProgramArguments"][:2] == ["/usr/bin/caffeinate", "-is"] and d["ProgramArguments"][-1] == "run"
