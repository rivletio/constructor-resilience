"""Intentional share units with audience + forward grants.

Laws:
  - Share is never ambient; always a discrete unit (packet or item ref).
  - ``forward`` never escalates: receiver can only re-share ≤ original grant.
  - Circle/public policy is host-enforced; this module is pure grant logic.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
import uuid

Audience = Literal["direct", "circle", "public"]
Forward = Literal["none", "circle", "public"]

_FORWARD_RANK = {"none": 0, "circle": 1, "public": 2}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_share(
    *,
    from_id: str,
    to_id: str,
    atoms: List[str],
    audience: Audience = "direct",
    forward: Forward = "none",
    note: str = "",
    content_refs: Optional[List[Dict[str, Any]]] = None,
    topic_id: Optional[str] = None,
) -> dict:
    """Build an intentional share unit (packet-shaped + grant)."""
    if _FORWARD_RANK[forward] > _FORWARD_RANK.get(
        {"direct": "none", "circle": "circle", "public": "public"}[audience],
        0,
    ):
        # forward cannot exceed audience openness
        # direct audience ⇒ forward none only (tighten)
        if audience == "direct":
            forward = "none"
        elif audience == "circle" and forward == "public":
            forward = "circle"

    from .mentions import mentions_from_atoms
    from .search import as_text

    texts = [as_text(a) for a in atoms]
    doc = {
        "version": 1,
        "kind": "intentional_share",
        "share_id": str(uuid.uuid4()),
        "from": from_id,
        "to": to_id,
        "audience": audience,
        "forward": forward,
        "shared_at": now_iso(),
        "note": note,
        "topic_id": topic_id,
        "atoms": texts,
        "content_refs": content_refs or extract_content_refs(atoms),
        "mentions": mentions_from_atoms(atoms),
        "provenance": [{"source": from_id, "text": t} for t in texts],
    }
    return doc


def extract_content_refs(atoms: List) -> List[Dict[str, Any]]:
    """Pull URLs / youtube ids (with timestamp) from atom text and refs."""
    from .refs_util import extract_references, parse_youtube_url
    from .search import as_text

    refs: List[Dict[str, Any]] = []
    seen = set()

    def _add(ref: Dict[str, Any], atom_text: str) -> None:
        key = ref.get("youtube_video_id") or ref.get("url") or ref.get("id")
        if not key or key in seen:
            return
        seen.add(key)
        out = dict(ref)
        out.setdefault("atom", atom_text[:200])
        refs.append(out)

    for a in atoms:
        text = as_text(a)
        if isinstance(a, dict):
            for r in a.get("refs") or []:
                if not isinstance(r, dict):
                    continue
                rec = dict(r)
                url = rec.get("url") or ""
                yt = parse_youtube_url(url) if url else None
                if yt:
                    rec = {**yt, **{k: v for k, v in rec.items() if v is not None}}
                    rec["kind"] = "youtube_video"
                _add(rec, text)
        for r in extract_references(text):
            _add(r, text)
    return refs


def can_forward(share: dict, *, as_user: str, to_audience: Audience) -> tuple[bool, str]:
    """Whether ``as_user`` may re-share this unit to ``to_audience``."""
    if share.get("to") != as_user and share.get("audience") == "direct":
        # only the designated recipient holds a direct share
        if as_user != share.get("to"):
            return False, "not_recipient"
    fwd = share.get("forward") or "none"
    if fwd == "none":
        return False, "forward_none"
    if to_audience == "public" and fwd != "public":
        return False, "forward_cannot_escalate_to_public"
    if to_audience == "circle" and _FORWARD_RANK[fwd] < _FORWARD_RANK["circle"]:
        return False, "forward_cannot_escalate_to_circle"
    return True, "ok"


def re_share(
    share: dict,
    *,
    from_id: str,
    to_id: str,
    audience: Audience = "circle",
    note: str = "",
) -> dict:
    """Create a re-share hop; raises ValueError if grant forbids."""
    ok, reason = can_forward(share, as_user=from_id, to_audience=audience)
    if not ok:
        raise ValueError(f"re_share denied: {reason}")

    # Cap forward of child at parent forward (no escalate)
    parent_fwd = share.get("forward") or "none"
    child_fwd: Forward = parent_fwd  # type: ignore
    if audience == "direct":
        child_fwd = "none"
    elif audience == "circle" and parent_fwd == "public":
        child_fwd = "circle"  # receiver may choose tighter; default circle

    # If parent is circle-forward only, child forward stays ≤ circle
    if parent_fwd == "circle":
        child_fwd = "circle" if audience != "direct" else "none"

    child = make_share(
        from_id=from_id,
        to_id=to_id,
        atoms=list(share.get("atoms") or []),
        audience=audience,
        forward=child_fwd if audience != "direct" else "none",
        note=note or f"forwarded from {share.get('from')}",
        content_refs=deepcopy(share.get("content_refs") or []),
        topic_id=share.get("topic_id"),
    )
    child["parent_share_id"] = share.get("share_id")
    child["forwarded"] = True
    return child


def receive_as_topic_store(share: dict, *, receiver_id: str) -> dict:
    """Materialize a received share as an atoms store (circle copy-in).

    Claim text stays clean. Grant metadata lives on ``store.share``.
    """
    from .atoms import atom_text, make_atom

    atoms = []
    for a in share.get("atoms") or []:
        text = atom_text(a)
        if not text:
            continue
        rec = make_atom(
            text,
            method="received",
            source=str(share.get("from") or ""),
            review_status="accepted",
            mentions=a.get("mentions") if isinstance(a, dict) else None,
            refs=a.get("refs") if isinstance(a, dict) else None,
            constraint=a.get("constraint") if isinstance(a, dict) else None,
        )
        atoms.append(rec)
    cons = {f"{i},{i+1}": 0.55 for i in range(max(0, len(atoms) - 1))}
    return {
        "version": 1,
        "description": f"Received share {share.get('share_id')} from {share.get('from')} to {receiver_id}",
        "created": now_iso(),
        "updated": now_iso(),
        "atoms": atoms,
        "consistency": cons,
        "visibility": "circle" if share.get("audience") != "public" else "public",
        "share": {
            "share_id": share.get("share_id"),
            "from": share.get("from"),
            "to": share.get("to"),
            "audience": share.get("audience"),
            "forward": share.get("forward"),
            "parent_share_id": share.get("parent_share_id"),
            "content_refs": share.get("content_refs") or [],
            "mentions": share.get("mentions") or [],
        },
    }
