"""End-to-end checks for the shipped examples. Run: python tests/test_examples.py"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ngm_tokens as n

CASES = [
    (ROOT / "examples" / "自动作答流程.ngm", "flowchart", 14, 13),
    (ROOT / "examples" / "uml-class.mmd", "uml-class", 6, 4),
    (ROOT / "examples" / "uml-sequence.puml", "uml-sequence", 3, 5),
    (ROOT / "examples" / "uml-state.mmd", "uml-state", 5, 6),
    (ROOT / "examples" / "uml-er.mmd", "uml-er", 3, 2),
]

for path, diagram, nodes, edges in CASES:
    graph = n.Graph(str(path), path.suffix.lstrip("."))
    n.load(path, graph)
    n.finalize(graph)
    assert graph.diagram == diagram, f"{path.name}: {graph.diagram} != {diagram}"
    assert len(graph.nodes) == nodes, f"{path.name}: {len(graph.nodes)} != {nodes}"
    assert len(graph.edges) == edges, f"{path.name}: {len(graph.edges)} != {edges}"
    print(f"PASS {path.name}: {diagram} / {nodes} nodes / {edges} edges")

for name in ("example-logic.md", "example-uml-class.md", "example-uml-sequence.md"):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "logic_check.py"), str(ROOT / "references" / name)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, f"{name} failed:\n{result.stdout}"
    tail = result.stdout.strip().splitlines()[-2:]
    print(f"PASS {name}: {' / '.join(tail)}")

print("ALL OK")
