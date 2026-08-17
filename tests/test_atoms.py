"""Atom provenance + review helpers."""

from coherence_cache.atoms import (
    REVIEW_ACCEPTED,
    REVIEW_PENDING,
    REVIEW_REJECTED,
    active_atoms,
    atom_text,
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
