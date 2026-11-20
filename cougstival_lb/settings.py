"""Reading and writing config.json and secrets.json."""
import json
import os

from . import paths
from .engine import with_defaults

SECRET_KEYS = ("gc_email", "gc_password", "ntfy_topic", "ping_url")


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def write_json(path, obj, private=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600 if private else 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_config():
    cfg = read_json(paths.path("config.json"), None)
    return with_defaults(cfg) if cfg else None


def save_config(cfg):
    write_json(paths.path("config.json"), cfg)


def load_secrets():
    return read_json(paths.path("secrets.json"), {})


def save_secrets(secrets):
    write_json(paths.path("secrets.json"), {k: secrets.get(k, "") for k in SECRET_KEYS}, private=True)
