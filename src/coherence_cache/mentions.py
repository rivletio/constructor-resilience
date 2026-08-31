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

# A mention is garbage when it is not attested in the claim.
# grounding = max(compact_hit, token_cover, initialism_hit) in [0, 1]
#   compact_hit: 1 if compact(name) (len≥3) is a substring of compact(text)
#                (hyphens/spaces dropped: compact name is a substring of compact text)
#   token_cover: fraction of name tokens (len≥2) that hit the text
#   initialism_hit: 1 if compact(name) equals initials of a title-case phrase
#                in the claim
# Aliases are scored the same way as the name.
# Anaphora ("It predicts…") is not attestation — the claim is not stand-alone.
# A locator is not attestation — it pins an artifact, not this sentence.
# Threshold 0.5 = at least half the name tokens, or compact/initialism hit.
MENTION_GROUND_MIN = 0.5


def _compact_alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _word_tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def _token_attested(tok: str, text_toks: set[str]) -> bool:
    if tok in text_toks:
        return True
    for t in text_toks:
        if len(t) > 4 and t.endswith("s") and t[:-1] == tok:
            return True
        if len(tok) > 4 and tok.endswith("s") and tok[:-1] == t:
            return True
        if t.startswith(tok) and 0 < len(t) - len(tok) <= 2:
            return True
        if tok.startswith(t) and 0 < len(tok) - len(t) <= 2:
            return True
    return False


_DUMMY_IT = re.compile(
    r"(?is)^it\s+(is|was|will\s+be|has\s+been|seems|appears)\b"
)
_ANAPHOR_SLOT = re.compile(
    r"(?is)(?:^|\b)("
    r"the\s+same"
    r"|this\s+(?:method|model|paper|architecture|objective|approach|claim)"
    r"|the\s+(?:method|model|paper|architecture|objective|author)"
    r")\b"
)
_PRONOUN_SUBJ = re.compile(
    r"(?is)^(it|they|this|these|that)\s+"
    r"(?!is\b|was\b|will\b|has\b|seems\b|appears\b)"
)


def claim_has_referential_anaphor(text: str) -> bool:
    """True when the sentence has a hole a mention could fill (not dummy 'it is')."""
    t = (text or "").strip()
    if not t:
        return False
    if _DUMMY_IT.match(t):
        return False
    return bool(_PRONOUN_SUBJ.match(t) or _ANAPHOR_SLOT.search(t))


def declared_mention_names(atom) -> set[str]:
    """Names hung on the structured record (not extracted from prose)."""
    out: set[str] = set()
    if not isinstance(atom, dict):
        return out
    for m in atom.get("mentions") or []:
        if isinstance(m, dict):
            n = str(m.get("name") or "").strip().lower()
            for al in m.get("aliases") or []:
                if str(al).strip():
                    out.add(str(al).strip().lower())
        else:
            n = str(m).strip().lower()
        if n:
            out.add(n)
    return out


def mention_attested_score(
    name: str,
    atom,
    *,
    aliases: list | None = None,
) -> float:
    """Grounding in the sentence, or 0.6 if this atom's mention fills an anaphor."""
    if isinstance(atom, dict):
        text = str(atom.get("text") or "")
        als = aliases if aliases is not None else None
        if als is None:
            for m in atom.get("mentions") or []:
                if isinstance(m, dict) and str(m.get("name") or "").strip().lower() == str(name).strip().lower():
                    als = m.get("aliases")
                    break
    else:
        text = str(atom or "")
        als = aliases
    g = mention_grounding(name, text, aliases=als)
    if g >= MENTION_GROUND_MIN:
        return g
    if claim_has_referential_anaphor(text) and str(name).strip().lower() in declared_mention_names(
        atom if isinstance(atom, dict) else {"mentions": [{"name": name}]}
    ):
        return 0.6
    return g


def mention_attestation_fail(
    name: str,
    atom,
    *,
    aliases: list | None = None,
) -> str | None:
    """Actionable FAIL if ``name`` is not attested on this atom, else None.

    Anaphor is attested when the mention hangs on this atom: packet/share
    carry that join with the claim.
    """
    g = mention_attested_score(name, atom, aliases=aliases)
    if g >= MENTION_GROUND_MIN:
        return None
    return (
        f"mention {name!r} not attested ({g:.2f}); "
        f"put the name or ALIAS in the sentence, or drop the join"
    )


