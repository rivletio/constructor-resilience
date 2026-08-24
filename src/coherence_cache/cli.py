#!/usr/bin/env python3
"""coherence CLI — durable claims, packets, and share files."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .paths import get_root, set_root, ensure_meta, meta_path, active_path
from . import refs_util as _refs_mod
from . import search as resilience_search
from .atoms import (
    REVIEW_ACCEPTED,
    REVIEW_PENDING,
    VALID_REVIEW,
    active_atoms,
    atom_review_status,
    atom_text,
    atom_texts,
    back_out,
    coerce_atom,
    make_atom,
    normalize_store_atoms,
    parse_ingest_payload,
    set_review,
)

extract_references = _refs_mod.extract_references
linkify_claim = _refs_mod.linkify_claim

def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def load_meta() -> dict:
    ensure_meta()
    meta = load_json(meta_path())
    if not meta:
        raise SystemExit(f"Meta-store not found: {meta_path()}")
    return meta


def save_meta(meta: dict) -> None:
    meta["updated"] = now_iso()
    save_json(meta_path(), meta)


def get_active() -> dict | None:
    return load_json(active_path())


def set_active(topic_id: str, meta: dict | None = None) -> dict:
    meta = meta or load_meta()
    topic = next((t for t in meta.get("topics", []) if t["id"] == topic_id), None)
    if not topic:
        raise SystemExit(f"Unknown topic id: {topic_id}")
    active = {
        "topic_id": topic_id,
        "path": topic["path"],
        "title": topic.get("title", topic_id),
        "atoms_path": str(get_root() / topic["path"] / "atoms.json"),
        "set_at": now_iso(),
    }
    save_json(active_path(), active)
    return active


def topic_atoms_path(topic: dict) -> Path:
    return get_root() / topic["path"] / "atoms.json"


def empty_store(description: str) -> dict:
    ts = now_iso()
    return {
        "version": 1,
        "description": description,
        "created": ts,
        "updated": ts,
        "atoms": [],
        "consistency": {},
        "notes": [
            "atoms: ordered list of knowledge atoms (strings).",
            "consistency: object with keys 'i,j' (i < j) mapping to scores in [-1.0, 1.0].",
        ],
    }


def cmd_status(_args):
    meta = load_meta()
    active = get_active()
    print(f"Knowledge root: {get_root()}")
    print(f"Topics: {len(meta.get('topics', []))}")
    print(f"Meta links: {len(meta.get('links', []))}")
    if active:
        print(f"Active topic: {active['topic_id']} — {active.get('title')}")
        print(f"  atoms: {active.get('atoms_path')}")
        p = Path(active["atoms_path"])
        if p.exists():
            store = load_json(p)
            print(f"  atom_count: {len(store.get('atoms', []))}")
            print(f"  edge_count: {len(store.get('consistency', {}))}")
            pending = sum(
                1
                for a in (store.get("atoms") or [])
                if atom_review_status(a) == REVIEW_PENDING
            )
            if pending:
                print(f"  pending_review: {pending}")
    else:
        print("Active topic: (none)")
        if not meta.get("topics"):
            print('  Pack claims:  coherence pack --title "Theme" --atom "Durable claim."')
        else:
            print("  Zoom in:      coherence use <topic-id>")


def cmd_list(_args):
    meta = load_meta()
    active = get_active() or {}
    active_id = active.get("topic_id")
    for t in meta.get("topics", []):
        mark = " *" if t["id"] == active_id else ""
        print(f"{t['id']}{mark}")
        print(f"  {t.get('title', '')}")
        print(f"  atoms={t.get('atom_count', '?')} edges={t.get('edge_count', '?')}  {t.get('path')}")
        if t.get("description"):
            print(f"  {t['description'][:120]}")
        print()


def cmd_use(args):
    active = set_active(args.topic_id)
    print(f"Active topic → {active['topic_id']}")
    print(f"  {active['atoms_path']}")


def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:64] or "topic"


def create_topic(
    *,
    title: str,
    topic_id: str | None = None,
    description: str = "",
    tags: list | None = None,
    use: bool = False,
    exist_ok: bool = False,
) -> dict:
    meta = load_meta()
    topic_id = topic_id or slugify(title)
    existing = next((t for t in meta.get("topics", []) if t["id"] == topic_id), None)
    if existing:
        if not exist_ok:
            raise SystemExit(f"Topic already exists: {topic_id}")
        if use:
            set_active(topic_id, meta)
        return existing

    rel_path = f"topics/{topic_id}"
    topic_dir = get_root() / rel_path
    topic_dir.mkdir(parents=True, exist_ok=True)

    description = description or title
    store = empty_store(description)
    atoms_path = topic_dir / "atoms.json"
    save_json(atoms_path, store)

    topic = {
        "id": topic_id,
        "title": title,
        "path": rel_path,
        "description": description,
        "atom_count": 0,
        "edge_count": 0,
        "created": now_iso(),
        "updated": now_iso(),
        "tags": tags or [],
    }
    meta.setdefault("topics", []).append(topic)
    save_meta(meta)

    if use or not get_active():
        set_active(topic_id, meta)
    return topic


def cmd_create(args):
    topic = create_topic(
        title=args.title,
        topic_id=args.id,
        description=args.description or "",
        tags=args.tags or [],
        use=bool(args.use),
    )
    print(f"Created topic: {topic['id']}")
    print(f"  {topic_atoms_path(topic)}")


def cmd_path(_args):
    active = get_active()
    if not active:
        raise SystemExit("No active topic. Run: coherence use <topic-id>")
    print(active["atoms_path"])


def refresh_topic_counts(topic_id: str):
    meta = load_meta()
    topic = next((t for t in meta["topics"] if t["id"] == topic_id), None)
    if not topic:
        return
    store = load_json(topic_atoms_path(topic), {})
    topic["atom_count"] = len(store.get("atoms", []))
    topic["edge_count"] = len(store.get("consistency", {}))
    topic["updated"] = now_iso()
    save_meta(meta)


def _no_topic_exit() -> None:
    raise SystemExit(
        "No active topic.\n"
        '  Pack claims:  coherence pack --title "Theme" --atom "Durable claim."\n'
        "  Or zoom in:   coherence use <topic-id>"
    )


def load_active_store():
    active = get_active()
    if not active:
        _no_topic_exit()
    path = Path(active["atoms_path"])
    store = load_json(path)
    if store is None:
        raise SystemExit(f"Store missing: {path}")
    return active, path, store


def parse_consistency_map(store: dict) -> dict:
    """Return dict[(i,j), float] from JSON string keys 'i,j'."""
    out = {}
    for key, score in (store.get("consistency") or {}).items():
        try:
            if isinstance(key, str) and "," in key:
                i, j = map(int, key.split(","))
            elif isinstance(key, (list, tuple)) and len(key) == 2:
                i, j = int(key[0]), int(key[1])
            else:
                continue
            a, b = (i, j) if i < j else (j, i)
            out[(a, b)] = float(score)
        except Exception:
            continue
    return out


def dump_consistency_map(cons: dict) -> dict:
    return {f"{i},{j}": round(float(s), 4) for (i, j), s in sorted(cons.items())}


def token_set(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def heuristic_pair_score(a, b) -> float:
    """Cheap lexical overlap heuristic in [-0.2, 0.85]. Not a substitute for LLM judgment."""
    ta, tb = token_set(atom_text(a)), token_set(atom_text(b))
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    jacc = inter / union if union else 0.0
    # map Jaccard to mild positive consistency; leave room for human/LLM overrides
    return round(min(0.85, max(0.0, jacc * 1.2 - 0.05)), 4)



def cmd_render(args):
    """Render active topic consistency graph as PNG."""
    active = get_active()
    if not active:
        raise SystemExit("No active topic. Run: coherence use <topic-id>")
    store_path = Path(active["atoms_path"])
    out_path = store_path.with_name("atoms_graph.png")
    from .render_graph_png import render as render_graph
    try:
        render_graph(store_path, out_path)
    except ImportError as e:
        raise SystemExit(
            f"Graph render requires matplotlib + networkx ({e}). "
            "pip install constructor-resilience[viz]"
        ) from e
    print(out_path)



def _append_scored_atom(store: dict, atom, *, auto_score: bool = False, min_abs: float = 0.05):
    atoms = store.setdefault("atoms", [])
    atoms.append(atom)
    idx = len(atoms) - 1
    cons = parse_consistency_map(store)
    if auto_score and idx > 0:
        for i in range(idx):
            s = heuristic_pair_score(atoms[i], atom)
            if abs(s) >= min_abs:
                cons[(i, idx)] = s
        store["consistency"] = dump_consistency_map(cons)
    return idx, cons


def cmd_add_atom(args):
    active, path, store = load_active_store()
    text = args.text.strip()
    if not text:
        raise SystemExit("Empty atom")
    # Structured by default so review/provenance works; --plain keeps legacy string.
    if getattr(args, "plain", False):
        atom = text
        status = REVIEW_ACCEPTED
    else:
        status = REVIEW_PENDING if getattr(args, "pending", False) else REVIEW_ACCEPTED
        atom = make_atom(
            text,
            method="manual",
            source="add-atom",
            review_status=status,
            constraint=getattr(args, "constraint", None),
        )
    idx, cons = _append_scored_atom(store, atom, auto_score=bool(args.auto_score))
    store["updated"] = now_iso()
    save_json(path, store)
    refresh_topic_counts(active["topic_id"])
    print(f"Added atom #{idx} to {active['topic_id']} [{status}]")
    if args.auto_score:
        linked = sum(1 for (i, j) in cons if j == idx or i == idx)
        print(f"  auto-score edges involving new atom: {linked}")


def _items_from_args(args) -> list:
    """Collect claims from --atom, --json, --text, or non-tty stdin. Never block on a TTY."""
    items: list = []
    for raw_atom in getattr(args, "atom", None) or []:
        text = (raw_atom or "").strip()
        if text:
            items.append(text)
    blob = None
    if getattr(args, "json", None):
        blob = Path(args.json).expanduser().read_text(encoding="utf-8")
    elif getattr(args, "text", None):
        blob = args.text
    elif not items and not sys.stdin.isatty():
        blob = sys.stdin.read()
    if blob and str(blob).strip():
        try:
            items.extend(parse_ingest_payload(json.loads(blob)))
        except (json.JSONDecodeError, ValueError) as e:
            raise SystemExit(f"ingest JSON: {e}") from e
    if not items:
        raise SystemExit(
            'Need claims:  --atom "Durable claim."  (repeatable)\n'
            "           or --json claims.json  or --text JSON"
        )
    constraint = getattr(args, "constraint", None)
    if constraint:
        out = []
        for item in items:
            if isinstance(item, str):
                out.append({"text": item, "constraint": constraint})
            else:
                rec = dict(item)
                rec.setdefault("constraint", constraint)
                out.append(rec)
        return out
    return items


def cmd_ingest(args):
    """Load claims written by the session (no extra model)."""
    items = _items_from_args(args)

    if getattr(args, "title", None):
        create_topic(title=args.title, topic_id=args.topic, use=True, exist_ok=True)
    elif getattr(args, "topic", None):
        set_active(args.topic)

    active, path, store = load_active_store()
    status = REVIEW_PENDING if getattr(args, "pending", False) else REVIEW_ACCEPTED
    seen = {atom_text(a).lower() for a in (store.get("atoms") or [])}
    added = 0
    skipped = 0
    for item in items:
        try:
            atom = coerce_atom(
                item,
                method="ingest",
                review_status=status,
                source=args.source or "ingest",
            )
        except ValueError as e:
            print(f"  skip: {e}")
            skipped += 1
            continue
        key = atom_text(atom).lower()
        if key in seen:
            print(f"  skip (duplicate): {atom_text(atom)}")
            skipped += 1
            continue
        seen.add(key)
        idx, _cons = _append_scored_atom(store, atom, auto_score=bool(args.auto_score))
        added += 1
        mcount = len(atom.get("mentions") or []) if isinstance(atom, dict) else 0
        rcount = len(atom.get("refs") or []) if isinstance(atom, dict) else 0
        extra = ""
        if mcount or rcount:
            extra = f" mentions={mcount} refs={rcount}"
        print(f"  [{idx}]{extra} {atom_text(atom)}")
    store["updated"] = now_iso()
    save_json(path, store)
    refresh_topic_counts(active["topic_id"])
    print(
        f"Ingested {added} atom(s) → {active['topic_id']} [{status}]"
        + (f" skipped={skipped}" if skipped else "")
        + (" (auto-scored)" if args.auto_score else "")
    )
    if added and not getattr(args, "no_packet", False):
        rebuilt = _rebuild_greedy_packet(
            active, path, store, max_size=int(getattr(args, "max_size", 6) or 6)
        )
        if rebuilt:
            print(f"  packet {rebuilt}")


def cmd_pack(args):
    """Ingest claims and print the resume packet (the 'pack this session' verb)."""
    if not getattr(args, "title", None) and not getattr(args, "topic", None) and not get_active():
        raise SystemExit(
            'pack needs --title "Theme" (or an active topic) and at least one --atom'
        )
    if not getattr(args, "auto_score", False):
        args.auto_score = True
    cmd_ingest(args)
    active, path, store = load_active_store()
    packet_path = Path(path).with_name("packet.json")
    if not packet_path.exists():
        raise SystemExit("pack: no packet written (no active atoms)")
    doc = load_json(packet_path, {}) or {}
    print(f"packed {active['topic_id']}  size={len(doc.get('atoms') or [])}")
    for i, a in enumerate(doc.get("atoms") or []):
        print(f"  [{i}] {a}")


def cmd_share(args):
    """Write an intentional share envelope from the active packet."""
    from .share import make_share

    active, path, store = load_active_store()
    path = Path(path)
    packet_path = path.with_name("packet.json")
    if args.rebuild or not packet_path.exists():
        rebuilt = _rebuild_greedy_packet(active, path, store, max_size=args.max_size)
        if not rebuilt:
            raise SystemExit("No active atoms to share")
        packet_path = Path(rebuilt)
    packet = load_json(packet_path, {}) or {}
    texts = [atom_text(a) for a in (packet.get("atoms") or [])]
    if not texts:
        raise SystemExit("Packet is empty — run: coherence search --greedy")

    # Join mentions from the source atoms (by text match)
    source_atoms = []
    full = store.get("atoms") or []
    by_text = {atom_text(a): a for a in full}
    for t in texts:
        source_atoms.append(by_text.get(t, t))

    share = make_share(
        from_id=args.from_id,
        to_id=args.to,
        atoms=source_atoms,
        audience=args.audience,
        forward=args.forward,
        note=args.note or "",
        topic_id=active.get("topic_id"),
    )
    share["packet"] = {
        "atom_indices": packet.get("atom_indices") or [],
        "method": packet.get("method"),
        "energy": packet.get("energy"),
        "max_size": packet.get("max_size"),
    }
    out = Path(args.out) if args.out else path.with_name("share.json")
    save_json(out, share)
    print(f"wrote {out}")
    print(
        f"share {share['share_id']}  {share['from']} → {share['to']}  "
        f"audience={share['audience']} forward={share['forward']}  "
        f"atoms={len(share['atoms'])} mentions={len(share.get('mentions') or [])}"
    )
    for i, a in enumerate(share["atoms"]):
        print(f"  [{i}] {a}")


def cmd_import(args):
    """Import atoms.json, packet.json, or an intentional_share as a topic."""
    src = Path(args.path).expanduser()
    data = load_json(src)
    if not data:
        raise SystemExit(f"Missing or empty: {src}")

    kind = data.get("kind") if isinstance(data, dict) else None
    title = args.title
    topic_id = args.topic
    items = []
    cons_in = {}
    share_meta = None

    if isinstance(data, list):
        items = data
    elif kind == "intentional_share":
        items = data.get("atoms") or []
        title = title or data.get("topic_id") or f"from-{data.get('from') or 'share'}"
        share_meta = {
            "share_id": data.get("share_id"),
            "from": data.get("from"),
            "to": data.get("to"),
            "audience": data.get("audience"),
            "forward": data.get("forward"),
            "content_refs": data.get("content_refs") or [],
            "mentions": data.get("mentions") or [],
        }
    elif "atoms" in data:
        items = data.get("atoms") or []
        cons_in = data.get("consistency") or {}
        title = title or data.get("description") or src.parent.name
    else:
        raise SystemExit("import expects atoms.json, a packet, or kind=intentional_share")

    if not items:
        raise SystemExit("import: no atoms in source")

    topic = create_topic(
        title=title or src.stem,
        topic_id=topic_id,
        description=args.title or title or "",
        use=bool(args.use),
        exist_ok=True,
    )
    set_active(topic["id"])
    active, path, store = load_active_store()
    status = REVIEW_ACCEPTED if args.accepted else REVIEW_PENDING
    method = "received" if kind == "intentional_share" else "imported"
    start = len(store.get("atoms") or [])
    for item in items:
        atom = coerce_atom(
            item,
            method=method,
            review_status=status,
            source=str(src),
        )
        _append_scored_atom(store, atom, auto_score=bool(args.auto_score))
    if cons_in and start == 0:
        store["consistency"] = cons_in
    if share_meta:
        store["share"] = share_meta
        vis = share_meta.get("audience")
        if vis == "public":
            store["visibility"] = "public"
        elif vis:
            store["visibility"] = "circle"
    store["updated"] = now_iso()
    save_json(path, store)
    refresh_topic_counts(active["topic_id"])
    print(f"Imported {len(items)} atom(s) → {active['topic_id']}")
    print(f"  {path}")


def cmd_mint(args):
    """Mint durable atoms from source text/file via local MLX (pending review)."""
    from . import mint as mint_mod
    from . import mlx_backend
    from .config import CFG

    active, path, store = load_active_store()
    if args.ensure_model:
        mid = mlx_backend.ensure_model(args.model)
        print(f"model ready: {mid}")
    source_loaders = {
        "file": lambda: (
            Path(args.file).expanduser().read_text(encoding="utf-8"),
            str(Path(args.file)),
        ),
        "text": lambda: (args.text or "", "stdin/arg"),
    }
    source, source_label = source_loaders["file" if args.file else "text"]()
    if not source.strip():
        raise SystemExit("mint requires --text or --file")
    cfg = CFG.replace(
        mlx_model=args.model or CFG.mlx_model,
        mint_max_atoms=args.max_atoms,
        mint_min_grounding=args.min_grounding,
    )
    result = mint_mod.mint_from_text(
        source,
        theme=args.theme or active.get("title"),
        model=args.model,
        existing=store.get("atoms") or [],
        cfg=cfg,
    )
    atoms = store.setdefault("atoms", [])
    cons = parse_consistency_map(store)
    added = 0
    for rec in result["atoms"]:
        if args.auto_accept:
            rec["review"]["status"] = REVIEW_ACCEPTED
            rec["review"]["reviewed_at"] = now_iso()
        atoms.append(rec)
        idx = len(atoms) - 1
        added += 1
        if args.auto_score and idx > 0:
            for i in range(idx):
                s = heuristic_pair_score(atoms[i], rec)
                if abs(s) >= 0.05:
                    cons[(i, idx)] = s
        g = (rec.get("extra") or {}).get("grounding")
        gtag = f" g={g}" if g is not None else ""
        print(f"  [{idx}]{gtag} {atom_text(rec)}")
    for d in result.get("dropped") or []:
        print(f"  dropped ({d.get('reason')} g={d.get('grounding')}): {d.get('text','')[:90]}")
    if args.auto_score:
        store["consistency"] = dump_consistency_map(cons)
    store["updated"] = now_iso()
    save_json(path, store)
    refresh_topic_counts(active["topic_id"])
    n_drop = len(result.get("dropped") or [])
    print(
        f"Minted {added} pending atom(s) via {result['model']} "
        f"(dropped {n_drop} ungrounded) from {source_label} "
        f"→ review with: coherence review --serve   # add --browser only if asked"
    )


def _atom_at(store: dict, idx: int, expected_text: str | None = None):
    atoms = store.get("atoms") or []
    if not (0 <= idx < len(atoms)):
        raise SystemExit(f"atom index {idx} out of range (n={len(atoms)})")
    atom = atoms[idx]
    if expected_text is not None and atom_text(atom) != expected_text.strip():
        raise SystemExit(
            f"atom #{idx} text does not match --text\n  have: {atom_text(atom)}"
        )
    return atoms, atom


def _rebuild_greedy_packet(active, path, store, *, max_size: int = 6):
    """Rebuild packet.json from non-rejected atoms. Returns the packet path or None."""
    path = Path(path)
    packet_path = path.with_name("packet.json")
    texts = _search_atoms(store)
    if not texts:
        print("no active atoms; packet not rebuilt")
        return None
    cons = _active_consistency(store)
    selected, eng = resilience_search.greedy_resilient(
        texts, cons, max_size=max_size, redundancy_scale=2.0
    )
    topic_id = active.get("id") or active.get("topic_id") or path.parent.name
    doc = build_packet_doc(
        topic_id, store.get("atoms") or [], selected, eng, "greedy", max_size, 2.0
    )
    write_packet(path, doc)
    return packet_path


def cmd_reject(args):
    """Back out an atom: keep for audit, drop from packets/search."""
    active, path, store = load_active_store()
    store = normalize_store_atoms(store)
    reason = (getattr(args, "reason", None) or "").strip()
    if not reason:
        raise SystemExit("reject/backout requires --reason")
    atoms, atom = _atom_at(store, args.index, getattr(args, "text", None))
    prev = atom_review_status(atom)
    atoms[args.index] = back_out(atom, reason=reason)
    store["atoms"] = atoms
    store["updated"] = now_iso()
    save_json(path, store)
    refresh_topic_counts(active["topic_id"])
    print(f"Backed out atom #{args.index} [{prev} → rejected]")
    print(f"  reason: {reason}")
    print("  kept on disk for audit; excluded from packets/search")
    if not getattr(args, "no_rebuild", False):
        packet_path = Path(path).with_name("packet.json")
        if packet_path.exists():
            rebuilt = _rebuild_greedy_packet(active, path, store)
            if rebuilt:
                print(f"  rebuilt {rebuilt}")


def cmd_set_review(args):
    """Set review.status on an atom by index (headless; includes restore)."""
    active, path, store = load_active_store()
    store = normalize_store_atoms(store)
    atoms, atom = _atom_at(store, args.index, getattr(args, "text", None))
    prev = atom_review_status(atom)
    if args.status == "rejected":
        reason = (args.notes or "").strip()
        if not reason:
            raise SystemExit("set-review --status rejected requires --notes (the reason)")
        atoms[args.index] = back_out(atom, reason=reason)
    else:
        atoms[args.index] = set_review(atom, args.status, notes=args.notes)
    store["atoms"] = atoms
    store["updated"] = now_iso()
    save_json(path, store)
    refresh_topic_counts(active["topic_id"])
    print(f"Atom #{args.index} review {prev} → {atom_review_status(atoms[args.index])}")
    if not getattr(args, "no_rebuild", False):
        packet_path = Path(path).with_name("packet.json")
        if packet_path.exists():
            rebuilt = _rebuild_greedy_packet(active, path, store)
            if rebuilt:
                print(f"  rebuilt {rebuilt}")


def cmd_review(args):
    """Open slick local HTML reviewer for provenance + keep/edit/reject."""
    from .review_server import serve

    active, path, store = load_active_store()
    store = normalize_store_atoms(store)
    save_json(path, store)

    def on_change():
        refresh_topic_counts(active["topic_id"])

    if args.apply_only:
        print(f"normalized {path} ({len(store.get('atoms') or [])} atoms)")
        return
    serve(
        Path(path),
        active["topic_id"],
        host=args.host,
        port=args.port,
        open_browser=bool(getattr(args, "browser", False)) and not getattr(args, "no_browser", False),
        on_change=on_change,
    )


def cmd_critique(args):
    """LLM critique of pending atoms; optional auto-accept/reject by confidence."""
    from . import critique as critique_mod
    from . import mlx_backend
    from .config import CFG

    active, path, store = load_active_store()
    store = normalize_store_atoms(store)
    if args.ensure_model:
        print(f"model ready: {mlx_backend.ensure_model(args.model)}")

    source_loaders = {
        "file": lambda: Path(args.source_file).expanduser().read_text(encoding="utf-8"),
        "text": lambda: args.source_text,
        "excerpts": lambda: critique_mod.collect_source_excerpts(store),
    }
    source_key = (
        "file" if args.source_file else "text" if args.source_text else "excerpts"
    )
    source = source_loaders[source_key]()

    cfg = CFG.replace(
        critique_min_grounding=getattr(args, "min_grounding", None),
        critique_accept_min_conf=getattr(args, "accept_min_conf", None),
        critique_reject_min_conf=getattr(args, "reject_min_conf", None),
        critique_edit_min_conf=getattr(args, "edit_min_conf", None),
        mlx_model=args.model or CFG.mlx_model,
    )
    report = critique_mod.critique_pending(
        store, source=source, model=args.model, cfg=cfg
    )
    out = Path(args.out) if args.out else Path(path).with_name("critique_report.json")
    save_json(out, report)
    print(f"wrote {out}  pending={report['n_pending']} model={report['model']}")
    for p in report.get("proposals") or []:
        print(
            f"  [{p['i']}] {p['action']} conf={p['confidence']:.2f} "
            f"g={p.get('grounding')}  {p.get('reason', '')[:70]}"
        )
        if p["action"] == "edit" and p.get("text") and p["text"] != p.get("original"):
            print(f"       → {p['text'][:90]}")

    mode = (
        "all"
        if args.apply_all
        else "gated+edits"
        if args.apply_edits
        else "gated"
        if args.apply
        else "attach"
    )
    apply_kwargs = {
        "attach": dict(attach_only=True),
        "gated": dict(apply_edits=False, apply_all=False),
        "gated+edits": dict(apply_edits=True, apply_all=False),
        "all": dict(apply_edits=True, apply_all=True),
    }[mode]
    result = critique_mod.apply_proposals(
        store, report.get("proposals") or [], cfg=cfg, **apply_kwargs
    )
    save_json(path, result["store"])
    refresh_topic_counts(active["topic_id"])
    a = result["applied"]
    print(
        f"mode={mode} accept={a['accepted']} edit={a['edited']} "
        f"reject={a['rejected']} proposed_only={a['proposed_only']}"
    )
    print("Review UI: coherence review --serve   # --browser only if asked")


def cmd_eval(args):
    """Score packet usefulness on arbitrary queries (local MLX)."""
    from . import eval_queries as eq
    from . import mlx_backend

    active, path, store = load_active_store()
    queries = eq.load_queries(
        Path(args.queries) if args.queries else None,
        list(args.query or []),
    )
    if not queries:
        raise SystemExit("Pass --query and/or --queries file")
    if args.ensure_model:
        print(f"model ready: {mlx_backend.ensure_model(args.model)}")
    # Default = query-aware (per-query seeded packet). --fixed-packet locks one global packet.
    packet = None
    if args.fixed_packet:
        packet_path = Path(path).with_name("packet.json")
        if packet_path.exists() and not args.rebuild_packet:
            doc = load_json(packet_path, {}) or {}
            packet = list(doc.get("atoms") or [])
            if packet and isinstance(packet[0], dict):
                packet = atom_texts(packet)
        if not packet:
            packet, _meta = eq.resolve_packet(store, max_size=args.max_size)
    report = eq.eval_queries(
        queries,
        store,
        packet=packet,
        max_size=args.max_size,
        model=args.model,
        query_aware=packet is None,
    )
    out = Path(args.out) if args.out else Path(path).with_name("eval_report.json")
    save_json(out, report)
    mode = "fixed-packet" if packet is not None else "query-aware"
    print(f"wrote {out}  mode={mode}")
    print(
        f"queries={report['n_queries']}  "
        f"mean_grounded={report['mean_grounded']}  "
        f"mean_coverage={report['mean_coverage']}  "
        f"insufficient={report['n_insufficient']}"
    )
    for i, row in enumerate(report.get("results") or []):
        g = row.get("grounded")
        c = row.get("coverage")
        flag = "∅" if row.get("insufficient") else "✓"
        print(f"  [{i}] {flag} g={g} c={c}  {row['query'][:80]}")


def cmd_ensure_model(args):
    from . import mlx_backend

    mid = mlx_backend.ensure_model(args.model)
    print(f"ready: {mid}")
    print(f"backend: mlx_lm  available={mlx_backend.available()}")


def cmd_set_consistency(args):
    active, path, store = load_active_store()
    n = len(store.get("atoms", []))
    i, j = int(args.i), int(args.j)
    if i == j:
        raise SystemExit("i and j must differ")
    if not (0 <= i < n and 0 <= j < n):
        raise SystemExit(f"Indices out of range 0..{n-1}")
    score = float(args.score)
    if score < -1.0 or score > 1.0:
        raise SystemExit("score must be in [-1, 1]")
    a, b = (i, j) if i < j else (j, i)
    cons = parse_consistency_map(store)
    cons[(a, b)] = score
    store["consistency"] = dump_consistency_map(cons)
    store["updated"] = now_iso()
    save_json(path, store)
    refresh_topic_counts(active["topic_id"])
    print(f"Set consistency ({a},{b}) = {score}")


def cmd_rescore(args):
    """Recompute all pairwise heuristic scores (overwrites consistency)."""
    active, path, store = load_active_store()
    atoms = store.get("atoms", [])
    n = len(atoms)
    cons = {}
    for i in range(n):
        for j in range(i + 1, n):
            s = heuristic_pair_score(atoms[i], atoms[j])
            if abs(s) >= float(args.min_abs):
                cons[(i, j)] = s
    store["consistency"] = dump_consistency_map(cons)
    store["updated"] = now_iso()
    save_json(path, store)
    refresh_topic_counts(active["topic_id"])
    print(f"Rescored {n} atoms → {len(cons)} edges (min_abs={args.min_abs})")



def build_packet_doc(
    topic_id: str,
    atoms: list,
    selected: list,
    energy: float,
    method: str,
    max_size,
    redundancy_scale: float,
    query: str | None = None,
) -> dict:
    """First-class packet artifact for agent/person handoff."""
    texts = atom_texts(atoms)
    selected_texts = [atom_text(s) for s in selected]
    indices = []
    for s in selected_texts:
        try:
            indices.append(texts.index(s))
        except ValueError:
            continue
    return {
        "version": 1,
        "kind": "resilient_packet",
        "topic_id": topic_id,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": method,
        "energy": float(energy),
        "max_size": max_size,
        "redundancy_scale": float(redundancy_scale),
        "query": query,
        "atom_indices": indices,
        "atoms": selected_texts,
        "atom_count_source": len(atoms),
    }


def _search_atoms(store: dict) -> list[str]:
    """Non-rejected atom texts for search/packet (HOW review gates the graph)."""
    return atom_texts(active_atoms(store))


def _active_consistency(store: dict) -> dict:
    """Remap consistency edges onto the active-only atom list."""
    from .atoms import is_active

    full = store.get("atoms") or []
    old_to_new = {}
    n = 0
    for i, a in enumerate(full):
        if is_active(a):
            old_to_new[i] = n
            n += 1
    cons = {}
    for (i, j), s in parse_consistency_map(store).items():
        if i in old_to_new and j in old_to_new:
            a, b = old_to_new[i], old_to_new[j]
            if a > b:
                a, b = b, a
            cons[(a, b)] = s
    return cons


def write_packet(store_path: Path, doc: dict) -> Path:
    out = store_path.with_name("packet.json")
    save_json(out, doc)
    return out



def cmd_packet(args):
    """Show or rebuild the first-class packet.json for the active topic."""
    active, path, store = load_active_store()
    path = Path(path)
    packet_path = path.with_name("packet.json")
    if args.rebuild or not packet_path.exists():
        # rebuild via greedy (accepted/pending/edited only — not rejected)
        atoms = store.get("atoms") or []
        texts = _search_atoms(store)
        if not texts:
            raise SystemExit("No atoms")
        mod = resilience_search
        cons = _active_consistency(store)
        selected, eng = mod.greedy_resilient(
            texts, cons, max_size=args.max_size, redundancy_scale=2.0
        )
        topic_id = active.get("id") or active.get("topic_id") or path.parent.name
        doc = build_packet_doc(
            topic_id, atoms, selected, eng, "greedy", args.max_size, 2.0
        )
        write_packet(path, doc)
        print(f"rebuilt {packet_path}")
    else:
        doc = load_json(packet_path, {})
        print(f"packet {packet_path}")
    doc = load_json(packet_path, {})
    print(f"topic={doc.get('topic_id')} method={doc.get('method')} E={doc.get('energy')} size={len(doc.get('atoms') or [])}")
    for i, a in enumerate(doc.get("atoms") or []):
        print(f"  [{i}] {a}")


def cmd_search(args):
    active, path, store = load_active_store()
    atoms = store.get("atoms", [])
    texts = _search_atoms(store)
    cons = _active_consistency(store)
    if not texts:
        raise SystemExit("Active store has no atoms")

    mod = resilience_search

    red_scale = getattr(args, "redundancy_scale", 2.0)
    red_thr = getattr(args, "redundancy_threshold", 0.35)
    write = not getattr(args, "no_write", False)
    topic_id = active.get("id") or active.get("topic_id") or Path(path).parent.name

    if args.greedy:
        selected, eng = mod.greedy_resilient(
            texts,
            cons,
            max_size=args.max_size,
            select_penalty=args.select_penalty,
            redundancy_scale=red_scale,
            redundancy_threshold=red_thr,
        )
        print(f"Greedy packet  E={eng:.4f}  size={len(selected)}  red_scale={red_scale}")
        for k, a in enumerate(selected):
            print(f"  [{k}] {a}")
        if write:
            doc = build_packet_doc(
                topic_id, atoms, selected, eng, "greedy",
                args.max_size, red_scale,
            )
            out = write_packet(Path(path), doc)
            print(f"wrote {out}")
        return

    ranked = mod.find_resilient_constructors(
        texts,
        cons,
        select_penalty=args.select_penalty,
        num_reads=args.reads,
        num_sweeps=args.sweeps,
        redundancy_scale=red_scale,
        redundancy_threshold=red_thr,
    )
    top = ranked[: max(1, args.top)]
    print(f"SA packets (showing {len(top)} of {len(ranked)} unique)")
    for rank, (selected, eng) in enumerate(top):
        print(f"\n#{rank}  E={eng:.4f}  size={len(selected)}")
        for a in selected:
            print(f"  - {atom_text(a)}")
    if write and top:
        selected, eng = top[0]
        doc = build_packet_doc(
            topic_id, atoms, selected, eng, "sa",
            None, red_scale,
        )
        out = write_packet(Path(path), doc)
        print(f"\nwrote {out}")


def cmd_score_new(args):
    """Heuristic-score the newest atom against all prior atoms and apply."""
    active, path, store = load_active_store()
    atoms = store.get("atoms", [])
    if len(atoms) < 2:
        raise SystemExit("Need at least 2 atoms to score")
    # reuse local heuristic
    cons = parse_consistency_map(store)
    new_idx = len(atoms) - 1
    added = 0
    for i in range(new_idx):
        s = heuristic_pair_score(atoms[i], atoms[new_idx])
        if abs(s) >= float(args.min_abs):
            cons[(i, new_idx)] = s
            added += 1
            print(f"  ({i},{new_idx}) = {s:+.3f}")
    store["consistency"] = dump_consistency_map(cons)
    store["updated"] = now_iso()
    save_json(path, store)
    refresh_topic_counts(active["topic_id"])
    print(f"score-new: wrote {added} edges for atom #{new_idx}")


def cmd_judge_prompt(args):
    """Print LLM-as-judge prompt for pairs (agent fills scores, then apply)."""
    active, path, store = load_active_store()
    atoms = store.get("atoms", [])
    from . import consistency as mod
    if args.new_only:
        if len(atoms) < 2:
            raise SystemExit("Need at least 2 atoms")
        pairs = mod.pairs_for_new_atom(len(atoms) - 1, len(atoms) - 1)
    else:
        pairs = mod.all_pairs(len(atoms))
    print(mod.format_judge_batch(atom_texts(atoms), pairs, max_pairs=args.max_pairs))


def cmd_apply_scores(args):
    """Apply JSON scores to active store. JSON: {"scores":[{"i":0,"j":1,"score":0.7},...]}"""
    active, path, store = load_active_store()
    if args.file:
        payload = json.loads(Path(args.file).read_text())
    else:
        payload = json.loads(args.json)
    items = payload.get("scores", payload if isinstance(payload, list) else [])
    cons = parse_consistency_map(store)
    n = len(store.get("atoms", []))
    applied = 0
    for item in items:
        i, j, s = int(item["i"]), int(item["j"]), float(item["score"])
        if not (0 <= i < n and 0 <= j < n) or i == j:
            continue
        if abs(s) < float(args.min_abs):
            cons.pop((min(i, j), max(i, j)), None)
            continue
        if s < -1 or s > 1:
            raise SystemExit(f"score out of range: {s}")
        cons[(min(i, j), max(i, j))] = s
        applied += 1
    store["consistency"] = dump_consistency_map(cons)
    store["updated"] = now_iso()
    save_json(path, store)
    refresh_topic_counts(active["topic_id"])
    print(f"apply-scores: {applied} edges on {active['topic_id']}")



def cmd_link(args):
    """Add a meta-graph edge between two topics."""
    meta = load_meta()
    ids = {t["id"] for t in meta.get("topics", [])}
    if args.src not in ids or args.dst not in ids:
        raise SystemExit(f"Unknown topic id(s). Known: {sorted(ids)}")
    if args.src == args.dst:
        raise SystemExit("Cannot link a topic to itself")
    score = float(args.score)
    if score < -1 or score > 1:
        raise SystemExit("score must be in [-1, 1]")
    links = meta.setdefault("links", [])
    # upsert
    key = (args.src, args.dst)
    links = [L for L in links if not (L.get("from") == key[0] and L.get("to") == key[1])]
    links.append({
        "from": args.src,
        "to": args.dst,
        "score": score,
        "relation": args.relation or "related",
    })
    meta["links"] = links
    save_meta(meta)
    print(f"link {args.src} --[{args.relation or 'related'}:{score}]--> {args.dst}")


def _topic_blob(topic: dict) -> str:
    parts = [topic.get("id", ""), topic.get("title", ""), topic.get("description", "")]
    parts += topic.get("tags") or []
    # sample atoms if present
    try:
        store = load_json(topic_atoms_path(topic), {})
        for a in (store.get("atoms") or [])[:20]:
            parts.append(atom_text(a))
    except Exception:
        pass
    return " ".join(parts).lower()


def cmd_find(args):
    """Rank topics by keyword overlap with a query (fast cache routing)."""
    meta = load_meta()
    q = set(re.findall(r"[a-z0-9]+", args.query.lower()))
    if not q:
        raise SystemExit("Empty query")
    ranked = []
    for t in meta.get("topics", []):
        blob = _topic_blob(t)
        tokens = set(re.findall(r"[a-z0-9]+", blob))
        inter = len(q & tokens)
        if inter == 0:
            continue
        score = inter / (len(q) ** 0.5)
        ranked.append((score, inter, t))
    ranked.sort(reverse=True)
    if not ranked:
        print("No matching topics")
        return
    for score, inter, t in ranked[: max(1, args.top)]:
        print(f"{t['id']}\tscore={score:.2f}\thits={inter}\tatoms={t.get('atom_count', '?')}")
        print(f"  {t.get('title', '')}")


def cmd_cache(args):
    """Fast cache layer: find topics for query, emit greedy resilient packets."""
    meta = load_meta()
    q = set(re.findall(r"[a-z0-9]+", args.query.lower()))
    ranked = []
    for t in meta.get("topics", []):
        blob = _topic_blob(t)
        tokens = set(re.findall(r"[a-z0-9]+", blob))
        inter = len(q & tokens)
        if inter == 0 and not args.all:
            continue
        score = inter / max(len(q) ** 0.5, 1)
        ranked.append((score, inter, t))
    ranked.sort(reverse=True)
    if not ranked:
        print("CACHE MISS — no matching topics.")
        print('  Pack claims:  coherence pack --title "Theme" --atom "Durable claim."')
        return

    mod = resilience_search

    top = ranked[: max(1, args.topics)]
    print(f"CACHE HIT — {len(top)} topic(s) for query")
    for score, inter, t in top:
        path = topic_atoms_path(t)
        store = load_json(path, {})
        atoms = store.get("atoms") or []
        cons = parse_consistency_map(store)
        print(f"\n## {t['id']}  (match={score:.2f}, atoms={len(atoms)})")
        if not atoms:
            print("  (empty store)")
            continue
        selected, eng = mod.greedy_resilient(
            atoms,
            cons,
            max_size=args.max_size,
            redundancy_scale=args.redundancy_scale,
        )
        print(f"  packet E={eng:.3f} size={len(selected)}")
        for a in selected:
            print(f"  • {atom_text(a)}")
        doc = build_packet_doc(
            t["id"], atoms, selected, eng, "greedy-cache",
            args.max_size, args.redundancy_scale, query=args.query,
        )
        out = write_packet(path, doc)
        print(f"  wrote {out}")

    # show meta neighbors of top topic
    links = meta.get("links") or []
    top_id = top[0][2]["id"]
    nbrs = [L for L in links if L.get("from") == top_id or L.get("to") == top_id]
    if nbrs:
        print("\n## meta neighbors")
        for L in nbrs:
            print(f"  {L.get('from')} --[{L.get('relation')}:{L.get('score')}]--> {L.get('to')}")


def cmd_meta_graph(_args):
    """Print meta-graph (topics + links)."""
    meta = load_meta()
    print("topics:")
    for t in meta.get("topics", []):
        print(f"  - {t['id']}  ({t.get('atom_count', '?')} atoms)  {t.get('title', '')}")
    print("links:")
    links = meta.get("links") or []
    if not links:
        print("  (none)")
    for L in links:
        print(f"  {L.get('from')} --[{L.get('relation')}:{L.get('score')}]--> {L.get('to')}")







def cmd_export(args):
    """Export active (or named) topic to human-friendly Obsidian markdown."""
    import importlib.util

    meta = load_meta()
    topic_id = args.topic
    if not topic_id:
        active = get_active()
        if not active:
            raise SystemExit("No active topic. Pass --topic or run: use <id>")
        topic_id = active.get("topic_id") or active.get("id")
        if not topic_id:
            raise SystemExit("Active pointer missing topic_id")
        store_path = Path(active["atoms_path"])
        title = active.get("title") or topic_id
        description = ""
    else:
        topics = {t["id"]: t for t in meta.get("topics", [])}
        if topic_id not in topics:
            raise SystemExit(f"Unknown topic: {topic_id}")
        tmeta = topics[topic_id]
        store_path = topic_atoms_path(tmeta)
        title = tmeta.get("title") or topic_id
        description = tmeta.get("description") or ""

    # fill description from meta if we used active
    if not description:
        for t in meta.get("topics", []):
            if t.get("id") == topic_id:
                description = t.get("description") or ""
                title = t.get("title") or title
                break

    store = load_json(store_path, {})
    atoms = store.get("atoms") or []
    cons_raw = store.get("consistency") or {}
    if not atoms:
        raise SystemExit("No atoms to export")

    thr = float(args.min_score)

    def parse_cons(d):
        out = {}
        for key, score in d.items():
            try:
                i, j = map(int, str(key).split(","))
                score = float(score)
            except Exception:
                continue
            if 0 <= i < len(atoms) and 0 <= j < len(atoms) and i != j:
                a, b = (i, j) if i < j else (j, i)
                out[(a, b)] = score
        return out

    cons = parse_cons(cons_raw)

    # --- human-readable titles ---
    def make_title(text: str, idx: int, used: set) -> str:
        """Short human name for an atom note (not a sentence)."""
        t = re.sub(r"\s+", " ", atom_text(text)).strip()
        for sep in [": ", " — ", " – "]:
            if sep in t:
                head = t.split(sep, 1)[0].strip()
                if 8 <= len(head) <= 64:
                    t = head
                    break
        if len(t) > 60:
            cut = t[:60].rsplit(" ", 1)[0]
            t = cut if len(cut) >= 16 else t[:60]
        t = t.rstrip(".,;:")
        base = t
        n = 2
        while t.lower() in used:
            t = f"{base} ({n})"
            n += 1
        used.add(t.lower())
        return t

    used_titles = set()
    titles = [make_title(atom_text(a), i, used_titles) for i, a in enumerate(atoms)]

    def safe_note_name(title: str) -> str:
        # Same string for [[wikilink]] and filename stem (Obsidian resolution)
        slug = re.sub(r'[\\/:*?"<>|]', "-", title)
        slug = re.sub(r"\s+", " ", slug).strip().rstrip(".")
        return slug

    titles = [safe_note_name(x) for x in titles]
    filenames = [f"{x}.md" for x in titles]

    # neighbors for each atom
    neighbors = {i: [] for i in range(len(atoms))}
    edges = []
    for (i, j), score in cons.items():
        if abs(score) < thr:
            continue
        neighbors[i].append((j, score))
        neighbors[j].append((i, score))
        edges.append((i, j, score))
    edges.sort(key=lambda x: -abs(x[2]))

    # resilient packet (constructor state)
    mod = resilience_search
    packet_atoms, packet_e = mod.greedy_resilient(
        atoms, cons, max_size=int(args.packet_size), redundancy_scale=2.0
    )
    texts = atom_texts(atoms)
    packet_idx = []
    for p in packet_atoms:
        pt = atom_text(p)
        try:
            packet_idx.append(texts.index(pt))
        except ValueError:
            continue

    out_dir = Path(args.out) if args.out else store_path.parent / "export_obsidian"
    out_dir.mkdir(parents=True, exist_ok=True)

    # clear previous export md files in dir (only our pattern) — keep simple: overwrite
    # --- Research writeup (main note) ---
    main_name = f"{title}.md"
    # sanitize main filename
    main_name = re.sub(r'[\\/:*?"<>|]', "", main_name)

    lines = []
    lines += [
        "---",
        f'title: "{title}"',
        f"topic_id: {topic_id}",
        f"atom_count: {len(atoms)}",
        "tags: [research, coherence-cache, constructor-resilience]",
        "---",
        "",
        f"# {title}",
        "",
    ]
    if description:
        lines += [description.strip(), ""]

    lines += [
        "## Research summary",
        "",
        f"This note is a human-readable export of the **{title}** claim store. "
        f"It holds **{len(atoms)} claims** (atoms) linked by consistency scores. "
        "The *constructor state* below is a compressed resilient packet—what an agent "
        "would load as high-signal context before continuing work on this theme.",
        "",
        "Atoms are durable claims only (not raw chat). Edges mark support or tension; "
        "near-duplicate claims are discouraged when forming the packet.",
        "",
        "## Constructor state (current resilient packet)",
        "",
        f"_Greedy packet · size {len(packet_idx)} · energy {packet_e:.2f}_",
        "",
    ]
    if not packet_idx:
        lines.append("_Empty packet._")
    else:
        for n, i in enumerate(packet_idx, 1):
            lines.append(f"{n}. [[{titles[i]}]] — {atom_text(atoms[i])}")
            lines.append("")

    lines += [
        "## Table of contents",
        "",
    ]
    for i, t in enumerate(titles):
        marker = " ★" if i in packet_idx else ""
        lines.append(f"- [[{t}]]{marker}")

    lines += [
        "",
        "## How to read the graph",
        "",
        "- ★ marks atoms currently in the resilient packet.",
        f"- Links appear on each atom note when |consistency| ≥ {thr}.",
        "- Source of truth for agents remains `atoms.json`; this export is for people.",
        "",
        "## Strong relationships",
        "",
    ]
    if not edges:
        lines.append("_No edges above threshold._")
    else:
        for i, j, s in edges[:25]:
            lines.append(f"- [[{titles[i]}]] — **{s:+.2f}** → [[{titles[j]}]]")

    # External references aggregated from all atoms
    all_refs = []
    seen_ref = set()
    for a in atoms:
        for r in extract_references(atom_text(a)):
            if r["url"] not in seen_ref:
                seen_ref.add(r["url"])
                all_refs.append(r)
    lines += ["", "## External references", ""]
    if not all_refs:
        lines.append("_No arXiv / DOI / URL references detected in atoms._")
    else:
        for r in all_refs:
            lines.append(f"- [{r['label']}]({r['url']})")

    (out_dir / main_name).write_text("\n".join(lines) + "\n", encoding="utf-8")

    # --- Export landing page (what you see first) ---
    other_topics = [t for t in meta.get("topics", []) if t.get("id") != topic_id]
    idx = [
        "---",
        'title: "Index"',
        "tags: [index, moc]",
        "---",
        "",
        "# Index",
        "",
        "Welcome. This is an **Obsidian export** of a constructor-resilience claim store.",
        "",
        "It is a human-readable view of durable research claims (**atoms**), how they support or conflict with each other, and a compressed **constructor state** (resilient packet) an agent would load as context.",
        "",
        "## Start here",
        "",
        f"1. Open [[{title}]] — research writeup, constructor state, and table of contents for the active topic.",
        "2. Browse atom notes from that page (named `[[wiki-links]]`).",
        "3. Agents should still use `atoms.json` as the source of truth; this export is for people.",
        "",
        "## Active topic",
        "",
        f"- **Title:** [[{title}]]",
        f"- **Topic id:** `{topic_id}`",
        f"- **Atoms:** {len(atoms)}",
        f"- **Packet size:** {len(packet_idx)}",
        "",
    ]
    if description:
        idx += [f"> {description.strip()}", ""]

    idx += [
        "### Constructor state (preview)",
        "",
    ]
    if not packet_idx:
        idx.append("_No packet._")
    else:
        for n, i in enumerate(packet_idx, 1):
            idx.append(f"{n}. [[{titles[i]}]]")
        idx.append("")

    idx += [
        "### All claims in this topic",
        "",
    ]
    for i, tname in enumerate(titles):
        star = " ★" if i in packet_idx else ""
        idx.append(f"- [[{tname}]]{star}")

    # --- Mermaid charts for Index ---
    def mermaid_id(i: int) -> str:
        return f"A{i}"

    def mermaid_label(title: str, limit: int = 36) -> str:
        t = title.replace('"', "'")
        if len(t) > limit:
            t = t[: limit - 1] + "…"
        return t

    # Full topic graph (edges >= thr)
    mm_topic = ["```mermaid", "graph LR"]
    for i, tname in enumerate(titles):
        lab = mermaid_label(tname)
        star = " ★" if i in packet_idx else ""
        mm_topic.append(f'  {mermaid_id(i)}["{lab}{star}"]')
    for i, j, s in edges[:40]:
        if s >= 0.85:
            mm_topic.append(f"  {mermaid_id(i)} ===|{s:.2f}| {mermaid_id(j)}")
        else:
            mm_topic.append(f"  {mermaid_id(i)} ---|{s:.2f}| {mermaid_id(j)}")
    mm_topic.append("```")

    # Packet-only subgraph
    mm_pkt = ["```mermaid", "graph LR"]
    pkt_set = set(packet_idx)
    for i in packet_idx:
        lab = mermaid_label(titles[i])
        mm_pkt.append(f'  {mermaid_id(i)}["{lab}"]')
    for i, j, s in edges:
        if i in pkt_set and j in pkt_set:
            if s >= 0.85:
                mm_pkt.append(f"  {mermaid_id(i)} ===|{s:.2f}| {mermaid_id(j)}")
            else:
                mm_pkt.append(f"  {mermaid_id(i)} ---|{s:.2f}| {mermaid_id(j)}")
    mm_pkt.append("```")

    # Meta-graph (topics)
    mm_meta = ["```mermaid", "graph LR"]
    for t in meta.get("topics", []):
        tid = t.get("id", "")
        safe = tid.replace("-", "_")
        tlab = (t.get("title") or tid).replace('"', "'")
        if len(tlab) > 40:
            tlab = tlab[:39] + "…"
        emphasis = ":::active" if tid == topic_id else ""
        mm_meta.append(f'  {safe}["{tlab}"]')
    for L in meta.get("links") or []:
        a = str(L.get("from", "")).replace("-", "_")
        b = str(L.get("to", "")).replace("-", "_")
        rel = str(L.get("relation") or "related")[:24]
        sc = L.get("score", "")
        mm_meta.append(f"  {a} ---|{rel} {sc}| {b}")
    mm_meta.append("```")

    idx += [
        "",
        "## Maps",
        "",
        "### Constructor state (packet graph)",
        "",
        *mm_pkt,
        "",
        "### Full topic consistency graph",
        "",
        *mm_topic,
        "",
        "### Meta-graph (topics)",
        "",
        *mm_meta,
        "",
        "## What the symbols mean",
        "",
        "- **★** — currently in the resilient packet (constructor state)",
        "- **Atom note** — one durable claim + related claims",
        f"- **Links** — consistency edges with |score| ≥ {thr}",
        "- **Mermaid** — rendered by Obsidian (Live Preview / Reading view)",
        "",
        "## This export vs agents",
        "",
        "| Audience | Artifact |",
        "|----------|----------|",
        "| Humans (Obsidian) | This folder / `Index` |",
        "| Agents / handoff | `atoms.json` in the topic store |",
        "",
    ]

    if other_topics:
        idx += [
            "## Other topics in the meta-graph",
            "",
            "_Re-run export with `--topic <id>` to generate a folder (or section) for each._",
            "",
        ]
        for t in other_topics:
            idx.append(
                f"- `{t.get('id')}` — {t.get('title') or t.get('id')} "
                f"({t.get('atom_count', '?')} atoms)"
            )
        idx.append("")

    links = [L for L in (meta.get("links") or []) if L.get("from") == topic_id or L.get("to") == topic_id]
    if links:
        idx += ["## Meta links from this topic", ""]
        for L in links:
            idx.append(
                f"- `{L.get('from')}` —[{L.get('relation')}:{L.get('score')}]→ `{L.get('to')}`"
            )
        idx.append("")

    idx += [
        "---",
        "",
        f"_Exported by constructor-resilience · topic `{topic_id}`_",
        "",
    ]
    (out_dir / "Index.md").write_text("\n".join(idx) + "\n", encoding="utf-8")


    # --- one note per atom (named) ---
    for i, a in enumerate(atoms):
        refs = extract_references(a)
        body = [
            "---",
            f'atom_title: "{titles[i]}"',
            f"atom_index: {i}",
            f"topic_id: {topic_id}",
            f"in_packet: {'true' if i in packet_idx else 'false'}",
            "tags: [atom]",
            "---",
            "",
            f"# {titles[i]}",
            "",
            linkify_claim(a),
            "",
        ]
        if i in packet_idx:
            body += ["> Part of the current **constructor state** (resilient packet).", ""]

        body += ["## References", ""]
        if refs:
            for r in refs:
                body.append(f"- [{r['label']}]({r['url']})")
            body.append("")
        else:
            body += ["_No external paper/URL detected in this claim._", ""]

        body += ["## Related claims", ""]
        rel = sorted(neighbors[i], key=lambda x: -abs(x[1]))
        if not rel:
            body.append("_No strong links above threshold._")
        else:
            for j, s in rel:
                body.append(f"- [[{titles[j]}]] ({s:+.2f})")
                body.append(f"  - {linkify_claim(atoms[j])}")
                body.append("")

        body += [
            "## Navigation",
            "",
            f"← Back to [[{title.replace('.md', '')}]]" if False else f"← Back to [[{title}]]",
            "",
        ]
        # fix backlink title only
        body[-3] = f"← Back to [[{title}]]"

        fname = filenames[i]
        # avoid collision with main file
        if fname.lower() == main_name.lower():
            fname = f"Atom - {fname}"
        (out_dir / fname).write_text("\n".join(body) + "\n", encoding="utf-8")

    # Roam outline still useful
    roam = [f"# {title}", "", f"topic_id:: {topic_id}", "", "## Constructor state", ""]
    for i in packet_idx:
        roam.append(f"- [[{titles[i]}]] {atoms[i]}")
    roam += ["", "## All atoms", ""]
    for i, a in enumerate(atoms):
        roam.append(f"- [[{titles[i]}]] {a}")
        for j, s in sorted(neighbors[i], key=lambda x: -abs(x[1]))[:6]:
            roam.append(f"  - [[{titles[j]}]] ({s:+.2f})")
    (out_dir / f"{topic_id}-roam-outline.md").write_text("\n".join(roam) + "\n", encoding="utf-8")

    print(out_dir)
    print(f"  main={main_name}")
    print(f"  atom_notes={len(atoms)}  packet={len(packet_idx)}  edges_exported={len(edges)}")





def cmd_intersect(args):
    """Interest intersection: my topic ∩ their topic → packet."""
    from .intersection import intersection_packet
    meta = load_meta()
    def load_topic(tid: str) -> dict:
        t = next((x for x in meta.get("topics", []) if x["id"] == tid), None)
        if not t:
            raise SystemExit(f"Unknown topic: {tid}")
        path = get_root() / t["path"] / "atoms.json"
        store = load_json(path)
        if not store:
            raise SystemExit(f"Missing store: {path}")
        return store
    mine = load_topic(args.mine)
    theirs = load_topic(args.theirs)
    doc = intersection_packet(
        mine,
        theirs,
        max_size=args.max_size,
        min_cross_sim=args.min_sim,
        seed_query=args.query,
        redundancy_scale=args.redundancy_scale,
        require_cross=not args.allow_one_sided,
    )
    out = args.out
    if out:
        outp = Path(out)
        save_json(outp, doc)
        print(f"wrote {outp}")
    print(
        f"intersection  E={doc.get('energy')}  size={len(doc.get('atoms') or [])}  "
        f"mine={doc.get('n_mine')} theirs={doc.get('n_theirs')}"
    )
    for i, a in enumerate(doc.get("atoms") or []):
        src = "?"
        for p in doc.get("provenance") or []:
            if p.get("text") == a:
                src = p.get("source", "?")
                break
        print(f"  [{i}] ({src}) {a}")



def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Durable claims (atoms), resume packets, and share files",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Store root (default: $COHERENCE_ROOT or ./.coherence)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Show meta + active topic").set_defaults(func=cmd_status)
    sub.add_parser("list", help="List topics").set_defaults(func=cmd_list)

    p_use = sub.add_parser("use", help="Zoom into a topic (set active)")
    p_use.add_argument("topic_id")
    p_use.set_defaults(func=cmd_use)

    p_create = sub.add_parser("create", help="Create a new topical store")
    p_create.add_argument("id", nargs="?", help="Topic id (slug); default from title")
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--description", default="")
    p_create.add_argument("--tags", nargs="*", default=[])
    p_create.add_argument("--use", action="store_true", help="Make active after create")
    p_create.set_defaults(func=cmd_create)

    sub.add_parser("path", help="Print active atoms.json path").set_defaults(func=cmd_path)

    p_render = sub.add_parser("render", help="Render active topic graph PNG")
    p_render.set_defaults(func=cmd_render)

    p_add = sub.add_parser("add-atom", help="Add one durable claim to the active topic")
    p_add.add_argument("text")
    p_add.add_argument(
        "--auto-score",
        action="store_true",
        help="Heuristic pairwise scores vs existing atoms",
    )
    p_add.add_argument(
        "--plain",
        action="store_true",
        help="Store as legacy plain string (no provenance/review)",
    )
    p_add.add_argument(
        "--accepted",
        action="store_true",
        help="Keep the claim (default)",
    )
    p_add.add_argument(
        "--pending",
        action="store_true",
        help="Queue for review instead of keeping",
    )
    p_add.add_argument(
        "--constraint",
        choices=["possibility", "impossibility", "fact", "decision"],
        help="What this claim constrains: possibility, impossibility, fact, or decision",
    )
    p_add.set_defaults(func=cmd_add_atom)

    p_ingest = sub.add_parser(
        "ingest",
        help="Load claims JSON into the active topic (no extra model)",
    )
    p_ingest.add_argument(
        "--atom",
        action="append",
        default=[],
        help="Durable claim (repeatable). Prefer this over a JSON file.",
    )
    p_ingest.add_argument("--json", help="Path to JSON list, {atoms:[...]}, or one atom")
    p_ingest.add_argument("--text", help="Inline JSON string")
    p_ingest.add_argument(
        "--constraint",
        choices=["possibility", "impossibility", "fact", "decision"],
        help="Default constraint for --atom strings",
    )
    p_ingest.add_argument("--title", help="Create/use a topic with this title")
    p_ingest.add_argument("--topic", help="Topic id to use")
    p_ingest.add_argument("--source", default="ingest", help="Provenance source label")
    p_ingest.add_argument("--auto-score", action="store_true")
    p_ingest.add_argument(
        "--accepted",
        action="store_true",
        help="Keep claims (default)",
    )
    p_ingest.add_argument(
        "--pending",
        action="store_true",
        help="Queue claims for review instead of keeping",
    )
    p_ingest.add_argument("--max-size", type=int, default=6, help="Packet size after ingest")
    p_ingest.add_argument("--no-packet", action="store_true", help="Do not rebuild packet.json")
    p_ingest.set_defaults(func=cmd_ingest)

    p_pack = sub.add_parser(
        "pack",
        help="Pack claims into a topic and write the resume packet",
    )
    p_pack.add_argument(
        "--atom",
        action="append",
        default=[],
        help="Durable claim (repeatable)",
    )
    p_pack.add_argument("--json", help="Path to claims JSON")
    p_pack.add_argument("--text", help="Inline claims JSON")
    p_pack.add_argument(
        "--constraint",
        choices=["possibility", "impossibility", "fact", "decision"],
        help="Default constraint for --atom strings",
    )
    p_pack.add_argument("--title", help="Topic title (creates the topic if needed)")
    p_pack.add_argument("--topic", help="Topic id to use")
    p_pack.add_argument("--source", default="ingest")
    p_pack.add_argument("--pending", action="store_true", help="Queue for review")
    p_pack.add_argument("--max-size", type=int, default=6)
    p_pack.set_defaults(func=cmd_pack, auto_score=True, accepted=False, no_packet=False)

    p_mint = sub.add_parser(
        "mint",
        help="Extract claims from a file with local MLX (pending review)",
    )
    p_mint.add_argument("--text", default="", help="Source text to atomize")
    p_mint.add_argument("--file", help="Source file path")
    p_mint.add_argument("--theme", help="Theme focus for minting")
    p_mint.add_argument(
        "--max-atoms",
        type=int,
        default=None,
        help="Cap minted atoms (default from config/env)",
    )
    p_mint.add_argument("--model", help="Override COHERENCE_MLX_MODEL")
    p_mint.add_argument("--ensure-model", action="store_true", help="Download/load model first")
    p_mint.add_argument(
        "--min-grounding",
        type=float,
        default=None,
        help="Drop minted claims below this source-overlap ratio (default from config/env)",
    )
    p_mint.add_argument("--auto-score", action="store_true")
    p_mint.add_argument(
        "--auto-accept",
        action="store_true",
        help="Skip pending review (not recommended)",
    )
    p_mint.set_defaults(func=cmd_mint)

    p_rev = sub.add_parser(
        "review",
        help="Local HTML UI to accept, edit, or reject claims",
    )
    p_rev.add_argument("--serve", action="store_true", default=True, help="Start review server")
    p_rev.add_argument("--host", default="127.0.0.1")
    p_rev.add_argument("--port", type=int, default=8765)
    p_rev.add_argument(
        "--browser",
        action="store_true",
        help="Open the system browser (off by default — can crash Chrome)",
    )
    p_rev.add_argument("--no-browser", action="store_true", help="Do not open a browser (default)")
    p_rev.add_argument(
        "--apply-only",
        action="store_true",
        help="Normalize atoms.json to structured records without serving",
    )
    p_rev.set_defaults(func=cmd_review)

    def _add_backout_args(p):
        p.add_argument("index", type=int, help="Atom index in the active store")
        p.add_argument(
            "--reason",
            required=True,
            help="Why the atom is being backed out (ill-defined or failed constraint)",
        )
        p.add_argument(
            "--text",
            help="If set, must exactly match the atom text (safety guard)",
        )
        p.add_argument(
            "--no-rebuild",
            action="store_true",
            help="Do not rebuild packet.json after the status change",
        )
        p.set_defaults(func=cmd_reject)

    _add_backout_args(
        sub.add_parser(
            "reject",
            help="Back out an atom (ill-defined or failed possibility/impossibility); keep for audit",
        )
    )
    _add_backout_args(
        sub.add_parser(
            "backout",
            help="Alias for reject — retract an atom that does not constrain possibility/impossibility",
        )
    )

    p_sr = sub.add_parser(
        "set-review",
        help="Set review status on an atom by index (headless accept/restore/reject)",
    )
    p_sr.add_argument("index", type=int)
    p_sr.add_argument(
        "--status",
        required=True,
        choices=sorted(VALID_REVIEW),
        help="pending | accepted | edited | rejected",
    )
    p_sr.add_argument("--notes", default=None, help="Review notes (required when status=rejected)")
    p_sr.add_argument("--text", help="If set, must exactly match the atom text")
    p_sr.add_argument("--no-rebuild", action="store_true")
    p_sr.set_defaults(func=cmd_set_review)

    p_crit = sub.add_parser(
        "critique",
        help="Critique pending atoms (MLX); optional gated auto-accept/reject",
    )
    p_crit.add_argument("--source-file", help="Grounding source file")
    p_crit.add_argument("--source-text", help="Grounding source text")
    p_crit.add_argument("--model", help="Override COHERENCE_MLX_MODEL")
    p_crit.add_argument("--ensure-model", action="store_true")
    p_crit.add_argument("--min-grounding", type=float, default=None)
    p_crit.add_argument("--accept-min-conf", type=float, default=None)
    p_crit.add_argument("--reject-min-conf", type=float, default=None)
    p_crit.add_argument("--edit-min-conf", type=float, default=None)
    p_crit.add_argument(
        "--apply",
        action="store_true",
        help="Auto-apply accept/reject when confidence+grounding clear gates",
    )
    p_crit.add_argument(
        "--apply-edits",
        action="store_true",
        help="Also auto-apply high-confidence grounded edits",
    )
    p_crit.add_argument(
        "--apply-all",
        action="store_true",
        help="Apply every proposal (skips confidence gates)",
    )
    p_crit.add_argument("--out", help="Write critique_report.json path")
    p_crit.set_defaults(func=cmd_critique)

    p_eval = sub.add_parser(
        "eval",
        help="Eval packet quality on arbitrary queries (local MLX judge)",
    )
    p_eval.add_argument("--query", action="append", default=[], help="Query (repeatable)")
    p_eval.add_argument("--queries", help="File with one query per line")
    p_eval.add_argument("--max-size", type=int, default=8, help="Packet size if rebuilding")
    p_eval.add_argument(
        "--rebuild-packet",
        action="store_true",
        help="Ignore saved packet.json; use query-aware packets from the store",
    )
    p_eval.add_argument(
        "--fixed-packet",
        action="store_true",
        help="Force one global packet (saved or greedy) for all queries",
    )
    p_eval.add_argument("--model", help="Override COHERENCE_MLX_MODEL")
    p_eval.add_argument("--ensure-model", action="store_true")
    p_eval.add_argument("--out", help="Write report JSON (default: eval_report.json beside atoms)")
    p_eval.set_defaults(func=cmd_eval)

    p_em = sub.add_parser(
        "ensure-model",
        help="Download/load default MLX model (Qwen3-8B-4bit)",
    )
    p_em.add_argument("--model", help="Override COHERENCE_MLX_MODEL")
    p_em.set_defaults(func=cmd_ensure_model)

    p_set = sub.add_parser("set-consistency", help="Set pairwise score (i j score)")
    p_set.add_argument("i", type=int)
    p_set.add_argument("j", type=int)
    p_set.add_argument("score", type=float)
    p_set.set_defaults(func=cmd_set_consistency)

    p_rescore = sub.add_parser("rescore", help="Heuristic rescore all pairs in active store")
    p_rescore.add_argument("--min-abs", type=float, default=0.05)
    p_rescore.set_defaults(func=cmd_rescore)

    p_search = sub.add_parser("search", help="Build a small packet from the active topic")
    p_search.add_argument("--reads", type=int, default=40)
    p_search.add_argument("--sweeps", type=int, default=400)
    p_search.add_argument("--top", type=int, default=3)
    p_search.add_argument("--select-penalty", type=float, default=-1.0)
    p_search.add_argument("--redundancy-scale", type=float, default=2.0,
                          help="Penalty scale for co-selecting lexically similar atoms")
    p_search.add_argument("--redundancy-threshold", type=float, default=0.22,
                          help="Min Jaccard similarity to count as redundant")
    p_search.add_argument("--greedy", action="store_true")
    p_search.add_argument("--max-size", type=int, default=None)
    p_search.add_argument("--no-write", action="store_true", help="Do not write packet.json")
    p_search.set_defaults(func=cmd_search)


    p_sn = sub.add_parser("score-new", help="Heuristic-score newest atom vs prior atoms")
    p_sn.add_argument("--min-abs", type=float, default=0.05)
    p_sn.set_defaults(func=cmd_score_new)

    p_jp = sub.add_parser("judge-prompt", help="Emit LLM-as-judge scoring prompt")
    p_jp.add_argument("--new-only", action="store_true")
    p_jp.add_argument("--max-pairs", type=int, default=30)
    p_jp.set_defaults(func=cmd_judge_prompt)

    p_as = sub.add_parser("apply-scores", help="Apply JSON scores to active store")
    p_as.add_argument("--json", default="", help="Inline JSON string")
    p_as.add_argument("--file", default="", help="Path to JSON file")
    p_as.add_argument("--min-abs", type=float, default=0.0)
    p_as.set_defaults(func=cmd_apply_scores)


    p_link = sub.add_parser("link", help="Link two topics on the meta-graph")
    p_link.add_argument("src")
    p_link.add_argument("dst")
    p_link.add_argument("--score", type=float, default=0.5)
    p_link.add_argument("--relation", default="related")
    p_link.set_defaults(func=cmd_link)

    p_find = sub.add_parser("find", help="Find topics matching a query")
    p_find.add_argument("query")
    p_find.add_argument("--top", type=int, default=5)
    p_find.set_defaults(func=cmd_find)

    p_cache = sub.add_parser("cache", help="Find packets for a question")
    p_cache.add_argument("query")
    p_cache.add_argument("--topics", type=int, default=2, help="Max topics to expand")
    p_cache.add_argument("--max-size", type=int, default=6)
    p_cache.add_argument("--redundancy-scale", type=float, default=2.0)
    p_cache.add_argument("--all", action="store_true", help="Include zero-overlap topics")
    p_cache.set_defaults(func=cmd_cache)

    sub.add_parser("meta", help="Show meta-graph topics and links").set_defaults(func=cmd_meta_graph)
    p_packet = sub.add_parser("packet", help="Show or rebuild the resume packet")
    p_packet.add_argument("--rebuild", action="store_true")
    p_packet.add_argument("--max-size", type=int, default=6)
    p_packet.set_defaults(func=cmd_packet)


    
    p_ix = sub.add_parser(
        "intersect",
        help="Overlap packet: my topic ∩ their topic",
    )
    p_ix.add_argument("mine", help="My topic id (interest surface)")
    p_ix.add_argument("theirs", help="Their topic id (public or shared surface)")
    p_ix.add_argument("--max-size", type=int, default=8)
    p_ix.add_argument("--min-sim", type=float, default=0.18, help="Min cross-surface lexical affinity")
    p_ix.add_argument("--query", default=None, help="Optional seed query to reweight browse")
    p_ix.add_argument("--redundancy-scale", type=float, default=2.0)
    p_ix.add_argument("--allow-one-sided", action="store_true")
    p_ix.add_argument("--out", default=None, help="Write intersection packet JSON")
    p_ix.set_defaults(func=cmd_intersect)

    p_export = sub.add_parser("export", help="Export topic to Obsidian/Roam markdown")
    p_export.add_argument("--topic", default=None, help="Topic id (default: active)")
    p_export.add_argument("--out", default=None, help="Output directory")
    p_export.add_argument("--min-score", type=float, default=0.55, help="Min |consistency| for links")
    p_export.add_argument("--packet-size", type=int, default=6, help="Resilient packet size for writeup")
    p_export.set_defaults(func=cmd_export)

    p_share = sub.add_parser(
        "share",
        help="Write share.json from the active packet",
    )
    p_share.add_argument(
        "--to",
        default="handoff",
        help="Recipient label (default: handoff)",
    )
    p_share.add_argument("--from-id", default="local", dest="from_id", help="Sender id")
    p_share.add_argument(
        "--audience",
        choices=["direct", "circle", "public"],
        default="circle",
    )
    p_share.add_argument(
        "--forward",
        choices=["none", "circle", "public"],
        default="none",
    )
    p_share.add_argument("--note", default="")
    p_share.add_argument("--out", help="Output path (default: topics/<id>/share.json)")
    p_share.add_argument("--rebuild", action="store_true", help="Rebuild packet first")
    p_share.add_argument("--max-size", type=int, default=6)
    p_share.set_defaults(func=cmd_share)

    p_imp = sub.add_parser(
        "import",
        help="Import atoms.json, packet.json, or share.json as a topic",
    )
    p_imp.add_argument("path", help="Path to atoms.json / packet.json / share.json")
    p_imp.add_argument("--topic", help="Topic id to create or append")
    p_imp.add_argument("--title", help="Topic title")
    p_imp.add_argument("--use", action="store_true")
    p_imp.add_argument("--auto-score", action="store_true")
    p_imp.add_argument(
        "--accepted",
        action="store_true",
        help="Mark imported atoms accepted (default: pending)",
    )
    p_imp.set_defaults(func=cmd_import)

    args = parser.parse_args(argv)
    set_root(args.root)
    ensure_meta()
    args.func(args)


if __name__ == "__main__":
    main()
