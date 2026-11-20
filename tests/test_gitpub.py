import os
import subprocess

from cougstival_lb import gitpub


def sh(*a, cwd=None, env=None):
    return subprocess.run(a, cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout.strip()


def test_connect_empty_then_existing_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("COUGSTIVAL_HOME", str(tmp_path / "home"))
    remote = str(tmp_path / "remote.git")
    sh("git", "init", "--bare", "-b", "main", remote)
    cfgfile = tmp_path / "gitconfig"             # pretend github.com is the local bare repo
    cfgfile.write_text(f'[url "{remote}"]\n\tinsteadOf = git@github.com:me/board.git\n')
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfgfile))
    monkeypatch.setattr(gitpub, "ENV", {**os.environ})
    monkeypatch.setattr(gitpub, "ensure_key", lambda: "ssh-ed25519 FAKE")

    assert gitpub.check("me/board") == 0                          # empty repo: first push works
    assert "index.html" in sh("git", "ls-tree", "--name-only", "main", cwd=remote)
    assert gitpub.check("me/board") == 0                          # repeating is safe

    # A repo that already has history (someone added a README on GitHub): we adopt it instead of failing.
    other = str(tmp_path / "other")
    sh("git", "clone", remote, other)
    open(os.path.join(other, "README.md"), "w").write("hi")
    sh("git", "add", ".", cwd=other)
    sh("git", "-c", "user.name=x", "-c", "user.email=x@x", "commit", "-m", "readme", cwd=other)
    sh("git", "push", cwd=other)
    assert gitpub.check("me/board") == 0
    assert sh("git", "ls-tree", "--name-only", "main", cwd=remote).split() == ["README.md", "index.html"]