def mention_grounding(
    name: str,
    text: str,
    *,
    aliases: list | None = None,
) -> float:
    """How attested ``name`` is in ``text``, in ``[0, 1]``.

    0.0 — name does not appear (garbage tag).
    1.0 — compact form or every name token is in the claim.
    """
    blob = text
    if not isinstance(blob, str):
        blob = str((blob or {}).get("text") if isinstance(blob, dict) else blob or "")
    best = 0.0
    for n in [name, *(aliases or [])]:
        n = str(n or "").strip()
        if not n:
            continue
        best = max(best, _ground_one(n, blob))
        if best >= 1.0:
            return 1.0
    return best


def _phrase_initialisms(text: str) -> set[str]:
    """Initials of title-case runs in ``text``."""
    out: set[str] = set()
    for m in re.finditer(
        r"\b[A-Z][a-z0-9]*(?:\s+[A-Z][a-z0-9]*)+\b", text or ""
    ):
        words = m.group(0).split()
        if 2 <= len(words) <= 8:
            out.add("".join(w[0] for w in words).lower())
    return out


def _ground_one(name: str, text: str) -> float:
    cn, ct = _compact_alnum(name), _compact_alnum(text)
    ntoks = {t for t in _word_tokens(name) if len(t) >= 2}
    ttoks = _word_tokens(text)
    scores: list[float] = []
    if ntoks:
        hits = sum(1 for t in ntoks if _token_attested(t, ttoks))
        scores.append(hits / len(ntoks))
    if len(cn) >= 3 and cn in ct:
        scores.append(1.0)
    elif len(cn) >= 3:
        for t in ttoks:
            if len(t) >= 3 and (cn in t or t in cn):
                scores.append(1.0)
                break
    elif cn and cn in ttoks:
        scores.append(1.0)
    if cn and 2 <= len(cn) <= 8 and cn in _phrase_initialisms(text):
        scores.append(1.0)
    return max(scores) if scores else 0.0


def join_grounding(a, b) -> float:
    """Best shared mention: min(grounding on A, grounding on B).

    0.0 if they share no name, or every shared name is unattested on one side.
    """
    def _names(atom) -> tuple[set[str], str]:
        out: set[str] = set()
        if isinstance(atom, dict):
            blob = str(atom.get("text") or "")
            for m in atom.get("mentions") or []:
                if isinstance(m, dict):
                    n = str(m.get("name") or "").strip().lower()
                    for al in m.get("aliases") or []:
                        if str(al).strip():
                            out.add(str(al).strip().lower())
                else:
                    n = str(m).strip().lower()
                if n:
                    out.add(n)
        else:
            blob = str(atom or "")
        blob = blob.strip()
        for m in extract_mentions(blob):
            n = str(m.get("name") or "").strip().lower()
            if n:
                out.add(n)
        return out, blob

    na, ta = _names(a)
    nb, tb = _names(b)
    shared = na & nb
    if not shared:
        return 0.0
    best = 0.0
    for n in shared:
        g = min(mention_attested_score(n, a), mention_attested_score(n, b))
        if g > best:
            best = g
    return best

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


def fill_locator(rec: dict[str, Any]) -> dict[str, Any]:
    """Normalize file/video/article locator keys and clickable url/label."""
    return _fill_mention_locator(rec)


