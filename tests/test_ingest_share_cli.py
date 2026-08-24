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


def test_pack_from_empty_store_writes_packet(tmp_path, capsys):
    root = tmp_path / ".coherence"
    claims = tmp_path / "claims.json"
    claims.write_text(
        json.dumps({"atoms": ["Packets are the share unit, not transcripts."]}),
        encoding="utf-8",
    )
    capsys.readouterr()
    _run(root, "status")
    hint = capsys.readouterr().out
    assert "pack --title" in hint
    assert "Pack claims" in hint

    _run(root, "pack", "--json", str(claims), "--title", "Share primitive")
    out = capsys.readouterr().out
    assert "packed share-primitive" in out
    topic = root / "topics" / "share-primitive"
    store = _load(topic / "atoms.json")
    assert store["atoms"][0]["review"]["status"] == "accepted"
    packet = _load(topic / "packet.json")
    assert packet["atoms"]
    assert "Packets are the share unit" in packet["atoms"][0]


def test_pack_atoms_flags_no_json_file(tmp_path, capsys):
    root = tmp_path / ".coherence"
    _run(
        root,
        "pack",
        "--title",
        "No file",
        "--constraint",
        "fact",
        "--atom",
        "Packets are the share unit, not transcripts.",
        "--atom",
        "Mentions hang on a claim, not a second graph.",
    )
    out = capsys.readouterr().out
    assert "packed no-file" in out
    topic = root / "topics" / "no-file"
    store = _load(topic / "atoms.json")
    assert len(store["atoms"]) == 2
    assert store["atoms"][0]["constraint"] == "fact"
    assert store["atoms"][0]["review"]["status"] == "accepted"
    # re-pack same claims: skip duplicates, keep packet
    capsys.readouterr()
    _run(
        root,
        "pack",
        "--title",
        "No file",
        "--atom",
        "Packets are the share unit, not transcripts.",
    )
    out = capsys.readouterr().out
    assert "duplicate" in out.lower()
    store2 = _load(topic / "atoms.json")
    assert len(store2["atoms"]) == 2


def test_cache_miss_points_at_ingest(tmp_path, capsys):
    root = tmp_path / ".coherence"
    _run(root, "cache", "anything")
    out = capsys.readouterr().out
    assert "CACHE MISS" in out
    assert "pack --title" in out
