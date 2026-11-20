"""Keep the scheduler running all week: a systemd user service on Linux, a launch agent on macOS, a Scheduled Task on Windows."""
import os
import subprocess
import sys

from . import paths
from .scheduler import self_cmd

LABEL = "com.cougstival.leaderboard"
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


def plist_path():
    return os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")


def plist_text():
    """macOS launch agent: starts at login, restarts if it stops, and caffeinate keeps the Mac from idle-sleeping."""
    from xml.sax.saxutils import escape
    args = ["/usr/bin/caffeinate", "-is"] + self_cmd("run")
    items = "\n".join(f"    <string>{escape(a)}</string>" for a in args)
    log = escape(paths.path("logs", "service.log"))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>
{items}
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
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
    if sys.platform == "darwin":
        os.makedirs(os.path.dirname(plist_path()), exist_ok=True)
        os.makedirs(paths.path("logs"), exist_ok=True)
        with open(plist_path(), "w") as f:
            f.write(plist_text())
        target = f"gui/{os.getuid()}"
        _run(["launchctl", "bootout", f"{target}/{LABEL}"])        # in case an older copy is loaded
        code, out = _run(["launchctl", "bootstrap", target, plist_path()])
        return code == 0, out or "Service installed and started. It starts at login and restarts if it stops."
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
    elif sys.platform == "darwin":
        code, out = _run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"])
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
    if sys.platform == "darwin":
        if not os.path.exists(plist_path()):
            return "not installed"
        code, out = _run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"])
        return "running" if code == 0 and "state = running" in out else "stopped"
    if not os.path.exists(os.path.expanduser(f"~/.config/systemd/user/{NAME}.service")):
        return "not installed"
    code, out = _run(["systemctl", "--user", "is-active", NAME + ".service"])
    return "running" if out.strip() == "active" else "stopped"