def locator_label(rec: dict | None) -> str:
    """Short where-string for logs: path:line, t=label, or url."""
    if not isinstance(rec, dict):
        return ""
    if rec.get("label"):
        return str(rec["label"])
    if rec.get("t_label"):
        return f"t={rec['t_label']}"
    if rec.get("t") is not None:
        return f"t={rec['t']}"
    if rec.get("url"):
        return str(rec["url"])
    return ""


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
    """Locator: ``path:LINE``, ``path#L42-L48``, ``t=SECONDS``, ``p.N ¶M``, or a URL."""
    text = (raw or "").strip().strip("'\"")
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
    pm = re.search(
        r"p(?:age)?[=.\s]*(\d+)(?:\s*[&,;]?\s*(?:¶+|para(?:graph)?[=.\s]*)(\d+))?",
        text,
        re.I,
    )
    if pm and re.match(r"^(p(?:age)?[=.\s]|¶)", text, re.I):
        rec: dict[str, Any] = {"page": int(pm.group(1))}
        if pm.group(2):
            rec["paragraph"] = int(pm.group(2))
        rec["label"] = f"p.{rec['page']}" + (f" ¶{rec['paragraph']}" if rec.get("paragraph") else "")
        return rec
    m = re.match(r"(.+?)#L(\d+)(?:-L(\d+))?$", text, re.I)
    if m:
        return _file_loc(m.group(1), int(m.group(2)), int(m.group(3)) if m.group(3) else None)
    m = re.match(r"(.+):(\d+)(?:-(\d+))?$", text)
    if m and "://" not in m.group(1):
        return _file_loc(m.group(1), int(m.group(2)), int(m.group(3)) if m.group(3) else None)
    m = re.match(r"(.+?)\s+line\s+(\d+)\s*$", text, re.I)
    if m:
        return _file_loc(m.group(1), int(m.group(2)), None)
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
    """``Name``, ``Name:kind``, or ``Name:kind @ path:LINE``."""
    text = (raw or "").strip().strip("'\"")
    if not text:
        return None
    loc = None
    if " @" in text:
        text, loc_raw = text.rsplit(" @", 1)
        loc = parse_at_flag(loc_raw.strip())
        text = text.strip()
    rec = None
    if ":" in text:
        name, kind = text.rsplit(":", 1)
        kind = kind.strip().lower()
        if kind in VALID_MENTION_KIND and name.strip():
            rec = normalize_mention({"name": name.strip(), "kind": kind})
    if rec is None:
        rec = normalize_mention({"name": text, "kind": "concept"})
    if rec and loc:
        rec.update(loc)
        rec = _fill_mention_locator(rec)
    return rec


def parse_pack_draft(blob: str, default_constraint: str | None = "fact") -> tuple[str | None, list[dict]]:
    """Labeled TITLE/CLAIM/MENTION/AT block for small hosts. Returns (title, items)."""
    text = (blob or "").strip()
    text = re.sub(r"^```(?:\w+)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    title = None
    constraint = default_constraint
    items: list[dict] = []
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        numbered = re.match(r"^(\d+)[\.)]?\s+(\S.*)$", line)
        if numbered and not re.match(r"^\d+:", line):
            current = {"text": numbered.group(2).strip(), "mentions": []}
            if constraint:
                current["constraint"] = constraint
            items.append(current)
            continue
        if ":" not in line:
            if current and current.get("text"):
                current["text"] = current["text"] + " " + line
            elif title is None and line[0].isalnum():
                title = line
            continue
        key, val = line.split(":", 1)
        key = key.strip().upper()
        val = val.strip()
        if key in ("TITLE", "THEME"):
            title = val or title
        elif key == "CONSTRAINT" and val:
            constraint = val.lower()
        elif key in ("CLAIM", "ATOM"):
            current = {"text": val, "mentions": []}
            if constraint:
                current["constraint"] = constraint
            items.append(current)
        elif key in ("MENTION", "JOIN") and current is not None:
            rec = parse_mention_flag(val)
            if rec:
                current.setdefault("mentions", []).append(rec)
        elif key == "ALIAS" and current is not None:
            mentions = current.get("mentions") or []
            if mentions and val:
                mentions[-1].setdefault("aliases", []).append(val)
        elif key == "AT" and current is not None:
            loc = parse_at_flag(val)
            if not loc:
                continue
            mentions = current.get("mentions") or []
            if mentions:
                mentions[-1].update(loc)
                current["mentions"][-1] = _fill_mention_locator(mentions[-1])
            else:
                current["at"] = _fill_mention_locator(loc)
    for it in items:
        if not it.get("mentions"):
            it.pop("mentions", None)
    return title, items


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
