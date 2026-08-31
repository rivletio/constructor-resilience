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
    assert all(isinstance(a, dict) and "text" in a for a in share["atoms"])
    assert any((a.get("mentions") or []) for a in share["atoms"])

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

    with pytest.raises(SystemExit) as packed:
        _run(root, "pack", "--json", str(claims), "--title", "Share primitive")
    assert packed.value.code == 1
    out = capsys.readouterr().out
    assert "packed share-primitive" in out
    topic = root / "topics" / "share-primitive"
    store = _load(topic / "atoms.json")
    assert store["atoms"][0]["review"]["status"] == "accepted"
    packet = _load(topic / "packet.json")
    assert packet["atoms"]
    a0 = packet["atoms"][0]
    blob = a0 if isinstance(a0, str) else a0.get("text", "")
    assert "Packets are the share unit" in blob


def test_packet_and_share_keep_mentions_on_each_claim(tmp_path, capsys):
    root = tmp_path / ".coherence"
    _run(
        root,
        "pack",
        "--title",
        "Join travels",
        "--constraint",
        "fact",
        "--atom",
        "It predicts in latent space rather than tokens.",
        "--mention",
        "JEPA:concept",
    )
    topic = root / "topics" / "join-travels"
    packet = _load(topic / "packet.json")
    rec = packet["atoms"][0]
    assert isinstance(rec, dict)
    assert rec["text"].startswith("It predicts")
    assert rec["mentions"][0]["name"] == "JEPA"
    capsys.readouterr()
    _run(root, "share", "--to", "alice", "--audience", "circle")
    share = _load(topic / "share.json")
    s0 = share["atoms"][0]
    assert isinstance(s0, dict)
    assert s0["mentions"][0]["name"] == "JEPA"
    imported_names = {m["name"] for m in (share.get("mentions") or [])}
    assert "JEPA" in imported_names


def test_pack_mention_flag_joins_last_atom(tmp_path, capsys):
    root = tmp_path / ".coherence"
    with pytest.raises(SystemExit) as exc:
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
    assert exc.value.code == 1
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
    ax = parse_at_flag("arxiv:2512.10942")
    assert ax.get("kind") == "arxiv"
    assert ax.get("id") == "2512.10942"
    assert "path" not in ax
    assert "arxiv.org/abs/2512.10942" in (ax.get("abs") or ax.get("url") or "")

    root = tmp_path / ".coherence"
    with pytest.raises(SystemExit) as exc:
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
    assert exc.value.code == 1
    store = _load(root / "topics" / "located-joins" / "atoms.json")
    m0, m1 = store["atoms"][0]["mentions"]
    assert m0["path"] == "src/coherence_cache/cli.py"
    assert m0["line"] == 358
    assert m0["url"] == "src/coherence_cache/cli.py#L358"
    assert m1["t"] == 3033
    assert "qCbfTN-caFI" in m1["url"] and "t=3033" in m1["url"]


