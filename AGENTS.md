# AGENTS.md

Guidance for coding agents (Claude Code, Codex, etc.) working in this repo. Read this before making changes.

## What we are building

An **experiment memory agent** for the MongoDB Student Hackathon, Track 1 (Agentic Memory), TransfiNITTe 2026.

It ingests ML experiment history from GitHub repos into a persistent memory bank in MongoDB Atlas. It answers questions and warns about repeated or invalidated work by citing that memory. It also writes new memories when the user reports results.

The track requires two things, and every feature should serve one of them:

1. **Stored memory must visibly change the agent's next response.**
2. **One hard case must be demonstrated.** Ours is the **retraction cascade**: a dataset or script is declared buggy, so the results derived from it are retracted, their dependents are flagged suspect, and the agent's answers change.

Judges will ask us to explain the architecture, data model and choices. Prefer simple, explainable logic over clever logic.

## Data sources

- **Dataset 1:** the team's own experiment repos (diff_model, lisa-rtm, optiver-close, NST). We know the ground truth, so we can verify extraction by hand.
- Optional dataset 2: one external repo (e.g. modded-nanogpt) to show the extractor works on code we did not write.
- Keep the input set small. Every memory that appears in the demo must be hand-checked.

## Architecture

```
GitHub repos
   │  collect (README, notebooks + outputs, configs, small results files, commit log)
   ▼
Experiment candidates  ── grouped by results dir / notebook / commit range
   │  LLM structured extraction
   ▼
Draft memories ──► Review queue (human approves / edits) ──► status: active
                                                                 │
                     ┌───────────────────────────────────────────┤
                     ▼                                           ▼
             Agent: retrieve → re-rank → answer          Corrections: retract / supersede
             (cites memory IDs + permalinks;             ($graphLookup downstream,
              writes back new results)                    change streams → UI)
```

## Data model

Single collection: `memories`.

```js
{
  _id: "<sha256(repo + path + commit_sha + type)>",  // deterministic, idempotent ingest
  type: "hypothesis" | "run" | "synthesis" | "dataset" | "code" | "note",
  title: "short human label",
  content: "text the agent reasons over",
  hypothesis: "string | null",
  inferred: false,              // true if the hypothesis was inferred rather than written down
  config: { },                  // key hyperparameters, null if unknown
  key_metrics: { },             // e.g. { val_loss: 2.91 }, null if unknown
  outcome: "worked" | "failed" | "inconclusive" | null,
  source: {
    repo: "owner/name",
    path: "relative/path",
    commit_sha: "full sha",
    permalink: "https://github.com/owner/name/blob/<sha>/<path>"
  },
  derived_from: ["<_id>", ...], // upstream dependencies (datasets, code, prior runs/syntheses)
  status: "draft" | "active" | "suspect" | "retracted" | "superseded",
  status_reason: "string | null",
  superseded_by: "<_id> | null",
  owner: "user id",
  created_at: ISODate,          // experiment time (from commit date where possible)
  ingested_at: ISODate,
  expires_at: ISODate | null,   // only for type "note" (short-lived working context)
  embedding: [ ... ]            // embedding of title + hypothesis + content
}
```

### Indexes

- Atlas Vector Search index on `embedding`, with filter fields `status`, `type`, `source.repo`, `owner`.
- Unique index on `_id` (default). The hash keeps re-ingestion idempotent.
- Regular index on `derived_from` (used by `$graphLookup`).
- TTL index on `expires_at` (`expireAfterSeconds: 0`). Only `note` memories set this field.

## Status semantics

| Status | Meaning | Retrieved? |
|---|---|---|
| `draft` | Extracted, not yet reviewed | No |
| `active` | Reviewed and trusted | Yes |
| `suspect` | Depends on something retracted; may still be valid | Yes, **with a warning** |
| `retracted` | Directly invalidated by the user | No, but the agent may mention it when the user asks about that experiment |
| `superseded` | Replaced by a newer version (`superseded_by`) | No |

## Invariants (do not break these)

1. **Never overwrite or hard-delete experiment memories.** Edits create a new memory and mark the old one `superseded`. Retractions change `status`. Only TTL removes `note` memories.
2. **Never invent data during extraction.** Unknown fields are `null`. A hypothesis not written anywhere in the repo is either `null` or set with `inferred: true`.
3. **Permalinks are pinned to a commit SHA**, never a branch.
4. **Ingest is idempotent.** Running it twice produces no duplicates.
5. **Every agent answer cites memory IDs and permalinks** for the claims it makes about past experiments.
6. **Retrieval never returns `draft`, `retracted` or `superseded` memories as evidence.** Filter in the vector search pre-filter, not after the LLM call.
7. **Memory logic is deterministic.** The LLM extracts fields and writes prose. Status changes, cascade and ranking are plain code.

