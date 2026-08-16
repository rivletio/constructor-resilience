#!/usr/bin/env python3
"""Render consistency graph + atom list as PNG."""
from __future__ import annotations
import argparse, json, math
from pathlib import Path

def render(store_path: Path, out_path: Path, min_score: float = 0.55) -> Path:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import networkx as nx

    store = json.loads(Path(store_path).read_text(encoding="utf-8"))
    atoms = store.get("atoms", [])
    consistency = store.get("consistency", {})
    n = len(atoms)
    G = nx.Graph()
    for i in range(n):
        G.add_node(i)
    buckets = {"strong": [], "med": [], "weak": []}
    for key, score in consistency.items():
        i, j = map(int, key.split(","))
        score = float(score)
        if score < min_score:
            continue
        if score >= 0.85:
            buckets["strong"].append((i, j, score))
        elif score >= 0.7:
            buckets["med"].append((i, j, score))
        else:
            buckets["weak"].append((i, j, score))
        G.add_edge(i, j, weight=score)
    pos = nx.spring_layout(G, seed=42, k=2.0 / math.sqrt(max(n, 1)), iterations=100)
    fig = plt.figure(figsize=(16, 11), facecolor="#0f1115")
    gs = fig.add_gridspec(1, 2, width_ratios=[1.35, 1.0], wspace=0.08)
    ax = fig.add_subplot(gs[0]); ax2 = fig.add_subplot(gs[1])
    ax.set_facecolor("#0f1115"); ax2.set_facecolor("#0f1115")
    def draw(edges, color, base, alpha):
        for i, j, s in edges:
            nx.draw_networkx_edges(G, pos, edgelist=[(i, j)], width=base + 2.2 * max(0, s - 0.5),
                                   edge_color=color, alpha=alpha, ax=ax)
    draw(buckets["weak"], "#64748b", 0.7, 0.3)
    draw(buckets["med"], "#fbbf24", 1.3, 0.75)
    draw(buckets["strong"], "#34d399", 2.0, 0.95)
    nx.draw_networkx_nodes(G, pos, node_color="#1e2430", edgecolors="#6ee7b7", linewidths=2.4, node_size=1600, ax=ax)
    nx.draw_networkx_labels(G, pos, labels={i: str(i) for i in G.nodes()}, font_color="#6ee7b7", font_size=12, font_weight="bold", ax=ax)
    ax.set_title("Consistency graph", color="#e6e8ec", fontsize=14, pad=10); ax.axis("off")
    handles = [mpatches.Patch(color="#34d399", label="Strong ≥ 0.85"),
               mpatches.Patch(color="#fbbf24", label="Medium ≥ 0.70"),
               mpatches.Patch(color="#64748b", label="Weak ≥ 0.55")]
    ax.legend(handles=handles, loc="lower left", facecolor="#1a1d24", edgecolor="#2a2f3a", labelcolor="#e6e8ec", fontsize=9)
    ax2.axis("off"); ax2.set_title("Atoms", color="#6ee7b7", fontsize=14, pad=10, loc="left")
    y = 0.98
    for i, a in enumerate(atoms):
        chunk = 78
        lines = [a[k:k+chunk] for k in range(0, len(a), chunk)]
        ax2.text(0.02, y, f"#{i}", color="#6ee7b7", fontsize=9, fontweight="bold", va="top", transform=ax2.transAxes, family="monospace")
        ax2.text(0.10, y, lines[0], color="#e6e8ec", fontsize=8.2, va="top", transform=ax2.transAxes)
        y -= 0.028
        for ln in lines[1:]:
            ax2.text(0.10, y, ln, color="#9aa3b2", fontsize=8.2, va="top", transform=ax2.transAxes)
            y -= 0.024
        y -= 0.012
        if y < 0.02: break
    fig.suptitle(f"Constructor Resilience — {n} atoms · {len(consistency)} edges", color="#e6e8ec", fontsize=15, y=0.98)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--min-score", type=float, default=0.55)
    args = ap.parse_args()
    print(render(args.store, args.out, args.min_score))

if __name__ == "__main__":
    main()
