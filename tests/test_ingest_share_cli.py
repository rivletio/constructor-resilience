"""Ingest, share envelope, and import."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence_cache import paths
from coherence_cache.cli import main


@pytest.fixture(autouse=True)
def _reset_root():
    paths._ROOT = None
    yield
    paths._ROOT = None


def _run(root: Path, *argv: str) -> None:
    main(["--root", str(root), *argv])


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_ingest_share_import_roundtrip(tmp_path, capsys):
    root = tmp_path / ".coherence"
    claims = tmp_path / "claims.json"
    claims.write_text(
        json.dumps(
            {
                "atoms": [
                    {
                        "text": "Atoms constrain a possibility or an impossibility.",
                        "constraint": "fact",
                    },
                    {
                        "text": "Mentions are joins on a claim, not a second graph.",
                        "constraint": "fact",
                        "mentions": [{"name": "NER", "kind": "concept"}],
                    },
                    "Packets are the share unit, not transcripts.",
                ]
            }
        ),
        encoding="utf-8",
    )

    _run(
        root,
        "ingest",
        "--json",
        str(claims),
        "--title",
        "Share primitive",
        "--auto-score",
        "--accepted",
    )
    topic = root / "topics" / "share-primitive"
    store = _load(topic / "atoms.json")
    assert len(store["atoms"]) == 3
    assert store["atoms"][0]["constraint"] == "fact"
    names = {m["name"] for a in store["atoms"] for m in (a.get("mentions") or [])}
    assert "NER" in names

    capsys.readouterr()
    _run(root, "share", "--to", "alice", "--audience", "circle", "--forward", "none")
    share = _load(topic / "share.json")
    assert share["kind"] == "intentional_share"
    assert share["to"] == "alice"
    assert share["atoms"]
    assert all(isinstance(a, str) for a in share["atoms"])

    _run(
        root,
        "import",
        str(topic / "share.json"),
        "--title",
        "From Alice",
        "--topic",
        "from-alice",
        "--accepted",
        "--use",
    )
    imported = _load(root / "topics" / "from-alice" / "atoms.json")
    assert len(imported["atoms"]) == len(share["atoms"])
    text0 = imported["atoms"][0]["text"]
    assert "[from:" not in text0
    assert imported.get("share", {}).get("from") == "local"
