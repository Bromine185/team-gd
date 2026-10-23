"""Turn data/extractions/<repo>.yaml into validated draft memories.

    python -m ingest.build --clones /path/to/clones [--out data/drafts]

For each extraction file: validate it, attach git provenance, compute deterministic
IDs, resolve `derived_from` keys to IDs, and write data/drafts/<repo>.jsonl.
A `derived_from` entry is either a key in the same file or `owner/name:key` for a
memory in another repo's extraction.

Every memory is written with status "draft". Nothing here talks to Atlas; loading,
embedding and review are separate steps.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ingest.collect import provenance
from memory.schema import Extraction, Memory, RepoExtraction, Source, memory_id

ROOT = Path(__file__).resolve().parent.parent
EXTRACTOR = "claude-code (manual read, hand-check pending)"


def load_extractions(directory: Path) -> list[RepoExtraction]:
    return [
        RepoExtraction.model_validate(yaml.safe_load(p.read_text()))
        for p in sorted(directory.glob("*.yaml"))
    ]


def clone_dir(clones: Path, repo: str) -> Path:
    name = repo.split("/", 1)[1]
    for cand in (clones / name, *clones.iterdir()):
        if cand.is_dir() and cand.name.lower() == name.lower():
            return cand
    raise FileNotFoundError(f"no clone of {repo} under {clones}")


def build(extractions: list[RepoExtraction], clones: Path, ingested_at: datetime) -> dict[str, list[Memory]]:
    # Pass 1: provenance and IDs for every memory in every repo, so cross-repo refs resolve.
    ids: dict[str, str] = {}
    prov = {}
    for ex in extractions:
        clone = clone_dir(clones, ex.repo)
        for m in ex.memories:
            p = provenance(clone, ex.repo, m.path)
            prov[(ex.repo, m.key)] = p
            ids[f"{ex.repo}:{m.key}"] = memory_id(ex.repo, m.path, p.commit_sha, m.type, m.key)

    # Pass 2: documents, with derived_from resolved to IDs.
    out: dict[str, list[Memory]] = {}
    for ex in extractions:
        docs = []
        for m in ex.memories:
            p = prov[(ex.repo, m.key)]
            upstream = []
            for ref in m.derived_from:
                full = ref if ":" in ref else f"{ex.repo}:{ref}"
                if full not in ids:
                    raise KeyError(f"{ex.repo}:{m.key} derives from unknown {ref!r}")
                if full == f"{ex.repo}:{m.key}":
                    raise ValueError(f"{full} derives from itself")
                upstream.append(ids[full])
            docs.append(
                Memory(
                    _id=ids[f"{ex.repo}:{m.key}"],
                    type=m.type,
                    title=m.title,
                    content=m.content.strip(),
                    hypothesis=m.hypothesis,
                    inferred=m.inferred,
                    config=m.config,
                    key_metrics=m.key_metrics,
                    outcome=m.outcome,
                    source=Source(repo=ex.repo, path=m.path, commit_sha=p.commit_sha, permalink=p.permalink),
                    derived_from=upstream,
                    status="draft",
                    owner=ex.owner,
                    created_at=p.created_at,
                    ingested_at=ingested_at,
                    extraction=Extraction(key=m.key, evidence=m.evidence.strip(), extractor=EXTRACTOR),
                )
            )
        out[ex.repo] = docs
    _check_acyclic([d for docs in out.values() for d in docs])
    return out


def _check_acyclic(docs: list[Memory]) -> None:
    edges = {d.id: d.derived_from for d in docs}
    state: dict[str, int] = {}

    def visit(n: str, trail: list[str]) -> None:
        if state.get(n) == 1:
            raise ValueError(f"derived_from cycle through {n}")
        if state.get(n) == 2:
            return
        state[n] = 1
        for up in edges.get(n, []):
            visit(up, trail + [n])
        state[n] = 2

    for n in edges:
        visit(n, [])


def write_jsonl(docs: list[Memory], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(d.model_dump(mode="json", by_alias=True, exclude={"embedding"}), ensure_ascii=False) for d in docs]
    path.write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--clones", type=Path, required=True, help="directory holding the source repo clones")
    ap.add_argument("--extractions", type=Path, default=ROOT / "data" / "extractions")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "drafts")
    args = ap.parse_args(argv)

    built = build(load_extractions(args.extractions), args.clones, datetime.now(timezone.utc))
    for repo, docs in built.items():
        target = args.out / f"{repo.split('/', 1)[1]}.jsonl"
        write_jsonl(docs, target)
        print(f"{repo}: {len(docs)} draft memories -> {target.relative_to(ROOT) if target.is_relative_to(ROOT) else target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
