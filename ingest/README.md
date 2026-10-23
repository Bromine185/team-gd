# Ingest

```
source clones ──► data/extractions/<repo>.yaml ──► python -m ingest.build ──► data/drafts/<repo>.jsonl ──► review ──► Atlas
                  (extractor: LLM or human)        (deterministic: git SHAs,      (status: draft)
                                                    IDs, derived_from, checks)
```

```bash
pip install -r requirements.txt
python -m ingest.build --clones /path/to/dir/with/clones   # writes data/drafts/*.jsonl
python -m pytest
```

## Extraction files

One YAML per source repo, validated by `memory.schema.RepoExtraction` (unknown keys are rejected). Each memory has a
`key` (slug, unique per file), the AGENTS.md fields, the primary source `path`, `derived_from` as keys, and an
`evidence` pointer that tells a reviewer exactly where to check the claims.

- `derived_from` holds keys, not IDs: `other-key` for the same repo, `owner/name:key` for another repo. `build.py`
  resolves keys to IDs and rejects unknown references and cycles. This resolves review note 5: upstream IDs are not needed at extraction time.
- `_id = sha256(repo, path, commit_sha, type, key)`. The key stops several memories from one file at one commit from colliding (review note 1). `commit_sha` is the
  last commit touching `path`, so re-ingesting an unchanged file gives the same ID; a changed file gives a new
  draft, which the reviewer approves as a supersede.
- `created_at` is the author date of the commit that added `path`. Permalinks pin `commit_sha` and are URL-encoded.

The first extractions were written by Claude Code reading each repo (no extraction LLM is wired up yet; provider is an
open decision). They are drafts: every memory must be hand-checked against its `evidence` before it becomes `active`.

## Not here yet

- Embeddings (model is an open decision). `python -m scripts.load_drafts` loads drafts without them.
- The review queue.
