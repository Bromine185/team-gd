"""Git provenance for a local clone: commit SHAs, dates and pinned permalinks.

Deterministic. No network, no LLM.
"""

from __future__ import annotations

import subprocess
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class FileProvenance:
    path: str
    commit_sha: str  # last commit touching the path at HEAD; the permalink pins to it
    created_at: datetime  # author date of the commit that first added the path
    permalink: str


def _git(clone: Path, *args: str) -> str:
    # Literal pathspecs: notebook names like "02_style_bakeoff (1).ipynb" are not globs.
    return subprocess.run(
        ["git", "--literal-pathspecs", "-C", str(clone), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def head_sha(clone: Path) -> str:
    return _git(clone, "rev-parse", "HEAD")


def provenance(clone: Path, repo: str, path: str) -> FileProvenance:
    """Raise if `path` is not tracked at HEAD, so a typo in an extraction cannot slip through."""
    if not _git(clone, "ls-files", "--", path):
        raise FileNotFoundError(f"{repo}: {path!r} is not tracked at HEAD")
    sha = _git(clone, "log", "-1", "--format=%H", "--", path)
    first = _git(clone, "log", "--diff-filter=A", "--follow", "--format=%aI", "--", path)
    added = first.splitlines()[-1] if first else _git(clone, "log", "-1", "--format=%aI", sha)
    return FileProvenance(
        path=path,
        commit_sha=sha,
        created_at=datetime.fromisoformat(added),
        permalink=f"https://github.com/{repo}/blob/{sha}/{urllib.parse.quote(path)}",
    )
