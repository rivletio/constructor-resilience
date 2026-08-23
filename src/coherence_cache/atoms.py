"""Atom shape helpers — strings remain valid; enriched records are preferred.

Wire format (SPEC v1 compatible):
  atoms: [ "plain string", { "text": "...", "provenance": {...}, "review": {...} }, ... ]

Indices stay stable for consistency edges. Search/packet always operate on
``atom_text(a)``. Review tooling inspects provenance + review status.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

REVIEW_PENDING = "pending"
REVIEW_ACCEPTED = "accepted"
REVIEW_REJECTED = "rejected"
REVIEW_EDITED = "edited"

VALID_REVIEW = frozenset(
    {REVIEW_PENDING, REVIEW_ACCEPTED, REVIEW_REJECTED, REVIEW_EDITED}
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atom_text(atom: Any) -> str:
    if isinstance(atom, str):
        return atom
    if isinstance(atom, dict):
        return str(atom.get("text") or "").strip()
    return str(atom).strip()


def atom_texts(atoms: list) -> list[str]:
    return [atom_text(a) for a in atoms]


def atom_review_status(atom: Any) -> str:
    if isinstance(atom, dict):
        st = (atom.get("review") or {}).get("status") or REVIEW_ACCEPTED
        # Legacy plain strings and pre-review objects without status =
        # treated as accepted (already in the graph by human/agent will).
        return st if st in VALID_REVIEW else REVIEW_ACCEPTED
    return REVIEW_ACCEPTED


def is_active(atom: Any) -> bool:
    """Rejected atoms stay in the file for audit but leave packets/search."""
    return atom_review_status(atom) != REVIEW_REJECTED


def active_atoms(store: dict) -> list:
    return [a for a in (store.get("atoms") or []) if is_active(a)]


def active_texts(store: dict) -> list[str]:
    return atom_texts(active_atoms(store))


def make_atom(
    text: str,
    *,
    method: str = "manual",
    model: str | None = None,
    source: str | None = None,
    source_excerpt: str | None = None,
    prompt: str | None = None,
    review_status: str = REVIEW_PENDING,
    extra: dict | None = None,
) -> dict:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        raise ValueError("empty atom text")
    rec: dict[str, Any] = {
        "text": text,
        "provenance": {
            "method": method,
            "model": model,
            "source": source,
            "source_excerpt": (source_excerpt or "")[:500] or None,
            "created": now_iso(),
            "prompt_sha256": (
                hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
                if prompt
                else None
            ),
        },
        "review": {
            "status": review_status if review_status in VALID_REVIEW else REVIEW_PENDING,
            "reviewed_at": None,
            "notes": "",
        },
    }
    if extra:
        rec["extra"] = dict(extra)
    return rec


def set_review(
    atom: Any,
    status: str,
    *,
    text: str | None = None,
    notes: str | None = None,
) -> dict:
    if status not in VALID_REVIEW:
        raise ValueError(f"bad review status: {status}")
    if isinstance(atom, str):
        atom = make_atom(atom, method="legacy", review_status=REVIEW_ACCEPTED)
    else:
        atom = dict(atom)
        atom.setdefault("provenance", {})
        atom.setdefault("review", {})
    if text is not None:
        new_text = re.sub(r"\s+", " ", text.strip())
        if new_text and new_text != atom_text(atom):
            atom["text"] = new_text
            if status == REVIEW_ACCEPTED:
                status = REVIEW_EDITED
    review = dict(atom.get("review") or {})
    review["status"] = status
    review["reviewed_at"] = now_iso()
    if notes is not None:
        review["notes"] = notes
    if status != REVIEW_REJECTED:
        review.pop("backed_out", None)
    atom["review"] = review
    return atom


def back_out(atom: Any, *, reason: str) -> dict:
    """Retract an atom that was ill-defined or failed its claimed constraint.

    Constructor-theoretic: an atom must actually create a possibility or an
    impossibility. If it does not, mark it rejected in place. Indices stay
    stable; ``is_active`` drops it from packets and search. The record remains
    on disk for audit.
    """
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("back_out requires a reason")
    previous = atom_review_status(atom)
    atom = set_review(atom, REVIEW_REJECTED, notes=reason)
    review = dict(atom.get("review") or {})
    review["previous_status"] = previous
    review["backed_out"] = True
    atom["review"] = review
    return atom


def normalize_store_atoms(store: dict) -> dict:
    """Ensure every atom is a dict (idempotent upgrade for review UI)."""
    atoms = store.get("atoms") or []
    out = []
    for a in atoms:
        if isinstance(a, str):
            out.append(
                make_atom(a, method="legacy", review_status=REVIEW_ACCEPTED)
            )
        elif isinstance(a, dict) and a.get("text"):
            a = dict(a)
            a.setdefault(
                "provenance",
                {"method": "unknown", "created": now_iso()},
            )
            a.setdefault(
                "review",
                {"status": REVIEW_ACCEPTED, "reviewed_at": None, "notes": ""},
            )
            out.append(a)
        else:
            continue
    store = dict(store)
    store["atoms"] = out
    return store


# ── Mint quality law (for prompts + filters) ─────────────────────────

ATOM_QUALITY_LAW = """\
Only emit DURABLE claims — facts, constraints, decisions, or partial explanations
worth injecting into a future agent turn on this topic.

