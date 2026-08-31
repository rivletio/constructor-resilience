"""Edge cases for intersect / union / belief challenges."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence_cache import paths
from coherence_cache.atoms import make_atom
from coherence_cache.check import (
    check_text,
    format_overlap_check,
    overlap_unresolved_count,
)
from coherence_cache.cli import main
from coherence_cache.intersection import (
    MENTION_JOIN_AFFINITY,
    claims_tension,
    compare_overlap,
    content_affinity,
    cross_affinity,
    intersection_packet,
)
from coherence_cache.mentions import MENTION_GROUND_MIN, join_grounding, mention_grounding
from coherence_cache.search import as_text


def _texts(doc) -> list[str]:
    return [as_text(a) for a in doc.get("atoms") or []]


def _blob(doc) -> str:
    return " ".join(_texts(doc)).lower()


@pytest.fixture(autouse=True)
def _reset_root():
    paths._ROOT = None
    yield
    paths._ROOT = None


def _run(root: Path, *argv: str) -> None:
    main(["--root", str(root), *argv])


def test_intersection_empty_when_other_side_empty():
    mine = {"atoms": ["Packets are the share unit, not transcripts."]}
    assert intersection_packet(mine, {"atoms": []})["atoms"] == []
    assert intersection_packet({"atoms": []}, mine)["atoms"] == []
    assert intersection_packet({"atoms": []}, {"atoms": []})["atoms"] == []


def test_union_with_empty_other_keeps_mine():
    mine = {"atoms": ["Packets are the share unit, not transcripts."]}
    uni = intersection_packet(mine, {"atoms": []}, require_cross=False)
    assert uni["kind"] == "interest_union"
    assert _texts(uni) == mine["atoms"]
    assert uni["challenges"]
    assert uni["challenges"][0]["other"] is None


def test_identical_text_keeps_both_provenances():
    same = "Packets are the share unit, not transcripts."
    doc = intersection_packet({"atoms": [same]}, {"atoms": [same]})
    sources = [p["source"] for p in doc["provenance"]]
    assert sources == ["mine", "theirs"]
    assert {p["store_index"] for p in doc["provenance"]} == {0}
    assert {c["source"] for c in doc["challenges"]} == {"mine", "theirs"}


def test_rejected_atoms_excluded_even_if_they_would_match():
    mine = {
        "atoms": [
            make_atom(
                "JEPA predicts in latent space rather than tokens.",
                mentions=[{"name": "JEPA", "kind": "concept"}],
                review_status="rejected",
            ),
            make_atom(
                "Packets are the share unit, not transcripts.",
                mentions=[{"name": "packet", "kind": "concept"}],
            ),
        ]
    }
    theirs = {
        "atoms": [
            make_atom(
                "V-JEPA extends the same objective to video.",
                mentions=[{"name": "JEPA", "kind": "concept"}],
            )
        ]
    }
    doc = intersection_packet(mine, theirs)
    blob = _blob(doc)
    assert "jepa" not in blob
    assert doc["n_mine"] == 1


def test_blank_atoms_skipped_in_union():
    uni = intersection_packet(
        {"atoms": ["", "   "]},
        {"atoms": ["Packets are the share unit, not transcripts."]},
        require_cross=False,
    )
    assert "" not in _texts(uni)
    assert all(t.strip() for t in _texts(uni))


def test_seed_query_does_not_fill_one_sided_intersection():
    mine = {"atoms": ["Refs are citations extracted from claim text."]}
    theirs = {
        "atoms": ["Interest in consciousness, AI, and the nature of understanding."]
    }
    doc = intersection_packet(mine, theirs, seed_query="citations")
    assert doc["atoms"] == []


def test_possible_vs_impossible_is_tension():
    a = "Task T is possible under the stated constraints."
    b = "Task T is impossible under the stated constraints."
    assert claims_tension(a, b)
    doc = intersection_packet({"atoms": [a]}, {"atoms": [b]})
    assert doc["challenges"]
    assert any(c.get("tension") for c in doc["challenges"])
    assert "conflict" in " ".join(c["prompt"] for c in doc["challenges"])
    printed = format_overlap_check(doc)
    assert "TENSION" in printed


def test_content_overlap_is_support_not_collapsed_join():
    a = "JEPA predicts in latent space rather than tokens."
    b = "JEPA predicts in latent space rather than pixels."
    doc = intersection_packet({"atoms": [a]}, {"atoms": [b]})
    kinds = {c.get("kind") for c in doc["challenges"] if c.get("other")}
    assert "support" in kinds
    assert "join" not in kinds


def test_all_contradictors_are_emitted():
    mine = {"atoms": ["JEPA predicts in latent space rather than tokens."]}
    theirs = {
        "atoms": [
            "JEPA predicts in latent space rather than pixels.",
            "JEPA does not predict in latent space at all.",
            "JEPA never predicts in latent space.",
        ]
    }
    doc = intersection_packet(mine, theirs)
    mine_ten = [
        c
        for c in doc["challenges"]
        if c["source"] == "mine" and (c.get("tension") or c.get("kind") == "tension")
    ]
    others = [c.get("other") or "" for c in mine_ten]
    assert any("does not" in o for o in others)
    assert any("never" in o for o in others)
    assert overlap_unresolved_count(doc) >= 2


def test_mention_grounding_score():
    assert mention_grounding("JEPA", "JEPA predicts in latent space rather than tokens.") == 1.0
    assert mention_grounding("JEPA", "V-JEPA extends the same objective to video.") == 1.0
    assert mention_grounding("packet", "Packets are the share unit, not transcripts.") >= 0.5
    assert mention_grounding("world models", "I care about world models and latent prediction.") == 1.0
    assert mention_grounding("AI", "Public talks explore AI and understanding.") == 1.0
    assert mention_grounding("AI", "mainly at dusk and dawn.") == 0.0
    assert mention_grounding("JEPA", "Domestic cats hunt primarily at dusk and dawn.") == 0.0
    assert mention_grounding("JEPA", "Domestic cats hunt primarily at dusk and dawn.") < MENTION_GROUND_MIN
    # Counterfactual: name as initials of a title-case phrase, not the string.
    assert mention_grounding(
        "JEPA",
        "Joint Embedding Predictive Architecture predicts in latent space rather than tokens.",
    ) == 1.0
    # Anaphora is not attestation (claim is not stand-alone).
    assert mention_grounding("JEPA", "It predicts in latent space rather than tokens.") == 0.0
    # Alias in the claim counts as the name.
    assert mention_grounding(
        "JEPA",
        "The joint embedding predictive architecture predicts in latent space.",
        aliases=["joint embedding predictive architecture"],
    ) == 1.0
    # Locator-style claim without the name is still ungrounded.
    assert mention_grounding("JEPA", "See the original talk at t=3033 for the claim.") == 0.0


def test_ungrounded_mention_fails_check():
    from coherence_cache.check import check_atom

    bad = {
        "text": "Domestic cats hunt primarily at dusk and dawn.",
        "constraint": "fact",
        "mentions": [{"name": "JEPA", "kind": "concept"}],
    }
    fails = check_atom(bad)
    assert any("not attested" in f and "drop the join" in f for f in fails)
    ok = {
        "text": "JEPA predicts in latent space rather than tokens.",
        "constraint": "fact",
        "mentions": [{"name": "JEPA", "kind": "concept"}],
    }
    assert not any("not attested" in f or f.startswith("anaphor") for f in check_atom(ok))
    path_only = {
        "text": "JEPA predicts in latent space rather than tokens.",
        "constraint": "fact",
        "mentions": [{"name": "JEPA", "kind": "concept"}],
        "at": {"path": "notes.md"},
    }
    assert any("claim has path but no line" in f for f in check_atom(path_only))


def test_anaphor_with_mention_on_atom_passes():
    from coherence_cache.check import check_atom

    atom = {
        "text": "It predicts in latent space rather than tokens.",
        "constraint": "fact",
        "mentions": [{"name": "JEPA", "kind": "concept"}],
    }
    assert check_atom(atom) == []
    dummy = {
        "text": "It is important to pack stand-alone claims about packets.",
        "constraint": "fact",
        "mentions": [{"name": "JEPA", "kind": "concept"}],
    }
    dfails = check_atom(dummy)
    assert any("not attested" in f for f in dfails)


def test_garbage_mention_does_not_create_overlap():
    mine = {
        "atoms": [
            make_atom(
                "Domestic cats hunt primarily at dusk and dawn.",
                mentions=[{"name": "JEPA", "kind": "concept"}],
            )
        ]
    }
    theirs = {
        "atoms": [
            make_atom(
                "Public talks explore consciousness and understanding.",
                mentions=[{"name": "JEPA", "kind": "concept"}],
            )
        ]
    }
    assert mention_grounding("JEPA", mine["atoms"][0]["text"]) < MENTION_GROUND_MIN
    assert join_grounding(mine["atoms"][0], theirs["atoms"][0]) < MENTION_GROUND_MIN
    doc = intersection_packet(mine, theirs)
    assert doc["atoms"] == []


def test_grounded_mention_join_survives_thin_content():
    mine = {
        "atoms": [
            make_atom(
                "JEPA predicts in latent space rather than tokens.",
                mentions=[{"name": "JEPA", "kind": "concept"}],
            )
        ]
    }
    theirs = {
        "atoms": [
            make_atom(
                "V-JEPA extends the same objective to video.",
                mentions=[{"name": "JEPA", "kind": "concept"}],
            )
        ]
    }
    assert join_grounding(mine["atoms"][0], theirs["atoms"][0]) >= MENTION_GROUND_MIN
    doc = intersection_packet(mine, theirs)
    assert doc["atoms"]
    paired = [c for c in doc["challenges"] if c.get("other")]
    assert paired
    assert paired[0]["affinity"] >= 0.18
    assert paired[0].get("grounding", 0) >= MENTION_GROUND_MIN
    assert paired[0].get("kind") in {"join", "support", "tension"}
    assert paired[0].get("kind") == "join" or content_affinity(
        mine["atoms"][0], theirs["atoms"][0]
    ) >= 0.18


def test_stopwords_do_not_fabricate_overlap():
    mine = {"atoms": ["The packet is the share unit of the store."]}
    theirs = {"atoms": ["The nature of the talk is the public store."]}
    assert cross_affinity(mine["atoms"][0], theirs["atoms"][0]) < 0.18
    doc = intersection_packet(mine, theirs)
    assert doc["atoms"] == []


def test_cjk_sentence_is_not_too_short():
    text = "日本語の主張はトークン集合が空になる。"
    assert "too short" not in check_text(text)
    assert "too short" in check_text("hi")
    uni = intersection_packet(
        {"atoms": [text]},
        {"atoms": ["別の日本語の文章で交差しないはずです。"]},
        require_cross=False,
    )
    assert uni["atoms"]
    assert "too short" not in format_overlap_check(uni)


def test_max_size_one_still_challenges_the_other_surface():
    a = "JEPA predicts in latent space rather than tokens."
    b = "JEPA does not predict in latent space at all."
    doc = intersection_packet({"atoms": [a]}, {"atoms": [b]}, max_size=1)
    assert len(doc["atoms"]) == 1
    assert doc["challenges"]
    ch = doc["challenges"][0]
    assert ch.get("other")
    assert ch.get("tension")


def test_max_size_zero_is_empty_not_crash():
    same = "Packets are the share unit, not transcripts."
    doc = intersection_packet(
        {"atoms": [same]}, {"atoms": [same]}, max_size=0
    )
    assert doc["atoms"] == []
    assert doc["challenges"] == []


def test_none_atoms_key_does_not_crash():
    doc = intersection_packet({}, {"atoms": None})
    assert doc["atoms"] == []


def test_check_packet_missing_file(tmp_path):
    root = tmp_path / ".coherence"
    _run(root, "create", "--title", "Empty Topic", "--use")
    with pytest.raises(SystemExit, match="Missing packet"):
        _run(root, "check", "--packet", str(tmp_path / "nope.json"))


def test_check_packet_on_atoms_json_uses_store_check(tmp_path, capsys):
    root = tmp_path / ".coherence"
    _run(
        root,
        "pack",
        "--title",
        "Bare Pack",
        "--constraint",
        "fact",
        "--atom",
        "Packets are the share unit, not transcripts.",
    )
    capsys.readouterr()
    atoms = root / "topics" / "bare-pack" / "atoms.json"
    with pytest.raises(SystemExit) as exc:
        _run(root, "check", "--packet", str(atoms))
    assert exc.value.code == 1
    assert "missing mentions" in capsys.readouterr().out


def test_self_intersect_challenges_other_atoms_not_clone():
    store = {
        "atoms": [
            "JEPA predicts in latent space rather than tokens.",
            "JEPA does not predict in latent space at all.",
            "Packets are the share unit, not transcripts.",
        ]
    }
    doc = intersection_packet(store, store, max_size=6)
    mine_pred = [
        c
        for c in doc["challenges"]
        if c["source"] == "mine" and "predicts in latent" in (c.get("text") or "")
    ]
    others = [c.get("other") or "" for c in mine_pred]
    assert any("does not" in o for o in others)
    assert not any(o.strip() == mine_pred[0]["text"].strip() for o in others if o)


def test_reconstruct_compare_against_previous():
    a = "JEPA predicts in latent space rather than tokens."
    b = "JEPA does not predict in latent space at all."
    old = intersection_packet({"atoms": [a, b]}, {"atoms": [a, b]}, max_size=4)
    new = intersection_packet({"atoms": [a]}, {"atoms": [a]}, max_size=4)
    cmp = compare_overlap(old, new)
    assert not cmp["fixed_point"]
    assert any("does not" in t for t in cmp["dropped"])
    assert cmp["tension_after"] < cmp["tension_before"]
    same = compare_overlap(new, new)
    assert same["fixed_point"]


def test_intersect_topic_with_itself(tmp_path, capsys):
    root = tmp_path / ".coherence"
    _run(
        root,
        "pack",
        "--title",
        "Self Surface",
        "--constraint",
        "fact",
        "--atom",
        "Packets are the share unit, not transcripts.",
        "--mention",
        "packet:concept",
    )
    outp = tmp_path / "self.json"
    capsys.readouterr()
    _run(root, "intersect", "self-surface", "self-surface", "--out", str(outp))
    doc = json.loads(outp.read_text(encoding="utf-8"))
    assert doc["atoms"]
    sources = {p["source"] for p in doc["provenance"]}
    assert sources == {"mine", "theirs"}

    # reconstruct and compare: same packet is a fixed point
    capsys.readouterr()
    _run(
        root,
        "intersect",
        "self-surface",
        "self-surface",
        "--out",
        str(tmp_path / "self2.json"),
        "--against",
        str(outp),
    )
    against_out = capsys.readouterr().out.lower()
    assert "matches previous" in against_out


def test_shared_work_name_is_join_not_paraphrase():
    """Two facts about the same paper must both survive an overlap packet."""
    paper = "Attention Is All You Need"
    mine = make_atom(
        "Attention Is All You Need introduced scaled dot-product attention.",
        mentions=[{"name": paper, "kind": "work"}],
        review_status="accepted",
    )
    theirs = make_atom(
        "Attention Is All You Need reports 28.4 BLEU on WMT 2014 English-to-German.",
        mentions=[{"name": paper, "kind": "work"}],
        review_status="accepted",
    )
    aff = cross_affinity(mine, theirs)
    assert aff >= 0.18
    assert aff <= MENTION_JOIN_AFFINITY
    assert content_affinity(mine, theirs) < 0.85
    assert cross_affinity(mine, mine) == 1.0

    doc = intersection_packet({"atoms": [mine]}, {"atoms": [theirs]}, max_size=4)
    blob = " ".join(_texts(doc))
    assert "scaled dot-product" in blob
    assert "28.4" in blob
    assert len(doc["atoms"]) == 2
    for c in doc["challenges"]:
        if c.get("other"):
            assert c["affinity"] <= MENTION_JOIN_AFFINITY


def test_example_surfaces_intersect_without_collapsing_paper_facts():
    """Shipped examples prove ∩ without a host: distinct paper facts both keep."""
    root = Path(__file__).resolve().parents[1] / "examples"
    arxiv = json.loads(
        (root / "demo-arxiv-passage" / "atoms.json").read_text(encoding="utf-8")
    )
    notes = json.loads(
        (root / "demo-attention-notes" / "atoms.json").read_text(encoding="utf-8")
    )
    doc = intersection_packet(arxiv, notes, max_size=8)
    assert doc["atoms"]
    sources = {p["source"] for p in doc["provenance"]}
    assert sources == {"mine", "theirs"}
    assert len(doc["atoms"]) >= 2
    blob = _blob(doc)
    assert "transformer" in blob
    joins = [c for c in doc["challenges"] if c.get("kind") == "join"]
    assert len(joins) == len(doc["atoms"])
    # 3×3×2 cartesian was 18; one join per atom plus real support pairs
    assert len(doc["challenges"]) < 18
    mine_joins = [c for c in joins if c["source"] == "mine"]
    assert mine_joins
    assert all((c.get("n_other") or 0) >= 2 for c in mine_joins)
    shared = {n for c in joins for n in (c.get("shared") or [])}
    assert "transformer" in shared
    assert "the transformer" not in shared
    printed = format_overlap_check(doc)
    assert "JOIN" in printed
    assert "name joins" in printed
    for c in doc["challenges"]:
        if not c.get("other"):
            continue
        if c.get("kind") == "support":
            assert c["affinity"] < 0.85 or content_affinity(
                c.get("text") or "", c.get("other") or ""
            ) >= 0.85


def test_cli_import_examples_and_intersect(tmp_path, capsys):
    """The product path: import two example surfaces, intersect, both sides stay."""
    examples = Path(__file__).resolve().parents[1] / "examples"
    root = tmp_path / ".coherence"
    _run(
        root,
        "import",
        str(examples / "demo-arxiv-passage" / "atoms.json"),
        "--title",
        "arXiv Transformer",
        "--topic",
        "arxiv-transformer",
        "--accepted",
        "--use",
    )
    _run(
        root,
        "import",
        str(examples / "demo-attention-notes" / "atoms.json"),
        "--title",
        "Attention notes",
        "--topic",
        "attention-notes",
        "--accepted",
        "--use",
    )
    outp = tmp_path / "overlap.json"
    capsys.readouterr()
    _run(root, "intersect", "arxiv-transformer", "attention-notes", "--out", str(outp))
    doc = json.loads(outp.read_text(encoding="utf-8"))
    assert doc["kind"] == "interest_intersection"
    assert len(doc["atoms"]) >= 2
    sources = {p["source"] for p in doc["provenance"]}
    assert sources == {"mine", "theirs"}
    blob = _blob(doc)
    assert "transformer" in blob
    out = capsys.readouterr().out
    assert "challenges" in out.lower()
    assert "JOIN" in out
    assert "name joins" in out
    joins = [c for c in doc["challenges"] if c.get("kind") == "join"]
    assert len(joins) == len(doc["atoms"])
    assert len(doc["challenges"]) < 18
    assert all(isinstance(a, dict) and a.get("text") for a in doc["atoms"])
    assert any(a.get("mentions") for a in doc["atoms"])
    assert any(a.get("refs") for a in doc["atoms"])

    capsys.readouterr()
    _run(root, "check", "--packet", str(outp))
    cout = capsys.readouterr().out
    assert "interest_intersection" in cout
    assert "JOIN" in cout
    assert "missing constraint" not in cout
    assert "missing mentions" not in cout

    _run(
        root,
        "import",
        str(outp),
        "--title",
        "From overlap",
        "--topic",
        "from-overlap",
        "--accepted",
        "--use",
    )
    imported = json.loads(
        (root / "topics" / "from-overlap" / "atoms.json").read_text(encoding="utf-8")
    )
    assert any((a.get("mentions") or []) for a in imported["atoms"])
    assert any((a.get("refs") or []) for a in imported["atoms"])


def test_lookup_miss_and_empty_query_are_empty_hits():
    from coherence_cache.intersection import overlap_lookup

    atom = make_atom(
        "Packets are the share unit, not transcripts.",
        constraint="fact",
        mentions=[{"name": "packet", "kind": "concept"}],
        review_status="accepted",
    )
    miss = overlap_lookup({"atoms": [atom], "challenges": []}, "giraffe zebra")
    assert miss["hits"] == []
    assert miss["n_union"] == 1
    empty = overlap_lookup({"atoms": [atom], "challenges": []}, "")
    assert empty["n_hits"] == 0


def test_union_lookup_hits_polarity_and_question():
    from coherence_cache.atoms import REVIEW_PENDING
    from coherence_cache.check import format_overlap_lookup
    from coherence_cache.intersection import overlap_lookup, union_dataset

    mine = {
        "atoms": [
            make_atom(
                "The Transformer is a transduction model based solely on attention.",
                constraint="fact",
                mentions=[{"name": "Transformer", "kind": "concept"}],
                review_status="accepted",
            )
        ]
    }
    theirs = {
        "atoms": [
            make_atom(
                "The Transformer adds positional encodings because attention has no token order.",
                constraint="fact",
                mentions=[{"name": "Transformer", "kind": "concept"}],
                review_status="accepted",
            ),
            make_atom(
                "A masked Transformer decoder can be trained autoregressively on translation.",
                constraint="possibility",
                mentions=[{"name": "Transformer", "kind": "concept"}],
                review_status="accepted",
            ),
            make_atom(
                "Without positional encodings the Transformer cannot distinguish token order.",
                constraint="impossibility",
                mentions=[{"name": "Transformer", "kind": "concept"}],
                review_status="accepted",
            ),
            make_atom(
                "It is unclear whether eight heads are necessary for the BLEU gain.",
                constraint="possibility",
                mentions=[{"name": "Transformer", "kind": "concept"}],
                review_status=REVIEW_PENDING,
            ),
        ]
    }
    uni = union_dataset(mine, theirs)
    assert uni["kind"] == "interest_union"
    assert uni["n_mine"] + uni["n_theirs"] == 5
    assert len(uni["atoms"]) == 5

    lu = overlap_lookup(uni, "positional encodings")
    assert lu["kind"] == "overlap_lookup"
    assert lu["hits"]
    hit_blob = " ".join(as_text(h["atom"]) for h in lu["hits"]).lower()
    assert "positional" in hit_blob
    assert lu["hits"][0]["score"] >= lu["hits"][-1]["score"]
    assert lu["polarity"]
    pair = lu["polarity"][0]
    assert "masked" in as_text(pair["possible"]).lower()
    assert "cannot distinguish" in as_text(pair["impossible"]).lower()
    assert "transformer" in (pair.get("shared") or [])
    whys = {w for r in lu["question"] for w in r["why"]}
    assert "pending" in whys
    assert "possibility" in whys or "impossibility" in whys
    printed = format_overlap_lookup(lu)
    assert "LOOKUP" in printed
    assert "hits" in printed
    assert "polarity" in printed
    assert "question" in printed
    assert "positional" in printed.lower()


def test_cli_lookup_union_of_examples(tmp_path, capsys):
    examples = Path(__file__).resolve().parents[1] / "examples"
    root = tmp_path / ".coherence"
    _run(
        root,
        "import",
        str(examples / "demo-arxiv-passage" / "atoms.json"),
        "--title",
        "arXiv Transformer",
        "--topic",
        "arxiv-transformer",
        "--accepted",
        "--use",
    )
    _run(
        root,
        "import",
        str(examples / "demo-attention-notes" / "atoms.json"),
        "--title",
        "Attention notes",
        "--topic",
        "attention-notes",
        "--accepted",
        "--use",
    )
    capsys.readouterr()
    _run(
        root,
        "lookup",
        "positional encodings",
        "--mine",
        "arxiv-transformer",
        "--theirs",
        "attention-notes",
    )
    out = capsys.readouterr().out
    assert "LOOKUP" in out
    assert "positional" in out.lower()
    assert "polarity" in out
    assert "possible" in out.lower()
    assert "impossible" in out.lower()
    assert "question" in out

    uni = tmp_path / "u.json"
    capsys.readouterr()
    _run(
        root,
        "union",
        "arxiv-transformer",
        "attention-notes",
        "--out",
        str(uni),
        "--lookup",
        "positional encodings",
    )
    uout = capsys.readouterr().out
    assert "union" in uout
    assert "LOOKUP" in uout
    capsys.readouterr()
    _run(root, "cache", "positional encodings", "--packet", str(uni))
    cached = capsys.readouterr().out
    assert "LOOKUP" in cached
    assert "positional" in cached.lower()
