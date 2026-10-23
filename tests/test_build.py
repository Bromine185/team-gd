import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from ingest.build import build
from memory.schema import RepoExtraction

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


@pytest.fixture
def clones(tmp_path: Path) -> Path:
    repo = tmp_path / "toy"
    repo.mkdir()
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(git[:3] + ["init", "-q"], check=True)
    for name in ("data.csv", "train (1).py", "results.json"):
        (repo / name).write_text(name)
    subprocess.run(git + ["add", "."], check=True)
    subprocess.run(git + ["commit", "-qm", "init"], check=True)
    return tmp_path


def mem(key, type_="run", path="results.json", derived_from=(), **kw):
    m = dict(key=key, type=type_, title=f"memory {key}", content="x" * 30, path=path,
             derived_from=list(derived_from), evidence="somewhere specific")
    if type_ == "run":
        m["outcome"] = "worked"
    return {**m, **kw}


def extraction(*memories):
    return RepoExtraction.model_validate({"repo": "o/toy", "owner": "o", "memories": list(memories)})


def test_ids_are_deterministic_and_deps_resolve(clones):
    ex = extraction(
        mem("data", "dataset", "data.csv"),
        mem("code", "code", "train (1).py"),
        mem("run-a", derived_from=["data", "code"]),
        mem("run-b", derived_from=["data"]),
    )
    first = build([ex], clones, T0)["o/toy"]
    second = build([ex], clones, T0)["o/toy"]
    assert [d.id for d in first] == [d.id for d in second]
    assert len({d.id for d in first}) == 4  # two runs from one file at one commit do not collide
    by_key = {d.extraction.key: d for d in first}
    assert by_key["run-a"].derived_from == [by_key["data"].id, by_key["code"].id]
    assert all(d.status == "draft" for d in first)
    assert "/blob/" + by_key["code"].source.commit_sha + "/train%20%281%29.py" in by_key["code"].source.permalink


def test_unknown_dependency_rejected(clones):
    with pytest.raises(KeyError):
        build([extraction(mem("run-a", derived_from=["nope"]))], clones, T0)


def test_cycle_rejected(clones):
    with pytest.raises(ValueError, match="cycle"):
        build([extraction(mem("a", derived_from=["b"]), mem("b", derived_from=["a"]))], clones, T0)


def test_untracked_path_rejected(clones):
    with pytest.raises(FileNotFoundError):
        build([extraction(mem("a", path="missing.json"))], clones, T0)


@pytest.mark.parametrize("bad", [
    {"type": "dataset", "outcome": "worked"},
    {"inferred": True, "hypothesis": None},
    {"type": "note"},
    {"key": "Not A Slug"},
    {"surprise": 1},
])
def test_extraction_schema_rejects(bad):
    with pytest.raises(ValidationError):
        extraction({**mem("a"), "outcome": None, **bad} if "type" in bad else {**mem("a"), **bad})


def test_duplicate_keys_rejected():
    with pytest.raises(ValidationError):
        extraction(mem("a"), mem("a"))
