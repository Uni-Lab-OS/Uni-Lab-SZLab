from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

PACKAGES = ("szlab_poly_studio", "ai4c_robot")


def _read_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_device_specs_and_profiles_match_current_template_schemas(repo_root: Path) -> None:
    device_schema = json.loads((repo_root / "schemas" / "device-template-v2.schema.json").read_text(encoding="utf-8"))
    profile_schema = json.loads((repo_root / "schemas" / "profile-v1.schema.json").read_text(encoding="utf-8"))
    device_validator = Draft202012Validator(device_schema)
    profile_validator = Draft202012Validator(profile_schema)

    for package_name in PACKAGES:
        spec = _read_yaml(repo_root / "specs" / f"{package_name}.yaml")
        profile = _read_yaml(repo_root / "packages" / package_name / "package.yaml")
        device_validator.validate(spec)
        profile_validator.validate(profile)


def test_shape_manifest_matches_schema_and_declares_every_station(
    repo_root: Path,
) -> None:
    schema = json.loads(
        (repo_root / "schemas" / "shape-manifest-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = _read_yaml(
        repo_root
        / "packages"
        / "szlab_poly_studio"
        / "szlab_poly_studio"
        / "shape_manifest.yaml"
    )
    Draft202012Validator(schema).validate(manifest)

    shapes_by_id = {shape["id"]: shape for shape in manifest["shapes"]}
    # 前端不再内置这些外形，缺一个就会退回实心方盒
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
    } <= set(shapes_by_id)

    # 有实测占位的设备必须带 envelope，导出脚本拿它当 size
    for shape_id in ("carousel_feeder", "gantry_pump", "stirrer_rack", "vision_cell"):
        assert len(shapes_by_id[shape_id]["envelope"]) == 3

    # 注粉瓶的 category 同时含 powder 与 reagent，必须赢过通用试剂瓶
    assert shapes_by_id["powder_container"]["priority"] > 0


def test_every_graph_category_resolves_to_a_declared_shape(repo_root: Path) -> None:
    """图里出现的每个 category 都要能查到外形，否则前端只会画个方盒。

    查表规则与前端 ``resolveShapeSpec`` 一致：精确 category 胜过子串匹配，
    同为子串匹配时先比 priority、再比 token 长度。
    """

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
        (
            repo_root
            / "packages"
            / "szlab_poly_studio"
            / "szlab_poly_studio"
            / "shape_manifest.yaml"
        ).read_text(encoding="utf-8"),
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

    # 只有主机/PLC 这类没有物理外形的节点可以不带 category
    assert {
        node["id"] for node in graph["nodes"] if not node.get("config", {}).get("category")
    } == {
        "szlab_poly_deck",
        "szlab_poly_plc",
        "s1_workstation",
        "szlab_s08_cap_station",
        "szlab_mixer_pipetting_station",
    }

    # 注粉瓶不能被通用试剂瓶抢走，烧杯/样品瓶各走各的轮廓
    assert resolve("powder_reagent") == "powder_container"
    assert resolve("liquid_reagent") == "capped_bottle"
    assert resolve("beaker") == "beaker"
    assert resolve("carousel_feeder") == "carousel_feeder"


def test_packaged_profile_copies_are_in_sync(repo_root: Path) -> None:
    for package_name in PACKAGES:
        source_spec = _read_yaml(repo_root / "specs" / f"{package_name}.yaml")
        packaged_spec = _read_yaml(repo_root / "packages" / package_name / package_name / "profile" / "device.yaml")
        assert packaged_spec == source_spec

        source_profile = _read_yaml(repo_root / "packages" / package_name / "package.yaml")
        packaged_profile = _read_yaml(repo_root / "packages" / package_name / package_name / "profile" / "package.yaml")
        assert packaged_profile == {
            **source_profile,
            "device_spec": "device.yaml",
        }


def test_profiles_load_and_expose_decorated_actions(profiles) -> None:
    assert set(profiles) == {"szlab_poly_studio", "ai4c_robot"}
    assert "szlab_mixer_stirrer.run_stirring" in profiles["szlab_poly_studio"].action_catalog
    assert "szlab_s08_cap_station.process_cap_with_sample_parts" in profiles["szlab_poly_studio"].action_catalog
    assert "AI4C_robot_arm.pick_well_plate_from_loading_rack" in profiles["ai4c_robot"].action_catalog


def test_macro_calls_use_generic_driver_method_contract(repo_root: Path) -> None:
    for package_name in PACKAGES:
        profile = _read_yaml(repo_root / "packages" / package_name / "package.yaml")
        spec = _read_yaml(repo_root / "specs" / f"{package_name}.yaml")
        assert profile["default_device_binding"]["driver_key"] == "generic_plc_macro"

        params_by_action = {
            action["id"]: {param["name"] for param in action.get("params", [])} for action in spec["actions"]
        }
        for action_id, steps in profile["driver_config"]["macros"].items():
            referenced_inputs: set[str] = set()
            for step in steps:
                assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", step["call"])
                for arg in step.get("args", []):
                    if isinstance(arg, dict) and set(arg) == {"input"}:
                        referenced_inputs.add(arg["input"])
            assert referenced_inputs <= params_by_action[action_id]
