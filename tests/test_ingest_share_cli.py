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
                        "mentions": [{"name": "Mentions", "kind": "concept"}],
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
    assert "Mentions" in names

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


def test_pack_draft_and_forgiving_locators(tmp_path, capsys):
    from coherence_cache.mentions import parse_at_flag, parse_mention_flag, parse_pack_draft

    loc = parse_at_flag("page=1&paragraph=1&excerpt=1")
    assert loc["page"] == 1 and loc["paragraph"] == 1
    m = parse_mention_flag("check_atom:concept @ src/coherence_cache/check.py:20")
    assert m["name"] == "check_atom" and m["line"] == 20
    title, items = parse_pack_draft(
        """
        TITLE: Check atom
        CONSTRAINT: fact
        CLAIM: check_atom returns fail reasons for one claim.
        MENTION: check_atom:concept @ src/coherence_cache/check.py:20
        CLAIM: RWKV-7 Goose uses constant memory per token.
        MENTION: RWKV-7:work
        AT: p.1 ¶1
        """
    )
    assert title == "Check atom"
    assert items[0]["mentions"][0]["line"] == 20
    assert items[1]["mentions"][0]["page"] == 1
    assert items[1]["mentions"][0]["paragraph"] == 1

    draft = tmp_path / "pack.txt"
    draft.write_text(
        "TITLE: Draft pack\nCONSTRAINT: fact\n"
        "CLAIM: check_atom returns fail reasons for one claim.\n"
        "MENTION: check_atom:concept @ src/coherence_cache/check.py:20\n",
        encoding="utf-8",
    )
    _run(root := tmp_path / ".coherence", "pack", "--draft", str(draft))
    out = capsys.readouterr().out
    assert "packed draft-pack" in out
    assert "FAIL" not in out or "check 1/1 PASS" in out
    store = _load(root / "topics" / "draft-pack" / "atoms.json")
    assert store["atoms"][0]["mentions"][0]["line"] == 20


def test_check_fails_missing_mentions_and_retries(tmp_path, capsys):
    from coherence_cache.check import check_atom

    assert "too short" in check_atom("hi")
    assert "copied template, not a session claim" in check_atom(
        {
            "text": "One stand-alone sentence from the session.",
            "constraint": "fact",
            "mentions": [{"name": "X", "kind": "concept"}],
        }
    )
    assert "quoted fragment, not a claim" in check_atom(
        {
            "text": '"constant memory usage and constant inference time per token."',
            "constraint": "fact",
            "mentions": [{"name": "RWKV-7", "kind": "work"}],
        }
    )
    ok = {
        "text": "ClaimParts attaches joins to the preceding atom.",
        "constraint": "fact",
        "mentions": [
            {
                "name": "ClaimParts",
                "kind": "concept",
                "path": "src/coherence_cache/cli.py",
                "line": 358,
                "url": "src/coherence_cache/cli.py#L358",
            }
        ],
    }
    assert check_atom(ok) == []
    bad_file = {
        "text": "ClaimParts attaches joins to the preceding atom.",
        "constraint": "fact",
        "mentions": [{"name": "ClaimParts", "kind": "concept", "path": "src/cli.py"}],
    }
    assert any("no line" in f for f in check_atom(bad_file))

    root = tmp_path / ".coherence"
    _run(
        root,
        "pack",
        "--title",
        "Bare",
        "--constraint",
        "fact",
        "--atom",
        "Packets are the share unit, not transcripts.",
    )
    out = capsys.readouterr().out
    assert "FAIL missing mentions" in out
    with pytest.raises(SystemExit) as exc:
        _run(root, "check")
    assert exc.value.code == 1
    assert "FAIL missing mentions" in capsys.readouterr().out
    # observe/experiment line is printed by format_check on FAIL


def test_intersect_union_challenges_and_check_packet(tmp_path, capsys):
    root = tmp_path / ".coherence"
    _run(
        root,
        "pack",
        "--title",
        "Mine AI",
        "--constraint",
        "fact",
        "--atom",
        "JEPA predicts in latent space rather than tokens.",
        "--mention",
        "JEPA:concept",
        "--atom",
        "Packets are the share unit, not transcripts.",
        "--mention",
        "packet:concept",
    )
    _run(
        root,
        "pack",
        "--title",
        "Theirs AI",
        "--constraint",
        "fact",
        "--atom",
        "V-JEPA extends the same latent objective to video.",
        "--mention",
        "JEPA:concept",
        "--atom",
        "Public talks explore consciousness and understanding.",
        "--mention",
        "consciousness:concept",
    )
    overlap = tmp_path / "overlap.json"
    capsys.readouterr()
    _run(
        root,
        "intersect",
        "mine-ai",
        "theirs-ai",
        "--out",
        str(overlap),
        "--min-sim",
        "0.12",
    )
    out = capsys.readouterr().out
    assert "intersection" in out
    assert "challenges" in out
    assert "still hold" in out
    doc = _load(overlap)
    assert doc["kind"] == "interest_intersection"
    assert doc["challenges"]
    assert any(c.get("other") for c in doc["challenges"])

    _run(
        root,
        "pack",
        "--title",
        "Cats",
        "--constraint",
        "fact",
        "--atom",
        "Domestic cats hunt primarily at dusk and dawn.",
        "--mention",
        "cat:concept",
    )
    empty_p = tmp_path / "empty.json"
    capsys.readouterr()
    _run(root, "intersect", "mine-ai", "cats", "--out", str(empty_p))
    assert _load(empty_p)["atoms"] == []
    uni_p = tmp_path / "uni.json"
    capsys.readouterr()
    _run(root, "union", "mine-ai", "cats", "--out", str(uni_p))
    uni_out = capsys.readouterr().out
    assert "union" in uni_out
    uni = _load(uni_p)
    assert uni["kind"] == "interest_union"
    assert len(uni["atoms"]) >= 1
    assert uni["challenges"]
    assert any(c.get("other") is None for c in uni["challenges"])

    capsys.readouterr()
    _run(root, "check", "--packet", str(uni_p))
    cout = capsys.readouterr().out
    assert "PASS" in cout
    assert "interest_union" in cout
    assert "challenge" in cout.lower()

    # --union flag on intersect is the same verb
    flag_p = tmp_path / "flag-union.json"
    capsys.readouterr()
    _run(
        root,
        "intersect",
        "mine-ai",
        "cats",
        "--union",
        "--out",
        str(flag_p),
    )
    assert _load(flag_p)["kind"] == "interest_union"

    bad = tmp_path / "bad-overlap.json"
    bad.write_text(
        json.dumps({"kind": "interest_union", "atoms": ["hi"], "challenges": []}),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as exc:
        _run(root, "check", "--packet", str(bad))
    assert exc.value.code == 1
    assert "too short" in capsys.readouterr().out


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
