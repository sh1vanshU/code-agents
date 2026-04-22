#!/usr/bin/env python3
"""Run graphify AST pipeline per top-level slice; outputs under graphify-out/folders/<slug>/."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Repo root = parent of scripts/
ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = ROOT / "graphify-out" / "folders"

FOLDERS = [
    "code_agents/core",
    "code_agents/chat",
    "code_agents/cli",
    "code_agents/routers",
    "code_agents/agent_system",
    "code_agents/knowledge",
    "code_agents/cicd",
    "code_agents/integrations",
    "code_agents/security",
    "code_agents/testing",
    "code_agents/observability",
    "code_agents/devops",
    "code_agents/git_ops",
    "code_agents/analysis",
    "code_agents/api",
    "code_agents/domain",
    "code_agents/reviews",
    "code_agents/tools",
    "code_agents/ui",
    "code_agents/parsers",
    "code_agents/generators",
    "code_agents/reporters",
    "code_agents/setup",
    "code_agents/webui",
    "terminal",
    "agents",
    "tests",
    "extensions/vscode",
]


def slug_for(rel: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", rel.strip("/")).strip("_") or "root"


def auto_community_labels(G, communities: dict[int, list[str]]) -> dict[int, str]:
    stop = set(
        "the a an for and or of to in on at with from by is are was were be been "
        "being as it its this that these those".split()
    )

    def short_label(text: str, max_words: int = 4) -> str:
        text = re.sub(r"[_.\\/]", " ", str(text))
        words = [
            w
            for w in re.findall(r"[A-Za-z][a-zA-Z0-9]*", text)
            if w.lower() not in stop and len(w) > 2
        ]
        if not words:
            words = text.split()[:4]
        return " ".join(words[:max_words])[:48]

    labels: dict[int, str] = {}
    for cid, members in communities.items():
        deg = [(G.degree(n), n) for n in members]
        deg.sort(reverse=True)
        top = [n for _, n in deg[:5]]
        parts = []
        for n in top:
            lab = G.nodes[n].get("label") or n
            parts.append(short_label(lab, 3))
        cnt = Counter(parts)
        best = cnt.most_common(1)[0][0] if cnt else f"Community {cid}"
        labels[cid] = best if best else f"Community {cid}"
    return labels


def run_one(rel: str) -> dict:
    from graphify.analyze import god_nodes, surprising_connections, suggest_questions
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.detect import detect
    from graphify.extract import collect_files, extract
    from graphify.export import to_html, to_json
    from graphify.report import generate

    import graphify.export as ge

    src = ROOT / rel
    if not src.is_dir():
        return {"path": rel, "error": "not a directory"}

    slug = slug_for(rel)
    out = OUT_ROOT / slug
    out.mkdir(parents=True, exist_ok=True)

    det = detect(src)
    det_path = out / ".graphify_detect.json"
    det_path.write_text(json.dumps(det))

    if det.get("total_files", 0) == 0:
        return {"path": rel, "slug": slug, "skipped": "no files"}

    code_files: list = []
    for f in det.get("files", {}).get("code", []):
        p = Path(f)
        code_files.extend(collect_files(p) if p.is_dir() else [p])

    if code_files:
        ast = extract(code_files)
    else:
        # e.g. agents/ is mostly .md + YAML — no tree-sitter code extensions — one node per doc file
        ast = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}
        all_docs: list[str] = []
        for key in ("document", "paper"):
            all_docs.extend(det.get("files", {}).get(key) or [])
        root_id = f"{slug}_corpus"
        ast["nodes"].append(
            {
                "id": root_id,
                "label": rel,
                "file_type": "document",
                "source_file": "",
                "source_location": None,
            }
        )
        for i, doc_rel in enumerate(sorted(all_docs)):
            nid = f"{slug}_f{i}"
            ast["nodes"].append(
                {
                    "id": nid,
                    "label": Path(doc_rel).name,
                    "file_type": "document",
                    "source_file": doc_rel,
                    "source_location": None,
                }
            )
            ast["edges"].append(
                {
                    "source": root_id,
                    "target": nid,
                    "relation": "includes_file",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": doc_rel,
                    "source_location": None,
                    "weight": 1.0,
                }
            )

    sem = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    seen = {n["id"] for n in ast["nodes"]}
    merged_nodes = list(ast["nodes"])
    for n in sem["nodes"]:
        if n["id"] not in seen:
            merged_nodes.append(n)
            seen.add(n["id"])
    extraction = {
        "nodes": merged_nodes,
        "edges": ast["edges"] + sem["edges"],
        "hyperedges": sem.get("hyperedges", []),
        "input_tokens": sem.get("input_tokens", 0),
        "output_tokens": sem.get("output_tokens", 0),
    }
    (out / ".graphify_extract.json").write_text(json.dumps(extraction, indent=2))

    G = build_from_json(extraction)
    n_nodes = G.number_of_nodes()
    if n_nodes == 0:
        return {"path": rel, "slug": slug, "error": "empty graph"}

    communities = cluster(G)
    cohesion = score_all(G, communities)
    tokens = {"input": extraction.get("input_tokens", 0), "output": extraction.get("output_tokens", 0)}
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    placeholder = {cid: f"Community {cid}" for cid in communities}
    questions = suggest_questions(G, communities, placeholder)

    report = generate(
        G,
        communities,
        cohesion,
        placeholder,
        gods,
        surprises,
        det,
        tokens,
        rel,
        suggested_questions=questions,
    )
    (out / "GRAPH_REPORT.md").write_text(report)

    analysis = {
        "communities": {str(k): v for k, v in communities.items()},
        "cohesion": {str(k): v for k, v in cohesion.items()},
        "gods": gods,
        "surprises": surprises,
        "questions": questions,
    }
    (out / ".graphify_analysis.json").write_text(json.dumps(analysis, indent=2))

    labels = auto_community_labels(G, communities)
    questions2 = suggest_questions(G, communities, labels)
    report2 = generate(
        G,
        communities,
        cohesion,
        labels,
        gods,
        surprises,
        det,
        tokens,
        rel,
        suggested_questions=questions2,
    )
    (out / "GRAPH_REPORT.md").write_text(report2)
    (out / ".graphify_labels.json").write_text(json.dumps({str(k): v for k, v in labels.items()}))

    to_json(G, communities, str(out / "graph.json"))

    old_max = ge.MAX_NODES_FOR_VIZ
    html_oversize = n_nodes > old_max
    if html_oversize:
        ge.MAX_NODES_FOR_VIZ = 10**9
    try:
        to_html(G, communities, str(out / "graph.html"), community_labels=labels)
    finally:
        ge.MAX_NODES_FOR_VIZ = old_max

    return {
        "path": rel,
        "slug": slug,
        "files": det.get("total_files"),
        "words": det.get("total_words"),
        "nodes": n_nodes,
        "edges": G.number_of_edges(),
        "communities": len(communities),
        "html_oversize": html_oversize,
        "out": str(out.relative_to(ROOT)),
    }


def main() -> int:
    sys.path.insert(0, str(ROOT))
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    index: list[dict] = []
    for rel in FOLDERS:
        print(f"\n=== {rel} ===", flush=True)
        try:
            r = run_one(rel)
            index.append(r)
            print(json.dumps(r, indent=2), flush=True)
        except Exception as e:
            err = {"path": rel, "error": str(e)}
            index.append(err)
            print(f"ERROR: {e}", flush=True)

    (OUT_ROOT / "index.json").write_text(json.dumps(index, indent=2))
    print(f"\nWrote {OUT_ROOT / 'index.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
