"""Atom provenance + review helpers."""

import pytest

from coherence_cache.atoms import (
    REVIEW_ACCEPTED,
    REVIEW_PENDING,
    REVIEW_REJECTED,
    active_atoms,
    atom_text,
    back_out,
    is_active,
    make_atom,
    normalize_store_atoms,
    parse_minted_list,
    set_review,
)


def test_make_and_review_cycle():
    a = make_atom("Durable claim about packets.", method="mlx_mint", model="test")
    assert atom_text(a) == "Durable claim about packets."
    assert a["review"]["status"] == REVIEW_PENDING
    a2 = set_review(a, REVIEW_ACCEPTED, notes="looks good")
    assert a2["review"]["status"] == REVIEW_ACCEPTED
    a3 = set_review(a2, REVIEW_ACCEPTED, text="Durable claim about packets (edited).")
    assert a3["review"]["status"] == "edited"
    assert "edited" in atom_text(a3)


def test_rejected_excluded_from_active():
    store = {
        "atoms": [
            make_atom("keep me", review_status=REVIEW_ACCEPTED),
            make_atom("drop me", review_status=REVIEW_REJECTED),
            "legacy string still active",
        ]
    }
    act = active_atoms(store)
    assert len(act) == 2
    assert atom_text(act[0]) == "keep me"


def test_normalize_upgrades_strings():
    store = normalize_store_atoms({"atoms": ["plain claim one"]})
    assert isinstance(store["atoms"][0], dict)
    assert store["atoms"][0]["review"]["status"] == REVIEW_ACCEPTED


def test_parse_minted_json():
    raw = 'Here you go:\n["Alpha is a durable claim.", "Beta supports alpha."]\n'
    got = parse_minted_list(raw)
    assert len(got) == 2
    assert "Alpha" in got[0]


def test_back_out_accepted_atom_keeps_text_and_records_why():
    """An accepted atom that failed its possibility/impossibility claim can be retracted."""
    claim = "Perpetual motion of the second kind is possible in a closed cycle."
    atom = make_atom(claim, review_status=REVIEW_ACCEPTED)
    out = back_out(
        atom,
        reason="claimed possibility does not hold: the task is impossible",
    )
    assert atom_text(out) == claim
    assert out["review"]["status"] == REVIEW_REJECTED
    assert out["review"]["previous_status"] == REVIEW_ACCEPTED
    assert out["review"]["backed_out"] is True
    assert "does not hold" in out["review"]["notes"]
    assert out["review"]["reviewed_at"]
    assert is_active(out) is False


def test_back_out_requires_reason():
    atom = make_atom("Ill-defined constraint.", review_status=REVIEW_ACCEPTED)
    with pytest.raises(ValueError, match="reason"):
        back_out(atom, reason="  ")


def test_back_out_does_not_shift_store_indices():
    store = {
        "atoms": [
            make_atom("Keep A — constructors exist for task T.", review_status=REVIEW_ACCEPTED),
            make_atom("Bad B — ill-defined impossibility.", review_status=REVIEW_ACCEPTED),
            make_atom("Keep C — task U is possible.", review_status=REVIEW_ACCEPTED),
        ]
    }
    store["atoms"][1] = back_out(
        store["atoms"][1],
        reason="atom was not defined correctly; no actual impossibility created",
    )
    assert len(store["atoms"]) == 3
    assert atom_text(store["atoms"][0]).startswith("Keep A")
    assert atom_text(store["atoms"][2]).startswith("Keep C")
    act = active_atoms(store)
    assert len(act) == 2
    assert [atom_text(a) for a in act] == [
        atom_text(store["atoms"][0]),
        atom_text(store["atoms"][2]),
    ]
