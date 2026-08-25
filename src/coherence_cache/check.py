"""Mechanical pack checks so a small model can retry from FAIL lines."""
from __future__ import annotations

import re
from typing import Any

from .atoms import REVIEW_REJECTED, atom_review_status, atom_text
from .mentions import mention_attestation_fail

_CHAT = re.compile(
    r"(?is)^(ok|okay|sure|thanks|hi|hello|hey)\b"
    r"|(this|the) (session|conversation|chat)"
    r"|^(i|we) (will|can|should|just) (pack|add|write)\b"
)
_CITE_IN_TEXT = re.compile(
    r"arxiv[:\s]+\d{4}\.\d{4,5}|youtube\.com/watch|youtu\.be/",
    re.I,
)
_TEMPLATE = re.compile(
    r"<[A-Z][A-Z0-9:_-]+>|stand-alone sentence from the session|Name:kind @ file\.py",
    re.I,
)
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


def check_text(text: str) -> list[str]:
    """Text-only FAILs (overlap packets are strings, not store records)."""
    fails: list[str] = []
    n_cjk = len(_CJK.findall(text or ""))
    if n_cjk < 8 and len(text) < 24:
        fails.append("too short")
    if _CHAT.search(text or ""):
        fails.append("chat, not a claim")
    if _TEMPLATE.search(text or ""):
        fails.append("copied template, not a session claim")
    if len(text) >= 2 and text[0] == text[-1] == '"':
        fails.append("quoted fragment, not a claim")
    return fails


def check_atom(atom: Any) -> list[str]:
    """Fail reasons (empty = pass). Rejected atoms are skipped."""
    if atom_review_status(atom) == REVIEW_REJECTED:
        return []
    text = atom_text(atom)
    fails = check_text(text)
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
        att = mention_attestation_fail(name, text, aliases=m.get("aliases"))
        if att:
            fails.append(att)
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
        first = next(f[0] for i, f in rows if i == idx and f)
        if first.startswith("anaphor"):
            exp = (
                f"coherence reject {idx} --reason \"anaphor\" "
                "then pack the claim with the name in the sentence"
            )
        elif "not attested" in first:
            exp = (
                f"coherence reject {idx} --reason \"mention not attested\" "
                "then put the name or ALIAS in the sentence, or drop the join"
            )
        else:
            exp = (
                f"coherence reject {idx} --reason \"check fail\" "
                "then pack one replacement"
            )
        lines.append(f"observe: FAIL [{idx}]; experiment: {exp}")
    return "\n".join(lines)


def overlap_fail_count(doc: dict) -> int:
    n = 0
    for a in doc.get("atoms") or []:
        if check_text(atom_text(a)):
            n += 1
    return n


def overlap_tension_count(doc: dict) -> int:
    return sum(
        1
        for c in doc.get("challenges") or []
        if c.get("tension") or c.get("kind") == "tension"
    )


def overlap_garbage_count(doc: dict) -> int:
    return sum(1 for c in doc.get("challenges") or [] if c.get("kind") == "garbage")


def overlap_unresolved_count(doc: dict) -> int:
    """Text FAILs plus polarity conflicts and ungrounded mention joins."""
    return overlap_fail_count(doc) + overlap_tension_count(doc) + overlap_garbage_count(doc)


def format_overlap_check(doc: dict) -> str:
    """Observe/reason/experiment for intersect or union packets."""
    atoms = doc.get("atoms") or []
    kind = doc.get("kind") or "packet"
    failed_idx: list[int] = []
    fail_lines: list[str] = []
    for i, a in enumerate(atoms):
        fails = check_text(atom_text(a))
        if fails:
            failed_idx.append(i)
            fail_lines.append(f"  [{i}] FAIL {' | '.join(fails)}")
    n = len(atoms)
    n_fail = len(failed_idx)
    lines = [f"check {n - n_fail}/{n} PASS  {kind}"]
    lines.extend(fail_lines)
    challenges = doc.get("challenges") or []
    if challenges:
        lines.append("challenges")
        for i, ch in enumerate(challenges):
            src = ch.get("source", "?")
            si = ch.get("store_index")
            src_l = f"{src}" + (f" #{si}" if si is not None else "")
            text = ch.get("text") or ""
            other = ch.get("other")
            prompt = ch.get("prompt") or ""
            lines.append(f"  [{i}] ({src_l}) {text}")
            if other:
                osrc = ch.get("other_source", "?")
                aff = ch.get("affinity", 0)
                kind = ch.get("kind") or ("tension" if ch.get("tension") else "")
                tag = ""
                if kind == "tension" or ch.get("tension"):
                    tag = " TENSION"
                elif kind == "garbage":
                    g = ch.get("grounding", 0)
                    tag = f" GARBAGE JOIN grounding={g}"
                lines.append(f"      vs ({osrc}) {other}  affinity={aff}{tag}")
            lines.append(f"      {prompt}")
    n_ten = overlap_tension_count(doc)
    n_garb = overlap_garbage_count(doc)
    if failed_idx:
        idx = failed_idx[0]
        lines.append(
            f"observe: FAIL [{idx}]; "
            "experiment: reject the originating atom then re-run intersect/union"
        )
    elif n_ten:
        lines.append(
            f"observe: TENSION x{n_ten}; "
            "reason: which claim is false given the other?; "
            "experiment: reject the falsified atom (`use` its topic), "
            "re-run overlap, compare with --against"
        )
    elif n_garb:
        lines.append(
            f"observe: GARBAGE JOIN x{n_garb}; "
            "reason: mention grounding < 0.5 — name is not in the claim; "
            "experiment: drop the unearned mention or reject the atom, then re-run"
        )
    elif challenges:
        lines.append(
            "observe: challenge each pair; "
            "reason: does this still hold given the other side?; "
            "experiment: reject the falsified atom (`use` its topic) then re-run"
        )
    elif n == 0:
        lines.append("observe: empty overlap; nothing to challenge")
    return "\n".join(lines)


def format_overlap_compare(cmp: dict) -> str:
    """Observe a reconstructed overlap against the previous packet."""
    lines = [
        "compare  "
        f"kept={len(cmp.get('kept') or [])} "
        f"dropped={len(cmp.get('dropped') or [])} "
        f"added={len(cmp.get('added') or [])}  "
        f"tension {cmp.get('tension_before', 0)}→{cmp.get('tension_after', 0)}"
    ]
    for t in cmp.get("dropped") or []:
        lines.append(f"  - {t}")
    for t in cmp.get("added") or []:
        lines.append(f"  + {t}")
    if cmp.get("fixed_point"):
        lines.append(
            "observe: reconstructed set matches previous; "
            "stop if check has no TENSION"
        )
    else:
        lines.append(
            "observe: reconstructed set differs; "
            "reason whether the drop/add is the right experiment, then continue"
        )
    return "\n".join(lines)
