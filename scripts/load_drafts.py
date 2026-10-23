"""Load data/drafts/*.jsonl into Atlas.

    MONGODB_URI=... python -m scripts.load_drafts [--db team_gd] [--dry-run]

Creates the `memories` collection (validator + indexes) if needed, then inserts each
draft. An `_id` that already exists is skipped, never updated (invariant 4 and review note 1).
Drafts carry no embedding yet: the validator requires `embedding` only once a memory
leaves `draft`, so embeddings are added at review time, before a memory becomes active.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from pymongo import ASCENDING, MongoClient
from pymongo.errors import BulkWriteError, CollectionInvalid

ROOT = Path(__file__).resolve().parent.parent
DATE_FIELDS = ("created_at", "ingested_at", "expires_at")

VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["_id", "type", "title", "content", "inferred", "source", "derived_from",
                     "status", "owner", "created_at", "ingested_at"],
        "properties": {
            "_id": {"bsonType": "string"},
            "type": {"enum": ["hypothesis", "run", "synthesis", "dataset", "code", "note"]},
            "title": {"bsonType": "string"},
            "content": {"bsonType": "string"},
            "hypothesis": {"bsonType": ["string", "null"]},
            "inferred": {"bsonType": "bool"},
            "config": {"bsonType": ["object", "null"]},
            "key_metrics": {"bsonType": ["object", "null"]},
            "outcome": {"enum": ["worked", "failed", "inconclusive", None]},
            "source": {
                "bsonType": "object",
                "required": ["repo", "path", "commit_sha", "permalink"],
            },
            "derived_from": {"bsonType": "array", "items": {"bsonType": "string"}},
            "status": {"enum": ["draft", "active", "suspect", "retracted", "superseded"]},
            "status_reason": {"bsonType": ["string", "null"]},
            "superseded_by": {"bsonType": ["string", "null"]},
            "owner": {"bsonType": "string"},
            "created_at": {"bsonType": "date"},
            "ingested_at": {"bsonType": "date"},
            "expires_at": {"bsonType": ["date", "null"]},
            "embedding": {"bsonType": "array", "items": {"bsonType": "double"}},
        },
    },
    # Only drafts may lack an embedding.
    "$or": [{"status": "draft"}, {"embedding": {"$exists": True}}],
}


def read_drafts(directory: Path) -> list[dict]:
    docs = []
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                for f in DATE_FIELDS:
                    if d.get(f):
                        d[f] = datetime.fromisoformat(d[f])
                docs.append(d)
    return docs


def ensure_collection(db) -> None:
    try:
        db.create_collection("memories", validator=VALIDATOR)
    except CollectionInvalid:
        db.command("collMod", "memories", validator=VALIDATOR)
    m = db.memories
    m.create_index([("derived_from", ASCENDING)], name="idx_derived_from")
    m.create_index([("status", ASCENDING), ("source.repo", ASCENDING)], name="idx_status_repo")
    m.create_index([("expires_at", ASCENDING)], name="idx_expires_at", expireAfterSeconds=0,
                   partialFilterExpression={"type": "note"})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default="team_gd")
    ap.add_argument("--drafts", type=Path, default=ROOT / "data" / "drafts")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    docs = read_drafts(args.drafts)
    assert all(d["status"] == "draft" for d in docs), "loader only inserts drafts"
    if args.dry_run:
        print(f"{len(docs)} drafts read; nothing written")
        return 0

    db = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=20000)[args.db]
    ensure_collection(db)
    try:
        inserted = len(db.memories.insert_many(docs, ordered=False).inserted_ids)
    except BulkWriteError as e:
        errors = e.details["writeErrors"]
        other = [w for w in errors if w["code"] != 11000]
        if other:
            raise
        inserted = e.details["nInserted"]
    print(f"{inserted} inserted, {len(docs) - inserted} already present (skipped)")
    print({r["_id"]: r["n"] for r in db.memories.aggregate(
        [{"$group": {"_id": "$source.repo", "n": {"$sum": 1}}}])})
    return 0


if __name__ == "__main__":
    sys.exit(main())
