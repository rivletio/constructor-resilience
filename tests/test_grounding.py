"""Grounding gate + query-aware packet seeding."""

from coherence_cache.atoms import grounding_score, is_grounded, query_overlap
from coherence_cache.eval_queries import packet_for_query


SOURCE = """
Constructor resilience compresses durable claims into atoms and resilient packets.
Interest surfaces are intentional — we do not share whole stores.
Qwen3 8B on MLX is the default local mint and eval model.
"""


def test_grounded_near_quote():
    claim = "Interest surfaces are intentional — we do not share whole stores."
    assert is_grounded(claim, SOURCE)
    assert grounding_score(claim, SOURCE) >= 0.55


def test_ungrounded_invention_dropped():
    claim = "Private stores automatically encrypt every personal claim overnight."
    assert not is_grounded(claim, SOURCE)


def test_query_overlap_prefers_relevant_atom():
    store_claim = "Interest surfaces are intentional — we do not share whole stores."
    model = "Qwen3 8B on MLX is the default local mint and eval model."
    assert query_overlap("Do we share whole stores?", store_claim) > query_overlap(
        "Do we share whole stores?", model
    )


def test_packet_for_query_seeds_relevant():
    store = {
        "atoms": [
            "Constructor resilience compresses durable claims into atoms and resilient packets.",
            "Interest surfaces are intentional — we do not share whole stores.",
            "Qwen3 8B on MLX is the default local mint and eval model.",
            "Unrelated filler about calendars and weather.",
        ],
        "consistency": {},
    }
    pkt, meta = packet_for_query(
        store, "Do we share whole stores?", max_size=3, seed_k=2
    )
    assert meta["method"] == "query_seeded_greedy"
    assert any("stores" in a.lower() for a in pkt)