def test_pack_claim_at_and_mention_at(tmp_path, capsys):
    root = tmp_path / ".coherence"
    _run(
        root,
        "pack",
        "--title",
        "Where",
        "--constraint",
        "fact",
        "--atom",
        "It predicts in latent space rather than tokens.",
        "--at",
        "t=3033",
        "--mention",
        "JEPA:concept",
        "--at",
        "t=3100",
    )
    store = _load(root / "topics" / "where" / "atoms.json")
    rec = store["atoms"][0]
    assert rec["at"]["t"] == 3033
    assert rec["mentions"][0]["t"] == 3100
    packet = _load(root / "topics" / "where" / "packet.json")
    prec = packet["atoms"][0]
    assert prec["at"]["t"] == 3033
    assert prec["mentions"][0]["t"] == 3100
    capsys.readouterr()
    _run(root, "share", "--to", "alice")
    share = _load(root / "topics" / "where" / "share.json")
    s0 = share["atoms"][0]
    assert s0["at"]["t"] == 3033
    assert s0["mentions"][0]["t"] == 3100

    from coherence_cache.mentions import parse_pack_draft

    _title, items = parse_pack_draft(
        """
        TITLE: Draft where
        CONSTRAINT: fact
        CLAIM: It predicts in latent space rather than tokens.
        AT: t=3033
        MENTION: JEPA:concept
        AT: t=3100
        """
    )
    assert items[0]["at"]["t"] == 3033
    assert items[0]["mentions"][0]["t"] == 3100

    title2, items2 = parse_pack_draft(
        "RWKV-7 Goose\n"
        "CONSTRAINT: fact\n"
        "1 RWKV-7 Goose is a constant-time sequence model.\n"
        "AT: paper.md:4\n"
        "MENTION: RWKV-7:work\n"
        "2 Softmax attention incurs quadratic cost.\n"
        "AT: paper.md:15\n"
        "MENTION: attention:concept\n"
    )
    assert title2 == "RWKV-7 Goose"
    assert len(items2) == 2
    assert "constant-time" in items2[0]["text"]
    assert items2[0]["mentions"][0]["name"] == "RWKV-7"
    assert items2[1]["at"]["path"] == "paper.md"
    assert items2[1]["at"]["line"] == 15


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
        CLAIM: The joint embedding predictive architecture predicts in latent space rather than tokens.
        MENTION: JEPA:concept
        ALIAS: joint embedding predictive architecture
        """
    )
    assert title == "Check atom"
    assert items[0]["mentions"][0]["line"] == 20
    assert items[1]["mentions"][0]["page"] == 1
    assert items[1]["mentions"][0]["paragraph"] == 1
    assert items[2]["mentions"][0]["aliases"] == [
        "joint embedding predictive architecture"
    ]

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


def test_pack_draft_arxiv_at_becomes_ref_not_path(tmp_path, capsys):
    root = tmp_path / ".coherence"
    draft = tmp_path / "ax.txt"
    draft.write_text(
        "TITLE: Paper cite\nCONSTRAINT: fact\n"
        "CLAIM: VL-JEPA predicts continuous embeddings of target texts rather than tokens.\n"
        "MENTION: VL-JEPA:work\n"
        "AT: arxiv:2512.10942\n",
        encoding="utf-8",
    )
    _run(root, "pack", "--draft", str(draft))
    store = _load(root / "topics" / "paper-cite" / "atoms.json")
    atom = store["atoms"][0]
    assert not (atom.get("at") or {}).get("path")
    refs = atom.get("refs") or []
    assert any(r.get("kind") == "arxiv" and r.get("id") == "2512.10942" for r in refs)
    assert all(not m.get("path") for m in (atom.get("mentions") or []))
    capsys.readouterr()
    _run(root, "check")
    assert "check 1/1 PASS" in capsys.readouterr().out


def test_pack_cli_arxiv_at_becomes_ref_not_mention_kind(tmp_path, capsys):
    root = tmp_path / ".coherence"
    _run(
        root,
        "pack",
        "--title",
        "CLI arxiv locator",
        "--constraint",
        "fact",
        "--atom",
        "VL-JEPA predicts continuous embeddings of target texts rather than tokens.",
        "--mention",
        "VL-JEPA:work",
        "--at",
        "arxiv:2512.10942",
    )
    store = _load(root / "topics" / "cli-arxiv-locator" / "atoms.json")
    atom = store["atoms"][0]
    mentions = atom.get("mentions") or []
    assert mentions and mentions[0].get("kind") == "work"
    assert mentions[0].get("name") == "VL-JEPA"
    assert "path" not in (mentions[0] or {})
    refs = atom.get("refs") or []
    assert any(r.get("kind") == "arxiv" and r.get("id") == "2512.10942" for r in refs)
    capsys.readouterr()
    _run(root, "check")
    assert "check 1/1 PASS" in capsys.readouterr().out


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
    with pytest.raises(SystemExit) as exc:
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
    assert exc.value.code == 1
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
    assert "still hold" in out or "stand alone" in out or "JOIN" in out
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
        "--constraint",
        "fact",
        "--atom",
        "A packet is a small subset of atoms maximizing coverage.",
        "--mention",
        "packet:concept",
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
        "--mention",
        "packet:concept",
        "--atom",
        "Mentions hang on a claim, not a second graph.",
        "--mention",
        "mention:concept",
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
    _run(
        root,
        "pack",
        "--title",
        "Alpha theme",
        "--constraint",
        "fact",
        "--atom",
        "Durable packet claim one.",
        "--mention",
        "packet:concept",
    )
    _run(
        root,
        "pack",
        "--title",
        "Beta theme",
        "--constraint",
        "fact",
        "--atom",
        "Durable packet claim two.",
        "--mention",
        "packet:concept",
    )
    capsys.readouterr()
    _run(root, "cache", "durable packet claim")
    out = capsys.readouterr().out
    assert "CACHE HIT" in out
    assert "alpha-theme" in out
    assert "beta-theme" in out


def test_cache_rewrites_only_top_topic_packet(tmp_path, capsys):
    root = tmp_path / ".coherence"
    _run(
        root,
        "pack",
        "--title",
        "JEPA language",
        "--constraint",
        "fact",
        "--atom",
        "VL-JEPA predicts continuous embeddings of target texts rather than tokens.",
        "--mention",
        "VL-JEPA:work",
    )
    _run(
        root,
        "pack",
        "--title",
        "Share language",
        "--constraint",
        "fact",
        "--atom",
        "Share language is atoms and packets, not transcripts.",
        "--mention",
        "packet:concept",
    )
    other = root / "topics" / "share-language" / "packet.json"
    before = other.read_text(encoding="utf-8")
    capsys.readouterr()
    _run(root, "cache", "VL-JEPA embeddings language")
    out = capsys.readouterr().out
    assert "jepa-language" in out
    assert "wrote" in out
    assert "share-language" in out
    assert "listed only" in out
    assert other.read_text(encoding="utf-8") == before
    top_pkt = json.loads(
        (root / "topics" / "jepa-language" / "packet.json").read_text(encoding="utf-8")
    )
    assert top_pkt.get("query") == "VL-JEPA embeddings language"


def test_cache_miss_points_at_ingest(tmp_path, capsys):
    root = tmp_path / ".coherence"
    _run(root, "cache", "anything")
    out = capsys.readouterr().out
    assert "CACHE MISS" in out
    assert "pack --title" in out
