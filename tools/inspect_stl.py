#!/usr/bin/env python3
"""Quick STL inspector: bounding box + three orthographic silhouettes.

用于从 CAD 网格反推 2.5D 画法所需的层板高度、板厚、开口方向等。
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

import numpy as np


def load_triangles(path: Path) -> np.ndarray:
    """Return (n, 3, 3) vertices from a binary or ASCII STL."""

    raw = path.read_bytes()
    if raw[:5].lower() == b"solid" and b"facet" in raw[:2048]:
        vertices = [
            [float(v) for v in line.split()[1:4]]
            for line in raw.decode("utf-8", "ignore").splitlines()
            if line.strip().startswith("vertex")
        ]
        return np.asarray(vertices, dtype=np.float64).reshape(-1, 3, 3)

    count = struct.unpack("<I", raw[80:84])[0]
    data = np.frombuffer(
        raw[84 : 84 + count * 50],
        dtype=np.dtype(
            [("normal", "<3f4"), ("vertices", "<9f4"), ("attr", "<u2")]
        ),
        count=count,
    )
    return data["vertices"].reshape(-1, 3, 3).astype(np.float64)


def flat_planes(
    tris: np.ndarray, axis: int
) -> list[tuple[float, float]]:
    """Rank constant-`axis` triangles by projected area: plates and shelves."""

    level = tris[:, :, axis]
    flat = np.isclose(level.max(axis=1), level.min(axis=1), atol=1e-6)
    others = [i for i in range(3) if i != axis]
    plane = tris[flat][:, :, others]
    area = 0.5 * np.abs(
        (plane[:, 1, 0] - plane[:, 0, 0]) * (plane[:, 2, 1] - plane[:, 0, 1])
        - (plane[:, 2, 0] - plane[:, 0, 0]) * (plane[:, 1, 1] - plane[:, 0, 1])
    )
    heights = np.round(level[flat][:, 0], 2)
    totals: dict[float, float] = {}
    for height, value in zip(heights, area):
        totals[float(height)] = totals.get(float(height), 0.0) + float(value)
    return sorted(totals.items(), key=lambda item: -item[1])


def clusters(
    tris: np.ndarray, axis: int, height: float, gap: float
) -> None:
    """Group the horizontal faces at one height into connected islands."""

    others = [i for i in range(3) if i != axis]
    level = tris[:, :, axis]
    selected = tris[
        np.isclose(level.max(axis=1), height, atol=0.5)
        & np.isclose(level.min(axis=1), height, atol=0.5)
    ]
    print(f"  clusters at {'xyz'[axis]}={height} ({len(selected)} faces):")
    boxes: list[list[float]] = []
    for triangle in selected[:, :, others]:
        lo = triangle.min(axis=0)
        hi = triangle.max(axis=0)
        for box in boxes:
            if (
                lo[0] <= box[2] + gap
                and hi[0] >= box[0] - gap
                and lo[1] <= box[3] + gap
                and hi[1] >= box[1] - gap
            ):
                box[0] = min(box[0], lo[0])
                box[1] = min(box[1], lo[1])
                box[2] = max(box[2], hi[0])
                box[3] = max(box[3], hi[1])
                break
        else:
            boxes.append([lo[0], lo[1], hi[0], hi[1]])
    for box in sorted(boxes, key=lambda b: (round(b[1], 1), b[0])):
        print(
            f"    {'xyz'[others[0]]}[{box[0]:8.2f},{box[2]:8.2f}] "
            f"{'xyz'[others[1]]}[{box[1]:8.2f},{box[3]:8.2f}] "
            f"size={box[2] - box[0]:7.2f}x{box[3] - box[1]:7.2f}"
        )


def slice_profile(tris: np.ndarray, axis: int, samples: int = 60) -> None:
    """Print per-slice extents along one axis to spot plates and openings."""

    centers = tris.mean(axis=1)
    lo, hi = tris[:, :, axis].min(), tris[:, :, axis].max()
    edges = np.linspace(lo, hi, samples + 1)
    others = [i for i in range(3) if i != axis]
    print(f"  slices along axis {axis} ({lo:.1f} .. {hi:.1f}):")
    for index in range(samples):
        mask = (centers[:, axis] >= edges[index]) & (
            centers[:, axis] < edges[index + 1]
        )
        if not mask.any():
            print(f"    {edges[index]:8.1f} : -")
            continue
        chunk = tris[mask]
        spans = " ".join(
            f"{'xyz'[o]}[{chunk[:, :, o].min():7.1f},"
            f"{chunk[:, :, o].max():7.1f}]"
            for o in others
        )
        print(f"    {edges[index]:8.1f} : n={mask.sum():6d} {spans}")


def render(tris: np.ndarray, out: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection

    views = (("X-Z (front)", 0, 2), ("Y-Z (side)", 1, 2), ("X-Y (top)", 0, 1))
    figure, axes = plt.subplots(1, 3, figsize=(16, 5.5))
    for axis, (name, u, v) in zip(axes, views):
        polys = tris[:, :, [u, v]]
        axis.add_collection(
            PolyCollection(
                polys,
                facecolors="#94a3b8",
                edgecolors="#0f172a",
                linewidths=0.05,
                alpha=0.55,
            )
        )
        axis.set_title(f"{name}  {name[0]}")
        axis.set_aspect("equal")
        axis.autoscale_view()
        axis.grid(alpha=0.3)
    figure.suptitle(title)
    figure.tight_layout()
    figure.savefig(out, dpi=110)
    print(f"  wrote {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stl", type=Path)
    parser.add_argument("--png", type=Path)
    parser.add_argument("--slice-axis", type=int, default=2)
    parser.add_argument("--slices", type=int, default=40)
    parser.add_argument("--mm", action="store_true", help="米 → 毫米")
    parser.add_argument(
        "--cluster-z",
        type=float,
        help="把该高度附近的水平面按 x/y 聚类，用于定位销/孔位",
    )
    parser.add_argument("--cluster-gap", type=float, default=5.0)
    args = parser.parse_args()

    tris = load_triangles(args.stl)
    if args.mm:
        tris = tris * 1000.0
    lo = tris.reshape(-1, 3).min(axis=0)
    hi = tris.reshape(-1, 3).max(axis=0)
    print(f"{args.stl.name}: {len(tris)} triangles")
    print(f"  bbox min={np.round(lo, 2)} max={np.round(hi, 2)}")
    print(f"  size   ={np.round(hi - lo, 2)}")
    print(f"  flat planes (z with most horizontal area):")
    for z, area in flat_planes(tris, args.slice_axis)[:12]:
        print(f"    {z:8.2f} : area={area:10.1f}")
    if args.cluster_z is not None:
        clusters(tris, args.slice_axis, args.cluster_z, args.cluster_gap)
    slice_profile(tris, args.slice_axis, args.slices)
    if args.png:
        render(tris, args.png, args.stl.name)


if __name__ == "__main__":
    main()
