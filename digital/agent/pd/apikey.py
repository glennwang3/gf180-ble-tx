"""Load the OpenRouter key without ever letting it reach a log or a repository.

Order of lookup:
  1. OPENROUTER_API_KEY in the environment
  2. the path in OPENROUTER_KEY_FILE
  3. ~/.config/openrouter/key

A file is refused unless it is readable by its owner only. Nothing here returns
the key in a representation meant for printing: use `masked()` for that.

Never pass the key as a command-line argument — on a shared machine anyone can
read another process's argv.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

DEFAULT_PATH = Path.home() / ".config" / "openrouter" / "key"
ENV_VAR = "OPENROUTER_API_KEY"
PATH_VAR = "OPENROUTER_KEY_FILE"


class KeyError_(RuntimeError):
    pass


def _from_file(path: Path) -> str:
    if not path.exists():
        raise KeyError_(f"no key file at {path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & (stat.S_IRGRP | stat.S_IROTH | stat.S_IWGRP | stat.S_IWOTH):
        raise KeyError_(
            f"{path} is readable or writable beyond its owner (mode {oct(mode)}). "
            f"Run: chmod 600 {path}")
    key = path.read_text().strip()
    if not key:
        raise KeyError_(f"{path} is empty")
    return key


def load(required: bool = True) -> str | None:
    """The key, or None when `required` is False and nothing is configured."""
    env = os.environ.get(ENV_VAR, "").strip()
    if env:
        return env
    explicit = os.environ.get(PATH_VAR, "").strip()
    if explicit:
        return _from_file(Path(explicit).expanduser())
    if DEFAULT_PATH.exists():
        return _from_file(DEFAULT_PATH)
    if required:
        raise KeyError_(
            f"no OpenRouter key found. Either export {ENV_VAR}, or put the key in "
            f"{DEFAULT_PATH} with mode 600. Do not pass it on the command line.")
    return None


def masked(key: str | None = None) -> str:
    """Safe to print or log: enough to tell two keys apart, not enough to use."""
    k = key or load(required=False)
    if not k:
        return "<none>"
    return f"{k[:8]}…{k[-4:]} ({len(k)} chars)" if len(k) > 16 else "<short>"


def scrub(text: str) -> str:
    """Remove any configured key from text before it is written anywhere.

    LiteLLM and httpx both include request details in some exception messages,
    so error text that is about to be stored or shown to a model goes through
    here first.
    """
    k = load(required=False)
    if not k:
        return text
    return text.replace(k, "sk-or-***REDACTED***")


def source() -> str:
    """Where the key came from, for an environment check. Never the value."""
    if os.environ.get(ENV_VAR, "").strip():
        return f"environment variable {ENV_VAR}"
    explicit = os.environ.get(PATH_VAR, "").strip()
    if explicit:
        return f"file {explicit}"
    if DEFAULT_PATH.exists():
        return f"file {DEFAULT_PATH}"
    return "not configured"


if __name__ == "__main__":
    print(f"  source : {source()}")
    try:
        print(f"  key    : {masked()}")
        print("  status : OK")
    except KeyError_ as e:
        print(f"  status : {e}")
