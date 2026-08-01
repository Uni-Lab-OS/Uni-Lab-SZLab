"""Expose decorator-owned 2.5D assets in the legacy frontend wire format."""

from __future__ import annotations

from copy import deepcopy
from functools import cache
from importlib.resources import files
from importlib.resources.abc import Traversable
from typing import Any

import yaml

_BUNDLE_ID = "szlab-poly-studio"
_SHAPE_FILENAME = "shape.yml"


@cache
def material_shape_items() -> tuple[dict[str, Any], ...]:
    """Load split ``models/shape.yml`` assets once per bridge process.

    This adapter exists only for the current local bridge endpoint. Model
    ownership and discovery remain declared by ``@device``/``@resource``;
    PackageCatalog will replace this compatibility projection.
    """

    items_by_id: dict[str, dict[str, Any]] = {}
    for shape_file in _iter_shape_files(files("szlab_poly_studio")):
        payload = yaml.safe_load(shape_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError(f"invalid shape asset: {shape_file}")
        shape = payload.get("shape")
        if not isinstance(shape, dict):
            raise ValueError(f"shape asset has no shape object: {shape_file}")
        item = _shape_item(shape, _BUNDLE_ID)
        shape_id = str(item["id"])
        existing = items_by_id.get(shape_id)
        if existing is not None and existing != item:
            raise ValueError(f"conflicting decorator-owned shape id: {shape_id}")
        items_by_id[shape_id] = item

    return tuple(items_by_id.values())


def _iter_shape_files(root: Traversable):
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if child.is_dir():
            yield from _iter_shape_files(child)
        elif child.name == _SHAPE_FILENAME and root.name == "models":
            yield child


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
