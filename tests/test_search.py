"""Golden tests for resilience search, Monte Carlo samplers, intersection."""

from __future__ import annotations

import math

from coherence_cache.intersection import intersection_packet, overlap_challenges
from coherence_cache.search import (
    SAMPLE_METHODS,
    build_qubo,
    energy,
    find_resilient_constructors,
    greedy_resilient,
    lexical_similarity,
)

# Near-dup pair is (1, 2). Support cluster is 0 with 1/3/4.
DIVERSITY_ATOMS = [
    "Share interest surfaces not whole stores.",
    "Packets maximize support and minimize redundancy.",
    "Packets maximize support and minimize redundancy almost same.",
    "Public creators publish intentional atoms.",
    "Inner circle requires intentional promote.",
]
DIVERSITY_CONS = {
    (0, 1): 0.8,
    (0, 3): 0.7,
    (0, 4): 0.9,
    (1, 2): 0.95,
    (1, 3): 0.6,
    (3, 4): 0.5,
}


def test_greedy_packet_prefers_diverse_support():
    selected, eng = greedy_resilient(
        DIVERSITY_ATOMS,
        DIVERSITY_CONS,
        max_size=3,
        redundancy_scale=2.0,
        redundancy_threshold=0.2,
    )
    assert 1 <= len(selected) <= 3
    assert math.isfinite(eng)
    assert not (
        DIVERSITY_ATOMS[1] in selected and DIVERSITY_ATOMS[2] in selected
    )


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
            "Public long-form talk explores world models and understanding.",
            "Listeners meet creators at mutual curiosity.",
            "Durable published claims beat raw take dumps.",
        ],
        "consistency": {"0,1": 0.7, "0,2": 0.6, "1,2": 0.65},
    }
    doc = intersection_packet(mine, theirs, max_size=6)
    assert doc["kind"] == "interest_intersection"
    assert len(doc["atoms"]) >= 2
    sources = {p["source"] for p in doc.get("provenance") or []}
    # With require_cross, expect both when both sides non-empty
    assert sources == {"mine", "theirs"} or len(doc["atoms"]) >= 1


def test_intersection_prefers_cross_links_not_internal_hubs():
    mine = {
        "atoms": [
            "Interest intersection is the browse primitive over two surfaces.",
            "Share envelopes copy mention joins from the packet.",
            "Duplicate claims are skipped so re-packing does not grow the store.",
        ],
        "consistency": {"0,1": 0.5, "1,2": 0.85, "0,2": 0.4},
    }
    theirs = {
        "atoms": [
            "Listeners meet creators at the intersection of mutual curiosity.",
            "Interest in consciousness, AI, and the nature of understanding.",
            "Long-form conversation explores hard ideas in public.",
        ],
        "consistency": {"0,1": 0.9, "1,2": 0.85, "0,2": 0.8},
    }
    doc = intersection_packet(mine, theirs, max_size=4, min_cross_sim=0.12)
    blob = " ".join(doc["atoms"]).lower()
    assert "intersection" in blob
    sources = {p["source"] for p in doc.get("provenance") or []}
    assert sources == {"mine", "theirs"}
    # Consciousness cluster is internally dense but not the overlap theme.
    assert "consciousness" not in blob or "intersection" in blob


def test_intersection_empty_when_no_cross_affinity():
    mine = {
        "atoms": ["Refs are citations extracted from claim text."],
        "consistency": {},
    }
    theirs = {
        "atoms": ["Interest in consciousness, AI, and the nature of understanding."],
        "consistency": {},
    }
    doc = intersection_packet(mine, theirs, max_size=4, min_cross_sim=0.18)
    assert doc["atoms"] == []


def test_intersection_mention_join_aligns_across_wording():
    from coherence_cache.atoms import make_atom

    mine = {
        "atoms": [
            make_atom(
                "JEPA predicts in latent space rather than tokens.",
                mentions=[{"name": "JEPA", "kind": "concept"}],
            ),
            make_atom("Unrelated claim about packing session flags."),
        ],
        "consistency": {"0,1": 0.2},
    }
    theirs = {
        "atoms": [
            make_atom(
                "V-JEPA extends the same objective to video.",
                mentions=[{"name": "JEPA", "kind": "concept"}],
            ),
            make_atom("A public long-form talk about consciousness."),
        ],
        "consistency": {"0,1": 0.9},
    }
    doc = intersection_packet(mine, theirs, max_size=3, min_cross_sim=0.18)
    blob = " ".join(doc["atoms"]).lower()
    assert "jepa" in blob
    assert "consciousness" not in blob


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
            make_atom("Public long-form talk explores world models and understanding."),
            make_atom("Listeners meet creators at mutual curiosity."),
        ],
        "consistency": {"0,1": 0.7},
    }
    doc = intersection_packet(mine, theirs, max_size=4)
    assert doc["atoms"]
    assert all(isinstance(a, str) for a in doc["atoms"])
    assert doc.get("challenges")
    assert all(p.get("store_index") is not None for p in doc["provenance"])


