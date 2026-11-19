"""Load key=value pairs from a local .env file into os.environ.

Zero dependencies. Import this module early (before reading os.environ) in any
entry point:

    import env_loader; env_loader.load()

Rules:
  - Lines are KEY=VALUE. Blank lines and lines starting with # are ignored.
  - An optional leading `export ` is stripped (so a shell-style .env also works).
  - Surrounding single or double quotes around the value are removed.
  - A real environment variable already set takes precedence over the file,
    so `$env:FOO = "x"` in your terminal still overrides .env.
  - Values are never printed, so secrets stay out of logs.
"""
import os
from pathlib import Path

_loaded = False


def load(path=None, override=False):
    """Load .env from `path` (default: next to this file). Returns the dict loaded.

    Set override=True to let the file win over already-set environment variables.
    """
    global _loaded
    env_path = Path(path) if path else Path(__file__).resolve().parent / ".env"
    loaded = {}
    if not env_path.is_file():
        _loaded = True
        return loaded
    try:
        # utf-8-sig transparently strips a BOM some editors add on Windows.
        text = env_path.read_text(encoding="utf-8-sig")
    except OSError:
        return loaded
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if not key:
            continue
        loaded[key] = value
        if override or key not in os.environ:
            os.environ[key] = value
    _loaded = True
    return loaded
