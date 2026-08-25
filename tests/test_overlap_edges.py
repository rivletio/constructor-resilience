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
    claims_tension,
    compare_overlap,
    cross_affinity,
    intersection_packet,
)
from coherence_cache.mentions import MENTION_GROUND_MIN, join_grounding, mention_grounding


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
    assert uni["atoms"] == mine["atoms"]
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
    blob = " ".join(doc["atoms"]).lower()
    assert "jepa" not in blob
    assert doc["n_mine"] == 1


def test_blank_atoms_skipped_in_union():
    uni = intersection_packet(
        {"atoms": ["", "   "]},
        {"atoms": ["Packets are the share unit, not transcripts."]},
        require_cross=False,
    )
    assert "" not in uni["atoms"]
    assert all(a.strip() for a in uni["atoms"])


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


def test_ungrounded_mention_fails_check():
    from coherence_cache.check import check_atom

    bad = {
        "text": "Domestic cats hunt primarily at dusk and dawn.",
        "constraint": "fact",
        "mentions": [{"name": "JEPA", "kind": "concept"}],
    }
    fails = check_atom(bad)
    assert any("not grounded" in f for f in fails)
    ok = {
        "text": "JEPA predicts in latent space rather than tokens.",
        "constraint": "fact",
        "mentions": [{"name": "JEPA", "kind": "concept"}],
    }
    assert not any("not grounded" in f for f in check_atom(ok))


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
    assert paired[0].get("kind") in {"support", "tension"}


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
