from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


def _read_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _profile_root(repo_root: Path) -> Path:
    return repo_root / "szlab_poly_studio" / "profiles" / "default"


def _shape_assets(repo_root: Path) -> list[dict]:
    package_root = repo_root / "szlab_poly_studio"
    payloads = [
        _read_yaml(path)
        for path in sorted(package_root.glob("**/models/shape.yml"))
    ]
    assert payloads
    assert all(payload.get("schema_version") == 1 for payload in payloads)
    return [payload["shape"] for payload in payloads]


def test_packaged_profile_matches_current_template_schemas(repo_root: Path) -> None:
    device_schema = json.loads(
        (repo_root / "schemas" / "device-template-v2.schema.json").read_text(
            encoding="utf-8"
        )
    )
    profile_schema = json.loads(
        (repo_root / "schemas" / "profile-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    profile_root = _profile_root(repo_root)
    Draft202012Validator(device_schema).validate(_read_yaml(profile_root / "device.yaml"))
    Draft202012Validator(profile_schema).validate(_read_yaml(profile_root / "package.yaml"))


def test_device_and_resource_shapes_are_split_and_schema_valid(repo_root: Path) -> None:
    schema = json.loads(
        (repo_root / "schemas" / "shape-manifest-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
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


def test_every_graph_category_resolves_to_a_declared_shape(repo_root: Path) -> None:
    from unilabos.app.local_bridge.material_shapes import (
        CORE_SHAPE_MANIFEST,
        _load_manifest_text,
        normalize_category,
    )

    shapes = _load_manifest_text(
        CORE_SHAPE_MANIFEST.read_text(encoding="utf-8"),
        fallback_bundle_id="unilabos-core",
    ).shapes
    shapes += _load_manifest_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "bundle": {"id": "szlab-poly-studio"},
                "shapes": _shape_assets(repo_root),
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        fallback_bundle_id="szlab-poly-studio",
    ).shapes

    def resolve(category: str) -> str | None:
        normalized = normalize_category(category)
        best: tuple[int, str] | None = None
        for shape in shapes:
            if normalized in shape.categories:
                score = 1 << 40
            else:
                matches = [
                    shape.priority * 1000 + len(token)
                    for token in shape.category_tokens
                    if token and token in normalized
                ]
                if not matches:
                    continue
                score = max(matches)
            if best is None or score > best[0]:
                best = (score, shape.id)
        return best[1] if best else None

    graph = json.loads(
        (repo_root / "deployment" / "graphs" / "szlab-local-debug.json").read_text(
            encoding="utf-8"
        )
    )
    unresolved = sorted(
        {
            category
            for node in graph["nodes"]
            if (category := node.get("config", {}).get("category"))
            and resolve(category) is None
        }
    )
    assert unresolved == []
    assert resolve("powder_reagent") == "powder_container"
    assert resolve("liquid_reagent") == "capped_bottle"
    assert resolve("beaker") == "beaker"
    assert resolve("carousel_feeder") == "carousel_feeder"


def test_profile_is_self_contained(repo_root: Path) -> None:
    profile_root = _profile_root(repo_root)
    profile = _read_yaml(profile_root / "package.yaml")
    assert profile["device_spec"] == "device.yaml"
    assert (profile_root / profile["device_spec"]).is_file()


def test_profile_and_decorators_contribute_to_one_action_catalog(
    profiles,
    decorated_action_catalog,
) -> None:
    assert set(profiles) == {"szlab_poly_studio"}
    assert "szlab_poly_studio.run_stirring" in profiles["szlab_poly_studio"].action_catalog
    assert "szlab_mixer_stirrer.run_stirring" in decorated_action_catalog
    assert "szlab_s08_cap_station.process_cap_with_sample_parts" in decorated_action_catalog


def test_macro_calls_use_generic_driver_method_contract(repo_root: Path) -> None:
    profile_root = _profile_root(repo_root)
    profile = _read_yaml(profile_root / "package.yaml")
    spec = _read_yaml(profile_root / "device.yaml")
    assert profile["default_device_binding"]["driver_key"] == "generic_plc_macro"

    params_by_action = {
        action["id"]: {param["name"] for param in action.get("params", [])}
        for action in spec["actions"]
    }
    for action_id, steps in profile["driver_config"]["macros"].items():
        referenced_inputs: set[str] = set()
        for step in steps:
            assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", step["call"])
            for arg in step.get("args", []):
                if isinstance(arg, dict) and set(arg) == {"input"}:
                    referenced_inputs.add(arg["input"])
        assert referenced_inputs <= params_by_action[action_id]
