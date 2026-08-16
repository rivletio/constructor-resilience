"""Best-effort external reference extraction and markdown linkify."""
from __future__ import annotations

import re
from typing import Dict, List


def extract_references(text: str) -> List[Dict[str, str]]:
    found: List[Dict[str, str]] = []
    seen = set()

    for m in re.finditer(r"arXiv[:\s]+(\d{4}\.\d{4,5})(?:v\d+)?", text, re.I):
        aid = m.group(1)
        if aid not in seen:
            seen.add(aid)
            found.append(
                {
                    "kind": "arxiv",
                    "id": aid,
                    "label": f"arXiv:{aid}",
                    "url": f"https://arxiv.org/abs/{aid}",
                }
            )

    for m in re.finditer(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b", text):
        aid = m.group(1)
        if aid in seen:
            continue
        try:
            yymm = int(aid.split(".")[0])
        except ValueError:
            continue
        if 1500 <= yymm <= 2999:
            seen.add(aid)
            found.append(
                {
                    "kind": "arxiv",
                    "id": aid,
                    "label": f"arXiv:{aid}",
                    "url": f"https://arxiv.org/abs/{aid}",
                }
            )

    for m in re.finditer(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b", text):
        doi = m.group(1).rstrip(".")
        if doi not in seen:
            seen.add(doi)
            found.append(
                {
                    "kind": "doi",
                    "id": doi,
                    "label": f"doi:{doi}",
                    "url": f"https://doi.org/{doi}",
                }
            )

    for m in re.finditer(r"https?://[^\s<>)\]\"']+", text):
        url = m.group(0).rstrip(".,;:)")
        if url not in seen:
            seen.add(url)
            found.append({"kind": "url", "id": url, "label": url, "url": url})

    return found


def linkify_claim(text: str) -> str:
    refs = extract_references(text)
    out = text
    for r in sorted(refs, key=lambda x: -len(x["id"])):
        if r["kind"] == "arxiv":
            labeled = f"[{r['label']}]({r['url']})"
            patterns = [
                rf"arXiv[:\s]+{re.escape(r['id'])}(?:v\d+)?",
                rf"\b{re.escape(r['id'])}(?:v\d+)?\b",
            ]
            for pat in patterns:
                out2, n = re.subn(pat, labeled, out, count=1, flags=re.I)
                if n:
                    out = out2
                    break
        elif r["kind"] == "doi":
            labeled = f"[{r['label']}]({r['url']})"
            out = re.sub(re.escape(r["id"]), labeled, out, count=1)
        elif r["kind"] == "url":
            if f"]({r['url']})" not in out:
                out = out.replace(r["url"], f"[link]({r['url']})")
    return out