## Core logic

### Retrieval and ranking
1. `$vectorSearch` with pre-filter `status in ["active", "suspect"]` (plus `owner`/`repo` scoping).
2. Re-rank: `score = w_sim * similarity + w_rec * recency + w_out * outcome_weight`. Keep the weights in config and expose the per-memory breakdown to the UI inspector.
3. The LLM answers using only the retrieved memories, and it must label anything resting on a `suspect` memory.

### Write-back
When the user reports a new result in chat, the agent creates a `run` (and optionally a `synthesis`) memory with `derived_from` set to the memories it builds on. It confirms what it stored in the reply.

### Retraction cascade
```
retract(root_id, reason):
  set root status = retracted, status_reason = reason
  downstream = $graphLookup(from memories, startWith root._id,
                            connectFromField "_id", connectToField "derived_from")
  direct results of the root (runs whose derived_from contains root) -> retracted
  everything else downstream -> suspect (unless already retracted/superseded)
  record who/when/why on each changed doc
```
"Suspect" is a flag for the user to review, not a verdict. Provide `clear_suspect(id)`.

### Change streams
The UI subscribes to status changes on `memories` so the provenance graph updates live during a retraction.

## Suggested layout

```
ingest/        collect.py, segment.py, extract.py (LLM prompts + schema), review.py
memory/        db.py (client, index setup), schema.py, retrieve.py, rank.py, cascade.py
agent/         loop.py (retrieve -> answer -> write-back), prompts.py
ui/            app.py (chat, memory inspector, provenance graph)
eval/          questions.yaml (question -> expected memory IDs), run_eval.py
scripts/       setup_indexes.py, seed_demo.py, reset_demo.py
data/          cached repo snapshots / extraction outputs (gitignored if large)
```

## Build phases

| Phase | Work | Done when |
|---|---|---|
| 0 | Atlas cluster, indexes, embedding model, skeleton | A test doc comes back from vector search |
| 1 | Ingestion on one repo + review queue | ~10 approved memories from one repo |
| 2 | Agent retrieve → answer → write-back | A past-experiment question gets a cited answer |
| 3 | Retraction cascade, supersede, TTL notes | Retracting a dataset flips its dependents |
| 4 | UI: inspector, provenance graph, change streams | Cascade is visible live |
| 5 | Remaining repos, eval set, demo rehearsal | Demo script runs start to finish |

Phases 1–3 are the core. If time is short, cut the graph view before cutting the eval.

## Demo script (target ~4 minutes)

1. Show ingested history from real repos.
2. Propose an experiment close to a past one. The agent warns and cites the permalink.
3. Log a new result in chat. The agent stores it with its parent link.
4. Declare a dataset/script buggy. The graph shows retracted and suspect nodes.
5. Re-ask the question from step 2. The answer changes.
6. Show eval numbers (retrieval hit rate; retracted memories no longer cited).

`scripts/reset_demo.py` must restore the pre-retraction state in one command so the demo can be rehearsed repeatedly.

## Conventions

- Python 3.11+. Type hints on public functions. Pydantic models for memory documents and extraction output.
- Secrets in `.env` (`MONGODB_URI`, `EMBEDDING_API_KEY`, `LLM_API_KEY`); never commit them. Provide `.env.example`.
- Every LLM extraction call validates against the Pydantic schema. If validation fails, retry once, then store as `draft` with `status_reason: "extraction_failed"`.
- Keep prompts in `agent/prompts.py` and `ingest/extract.py`, not inline in logic.
- Small, focused commits. Do not reformat unrelated files.

## Testing

- Unit tests for `cascade.py` on a small hand-built graph (root, direct results, two levels of dependents, an already-superseded node).
- Test that ingest run twice yields the same document count.
- Test that retrieval never returns `draft`/`retracted`/`superseded`.
- `eval/run_eval.py` reports retrieval hit rate before and after the demo retraction.

## Open decisions (ask the team before assuming)

- Embedding model (MongoDB automated embedding / Voyage vs another provider) and dimensions.
- LLM provider for extraction and answering.
- UI framework (default: Streamlit).
- Which dataset or script is the planted bug. It must have at least 3 downstream experiments.
- Ranking weights.

## Do not

- Do not add features outside Track 1's scope (no auth system, no multi-tenant admin).
- Do not let the LLM decide status changes.
- Do not fetch or store model weights, datasets or large binaries from repos.
- Do not show any memory in the demo that has not been human-reviewed.
