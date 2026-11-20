"""The setup app: a small web server on this computer (127.0.0.1 only) that serves the setup page and its API."""
import json
import os
import secrets as rand
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, paths, service, settings
from .engine import experience_id, validate, with_defaults
from .scheduler import self_cmd

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

# Things the page may start. Each is just this app run with a command.
JOBS = {
    "check-login": ["check-login"],
    "check-login-headed": ["check-login", "--headed"],
    "install-browser": ["install-browser"],
    "once": ["once"],
    "test-alert": ["test-alert"],
    "test-ping": ["test-ping"],
}


class Job:
    """One background command whose output the page polls."""
    def __init__(self):
        self.lines, self.running, self.ok, self.name = [], False, None, ""
        self.lock = threading.Lock()

    def start(self, name, args):
        with self.lock:
            if self.running:
                return False
            self.lines, self.running, self.ok, self.name = [], True, None, name
        threading.Thread(target=self._run, args=(args,), daemon=True).start()
        return True

    def _run(self, args):
        try:
            p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
                                 stdin=subprocess.DEVNULL,
                                 creationflags=0x08000000 if sys.platform == "win32" else 0)   # no console window
            for line in p.stdout:
                self.lines.append(line.rstrip())
            self.ok = p.wait() == 0
        except Exception as e:
            self.lines.append(f"could not start: {e}")
            self.ok = False
        self.running = False


def browser_installed():
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or paths.path("browsers")
    return os.path.isdir(root) and any(n.startswith("chromium") for n in os.listdir(root))


def site_url(cfg):
    pub = cfg["publish"]
    if pub["mode"] == "github" and pub.get("repo"):
        owner, name = pub["repo"].split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}/"
    return f"http://localhost:{pub['port']}/"


def make_handler(token, job, on_quit=lambda: None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _allowed(self):
            """Only this computer's own page may call the API (blocks other websites and other computers)."""
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost") and self.headers.get("X-Token") == token

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                with open(os.path.join(WEB, "setup.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if not self._allowed():
                return self._send(403, {"error": "forbidden"})
            if path == "/api/state":
                return self._send(200, state())
            if path == "/api/job":
                return self._send(200, {"name": job.name, "running": job.running, "ok": job.ok, "lines": job.lines})
            if path == "/api/log":
                try:
                    with open(paths.path("logs", "app.log"), encoding="utf-8", errors="replace") as f:
                        return self._send(200, {"lines": f.read().splitlines()[-60:]})
                except FileNotFoundError:
                    return self._send(200, {"lines": []})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._allowed():
                return self._send(403, {"error": "forbidden"})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            except ValueError:
                return self._send(400, {"error": "bad request"})
            path = self.path.split("?")[0]
            if path == "/api/save":
                return self._send(200, save(body))
            if path == "/api/job":
                name = body.get("name")
                if name == "github-check":
                    repo = (settings.load_config() or {}).get("publish", {}).get("repo", "")
                    if not repo:
                        return self._send(200, {"ok": False, "error": "Save your settings with a GitHub repo first."})
                    args = self_cmd("github-check", repo)
                elif name in JOBS:
                    args = self_cmd(*JOBS[name])
                else:
                    return self._send(400, {"error": "unknown job"})
                return self._send(200, {"ok": job.start(name, args)})
            if path == "/api/quit":
                self._send(200, {"ok": True})
                return on_quit()
            if path == "/api/service":
                action = body.get("action")
                if action == "install":
                    ok, msg = service.install()
                elif action == "stop":
                    ok, msg = service.stop()
                else:
                    return self._send(400, {"error": "unknown action"})
                return self._send(200, {"ok": ok, "message": msg, "status": service.status()})
            self._send(404, {"error": "not found"})
    return Handler


def state():
    cfg = settings.load_config()
    sec = settings.load_secrets()
    return {
        "version": __version__,
        "config": cfg,
        "has": {"password": bool(sec.get("gc_password")), "ntfy": bool(sec.get("ntfy_topic")),
                "ping": bool(sec.get("ping_url"))},
        "email": sec.get("gc_email", ""),     # never the password, topic or ping URL
        "browser_installed": browser_installed(),
        "service": service.status(),
        "site_url": site_url(cfg) if cfg else "",
        "platform": sys.platform,
    }


def save(body):
    """Validate and store settings. Secrets left blank keep their saved value; they are never sent back."""
    cfg = body.get("config") or {}
    cfg["experience_id"] = experience_id(cfg.get("experience_id", "")) or ""
    cfg = with_defaults(cfg)
    pub = cfg["publish"]
    try:
        pub["port"] = int(pub.get("port"))
    except (TypeError, ValueError):
        pub["port"] = 0
    errs = validate(cfg)
    sec_in = body.get("secrets") or {}
    sec = settings.load_secrets()
    for key in settings.SECRET_KEYS:
        if sec_in.get(key):
            sec[key] = sec_in[key].strip() if key != "gc_password" else sec_in[key]
    if not sec.get("gc_email") or not sec.get("gc_password"):
        errs.append("Goosechase email and password are needed.")
    if errs:
        return {"ok": False, "errors": errs}
    settings.save_config(cfg)
    settings.save_secrets(sec)
    from .cycle import install_site_page
    install_site_page()
    return {"ok": True, "site_url": site_url(cfg)}


def serve_setup(open_browser=True, port=0):
    token, job = rand.token_urlsafe(24), Job()
    server = None

    def quit_server():
        threading.Thread(target=server.shutdown, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(token, job, quit_server))
    url = f"http://127.0.0.1:{server.server_port}/#{token}"
    print("Setup is open in your browser. If it did not open, go to:", url, flush=True)
    print("Close this window (or press Ctrl-C) when you are done.", flush=True)
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
