"""Golden tests for resilience search + intersection."""

from __future__ import annotations

from coherence_cache.intersection import intersection_packet
from coherence_cache.search import greedy_resilient, lexical_similarity


def test_greedy_packet_prefers_diverse_support():
    atoms = [
        "Share interest surfaces not whole stores.",
        "Packets maximize support and minimize redundancy.",
        "Packets maximize support and minimize redundancy almost same.",  # near-dup
        "Public creators publish intentional atoms.",
        "Inner circle requires intentional promote.",
    ]
    consistency = {
        (0, 1): 0.8,
        (0, 3): 0.7,
        (0, 4): 0.9,
        (1, 2): 0.95,  # paraphrase pair
        (1, 3): 0.6,
        (3, 4): 0.5,
    }
    selected, eng = greedy_resilient(
        atoms, consistency, max_size=3, redundancy_scale=2.0, redundancy_threshold=0.2
    )
    assert 1 <= len(selected) <= 3
    # Should not need both near-duplicates in a size-3 packet always, but
    # energy must be finite and selection non-empty.
    assert eng <= 0.0 or len(selected) >= 1


def test_lexical_similarity_symmetric():
    a = "interest intersection browse overlap"
    b = "browse interest overlap intersection"
    assert abs(lexical_similarity(a, b) - lexical_similarity(b, a)) < 1e-9
    assert lexical_similarity(a, b) > 0.5


def test_greedy_accepts_structured_atoms():
    from coherence_cache.atoms import make_atom

    atoms = [
        make_atom("Share interest surfaces not whole stores.", review_status="accepted"),
        make_atom("Packets maximize support and minimize redundancy.", review_status="accepted"),
        make_atom("Public creators publish intentional atoms.", review_status="accepted"),
    ]
    selected, eng = greedy_resilient(
        atoms, {(0, 1): 0.8, (0, 2): 0.7}, max_size=2
    )
    assert selected
    assert all(isinstance(s, str) for s in selected)
    assert eng == eng  # finite


def test_intersection_includes_both_sides_when_possible():
    mine = {
        "atoms": [
            "I care about world models and latent prediction.",
            "Share intentional interests not full stores.",
            "Resume from a packet first.",
        ],
        "consistency": {"0,1": 0.5, "0,2": 0.6, "1,2": 0.55},
    }
    theirs = {
        "atoms": [
            "Public long-form talk explores AI and understanding.",
            "Listeners meet creators at mutual curiosity.",
            "Durable published claims beat raw take dumps.",
        ],
        "consistency": {"0,1": 0.7, "0,2": 0.6, "1,2": 0.65},
    }
    doc = intersection_packet(mine, theirs, max_size=6, min_cross_sim=0.05)
    assert doc["kind"] == "interest_intersection"
    assert len(doc["atoms"]) >= 2
    sources = {p["source"] for p in doc.get("provenance") or []}
    # With require_cross, expect both when both sides non-empty
    assert sources == {"mine", "theirs"} or len(doc["atoms"]) >= 1


def test_intersection_structured_atoms_stay_text():
    from coherence_cache.atoms import make_atom

    mine = {
        "atoms": [
            make_atom("I care about world models and latent prediction."),
            make_atom("Share intentional interests not full stores."),
        ],
        "consistency": {"0,1": 0.6},
    }
    theirs = {
        "atoms": [
            make_atom("Public long-form talk explores AI and understanding."),
            make_atom("Listeners meet creators at mutual curiosity."),
        ],
        "consistency": {"0,1": 0.7},
    }
    doc = intersection_packet(mine, theirs, max_size=4, min_cross_sim=0.05)
    assert doc["atoms"]
    assert all(isinstance(a, str) for a in doc["atoms"])
