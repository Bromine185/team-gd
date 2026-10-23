# AGENTS.md review notes

Open issues found while reviewing `AGENTS.md`. To be addressed later; none of these block ingestion work.

## Structural (fix before Phase 2/3)

1. **`_id` hash collides.** `sha256(repo + path + commit_sha + type)` gives the same ID to multiple runs in one notebook at one commit, and to a superseding edit of an existing memory. Write-back memories from chat have no repo/path/commit at all.
   - Add a discriminator (candidate index or title slug) for ingested memories.
   - Use a separate ID scheme for chat-created memories.
   - Define re-ingest behaviour when `_id` exists: skip, never upsert.
2. **No `rejected` state.** A reviewer cannot discard a bad extraction. Either add `rejected` or state that drafts are not yet experiment memories and may be hard-deleted.
3. **Schema cannot record cascade provenance.** Cascade says "record who/when/why on each changed doc" but schema has only `status_reason`. Add `status_history: [{status, reason, by, at, cause_id}]` and `suspect_because: <root_id>` so `clear_suspect` can tell whether another retraction still covers the node.
4. **Retracted memories have no path to the agent.** Invariant 6 pre-filters them out, but the status table says the agent "may mention" them. Decide: a second, labelled query for retracted neighbours passed as context (not evidence), or an explicit lookup when the user names an experiment. Add to invariants.
5. **Dependency extraction is under-specified.** The LLM cannot emit `derived_from` IDs before upstream memories exist. Use two-pass ingest: datasets/code first, then runs referencing upstreams by path, resolved to IDs in code. Allow a per-repo `candidates.yaml` as a manual segmentation override.

## Semantics

6. **Outcome weight direction.** Failed experiments are the most valuable to surface for "repeated work" warnings. Do not penalise `failed`. Consider a status term so `suspect` ranks below `active`.
7. **Notes in `derived_from`.** TTL-deleted notes leave dangling edges. Forbid depending on `note` memories.
8. **State machine not written down.** draft->active, active|suspect->retracted, suspect->active (clear_suspect), active->superseded. Nothing leaves retracted. Add a table.
9. **Cascade edge cases.** Set `maxDepth` on `$graphLookup`; define diamonds and a root that is already `suspect`; apply as one `bulkWrite` so the change stream is coherent.
10. **Edits of drafts.** Clarify that invariant 1 (new memory + supersede) applies to `active` and later; drafts are edited in place in the review queue.

## Process

11. **`reset_demo.py` violates invariant 1.** Declare it a demo-only exception, or implement as collection snapshot/restore.
12. **Local dev needs Atlas.** Vector search and change streams do not run on standalone mongod. Share one cluster with per-developer DB names.
13. **Eval undefined.** Fix k for hit rate and partial-match rule. Add metric: zero retracted IDs cited after cascade.
14. **Planted bug should be decided before Phase 1.** It determines which repos and memories get hand-checked.
15. **Open decisions need defaults.** "Ask the team" does not work in an autonomous agent session. Give each a default until overridden.
16. **Review-queue indexes.** Add a compound index on `status` + `source.repo` for queue and inspector listings.
