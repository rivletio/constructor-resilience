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


def test_parse_minted_unwraps_json_string_objects():
    raw = (
        '[{"atom": "LLM APIs never run in the guest VM.", "text": "Ikonic OS law"},'
        ' "{\\"atom\\": \\"Pack does not require a mint model.\\", '
        '\\"text\\": \\"Pack does not require a mint model.\\"}"]'
    )
    got = parse_minted_list(raw)
    assert any("guest VM" in t for t in got)
    assert any("mint model" in t for t in got)
    assert not any(t.startswith("{") for t in got)


def test_parse_minted_unwraps_one_object_per_line():
    raw = (
        '{"atom": "LLM APIs never run in the guest VM.", "text": "Ikonic OS law"}\n'
        '{"atom": "Pack does not require a mint model.", '
        '"text": "Pack does not require a mint model."}\n'
    )
    got = parse_minted_list(raw)
    assert got == [
        "LLM APIs never run in the guest VM.",
        "Pack does not require a mint model.",
    ]


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


def test_make_atom_constraint_mentions_refs():
    a = make_atom(
        "JEPA predicts in latent space rather than tokens. See https://arxiv.org/abs/2206.14607",
        constraint="possibility",
    )
    assert a["constraint"] == "possibility"
    names = {m["name"] for m in a.get("mentions") or []}
    assert "JEPA" in names
    noisy = make_atom("The skill is a thin client of the coherence CLI; PATH may be empty.")
    noisy_names = {m["name"] for m in noisy.get("mentions") or []}
    assert "CLI" not in noisy_names
    assert "PATH" not in noisy_names
    kinds = {r["kind"] for r in a.get("refs") or []}
    assert "url" in kinds or "arxiv" in kinds


def test_make_atom_fills_arxiv_locator_url():
    a = make_atom(
        "The Transformer dispenses with recurrence and convolutions.",
        constraint="fact",
        refs=[
            {
                "kind": "arxiv",
                "id": "1706.03762",
                "page": 1,
                "paragraph": 1,
                "excerpt": "We propose a new simple network architecture, the Transformer",
            }
        ],
    )
    r = a["refs"][0]
    assert r["url"] == "https://arxiv.org/pdf/1706.03762#page=1"
    assert r["paragraph"] == 1
    assert r["html"].startswith("https://arxiv.org/html/1706.03762#:~:text=")
    assert "We propose a new simple network architecture" in r["excerpt"]


def test_make_atom_rejects_bad_constraint():
    with pytest.raises(ValueError, match="constraint"):
        make_atom("A durable claim about packets.", constraint="vibes")


def test_coerce_and_parse_ingest_payload():
    from coherence_cache.atoms import coerce_atom, parse_ingest_payload

    items = parse_ingest_payload(
        {
            "atoms": [
                "Packets are the share unit, not transcripts.",
                {
                    "text": "Mentions are joins onto a claim, not a second graph.",
                    "constraint": "fact",
                    "mentions": [{"name": "constructor-resilience", "kind": "work"}],
                },
            ]
        }
    )
    assert len(items) == 2
    a = coerce_atom(items[1], method="host_mint")
    assert a["constraint"] == "fact"
    assert a["mentions"][0]["name"] == "constructor-resilience"
    assert a["review"]["status"] == "pending"


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
