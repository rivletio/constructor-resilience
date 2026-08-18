"""Local atom review UI — stdlib HTTP server, no frontend build.

  coherence review --serve [--port 8765]

Reviewer can accept / edit / reject; decisions write through to atoms.json.
Pending mints are the default focus — HOW we made them is shown (model, method, excerpt).
"""

from __future__ import annotations

import json
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from .atoms import (
    REVIEW_ACCEPTED,
    REVIEW_EDITED,
    REVIEW_PENDING,
    REVIEW_REJECTED,
    atom_review_status,
    atom_text,
    normalize_store_atoms,
    set_review,
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, store: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Atom review — constructor-resilience</title>
<style>
  :root {
    --bg: #0b0f14; --panel: #121821; --ink: #e7eef7; --muted: #8aa0b8;
    --accent: #5ad2ff; --ok: #3ddc97; --bad: #ff6b7a; --warn: #ffc857;
    --border: #1e2a3a; --chip: #1a2433;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; font: 14px/1.45 ui-sans-serif, system-ui, -apple-system, sans-serif;
    background: radial-gradient(1200px 600px at 10% -10%, #152033, var(--bg));
    color: var(--ink); min-height: 100vh;
  }
  header {
    display: flex; gap: 1rem; align-items: center; justify-content: space-between;
    padding: 1rem 1.25rem; border-bottom: 1px solid var(--border);
    backdrop-filter: blur(8px); position: sticky; top: 0; background: #0b0f14cc; z-index: 5;
  }
  h1 { font-size: 1.05rem; margin: 0; letter-spacing: 0.02em; }
  h1 span { color: var(--accent); font-weight: 600; }
  .filters { display: flex; gap: 0.4rem; flex-wrap: wrap; }
  .chip {
    border: 1px solid var(--border); background: var(--chip); color: var(--muted);
    border-radius: 999px; padding: 0.25rem 0.7rem; cursor: pointer; font-size: 12px;
  }
  .chip.on { color: var(--ink); border-color: var(--accent); box-shadow: 0 0 0 1px #5ad2ff33; }
  main { display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 1rem; padding: 1rem 1.25rem 2rem; }
  @media (max-width: 960px) { main { grid-template-columns: 1fr; } }
  .list, .detail {
    background: var(--panel); border: 1px solid var(--border); border-radius: 14px;
    min-height: 70vh; overflow: hidden; display: flex; flex-direction: column;
  }
  .list-hd, .detail-hd {
    padding: 0.75rem 1rem; border-bottom: 1px solid var(--border);
    color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em;
  }
  .cards { overflow: auto; flex: 1; }
  .card {
    padding: 0.85rem 1rem; border-bottom: 1px solid var(--border); cursor: pointer;
  }
  .card:hover { background: #162031; }
  .card.sel { background: #183047; border-left: 3px solid var(--accent); }
  .meta { display: flex; gap: 0.45rem; flex-wrap: wrap; margin-bottom: 0.35rem; }
  .tag {
    font-size: 11px; padding: 0.1rem 0.45rem; border-radius: 6px;
    background: #0f1722; color: var(--muted); border: 1px solid var(--border);
  }
  .tag.pending { color: var(--warn); border-color: #5a4820; }
  .tag.accepted, .tag.edited { color: var(--ok); border-color: #1f5a40; }
  .tag.rejected { color: var(--bad); border-color: #5a2030; }
  .card p { margin: 0; }
  .detail-body { padding: 1rem; overflow: auto; flex: 1; display: flex; flex-direction: column; gap: 0.75rem; }
  textarea {
    width: 100%; min-height: 140px; resize: vertical; background: #0c121b; color: var(--ink);
    border: 1px solid var(--border); border-radius: 10px; padding: 0.75rem; font: inherit;
  }
  .prov {
    background: #0c121b; border: 1px dashed var(--border); border-radius: 10px;
    padding: 0.75rem; color: var(--muted); font-size: 12px; white-space: pre-wrap;
  }
  .actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
  button {
    border: 0; border-radius: 10px; padding: 0.55rem 0.9rem; cursor: pointer;
    font-weight: 600; font-size: 13px;
  }
  button.accept { background: var(--ok); color: #062216; }
  button.reject { background: var(--bad); color: #2a060c; }
  button.save { background: var(--accent); color: #042433; }
  button.ghost { background: transparent; color: var(--muted); border: 1px solid var(--border); }
  .empty { padding: 2rem; color: var(--muted); text-align: center; }
  .stat { color: var(--muted); font-size: 12px; }
</style>
</head>
<body>
<header>
  <div>
    <h1>Atom review · <span id="topic">…</span></h1>
    <div class="stat" id="stats"></div>
  </div>
  <div class="filters" id="filters"></div>
</header>
<main>
  <section class="list">
    <div class="list-hd">Atoms</div>
    <div class="cards" id="cards"></div>
  </section>
  <section class="detail">
    <div class="detail-hd">Inspector</div>
    <div class="detail-body" id="detail">
      <div class="empty">Select an atom to review provenance and decide keep / edit / reject.</div>
    </div>
  </section>
</main>
<script>
const FILTERS = ["pending","accepted","edited","rejected","all"];
let state = { atoms: [], filter: "pending", sel: null, topic: "" };

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function count(status) {
  if (status === "all") return state.atoms.length;
  return state.atoms.filter(a => (a.review?.status || "accepted") === status).length;
}

function renderFilters() {
  const el = document.getElementById("filters");
  el.innerHTML = FILTERS.map(f =>
    `<button class="chip ${state.filter===f?"on":""}" data-f="${f}">${f} (${count(f)})</button>`
  ).join("");
  el.querySelectorAll(".chip").forEach(b => b.onclick = () => {
    state.filter = b.dataset.f; state.sel = null; render();
  });
}

function filtered() {
  if (state.filter === "all") return state.atoms.map((a,i)=>({a,i}));
  return state.atoms.map((a,i)=>({a,i})).filter(({a}) =>
    (a.review?.status || "accepted") === state.filter);
}

function renderCards() {
  const root = document.getElementById("cards");
  const rows = filtered();
  if (!rows.length) {
    root.innerHTML = `<div class="empty">No ${state.filter} atoms.</div>`;
    return;
  }
  root.innerHTML = rows.map(({a,i}) => {
    const st = a.review?.status || "accepted";
    const method = a.provenance?.method || "?";
    const model = (a.provenance?.model || "").split("/").pop() || "";
    const crit = a.review?.critique;
    const critTag = crit
      ? `<span class="tag ${crit.action==="reject"?"rejected":crit.action==="accept"?"accepted":"pending"}">critique:${crit.action} ${Number(crit.confidence||0).toFixed(2)}</span>`
      : "";
    return `<div class="card ${state.sel===i?"sel":""}" data-i="${i}">
      <div class="meta">
        <span class="tag ${st}">#${i} ${st}</span>
        <span class="tag">${method}</span>
        ${model ? `<span class="tag">${model}</span>` : ""}
        ${critTag}
      </div>
      <p>${escapeHtml(a.text || "")}</p>
    </div>`;
  }).join("");
  root.querySelectorAll(".card").forEach(c => c.onclick = () => {
    state.sel = +c.dataset.i; renderDetail(); renderCards();
  });
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

function renderDetail() {
  const el = document.getElementById("detail");
  if (state.sel == null || !state.atoms[state.sel]) {
    el.innerHTML = `<div class="empty">Select an atom to review provenance and decide keep / edit / reject.</div>`;
    return;
  }
  const i = state.sel;
  const a = state.atoms[i];
  const p = a.provenance || {};
  const prov = [
    `method: ${p.method || "?"}`,
    `model:  ${p.model || "—"}`,
    `source: ${p.source || "—"}`,
    `created:${p.created || "—"}`,
    p.source_excerpt ? `\nexcerpt:\n${p.source_excerpt}` : "",
  ].join("\n");
  const crit = a.review?.critique;
  const critBlock = crit ? [
    `action: ${crit.action}`,
    `confidence: ${crit.confidence}`,
    `grounding: ${crit.grounding ?? "—"}`,
    `reason: ${crit.reason || "—"}`,
    crit.proposed_text && crit.proposed_text !== a.text
      ? `\nproposed:\n${crit.proposed_text}` : "",
  ].join("\n") : "";
  el.innerHTML = `
    <div class="meta">
      <span class="tag">#${i}</span>
      <span class="tag ${a.review?.status||"accepted"}">${a.review?.status||"accepted"}</span>
    </div>
    <label class="stat">Claim text</label>
    <textarea id="edit">${escapeHtml(a.text||"")}</textarea>
    <label class="stat">How it was made</label>
    <div class="prov">${escapeHtml(prov)}</div>
    ${critBlock ? `<label class="stat">Critique proposal</label><div class="prov">${escapeHtml(critBlock)}</div>` : ""}
    <label class="stat">Review notes</label>
    <textarea id="notes" style="min-height:70px">${escapeHtml(a.review?.notes||"")}</textarea>
    <div class="actions">
      <button class="accept" id="btn-accept">Accept</button>
      <button class="save" id="btn-save">Save edit</button>
      <button class="reject" id="btn-reject">Reject</button>
      <button class="ghost" id="btn-pending">Mark pending</button>
    </div>`;
  const post = async (status) => {
    const body = {
      status,
      text: document.getElementById("edit").value,
      notes: document.getElementById("notes").value,
    };
    const updated = await api(`/api/atoms/${i}/review`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(body),
    });
    state.atoms[i] = updated.atom;
    document.getElementById("stats").textContent = updated.stats_line || "";
    render();
  };
  document.getElementById("btn-accept").onclick = () => post("accepted");
  document.getElementById("btn-save").onclick = () => post("edited");
  document.getElementById("btn-reject").onclick = () => post("rejected");
  document.getElementById("btn-pending").onclick = () => post("pending");
}

function render() {
  document.getElementById("topic").textContent = state.topic || "topic";
  renderFilters();
  renderCards();
  renderDetail();
}

async function boot() {
  const data = await api("/api/store");
  state.atoms = data.atoms || [];
  state.topic = data.topic_id || "";
  document.getElementById("stats").textContent = data.stats_line || "";
  // Prefer pending; else all
  if (count("pending") === 0) state.filter = "all";
  render();
}
boot();
</script>
</body>
</html>
"""


def make_handler(store_path: Path, topic_id: str, on_change: Callable[[], None] | None = None):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quieter
            if "/api/" in (args[0] if args else ""):
                super().log_message(fmt, *args)

        def _json(self, code: int, obj):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _html(self, code: int, text: str):
            body = text.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                return self._html(200, HTML)
            if path == "/api/store":
                with lock:
                    store = normalize_store_atoms(_load(store_path))
                    _save(store_path, store)
                atoms = store.get("atoms") or []
                pending = sum(1 for a in atoms if atom_review_status(a) == REVIEW_PENDING)
                accepted = sum(
                    1
                    for a in atoms
                    if atom_review_status(a) in (REVIEW_ACCEPTED, REVIEW_EDITED)
                )
                rejected = sum(1 for a in atoms if atom_review_status(a) == REVIEW_REJECTED)
                return self._json(
                    200,
                    {
                        "topic_id": topic_id,
                        "atoms": atoms,
                        "stats_line": (
                            f"{len(atoms)} atoms · {pending} pending · "
                            f"{accepted} kept · {rejected} rejected · {store_path}"
                        ),
                    },
                )
            self._json(404, {"error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            m = re.fullmatch(r"/api/atoms/(\d+)/review", path)
            if not m:
                return self._json(404, {"error": "not found"})
            idx = int(m.group(1))
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._json(400, {"error": "bad json"})
            status = body.get("status") or REVIEW_ACCEPTED
            with lock:
                store = normalize_store_atoms(_load(store_path))
                atoms = store.get("atoms") or []
                if not (0 <= idx < len(atoms)):
                    return self._json(400, {"error": "index out of range"})
                atoms[idx] = set_review(
                    atoms[idx],
                    status,
                    text=body.get("text"),
                    notes=body.get("notes"),
                )
                store["atoms"] = atoms
                from datetime import datetime, timezone

                store["updated"] = datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
                _save(store_path, store)
            if on_change:
                on_change()
            pending = sum(1 for a in atoms if atom_review_status(a) == REVIEW_PENDING)
            return self._json(
                200,
                {
                    "ok": True,
                    "atom": atoms[idx],
                    "stats_line": f"{len(atoms)} atoms · {pending} pending · {store_path}",
                },
            )

    return Handler


def serve(
    store_path: Path,
    topic_id: str,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    on_change: Callable[[], None] | None = None,
) -> None:
    store_path = Path(store_path)
    # Normalize once so UI always sees records
    store = normalize_store_atoms(_load(store_path))
    _save(store_path, store)

    handler = make_handler(store_path, topic_id, on_change=on_change)
    httpd = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    print(f"Atom review UI → {url}")
    print(f"  store: {store_path}")
    print("  Ctrl+C to stop")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
