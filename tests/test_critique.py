"""Critique parse + apply gates (no MLX)."""

from coherence_cache.config import CoherenceConfig
from coherence_cache.critique import (
    apply_proposals,
    parse_critique_batch,
)
from coherence_cache.atoms import REVIEW_PENDING, atom_review_status, make_atom


CFG = CoherenceConfig(
    critique_accept_min_conf=0.8,
    critique_reject_min_conf=0.75,
    critique_edit_min_conf=0.85,
    critique_min_grounding=0.55,
)


def test_parse_critique_batch():
    raw = """[
      {"i": 0, "action": "accept", "confidence": 0.9, "text": "A", "reason": "ok"},
      {"i": 1, "action": "reject", "confidence": 0.95, "reason": "invented"},
      {"i": 2, "action": "nope", "confidence": 1.0}
    ]"""
    got = parse_critique_batch(raw, cfg=CFG)
    assert [p.action for p in got] == ["accept", "reject"]
    assert got[0].confidence == 0.9


def test_apply_gates_dict_dispatch():
    store = {
        "atoms": [
            make_atom("Interest surfaces are intentional.", review_status=REVIEW_PENDING),
            make_atom("Invented nonsense about Mars.", review_status=REVIEW_PENDING),
            make_atom("Almost good claim.", review_status=REVIEW_PENDING),
        ]
    }
    proposals = [
        {
            "i": 0,
            "action": "accept",
            "confidence": 0.91,
            "grounding": 0.9,
            "text": "Interest surfaces are intentional.",
            "reason": "solid",
        },
        {
            "i": 1,
            "action": "reject",
            "confidence": 0.9,
            "grounding": 0.1,
            "text": "Invented nonsense about Mars.",
            "reason": "ungrounded",
        },
        {
            "i": 2,
            "action": "edit",
            "confidence": 0.95,
            "grounding": 0.9,
            "text": "Almost good claim (cleaner).",
            "reason": "tighten",
        },
    ]
    # Without apply_edits: accept+reject apply, edit stays proposed_only
    result = apply_proposals(store, proposals, cfg=CFG, apply_edits=False)
    atoms = result["store"]["atoms"]
    assert atom_review_status(atoms[0]) == "accepted"
    assert atom_review_status(atoms[1]) == "rejected"
    assert atom_review_status(atoms[2]) == "pending"
    assert atoms[2]["review"]["critique"]["action"] == "edit"
    assert result["applied"] == {
        "accepted": 1,
        "edited": 0,
        "rejected": 1,
        "proposed_only": 1,
    }

    # With apply_edits: edit applies too
    store2 = {
        "atoms": [
            make_atom("Almost good claim.", review_status=REVIEW_PENDING),
        ]
    }
    result2 = apply_proposals(
        store2,
        [
            {
                "i": 0,
                "action": "edit",
                "confidence": 0.95,
                "grounding": 0.9,
                "text": "Almost good claim (cleaner).",
                "reason": "tighten",
            }
        ],
        cfg=CFG,
        apply_edits=True,
    )
    assert atom_review_status(result2["store"]["atoms"][0]) == "edited"
    assert result2["applied"]["edited"] == 1


def test_attach_only_never_changes_status():
    store = {
        "atoms": [make_atom("Keep pending.", review_status=REVIEW_PENDING)]
    }
    result = apply_proposals(
        store,
        [
            {
                "i": 0,
                "action": "accept",
                "confidence": 0.99,
                "grounding": 1.0,
                "text": "Keep pending.",
                "reason": "would accept",
            }
        ],
        cfg=CFG,
        attach_only=True,
    )
    assert atom_review_status(result["store"]["atoms"][0]) == "pending"
    assert result["applied"]["proposed_only"] == 1
