"""Named-entity *joins* on atoms — not a second knowledge graph.

Mentions and refs hang off a claim so a host can project them into its own
entity store. Constructor-resilience does not own ontology, types-as-truth,
or NER models.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from .refs_util import extract_references

VALID_CONSTRAINT = frozenset({"possibility", "impossibility", "fact", "decision"})
VALID_MENTION_KIND = frozenset(
    {"concept", "person", "org", "work", "place", "other"}
)

_STOP_ACRONYM = frozenset(
    {
        "THE",
        "AND",
        "FOR",
        "BUT",
        "NOT",
        "YOU",
        "ARE",
        "WAS",
        "ITS",
        "HTTP",
        "HTTPS",
        "HTML",
        "URL",
        "URI",
        "WWW",
        "PDF",
        "CLI",
        "PATH",
        "CPU",
        "GPU",
        "OS",
        "ID",
        "OK",
    }
)

_ACRONYM = re.compile(r"\b[A-Z]{2,8}\b")
_PROPER = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")


def normalize_constraint(value: Any) -> str | None:
    if value is None or value == "":
        return None
    c = str(value).strip().lower()
    if c not in VALID_CONSTRAINT:
        raise ValueError(
            f"constraint must be one of {sorted(VALID_CONSTRAINT)}, got {value!r}"
        )
    return c


def normalize_mention(item: Any) -> dict | None:
    if isinstance(item, str):
        name = item.strip()
        kind = "concept"
    elif isinstance(item, dict):
        name = str(item.get("name") or "").strip()
        kind = str(item.get("kind") or "concept").strip().lower()
    else:
        return None
    if not name:
        return None
    if kind not in VALID_MENTION_KIND:
        kind = "other"
    rec: dict[str, Any] = {"name": name, "kind": kind}
    if isinstance(item, dict):
        for k in ("id", "aliases"):
            if item.get(k) is not None:
                rec[k] = item[k]
    return rec


def normalize_mentions(items: Iterable | None) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in items or []:
        rec = normalize_mention(item)
        if not rec:
            continue
        key = (rec["name"].lower(), rec["kind"])
        if key in seen:
            continue
        seen.add(key)
        out.append(rec)
    return out


def extract_mentions(text: str) -> list[dict]:
    """High-precision heuristic joins: acronyms + multi-word proper names."""
    found: list[dict] = []
    for m in _PROPER.finditer(text or ""):
        found.append({"name": m.group(1), "kind": "concept"})
    for m in _ACRONYM.finditer(text or ""):
        name = m.group(0)
        if name in _STOP_ACRONYM:
            continue
        found.append({"name": name, "kind": "concept"})
    return normalize_mentions(found)


def mentions_from_atoms(atoms: Iterable) -> list[dict]:
    """Union of mention joins hanging off a list of atoms."""
    bag: list[dict] = []
    for a in atoms or []:
        if isinstance(a, dict):
            bag.extend(a.get("mentions") or [])
        else:
            bag.extend(extract_mentions(str(a)))
    return normalize_mentions(bag)


def refs_for_text(text: str, refs: list | None = None) -> list[dict]:
    if refs is not None:
        return list(refs)
    return extract_references(text)