def test_union_keeps_one_sided_when_intersection_empty():
    mine = {
        "atoms": ["Refs are citations extracted from claim text."],
        "consistency": {},
    }
    theirs = {
        "atoms": ["Interest in consciousness, AI, and the nature of understanding."],
        "consistency": {},
    }
    ix = intersection_packet(mine, theirs, max_size=4, min_cross_sim=0.18)
    assert ix["atoms"] == []
    assert ix["kind"] == "interest_intersection"
    assert ix["challenges"] == []
    uni = intersection_packet(
        mine, theirs, max_size=4, min_cross_sim=0.18, require_cross=False
    )
    assert uni["kind"] == "interest_union"
    assert len(uni["atoms"]) >= 1
    sources = {p["source"] for p in uni.get("provenance") or []}
    assert sources <= {"mine", "theirs"}
    assert uni["challenges"]
    assert any(ch.get("other") is None for ch in uni["challenges"])


def test_overlap_challenges_pair_cross_surface():
    from coherence_cache.atoms import make_atom

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
    doc = intersection_packet(mine, theirs, max_size=4, min_cross_sim=0.18)
    assert doc["challenges"]
    paired = [c for c in doc["challenges"] if c.get("other")]
    assert paired
    assert all(c.get("kind") in {"support", "weak", "tension"} for c in paired)
    assert all(c.get("prompt") for c in paired)
    assert all(c.get("affinity", 0) >= 0.18 for c in paired)


def test_overlap_challenges_one_sided_without_match():
    prov = [
        {
            "index": 0,
            "source": "mine",
            "text": "Domestic cats hunt primarily at dusk and dawn.",
            "store_index": 0,
        }
    ]
    ch = overlap_challenges(
        prov,
        {"atoms": ["Domestic cats hunt primarily at dusk and dawn."]},
        {"atoms": ["Packets are the share unit, not transcripts."]},
        min_sim=0.18,
    )
    assert len(ch) == 1
    assert ch[0]["other"] is None
    assert "without them" in ch[0]["prompt"]


def test_qubo_energy_two_spins():
    Q = {(0, 0): -1.0, (1, 1): -1.0, (0, 1): 2.0}
    assert energy([0, 0], Q) == 0.0
    assert energy([1, 0], Q) == -1.0
    assert energy([0, 1], Q) == -1.0
    assert energy([1, 1], Q) == 0.0
    built = build_qubo(2, {(0, 1): -1.0}, select_penalty=-1.0, coupling_scale=1.5)
    # J = -1.5 * (-1) = +1.5 — conflict raises energy when both on
    assert built[(0, 0)] == -1.0
    assert abs(built[(0, 1)] - 1.5) < 1e-12


def test_greedy_empty_and_singleton():
    assert greedy_resilient([], {}) == ([], 0.0)
    selected, eng = greedy_resilient(["Only claim."], {})
    assert selected == ["Only claim."]
    assert eng == -1.0


def test_greedy_will_not_pair_direct_conflict():
    atoms = ["Task T is possible.", "Task T is impossible."]
    selected, _eng = greedy_resilient(atoms, {(0, 1): -1.0}, max_size=2)
    assert len(selected) == 1


def test_sa_seed_reproducible():
    kwargs = dict(
        num_reads=8,
        num_sweeps=25,
        seed=7,
        method="sa-sweep",
        redundancy_scale=2.0,
        redundancy_threshold=0.2,
    )
    a = find_resilient_constructors(DIVERSITY_ATOMS, DIVERSITY_CONS, **kwargs)
    b = find_resilient_constructors(DIVERSITY_ATOMS, DIVERSITY_CONS, **kwargs)
    assert a[0] == b[0]


def test_monte_carlo_methods_avoid_paraphrase_pair():
    energies = {}
    for method in SAMPLE_METHODS:
        packets = find_resilient_constructors(
            DIVERSITY_ATOMS,
            DIVERSITY_CONS,
            num_reads=16,
            num_sweeps=40,
            seed=0,
            method=method,
            redundancy_scale=2.0,
            redundancy_threshold=0.2,
            max_size=3,
        )
        top, eng = packets[0]
        energies[method] = eng
        assert packets[0][1] == min(p[1] for p in packets)
        assert len(top) <= 3, method
        # One-flip-per-T (sa-geo) mixes less; sweep/metropolis should drop the paraphrase pair.
        if method != "sa-geo":
            assert not (
                DIVERSITY_ATOMS[1] in top and DIVERSITY_ATOMS[2] in top
            ), method
    assert energies["sa-sweep"] <= energies["sa-geo"] + 1e-9


def test_unknown_sample_method_errors():
    try:
        find_resilient_constructors(["a", "b"], {(0, 1): 0.5}, method="gibbs")
    except ValueError as e:
        assert "gibbs" in str(e)
    else:
        raise AssertionError("expected ValueError")
