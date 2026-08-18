"""Gated utterance_seed proposals from accepted atoms (no MLX)."""

from coherence_cache.atoms import REVIEW_ACCEPTED, REVIEW_PENDING, make_atom
from coherence_cache.config import CoherenceConfig
from coherence_cache.seed_propose import (
    propose_seeds_from_store,
    proposals_document,
)


CFG = CoherenceConfig(seed_propose_enabled=True, seed_propose_min_conf=0.55)


def test_propose_from_calendar_atom():
    store = {
        "atoms": [
            make_atom(
                "Calendar agenda is FREE vault data: say calendar, agenda, "
                "or calendar today to list today's events without residual LLM.",
                review_status=REVIEW_ACCEPTED,
            )
        ]
    }
    got = propose_seeds_from_store(store, cfg=CFG)
    tools = {p.tool for p in got}
    phrasings = {p.phrasing for p in got}
    assert "/calendar" in tools or "/calendar today" in tools
    assert any("calendar" in p or "agenda" in p for p in phrasings)


def test_propose_from_say_to_cmd():
    store = {
        "atoms": [
            make_atom(
                "Say show me commands to /help to list the registry.",
                review_status=REVIEW_ACCEPTED,
            )
        ]
    }
    got = propose_seeds_from_store(store, cfg=CFG)
    assert any(p.tool.startswith("/help") for p in got)
    assert any("show me commands" in p.phrasing for p in got)


def test_pending_skipped_by_default():
    store = {
        "atoms": [
            make_atom(
                "Say open explore to /surface open Explore now.",
                review_status=REVIEW_PENDING,
            )
        ]
    }
    assert propose_seeds_from_store(store, cfg=CFG) == []
    assert propose_seeds_from_store(store, cfg=CFG, accepted_only=False)


def test_disabled_gate():
    store = {
        "atoms": [
            make_atom(
                "Tasks are a personal kanban; task list and focus board are FREE.",
                review_status=REVIEW_ACCEPTED,
            )
        ]
    }
    off = CFG.replace(seed_propose_enabled=False)
    assert propose_seeds_from_store(store, cfg=off) == []


def test_proposals_document_law():
    store = {
        "atoms": [
            make_atom(
                "Add work with task add; list with /task list on the board.",
                review_status=REVIEW_ACCEPTED,
            )
        ]
    }
    props = propose_seeds_from_store(store, cfg=CFG)
    doc = proposals_document(props, topic_id="tasks-law", cfg=CFG)
    assert doc["kind"] == "utterance_seed_proposals"
    assert doc["status"] == "pending_human_or_ci"
    assert "never auto-merge" in doc["law"].lower() or "do not auto-merge" in doc["law"].lower()
    assert doc["count"] == len(props)
