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


def test_pack_mention_flag_joins_last_atom(tmp_path, capsys):
    root = tmp_path / ".coherence"
    _run(
        root,
        "pack",
        "--title",
        "Joins",
        "--constraint",
        "fact",
        "--atom",
        "RWKV-7 has constant memory and constant time per token.",
        "--mention",
        "RWKV-7:work",
        "--mention",
        "compressive state:concept",
        "--atom",
        "Packets are the share unit, not transcripts.",
    )
    store = _load(root / "topics" / "joins" / "atoms.json")
    names0 = {(m["name"], m["kind"]) for m in store["atoms"][0].get("mentions") or []}
    assert ("RWKV-7", "work") in names0
    assert ("compressive state", "concept") in names0
    assert not (store["atoms"][1].get("mentions") or [])


def test_pack_mention_at_file_line_and_timestamp(tmp_path, capsys):
    from coherence_cache.mentions import parse_at_flag

    loc = parse_at_flag("src/coherence_cache/cli.py:358")
    assert loc["path"] == "src/coherence_cache/cli.py"
    assert loc["line"] == 358
    assert loc["url"] == "src/coherence_cache/cli.py#L358"
    span = parse_at_flag("src/foo.py#L10-L12")
    assert span["line"] == 10 and span["end_line"] == 12
    assert span["url"].endswith("#L10-L12")
    ts = parse_at_flag("t=3033")
    assert ts["t"] == 3033 and ts["t_label"] == "50:33"

    root = tmp_path / ".coherence"
    _run(
        root,
        "pack",
        "--title",
        "Located joins",
        "--constraint",
        "fact",
        "--atom",
        "ClaimParts attaches joins to the preceding atom.",
        "--mention",
        "ClaimParts:concept",
        "--at",
        "src/coherence_cache/cli.py:358",
        "--mention",
        "Lex Fridman:person",
        "--at",
        "https://www.youtube.com/watch?v=qCbfTN-caFI&t=3033",
    )
    store = _load(root / "topics" / "located-joins" / "atoms.json")
    m0, m1 = store["atoms"][0]["mentions"]
    assert m0["path"] == "src/coherence_cache/cli.py"
    assert m0["line"] == 358
    assert m0["url"] == "src/coherence_cache/cli.py#L358"
    assert m1["t"] == 3033
    assert "qCbfTN-caFI" in m1["url"] and "t=3033" in m1["url"]


def test_cache_ignores_weak_tokens(tmp_path, capsys):
    root = tmp_path / ".coherence"
    _run(
        root,
        "pack",
        "--title",
        "Packet search",
        "--atom",
        "A packet is a small subset of atoms maximizing coverage.",
    )
    capsys.readouterr()
    _run(root, "cache", "small-world scale-free co-authorship")
    out = capsys.readouterr().out
    assert "CACHE MISS" in out
    _run(root, "cache", "packet coverage atoms")
    hit = capsys.readouterr().out
    assert "CACHE HIT" in hit
    assert "packet-search" in hit


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


def test_cache_tied_scores_do_not_crash(tmp_path, capsys):
    root = tmp_path / ".coherence"
    _run(root, "pack", "--title", "Alpha theme", "--atom", "Durable packet claim one.")
    _run(root, "pack", "--title", "Beta theme", "--atom", "Durable packet claim two.")
    capsys.readouterr()
    _run(root, "cache", "durable packet claim")
    out = capsys.readouterr().out
    assert "CACHE HIT" in out
    assert "alpha-theme" in out
    assert "beta-theme" in out


def test_cache_miss_points_at_ingest(tmp_path, capsys):
    root = tmp_path / ".coherence"
    _run(root, "cache", "anything")
    out = capsys.readouterr().out
    assert "CACHE MISS" in out
    assert "pack --title" in out
