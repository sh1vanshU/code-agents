---
name: dep-graph-viz
description: Dependency graph with Mermaid, Graphviz DOT, and ASCII visualization output
tags: [code-understanding, visualization, dependencies]
---

# Dependency Graph Visualizer

Build and visualize module dependency graphs in multiple formats.

## Workflow

1. Scan all source files (Python, Java, JS/TS)
2. Build import/dependency graph
3. Generate visualization in chosen format
4. Detect circular dependencies

## Usage

```
/dep-graph stream
/dep-graph stream --mermaid
/dep-graph config --dot
/dep-graph backend --depth 5
```

## Output Formats
- **ASCII** (default): Box-drawing character tree
- **Mermaid**: Copy-paste into GitHub, Notion, or any Mermaid renderer
- **DOT**: For Graphviz rendering (svg, png)

## Analysis Includes
- Outgoing dependencies (what this module uses)
- Incoming dependencies (what uses this module)
- Circular dependency detection
