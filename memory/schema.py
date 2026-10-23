"""Pydantic models for memory documents and extraction output.

Mirrors the `memories` schema in AGENTS.md and the validator in
`Javascript(memory schema)`. Two additions, both from docs/AGENTS_REVIEW_NOTES.md:

- `extraction.key` is a per-repo slug that discriminates several memories from one
  file at one commit (note 1). It is part of the `_id` hash.
- `derived_from` in extraction files names upstream memories by key, so the LLM (or
  a human) never has to know an `_id`. Keys are resolved to IDs in code (note 5).
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MemoryType = Literal["hypothesis", "run", "synthesis", "dataset", "code", "note"]
Outcome = Literal["worked", "failed", "inconclusive"]
Status = Literal["draft", "active", "suspect", "retracted", "superseded"]

KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def memory_id(repo: str, path: str, commit_sha: str, type_: str, key: str) -> str:
    """Deterministic `_id`. Fields are joined with a separator so they cannot run together."""
    return hashlib.sha256("\x1f".join([repo, path, commit_sha, type_, key]).encode()).hexdigest()


class ExtractedMemory(BaseModel):
    """One memory as written in data/extractions/<repo>.yaml (the extractor's output)."""

    model_config = ConfigDict(extra="forbid")

    key: str
    type: MemoryType
    title: str = Field(min_length=3, max_length=120)
    content: str = Field(min_length=20)
    hypothesis: str | None = None
    inferred: bool = False
    config: dict[str, Any] | None = None
    key_metrics: dict[str, Any] | None = None
    outcome: Outcome | None = None
    path: str
    derived_from: list[str] = Field(default_factory=list)
    evidence: str = Field(min_length=10)  # where in `path` a reviewer can check the claims

    @field_validator("key")
    @classmethod
    def _key_slug(cls, v: str) -> str:
        if not KEY_RE.match(v):
            raise ValueError(f"key must be a lowercase slug: {v!r}")
        return v

    @model_validator(mode="after")
    def _consistent(self) -> "ExtractedMemory":
        if self.inferred and self.hypothesis is None:
            raise ValueError("inferred=true needs a hypothesis")
        if self.type in ("dataset", "code") and self.outcome is not None:
            raise ValueError(f"{self.type} memories have no outcome")
        if self.type == "note":
            raise ValueError("notes are chat-only working context, not ingested")
        return self


class RepoExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo: str  # owner/name
    owner: str
    memories: list[ExtractedMemory]

    @model_validator(mode="after")
    def _unique_keys(self) -> "RepoExtraction":
        keys = [m.key for m in self.memories]
        dupes = {k for k in keys if keys.count(k) > 1}
        if dupes:
            raise ValueError(f"duplicate keys: {sorted(dupes)}")
        return self


class Source(BaseModel):
    repo: str
    path: str
    commit_sha: str
    permalink: str

    @field_validator("commit_sha")
    @classmethod
    def _full_sha(cls, v: str) -> str:
        if not SHA_RE.match(v):
            raise ValueError("commit_sha must be a full 40-char SHA")
        return v

    @model_validator(mode="after")
    def _pinned(self) -> "Source":
        # Invariant 3: permalinks are pinned to a commit SHA, never a branch.
        if f"/blob/{self.commit_sha}/" not in self.permalink:
            raise ValueError("permalink must be pinned to commit_sha")
        return self


class Extraction(BaseModel):
    key: str
    evidence: str
    extractor: str


class Memory(BaseModel):
    """A document in the `memories` collection. `embedding` is added at load time."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    type: MemoryType
    title: str
    content: str
    hypothesis: str | None
    inferred: bool
    config: dict[str, Any] | None
    key_metrics: dict[str, Any] | None
    outcome: Outcome | None
    source: Source
    derived_from: list[str]
    status: Status
    status_reason: str | None = None
    superseded_by: str | None = None
    owner: str
    created_at: datetime
    ingested_at: datetime
    expires_at: datetime | None = None
    extraction: Extraction
    embedding: list[float] | None = None
