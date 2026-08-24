"""Mechanical pack checks so a small model can retry from FAIL lines."""
from __future__ import annotations

import re
from typing import Any

from .atoms import REVIEW_REJECTED, atom_review_status, atom_text

_CHAT = re.compile(
    r"(?is)^(ok|okay|sure|thanks|hi|hello|hey)\b"
    r"|(this|the) (session|conversation|chat)"
    r"|^(i|we) (will|can|should|just) (pack|add|write)\b"
)
_CITE_IN_TEXT = re.compile(
    r"arxiv[:\s]+\d{4}\.\d{4,5}|youtube\.com/watch|youtu\.be/",
    re.I,
)


def check_atom(atom: Any) -> list[str]:
    """Fail reasons (empty = pass). Rejected atoms are skipped."""
    if atom_review_status(atom) == REVIEW_REJECTED:
        return []
    fails: list[str] = []
    text = atom_text(atom)
    if len(text) < 24:
        fails.append("too short")
    if _CHAT.search(text or ""):
        fails.append("chat, not a claim")
    rec = atom if isinstance(atom, dict) else {}
    if not rec.get("constraint"):
        fails.append("missing constraint")
    mentions = rec.get("mentions") or []
    if not mentions:
        fails.append("missing mentions")
    for m in mentions:
        if not isinstance(m, dict):
            continue
        name = m.get("name") or "?"
        if m.get("path") and not m.get("line"):
            fails.append(f"mention {name!r} has path but no line")
        url = str(m.get("url") or "")
        if ("youtube.com" in url or "youtu.be/" in url) and m.get("t") is None:
            fails.append(f"mention {name!r} YouTube URL missing t=")
    if _CITE_IN_TEXT.search(text or "") and not (rec.get("refs") or []):
        fails.append("citation in text but no refs")
    return fails


def check_store(store: dict) -> tuple[list[tuple[int, list[str]]], int, int]:
    """Return ([(index, fails), ...], n_active, n_fail)."""
    rows: list[tuple[int, list[str]]] = []
    n_active = 0
    n_fail = 0
    for i, atom in enumerate(store.get("atoms") or []):
        if atom_review_status(atom) == REVIEW_REJECTED:
            continue
        n_active += 1
        fails = check_atom(atom)
        rows.append((i, fails))
        if fails:
            n_fail += 1
    return rows, n_active, n_fail


def format_check(store: dict) -> str:
    rows, n_active, n_fail = check_store(store)
    n_pass = n_active - n_fail
    lines = [f"check {n_pass}/{n_active} PASS"]
    failed_idx: list[int] = []
    for i, fails in rows:
        if not fails:
            continue
        failed_idx.append(i)
        lines.append(f"  [{i}] FAIL {' | '.join(fails)}")
    if failed_idx:
        idx = failed_idx[0]
        lines.append(
            f'retry: coherence reject {idx} --reason "check fail" '
            "then pack the replacement with --mention and --at"
        )
    return "\n".join(lines)
