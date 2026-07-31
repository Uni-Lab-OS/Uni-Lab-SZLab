"""Expose this package's 2.5D manifest in the shared frontend wire format."""

from __future__ import annotations

from copy import deepcopy
from functools import cache
from importlib.resources import files
from typing import Any

import yaml


@cache
def material_shape_items() -> tuple[dict[str, Any], ...]:
    """Load and normalize ``shape_manifest.yaml`` once per bridge process."""

    manifest_text = (
        files("szlab_poly_studio")
        .joinpath("shape_manifest.yaml")
        .read_text(encoding="utf-8")
    )
    manifest = yaml.safe_load(manifest_text)
    if not isinstance(manifest, dict):
        raise ValueError("shape_manifest.yaml must contain an object")

    bundle = manifest.get("bundle")
    bundle_id = bundle.get("id") if isinstance(bundle, dict) else None
    if not isinstance(bundle_id, str) or not bundle_id:
        raise ValueError("shape_manifest.yaml bundle.id is required")

    shapes = manifest.get("shapes")
    if not isinstance(shapes, list):
        raise ValueError("shape_manifest.yaml shapes must contain an array")

    return tuple(
        _shape_item(shape, bundle_id)
        for shape in shapes
        if isinstance(shape, dict)
    )


def _shape_item(
    shape: dict[str, Any],
    bundle_id: str,
) -> dict[str, Any]:
    applies_to = shape.get("applies_to")
    if not isinstance(applies_to, list):
        applies_to = []

    categories: list[str] = []
    category_tokens: list[str] = []
    for matcher in applies_to:
        if not isinstance(matcher, dict):
            continue
        category = matcher.get("category")
        if isinstance(category, str) and category:
            categories.append(category)
        category_token = matcher.get("category_contains")
        if isinstance(category_token, str) and category_token:
            category_tokens.append(category_token)

    shape_id = shape.get("id")
    parts = shape.get("parts")
    if not isinstance(shape_id, str) or not shape_id:
        raise ValueError("shape manifest item id is required")
    if not categories and not category_tokens:
        raise ValueError(f"shape manifest item {shape_id} has no category matcher")
    if not isinstance(parts, list) or not parts:
        raise ValueError(f"shape manifest item {shape_id} has no parts")

    item: dict[str, Any] = {
        "id": shape_id,
        "bundle": bundle_id,
        "categories": categories,
        "categoryTokens": category_tokens,
        "parts": deepcopy(parts),
    }
    display_name = shape.get("display_name")
    if isinstance(display_name, str) and display_name:
        item["displayName"] = display_name
    for key in ("priority", "envelope", "units", "shadow", "sort"):
        if key in shape:
            item[key] = deepcopy(shape[key])
    return item
