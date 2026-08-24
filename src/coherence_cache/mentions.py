"""Named-entity *joins* on atoms — not a second knowledge graph.

The packing agent extracts names the claim is about. Mentions and refs hang
off that claim so a host can project them. This package does not own
ontology, types-as-truth, or an NER model.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from .refs_util import (
    extract_references,
    file_line_url,
    normalize_ref,
    parse_timestamp,
    parse_youtube_url,
    timestamp_label,
)

_LOCATOR_KEYS = (
    "path",
    "line",
    "end_line",
    "url",
    "t",
    "t_label",
    "page",
    "paragraph",
    "excerpt",
    "label",
)

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
        for k in ("id", "aliases", *_LOCATOR_KEYS):
            if item.get(k) is not None:
                rec[k] = item[k]
        rec = _fill_mention_locator(rec)
    return rec


def _fill_mention_locator(rec: dict[str, Any]) -> dict[str, Any]:
    if rec.get("path") and not rec.get("url"):
        rec["url"] = file_line_url(rec["path"], rec.get("line"), rec.get("end_line"))
    if rec.get("path") and rec.get("line") and not rec.get("label"):
        rec["label"] = f"{rec['path']}:{rec['line']}"
        if rec.get("end_line") and rec["end_line"] != rec["line"]:
            rec["label"] += f"-{rec['end_line']}"
    if rec.get("t") is not None and not rec.get("t_label"):
        rec["t_label"] = timestamp_label(int(rec["t"]))
    return rec


def parse_at_flag(raw: str) -> dict[str, Any]:
    """Locator after ``--mention``: ``file.py:42``, ``file.py#L42-L48``, ``t=3033``, or a URL."""
    text = (raw or "").strip()
    if not text:
        return {}
    yt = parse_youtube_url(text)
    if yt:
        out: dict[str, Any] = {"url": yt["url"]}
        if yt.get("t") is not None:
            out["t"] = yt["t"]
            out["t_label"] = yt.get("t_label")
        return out
    t_raw = text[2:] if text.lower().startswith("t=") else text
    if text.lower().startswith("t=") or re.fullmatch(r"\d+:\d{2}(?::\d{2})?", text):
        t = parse_timestamp(t_raw)
        if t is not None:
            return {"t": t, "t_label": timestamp_label(t)}
    m = re.match(r"(.+?)#L(\d+)(?:-L(\d+))?$", text, re.I)
    if m:
        return _file_loc(m.group(1), int(m.group(2)), int(m.group(3)) if m.group(3) else None)
    m = re.match(r"(.+):(\d+)(?:-(\d+))?$", text)
    if m and "://" not in m.group(1):
        return _file_loc(m.group(1), int(m.group(2)), int(m.group(3)) if m.group(3) else None)
    if re.match(r"https?://", text, re.I):
        return {"url": text}
    return _file_loc(text, None, None)


def _file_loc(path: str, line: int | None, end_line: int | None) -> dict[str, Any]:
    path = path.strip()
    rec: dict[str, Any] = {
        "path": path,
        "url": file_line_url(path, line, end_line),
    }
    if line:
        rec["line"] = int(line)
    if end_line:
        rec["end_line"] = int(end_line)
    rec["label"] = path + (f":{line}" if line else "")
    if end_line and line and int(end_line) != int(line):
        rec["label"] += f"-{end_line}"
    return rec


def parse_mention_flag(raw: str) -> dict | None:
    """``Name`` or ``Name:kind`` from a CLI flag."""
    text = (raw or "").strip()
    if not text:
        return None
    if ":" in text:
        name, kind = text.rsplit(":", 1)
        kind = kind.strip().lower()
        if kind in VALID_MENTION_KIND and name.strip():
            return normalize_mention({"name": name.strip(), "kind": kind})
    return normalize_mention({"name": text, "kind": "concept"})


def normalize_mentions(items: Iterable | None) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in items or []:
        rec = normalize_mention(item)
        if not rec:
            continue
        key = (
            rec["name"].lower(),
            rec["kind"],
            rec.get("path"),
            rec.get("line"),
            rec.get("t"),
            rec.get("url"),
        )
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
        return [normalize_ref(r) if isinstance(r, dict) else r for r in refs]
    return extract_references(text)
