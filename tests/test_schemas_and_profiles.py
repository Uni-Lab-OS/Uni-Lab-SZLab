from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


def _read_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _shape_assets(repo_root: Path) -> list[dict]:
    package_root = repo_root / "szlab_poly_studio"
    payloads = [_read_yaml(path) for path in sorted(package_root.glob("**/models/shape.yml"))]
    assert payloads
    assert all(payload.get("schema_version") == 1 for payload in payloads)
    return [payload["shape"] for payload in payloads]


def test_device_and_resource_shapes_are_split_and_schema_valid(repo_root: Path) -> None:
    schema = json.loads((repo_root / "schemas" / "shape-manifest-v1.schema.json").read_text(encoding="utf-8"))
    shapes = _shape_assets(repo_root)
    compatibility_manifest = {
        "schema_version": 1,
        "bundle": {
            "id": "szlab-poly-studio",
            "display_name": "SZLab 聚合物工作站",
            "source_namespace": "szlab",
        },
        "shapes": shapes,
    }
    Draft202012Validator(schema).validate(compatibility_manifest)

    shapes_by_id = {shape["id"]: shape for shape in shapes}
    assert {
        "carousel_feeder",
        "gantry_pump",
        "stirrer_rack",
        "vision_cell",
        "rail_robot",
        "beaker_stack",
        "reagent_stack",
        "powder_stack",
        "tip_stack",
        "tip_box",
        "powder_container",
        "sample_vial_stack",
    } == set(shapes_by_id)
    for shape_id in ("carousel_feeder", "gantry_pump", "stirrer_rack", "vision_cell"):
        assert len(shapes_by_id[shape_id]["envelope"]) == 3
    assert shapes_by_id["powder_container"]["priority"] > 0


def test_every_decorator_model_entry_is_literal_and_package_local(repo_root: Path) -> None:
    package_root = (repo_root / "szlab_poly_studio").resolve()
    resolved_assets: set[Path] = set()

    for source_path in package_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                name = decorator.func.id if isinstance(decorator.func, ast.Name) else ""
                if name not in {"device", "resource"}:
                    continue
                model_kw = next(
                    (keyword for keyword in decorator.keywords if keyword.arg == "model"),
                    None,
                )
                if model_kw is None:
                    continue
                model = ast.literal_eval(model_kw.value)
                descriptors = [model]
                if isinstance(model.get("shape"), dict):
                    descriptors.append(model["shape"])
                for descriptor in descriptors:
                    entry = descriptor.get("entry")
                    if not entry:
                        continue
                    asset = (source_path.parent / entry).resolve()
                    assert asset.is_relative_to(package_root)
                    assert asset.is_file(), f"missing model asset: {asset}"
                    resolved_assets.add(asset)

    assert resolved_assets == set(package_root.glob("**/models/shape.yml"))


def test_package_shape_categories_are_self_describing_without_an_os_bridge(
    repo_root: Path,
) -> None:
    shapes = _shape_assets(repo_root)
    by_id = {shape["id"]: shape for shape in shapes}

    def normalize(value: str) -> str:
        return value.strip().casefold().replace("-", "_").replace(" ", "_")

    def resolve(category: str) -> str | None:
        normalized = normalize(category)
        best: tuple[int, str] | None = None
        for shape in shapes:
            categories = {
                normalize(str(item["category"]))
                for item in shape.get("applies_to", [])
                if isinstance(item, dict) and item.get("category")
            }
            tokens = {
                normalize(str(item))
                for item in shape.get("category_tokens", [])
                if item
            }
            if normalized in categories:
                score = 1 << 40
            else:
                matches = [
                    int(shape.get("priority", 0)) * 1000 + len(token)
                    for token in tokens
                    if token and token in normalized
                ]
                if not matches:
                    continue
                score = max(matches)
            if best is None or score > best[0]:
                best = (score, str(shape["id"]))
        return best[1] if best else None

    assert set(by_id) == {
        "carousel_feeder",
        "gantry_pump",
        "stirrer_rack",
        "vision_cell",
        "rail_robot",
        "beaker_stack",
        "reagent_stack",
        "powder_stack",
        "tip_stack",
        "tip_box",
        "powder_container",
        "sample_vial_stack",
    }
    assert resolve("powder_reagent") == "powder_container"
    assert resolve("sample_vial_stack") == "sample_vial_stack"
    assert resolve("carousel_feeder") == "carousel_feeder"
