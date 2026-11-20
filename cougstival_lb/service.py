"""Keep the scheduler running all week: a systemd user service on Linux, a Scheduled Task on Windows."""
import os
import subprocess
import sys

from .scheduler import self_cmd

NAME = "cougstival-leaderboard"
TASK = "CougstivalLeaderboard"


def unit_text():
    cmd = " ".join(f'"{c}"' for c in self_cmd("run"))
    return f"""[Unit]
Description=Cougstival leaderboard scheduler

[Service]
ExecStart=systemd-inhibit --what=sleep:idle --who="Cougstival Leaderboard" --why="Updating the leaderboard" {cmd}
Restart=always
RestartSec=15

[Install]
WantedBy=default.target
"""


def powershell_install_script():
    exe, *args = self_cmd("run")
    arg = " ".join(args)
    action = f"New-ScheduledTaskAction -Execute '{exe}'" + (f" -Argument '{arg}'" if arg else "")
    return f"""$ErrorActionPreference = 'Stop'
$a = {action}
$t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$s = New-ScheduledTaskSettingsSet -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName '{TASK}' -Action $a -Trigger $t -Settings $s -Force | Out-Null
Start-ScheduledTask -TaskName '{TASK}'
"""


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def _ps(script):
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script])


def install():
    """Create and start the always-on service. Returns (ok, message)."""
    if sys.platform == "win32":
        code, out = _ps(powershell_install_script())
        return code == 0, out or "Scheduled task created and started. It also starts every time you log in."
    unit_dir = os.path.expanduser("~/.config/systemd/user")
    os.makedirs(unit_dir, exist_ok=True)
    with open(os.path.join(unit_dir, NAME + ".service"), "w") as f:
        f.write(unit_text())
    steps = [["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", NAME + ".service"]]
    for s in steps:
        code, out = _run(s)
        if code:
            return False, out
    _run(["loginctl", "enable-linger", os.environ.get("USER", "")])   # keep running after logout; may be refused
    return True, "Service installed and started. It restarts itself if it stops."


def stop():
    if sys.platform == "win32":
        code, out = _ps(f"Stop-ScheduledTask -TaskName '{TASK}'")
    else:
        code, out = _run(["systemctl", "--user", "stop", NAME + ".service"])
    return code == 0, out or "Stopped."


def status():
    """'running', 'stopped' or 'not installed'."""
    if sys.platform == "win32":
        code, out = _ps(f"(Get-ScheduledTask -TaskName '{TASK}').State")
        if code:
            return "not installed"
        return "running" if out.strip() == "Running" else "stopped"
    if not os.path.exists(os.path.expanduser(f"~/.config/systemd/user/{NAME}.service")):
        return "not installed"
    code, out = _run(["systemctl", "--user", "is-active", NAME + ".service"])
    return "running" if out.strip() == "active" else "stopped"
