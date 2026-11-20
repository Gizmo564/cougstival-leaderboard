"""Set up publishing to the organizer's own GitHub repo (GitHub Pages) with a deploy key."""
import os
import subprocess
import sys

from . import paths, settings
from .cycle import install_site_page, site_dir

ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}


def key_path():
    return paths.path("deploy_key")


def git(*args, check=True):
    return subprocess.run(["git", "-C", site_dir(), *args], capture_output=True, text=True, env=ENV,
                          check=check, timeout=120)


def ensure_key():
    """Create the deploy key if needed. Returns the public key text."""
    if not os.path.exists(key_path()):
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key_path(), "-C", "cougstival-leaderboard"],
                       check=True)
    with open(key_path() + ".pub") as f:
        return f.read().strip()


def setup_repo(repo):
    """Point the site folder at the GitHub repo. Safe to repeat."""
    os.makedirs(site_dir(), exist_ok=True)
    install_site_page()
    if not os.path.isdir(os.path.join(site_dir(), ".git")):
        git("init")
    git("checkout", "-B", "main")
    ssh = f'ssh -i "{key_path().replace(os.sep, "/")}" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'
    git("config", "core.sshCommand", ssh)
    url = f"git@github.com:{repo}.git"
    if git("remote", "get-url", "origin", check=False).returncode == 0:
        git("remote", "set-url", "origin", url)
    else:
        git("remote", "add", "origin", url)
    if git("fetch", "origin", check=False).returncode == 0 and \
            git("rev-parse", "--verify", "origin/main", check=False).returncode == 0:
        git("reset", "origin/main")      # keep our files, adopt the repo's history


def check(repo):
    """Print what the organizer needs to do next. Returns 0 when GitHub accepts the key."""
    pub = ensure_key()
    setup_repo(repo)
    # A real push of the first page proves write access (a dry run does not check permissions on every setup).
    git("add", "index.html")
    if git("diff", "--cached", "--quiet", check=False).returncode != 0:
        git("-c", "user.name=Cougstival Leaderboard", "-c", "user.email=leaderboard-bot@users.noreply.github.com",
            "commit", "-m", "Add leaderboard page")
    r = git("push", "-u", "origin", "main", check=False)
    if r.returncode == 0:
        print("GitHub accepts this computer. Publishing works.")
        print(f"Last step: in the repo's Settings > Pages, choose 'Deploy from a branch', branch main, folder / (root).")
        print(f"Your site will be at https://{repo.split('/')[0].lower()}.github.io/{repo.split('/')[1]}/")
        return 0
    print("GitHub did not accept this computer yet.")
    print(f"1. Make sure the repository exists (public): https://github.com/{repo}")
    print(f"2. Add this deploy key at https://github.com/{repo}/settings/keys/new")
    print("   Tick 'Allow write access'. Key:")
    print(pub)
    print("Then press this button again. Details:", (r.stderr or "").strip()[-300:])
    return 1
