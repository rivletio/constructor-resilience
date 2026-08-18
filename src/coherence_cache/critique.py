"""Pre-human critique of pending atoms — config + dict dispatch, no magic if-ladders."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from . import mlx_backend
from .atoms import (
    ATOM_QUALITY_LAW,
    REVIEW_ACCEPTED,
    REVIEW_EDITED,
    REVIEW_PENDING,
    REVIEW_REJECTED,
    atom_review_status,
    atom_text,
    grounding_score,
    is_grounded,
    make_atom,
    now_iso,
    set_review,
)
from .config import CFG, CoherenceConfig

Action = Literal["accept", "edit", "reject"]
ACTIONS: frozenset[str] = frozenset({"accept", "edit", "reject"})

CRITIQUE_SYSTEM = f"""You are a strict reviewer for a constructor-resilience coherence cache.

{ATOM_QUALITY_LAW}

For EACH pending atom, decide:
- accept — durable, grounded in SOURCE, non-duplicate, clear
- edit — almost good; return improved text that stays grounded in SOURCE
- reject — invented, filler, duplicate, or not durable

Return ONLY a JSON array of objects:
[{{"i": <index>, "action": "accept"|"edit"|"reject", "confidence": 0.0-1.0,
  "text": "<edited text or original>", "reason": "<short>"}}]
