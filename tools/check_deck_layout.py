"""列出台面上各设备/堆栈的占位并报告 XY 重叠，用于核对实测落位。"""

import json
from pathlib import Path

GRAPH = (
    Path(__file__).resolve().parents[1]
    / "deployment"
    / "graphs"
    / "szlab-local-debug.json"
)

graph = json.loads(GRAPH.read_text(encoding="utf-8"))
deck = next(n for n in graph["nodes"] if n["id"] == "szlab_poly_deck")
deck_cfg = deck["config"]

boxes = []
for node in graph["nodes"]:
    if node.get("type") not in ("device", "warehouse"):
        continue
    cfg = node.get("config") or {}
    pos = node.get("position") or {}
    if "size_x" not in cfg:
        continue
    boxes.append(
        (
            node["id"],
            node.get("name"),
            float(pos.get("x", 0)),
            float(pos.get("y", 0)),
            float(pos.get("z", 0)),
            float(cfg["size_x"]),
            float(cfg["size_y"]),
            float(cfg["size_z"]),
        )
    )

print(f"deck {deck_cfg['size_x']} x {deck_cfg['size_y']}")
for box in sorted(boxes, key=lambda b: (b[3], b[2])):
    node_id, name, x, y, z, sx, sy, sz = box
    outside = (
        "  ← 越界"
        if x < 0
        or y < 0
        or x + sx > deck_cfg["size_x"]
        or y + sy > deck_cfg["size_y"]
        else ""
    )
    print(
        f"  {node_id:34s} {str(name):16s} "
        f"x[{x:7.1f},{x + sx:7.1f}] y[{y:7.1f},{y + sy:7.1f}] "
        f"z[{z:6.1f},{z + sz:6.1f}]{outside}"
    )

print("\nXY 重叠：")
found = False
for i, a in enumerate(boxes):
    for b in boxes[i + 1 :]:
        ax0, ay0, ax1, ay1 = a[2], a[3], a[2] + a[5], a[3] + a[6]
        bx0, by0, bx1, by1 = b[2], b[3], b[2] + b[5], b[3] + b[6]
        dx = min(ax1, bx1) - max(ax0, bx0)
        dy = min(ay1, by1) - max(ay0, by0)
        if dx > 0 and dy > 0:
            found = True
            print(f"  {a[0]} ↔ {b[0]}  重叠 {dx:.1f} x {dy:.1f}")
if not found:
    print("  无")