A well-formed atom constrains possibility or impossibility on the topic
(a constructor-fragment). If a minted atom is later found ill-defined, or
does not actually create the possibility/impossibility it claimed, back it
out (reject in place). Do not delete; indices stay stable for audit.

DO NOT emit:
- greetings, filler, or process chatter ("ok let's continue")
- ephemeral UI/state ("the button is blue right now")
- near-duplicates of claims already listed
- speculative wishes without grounding
- claims NOT entailed by the source (no invention, no "helpful" elaboration)

Each atom: one sentence, concrete, stand-alone, no markdown bullets.
Prefer claims that could support or conflict with other claims.
Extract; do not invent.
"""


MINT_SYSTEM = f"""You extract knowledge atoms for a constructor-resilience coherence cache.

{ATOM_QUALITY_LAW}

Return ONLY a JSON array of strings (the atom texts). No preamble.
Every string MUST be a paraphrase or near-quote of something in the source.
"""


def mint_prompt(source_text: str, *, theme: str | None = None, max_atoms: int = 12) -> str:
    theme_line = f"Theme focus: {theme}\n" if theme else ""
    return (
        f"{MINT_SYSTEM}\n"
        f"{theme_line}"
        f"Extract up to {max_atoms} atoms from the source below.\n"
        f"If the source has fewer durable claims, return fewer atoms.\n\n"
        f"--- SOURCE ---\n{source_text.strip()[:12000]}\n--- END ---\n"
    )


_STOP = frozenset(
    """
    a an the and or but if then than to of in on for with from by as is are was
    were be been being it its this that these those we you they he she their our
    not no nor so at into about over under after before when while who which what
    how why can could should would may might must will shall do does did done
    have has had having also just only very more most other such own same
    """.split()
)


def content_tokens(text: str) -> set[str]:
    toks = set(re.findall(r"[a-z0-9']+", (text or "").lower()))
    return {t for t in toks if len(t) >= 4 and t not in _STOP}


def grounding_score(claim: str, source: str) -> float:
    """Fraction of claim content tokens attested in the source (0–1)."""
    c = content_tokens(claim)
    if not c:
        return 0.0
    s = content_tokens(source)
    # Also allow substring hits for short technical tokens already in source lower
    src_l = (source or "").lower()
    hit = 0
    for t in c:
        if t in s or t in src_l:
            hit += 1
    return hit / len(c)


def is_grounded(claim: str, source: str, *, min_ratio: float = 0.55) -> bool:
    """True if claim is sufficiently attested by source (anti-invention gate)."""
    claim = (claim or "").strip()
    if len(claim) < 12:
        return False
    # Near-quote: long contiguous span from source
    src_l = re.sub(r"\s+", " ", (source or "").lower())
    cl = re.sub(r"\s+", " ", claim.lower())
    if len(cl) >= 24 and cl in src_l:
        return True
    # Sliding window of 6+ consecutive content words
    words = [w for w in re.findall(r"[a-z0-9']+", cl) if w not in _STOP and len(w) >= 3]
    if len(words) >= 6:
        for i in range(0, len(words) - 5):
            span = " ".join(words[i : i + 6])
            if span in src_l:
                return True
    return grounding_score(claim, source) >= min_ratio


def query_overlap(query: str, claim: str) -> float:
    """How much a claim covers a query (for query-aware packets)."""
    q = content_tokens(query)
    if not q:
        return 0.0
    c = content_tokens(claim)
    return len(q & c) / len(q)


def parse_minted_list(raw: str) -> list[str]:
    """Parse model output into atom strings (JSON array or line bullets)."""
    raw = (raw or "").strip()
    # Strip common reasoning fences
    if "</think>" in raw:
        raw = raw.split("</think>")[-1].strip()
    # JSON array
    start = raw.find("[")
    end = raw.rfind("]")
    if start >= 0 and end > start:
        import json

        try:
            data = json.loads(raw[start : end + 1])
            if isinstance(data, list):
                out = []
                for item in data:
                    if isinstance(item, str) and item.strip():
                        out.append(re.sub(r"\s+", " ", item.strip()))
                    elif isinstance(item, dict) and item.get("text"):
                        out.append(re.sub(r"\s+", " ", str(item["text"]).strip()))
                return out
        except json.JSONDecodeError:
            pass
    # Fallback: lines
    out = []
    for line in raw.splitlines():
        line = line.strip().lstrip("-•*0123456789.) ").strip()
        if len(line) >= 12 and not line.lower().startswith(("here", "sure", "json")):
            out.append(re.sub(r"\s+", " ", line))
    return out
