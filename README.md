# Event Leaderboard Kit

Per-day and total leaderboards for a [Goosechase](https://goosechase.com) event. It logs in to Goosechase Studio, reads the
experience's submissions every 20 minutes, and publishes tabs for each day plus an overall Total, either to your own
GitHub Pages site or to your local network. Built for Cougstival, usable for any event.

## What it does
- Each day's board counts points from that day's **open** to **close** (you choose the times). Points outside every day
  count toward the Total only, or you can choose to **roll them into the next day**.
- Runs **exactly** at every day's close time, on top of the regular 20-minute updates, and retries if that run fails.
- Closed days are frozen; later changes in Goosechase don't alter them.
- Choose team names or individual participants, and a tiebreaker (share the rank, earliest last submission, most submissions, alphabetical).
- Phone alerts (ntfy) when the login breaks or updates stop, and an optional healthchecks.io dead-man's switch.
- Refuses to publish if the number of submissions suddenly drops (a bad fetch).

## Install
Download from the [Releases](../../releases) page:
- **Ubuntu / Debian:** the `.deb` file. Install with `sudo apt install ./cougstival-leaderboard_*.deb`, then open **Leaderboard Setup** from the app menu (or run `cougstival-lb`).
- **Windows 10/11:** `LeaderboardKit-Setup-*.exe`. Publishing to GitHub also needs [Git for Windows](https://git-scm.com/download/win) and the Windows OpenSSH Client (an optional Windows feature, usually present).

The setup opens in your web browser (a page served only on your own computer). Work down the sections:
1. Goosechase email, password and experience link, then **Test login and link**.
2. Event title, color, timezone, names, tiebreaker, and what happens to points after a day closes.
3. The daily schedule. Fill the table, then edit any day's open and close.
4. Alerts (optional but recommended).
5. Where to publish: your own GitHub repository, or local only.
6. Save, install the browser (once), run one update, then **Start and keep running**.

### Publishing to GitHub
Create an empty **public** repository, enter `owner/name`, and press **Connect GitHub and test**. It prints a deploy key.
Add it under the repository's Settings > Deploy keys with **write access**, press the button again, then enable
Settings > Pages > Deploy from a branch > `main` / root. Your site is `https://owner.github.io/name/`.

### Local only
No GitHub needed. The scheduler serves the page on the port you choose; people on the same network open
`http://<this computer's address>:<port>/`. Your firewall may ask to allow it.

## Keeping it running
**Start and keep running** installs a systemd user service (Linux) or a Scheduled Task that starts at login (Windows).
Keep the computer on, logged in and online for the whole event. On Linux the service asks the system not to sleep while it runs;
on Windows it asks Windows not to sleep. Only one scheduler runs at a time per computer; a second copy exits immediately.
Never run the same event from two computers at once: both would publish and send alerts.

Your settings, the saved Goosechase login and logs are in `~/.local/share/cougstival-leaderboard` (Linux) or
`%APPDATA%\CougstivalLeaderboard` (Windows). `secrets.json` there holds your password in plain text, readable only by your account.

## Honest limits
- It reads Goosechase through the same internal calls the admin web page makes. That is not a documented public API and Goosechase can change it.
- A captcha at login may stop the quiet login test. Use **Test with a visible window** once and finish logging in; the session is remembered.
- The Windows installer and Task Scheduler setup, the GitHub push, and per-participant boards are built to the same design as the tested
  Linux and team versions but have not been run on real Windows or against live participant data.
- The login session expires if you are logged out of Goosechase; the alert tells you.

## From source
```
pip install -r requirements.txt pytest
python -m pytest tests
python -m cougstival_lb        # opens setup
```
Commands: `setup`, `run`, `once`, `check-login [--headed]`, `install-browser`, `test-alert`, `test-ping`, `github-check owner/name`.

License: GPL-3.0-or-later.
