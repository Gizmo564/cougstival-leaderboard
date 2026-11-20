from cougstival_lb import service


def test_unit_and_powershell_text():
    u = service.unit_text()
    assert "systemd-inhibit" in u and "Restart=always" in u and "WantedBy=default.target" in u and '"run"' in u
    p = service.powershell_install_script()
    assert "Register-ScheduledTask" in p and "-AtLogOn" in p and "-RestartCount" in p and "CougstivalLeaderboard" in p
