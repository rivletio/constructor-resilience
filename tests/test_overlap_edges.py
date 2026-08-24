"""Edge cases for intersect / union / belief challenges."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence_cache import paths
from coherence_cache.atoms import make_atom
from coherence_cache.check import check_text, format_overlap_check
from coherence_cache.cli import main
from coherence_cache.intersection import (
    claims_tension,
    cross_affinity,
    intersection_packet,
)


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


def test_challenge_prefers_contradictor_over_paraphrase():
    mine = {"atoms": ["JEPA predicts in latent space rather than tokens."]}
    theirs = {
        "atoms": [
            "JEPA predicts in latent space rather than pixels.",
            "JEPA does not predict in latent space at all.",
        ]
    }
    doc = intersection_packet(mine, theirs)
    mine_ch = next(c for c in doc["challenges"] if c["source"] == "mine")
    assert mine_ch.get("tension")
    assert "does not" in (mine_ch.get("other") or "")


def test_mention_join_survives_into_challenges():
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
    doc = intersection_packet(mine, theirs)
    assert doc["atoms"]
    paired = [c for c in doc["challenges"] if c.get("other")]
    assert paired
    assert paired[0]["affinity"] >= 0.18


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
