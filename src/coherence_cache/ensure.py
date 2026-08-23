"""Ensure overlapping content refs exist as raw items in a host store.

Intersection without ensure is hollow: a host can only act on *new*
when the receiver can open the raw object.

Host-agnostic core: extract refs, plan ensure against a local inbox of JSON
items with a `url` field (optional `feeds/inbox_items/` layout).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def refs_from_atoms(atoms: List[str]) -> List[Dict[str, Any]]:
    from .share import extract_content_refs

    return extract_content_refs(atoms)


def refs_from_packet(packet: dict) -> List[Dict[str, Any]]:
    refs = list(packet.get("content_refs") or [])
    if refs:
        return refs
    return refs_from_atoms(list(packet.get("atoms") or []))


def vault_has_url(vault_root: Path, url: str) -> Optional[int]:
    """Return inbox item id if url already present, else None."""
    url_l = url.strip().rstrip("/")
    vid = None
    m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", url_l)
    if m:
        vid = m.group(1)

    inbox = vault_root / "feeds" / "inbox_items"
    if not inbox.is_dir():
        return None
    for p in inbox.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        u = (d.get("url") or "").strip().rstrip("/")
        if u == url_l or (vid and vid in u):
            iid = d.get("id")
            if isinstance(iid, int):
                return iid
            try:
                return int(iid)
            except Exception:
                return None
    return None


def plan_ensure(
    packet: dict,
    vault_root: Path,
) -> Dict[str, Any]:
    """Classify refs: already_local vs need_fetch."""
    refs = refs_from_packet(packet)
    already = []
    need = []
    for r in refs:
        url = r.get("url") or ""
        if not url:
            continue
        iid = vault_has_url(vault_root, url)
        if iid is not None:
            already.append({**r, "item_id": iid, "status": "local"})
        else:
            need.append({**r, "status": "need_fetch"})
    return {
        "version": 1,
        "kind": "ensure_plan",
        "already_local": already,
        "need_fetch": need,
        "local_count": len(already),
        "fetch_count": len(need),
    }


def ensure_packet_content(
    packet: dict,
    vault_root: Path,
) -> Dict[str, Any]:
    """Plan which cited refs are already local vs still need a host fetch."""
    plan = plan_ensure(packet, vault_root)
    return {
        "plan": plan,
        "ready": list(plan["already_local"]),
        "not_ready": list(plan["need_fetch"]),
    }
