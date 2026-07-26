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