Use the given atom indices. Do not invent atoms outside SOURCE.
"""


@dataclass(frozen=True)
class Proposal:
    i: int
    action: Action
    confidence: float
    text: str | None
    reason: str
    grounding: float | None = None
    original: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "i": self.i,
            "action": self.action,
            "confidence": self.confidence,
            "text": self.text,
            "reason": self.reason,
            "grounding": self.grounding,
            "original": self.original,
        }


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _parse_item(item: Any, *, reason_max: int) -> Proposal | None:
    if not isinstance(item, dict):
        return None
    try:
        i = int(item["i"])
    except (KeyError, TypeError, ValueError):
        return None
    action = str(item.get("action") or "").lower().strip()
    if action not in ACTIONS:
        return None
    try:
        conf = _clamp01(float(item.get("confidence", 0.0)))
    except (TypeError, ValueError):
        conf = 0.0
    text = item.get("text")
    if text is not None:
        text = re.sub(r"\s+", " ", str(text).strip()) or None
    return Proposal(
        i=i,
        action=action,  # type: ignore[arg-type]
        confidence=conf,
        text=text,
        reason=str(item.get("reason") or "")[:reason_max],
    )


def parse_critique_batch(raw: str, *, cfg: CoherenceConfig = CFG) -> list[Proposal]:
    text = (raw or "").strip()
    if "</think>" in text:
        text = text.split("</think>")[-1].strip()
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [p for p in (_parse_item(x, reason_max=cfg.reason_max_chars) for x in data) if p]


def source_for_atom(atom: Any, fallback: str | None) -> str:
    if isinstance(atom, dict):
        excerpt = (atom.get("provenance") or {}).get("source_excerpt")
        if excerpt:
            return str(excerpt)
    return fallback or ""


def collect_source_excerpts(store: dict) -> str | None:
    chunks: list[str] = []
    seen: set[str] = set()
    for a in store.get("atoms") or []:
        if not isinstance(a, dict):
            continue
        ex = (a.get("provenance") or {}).get("source_excerpt")
        if ex and ex not in seen:
            seen.add(ex)
            chunks.append(str(ex))
    return "\n".join(chunks) or None


def pending_indices(atoms: list, *, only_pending: bool = True) -> list[int]:
    if not only_pending:
        return list(range(len(atoms)))
    return [i for i, a in enumerate(atoms) if atom_review_status(a) == REVIEW_PENDING]


def _fallback_proposal(i: int, atom: Any, source: str | None, cfg: CoherenceConfig) -> Proposal:
    text = atom_text(atom)
    grounded = (not source) or is_grounded(
        text, source, min_ratio=cfg.critique_min_grounding
    )
    action: Action = "accept" if grounded else "reject"
    return Proposal(
        i=i,
        action=action,
        confidence=cfg.critique_fallback_conf,
        text=text,
        reason="fallback heuristic (model omitted index)",
        original=text,
    )


def _normalize_proposal(
    p: Proposal,
    *,
    atom: Any,
    source: str | None,
    cfg: CoherenceConfig,
) -> Proposal:
    original = atom_text(atom)
    claim = (p.text or original).strip()
    g = grounding_score(claim, source) if source else None

    action = p.action
    conf = p.confidence
    reason = p.reason
    text = p.text

    # Collapse no-op edits
    if action == "edit" and (not text or text == original):
        action, text = "accept", original

    # Source-known + ungrounded accept/edit → forced reject
    if (
        source
        and action in ("accept", "edit")
        and not is_grounded(claim, source, min_ratio=cfg.critique_min_grounding)
    ):
        action = "reject"
        reason = f"{reason} [forced reject: ungrounded]".strip()
        conf = max(conf, cfg.critique_force_reject_conf)

    return Proposal(
        i=p.i,
        action=action,
        confidence=conf,
        text=text or original,
        reason=reason,
        grounding=round(g, 3) if g is not None else None,
        original=original,
    )


def _batch_prompt(atoms: list, targets: list[int], source: str | None, cfg: CoherenceConfig) -> str:
    blocks = []
    for i in targets:
        a = atoms[i]
        src = source_for_atom(a, source)
        g = grounding_score(atom_text(a), src) if src else None
        method = (
            (a.get("provenance") or {}).get("method")
            if isinstance(a, dict)
            else "legacy"
        )
        blocks.append(
            f"[{i}] grounding={g if g is not None else 'n/a'} method={method}\n"
            f"CLAIM: {atom_text(a)}\n"
            f"SOURCE_EXCERPT: {(src or '')[: cfg.source_excerpt_chars]}\n"
        )
    return "Critique these pending atoms.\n\n" + "\n".join(blocks) + "\nReturn the JSON array now."


def critique_pending(
    store: dict,
    *,
    source: str | None = None,
    model: str | None = None,
    cfg: CoherenceConfig = CFG,
    only_pending: bool = True,
) -> dict[str, Any]:
    """Judge pending atoms; return proposals (does not mutate store)."""
    atoms = list(store.get("atoms") or [])
    targets = pending_indices(atoms, only_pending=only_pending)
    empty = {
        "proposals": [],
        "model": model or cfg.mlx_model,
        "n_pending": 0,
        "raw": "",
        "created": now_iso(),
    }
    if not targets:
        return empty

    out = mlx_backend.generate(
        _batch_prompt(atoms, targets, source, cfg),
        system=CRITIQUE_SYSTEM,
        model=model or cfg.mlx_model,
        max_tokens=cfg.critique_max_tokens,
        temp=cfg.critique_temp,
    )
    by_i = {p.i: p for p in parse_critique_batch(out["text"], cfg=cfg)}
    finalized = [
        _normalize_proposal(
            by_i.get(i) or _fallback_proposal(i, atoms[i], source, cfg),
            atom=atoms[i],
            source=source_for_atom(atoms[i], source),
            cfg=cfg,
        )
        for i in targets
    ]
    return {
        "proposals": [p.as_dict() for p in finalized],
        "model": out["model"],
        "n_pending": len(targets),
        "raw": out["text"],
        "created": now_iso(),
    }


# ── Apply: gate table + action handlers ──────────────────────────────


def _ensure_record(atom: Any) -> dict:
    if isinstance(atom, str):
        return make_atom(atom, method="legacy", review_status=REVIEW_PENDING)
    return dict(atom)


def _attach_critique(atom: dict, p: dict) -> dict:
    review = dict(atom.get("review") or {})
    review["critique"] = {
        "action": p["action"],
        "confidence": p["confidence"],
        "grounding": p.get("grounding"),
        "reason": p.get("reason"),
        "proposed_text": p.get("text"),
        "created": now_iso(),
    }
    atom["review"] = review
    return atom


def _gate_accept(p: dict, cfg: CoherenceConfig, *, apply_edits: bool, apply_all: bool) -> bool:
    if apply_all:
        return True
    g = p.get("grounding")
    g_ok = g is None or float(g) >= cfg.critique_min_grounding
    conf = float(p.get("confidence") or 0)
    return conf >= cfg.critique_accept_min_conf and g_ok


def _gate_reject(p: dict, cfg: CoherenceConfig, *, apply_edits: bool, apply_all: bool) -> bool:
    if apply_all:
        return True
    return float(p.get("confidence") or 0) >= cfg.critique_reject_min_conf


def _gate_edit(p: dict, cfg: CoherenceConfig, *, apply_edits: bool, apply_all: bool) -> bool:
    if apply_all:
        return True
    if not apply_edits:
        return False
    g = p.get("grounding")
    g_ok = g is None or float(g) >= cfg.critique_min_grounding
    return float(p.get("confidence") or 0) >= cfg.critique_edit_min_conf and g_ok


GATES: dict[Action, Callable[..., bool]] = {
    "accept": _gate_accept,
    "reject": _gate_reject,
    "edit": _gate_edit,
}


def _apply_accept(atom: dict, p: dict) -> dict:
    return set_review(atom, REVIEW_ACCEPTED, notes=p.get("reason") or "critique auto-accept")


def _apply_reject(atom: dict, p: dict) -> dict:
    return set_review(atom, REVIEW_REJECTED, notes=p.get("reason") or "critique auto-reject")


def _apply_edit(atom: dict, p: dict) -> dict:
    return set_review(
        atom,
        REVIEW_EDITED,
        text=p.get("text") or atom_text(atom),
        notes=p.get("reason") or "critique auto-edit",
    )


APPLIERS: dict[Action, Callable[[dict, dict], dict]] = {
    "accept": _apply_accept,
    "reject": _apply_reject,
    "edit": _apply_edit,
}

STAT_KEY = {"accept": "accepted", "reject": "rejected", "edit": "edited"}


def apply_proposals(
    store: dict,
    proposals: list[dict],
    *,
    cfg: CoherenceConfig = CFG,
    apply_edits: bool = False,
    apply_all: bool = False,
    attach_only: bool = False,
) -> dict[str, Any]:
    """Attach critique to atoms; optionally auto-apply via gate table + APPLIERS."""
    atoms = list(store.get("atoms") or [])
    applied = {"accepted": 0, "edited": 0, "rejected": 0, "proposed_only": 0}

    for p in proposals:
        i = int(p["i"])
        if not (0 <= i < len(atoms)):
            continue
        action: Action = p["action"]
        atom = _attach_critique(_ensure_record(atoms[i]), p)
        atoms[i] = atom

        should = (not attach_only) and GATES[action](
            p, cfg, apply_edits=apply_edits, apply_all=apply_all
        )
        if not should:
            applied["proposed_only"] += 1
            continue
        atoms[i] = APPLIERS[action](atom, p)
        applied[STAT_KEY[action]] += 1

    out = dict(store)
    out["atoms"] = atoms
    out["updated"] = now_iso()
    return {"store": out, "applied": applied, "proposals": proposals}
