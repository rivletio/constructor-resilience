"""Store root resolution for the coherence cache.

Priority:
  1. Explicit ``root`` argument / ``--root`` CLI flag
  2. ``COHERENCE_ROOT`` environment variable
  3. ``./.coherence`` under the current working directory
  4. Legacy Grok artifact path if it exists (migration only)
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV = "COHERENCE_ROOT"
_LEGACY = Path("/home/workdir/artifacts/knowledge")
_LOCAL = Path(".coherence")

# Module-level default overridden by CLI before subcommands run.
_ROOT: Path | None = None


def set_root(path: Path | str | None) -> Path:
    """Set process-wide store root. Creates the directory if needed."""
    global _ROOT
    if path is None:
        _ROOT = resolve_root(None)
    else:
        _ROOT = Path(path).expanduser().resolve()
    _ROOT.mkdir(parents=True, exist_ok=True)
    return _ROOT


def get_root() -> Path:
    """Return the active store root (resolving defaults if unset)."""
    global _ROOT
    if _ROOT is None:
        _ROOT = resolve_root(None)
        _ROOT.mkdir(parents=True, exist_ok=True)
    return _ROOT


def resolve_root(explicit: Path | str | None = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get(_ENV, "").strip()
    if env:
        return Path(env).expanduser().resolve()
    local = (Path.cwd() / _LOCAL).resolve()
    if local.is_dir() or not _LEGACY.is_dir():
        return local
    return _LEGACY.resolve()


def meta_path(root: Path | None = None) -> Path:
    return (root or get_root()) / "meta.json"


def active_path(root: Path | None = None) -> Path:
    return (root or get_root()) / "active.json"


def ensure_meta(root: Path | None = None) -> dict:
    """Create an empty meta-store on first run."""
    from datetime import datetime, timezone
    import json

    root = root or get_root()
    root.mkdir(parents=True, exist_ok=True)
    mp = meta_path(root)
    if mp.exists():
        with open(mp, encoding="utf-8") as f:
            return json.load(f)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = {
        "version": 1,
        "description": "Meta-store for constructor-resilience topical knowledge stores",
        "created": ts,
        "updated": ts,
        "topics": [],
        "links": [],
    }
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")
    return meta
