"""Ensure overlapping content refs exist as raw items in a host store.

Intersection without ensure is hollow: a host can only act on *new*
when the receiver can open the raw object.

Host-agnostic core: extract refs, plan ensure against a local inbox of JSON
items with a `url` field (optional `feeds/inbox_items/` layout). Optional
HTTP fetch uses a host dispatch endpoint (`POST {api_base}/api/voice/dispatch`).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
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


def dispatch_ensure_url(
    api_base: str,
    token: str,
    url: str,
    *,
    timeout: float = 90.0,
) -> Dict[str, Any]:
    """
    Best-effort ensure via host voice/text dispatch:
      POST {api_base}/api/voice/dispatch  {"text": "open <url>", "execute": true}
    Returns a dispatch body summary. Any host that speaks this endpoint works.
    """
    api_base = api_base.rstrip("/")
    text = f"open {url}"
    body = json.dumps({"text": text, "execute": True}).encode()
    req = urllib.request.Request(
        f"{api_base}/api/voice/dispatch",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"http_{e.code}", "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e), "url": url}

    ex = data.get("execution") or {}
    item_id = None
    for a in ex.get("actions") or []:
        if a.get("type") == "open_item":
            params = a.get("params") or {}
            item_id = params.get("item_id") or params.get("itemId")
            break
    arts = ex.get("articles") or []
    if item_id is None and arts:
        item_id = arts[0].get("itemId") or arts[0].get("feedEntryId")

    return {
        "ok": bool(data.get("matched")),
        "url": url,
        "pattern_id": data.get("pattern_id"),
        "spoken": (ex.get("spoken_detail") or data.get("confirmation") or "")[:200],
        "item_id": item_id,
        "kind": ex.get("kind") or ex.get("action_type"),
        "executed": ex.get("executed"),
    }


def ensure_packet_content(
    packet: dict,
    vault_root: Path,
    *,
    api_base: Optional[str] = None,
    token: Optional[str] = None,
    fetch: bool = True,
) -> Dict[str, Any]:
    """Plan + optionally fetch missing refs via host dispatch."""
    plan = plan_ensure(packet, vault_root)
    results = []
    if fetch and api_base and token:
        for r in plan["need_fetch"]:
            url = r["url"]
            atom = r.get("atom") or ""
            title_guess = None
            if ":" in atom:
                m = re.search(r":\s*(.+?)\s*[\(|—]", atom)
                if m:
                    title_guess = m.group(1).strip()
            if title_guess and len(title_guess) > 8:
                text = f"open {title_guess}"
                body = json.dumps({"text": text, "execute": True}).encode()
                req = urllib.request.Request(
                    f"{api_base.rstrip('/')}/api/voice/dispatch",
                    data=body,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=90) as resp:
                        data = json.loads(resp.read().decode())
                    ex = data.get("execution") or {}
                    item_id = None
                    for a in ex.get("actions") or []:
                        if a.get("type") == "open_item":
                            item_id = (a.get("params") or {}).get("item_id")
                            break
                    results.append({
                        "url": url,
                        "via": "title_open",
                        "ok": bool(data.get("matched")),
                        "pattern_id": data.get("pattern_id"),
                        "spoken": (ex.get("spoken_detail") or data.get("confirmation") or "")[:160],
                        "item_id": item_id,
                    })
                    continue
                except Exception as e:
                    results.append({"url": url, "via": "title_open", "ok": False, "error": str(e)})

            results.append(dispatch_ensure_url(api_base, token, url))

    plan_after = plan_ensure(packet, vault_root)
    return {
        "plan_before": plan,
        "fetch_results": results,
        "plan_after": plan_after,
        "voice_ready": [
            {**r, "voice": "can_announce_and_open"}
            for r in plan_after["already_local"]
        ],
        "not_ready": plan_after["need_fetch"],
    }
