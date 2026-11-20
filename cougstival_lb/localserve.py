"""Local-only publishing: serve the site folder to the local network (no GitHub needed)."""
import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):
        pass


def serve(directory, port):
    """Start serving in a background thread. Returns the server, or None if the port is taken."""
    try:
        server = ThreadingHTTPServer(("0.0.0.0", port), functools.partial(Handler, directory=directory))
    except OSError as e:
        print(f"could not serve the site on port {port}: {e}")
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"serving the site on port {port}")
    return server
