from __future__ import annotations

from pathlib import Path

from unilabos.registry.registry import Registry

SZLAB_DEVICES = {
    "s1_workstation",
    "szlab_mixer_photoshotting",
    "szlab_mixer_pipetting_station",
    "szlab_mixer_pump",
    "szlab_mixer_robot",
    "szlab_mixer_stirrer",
    "szlab_poly_plc",
    "szlab_s07_solid_addition",
    "szlab_s08_cap_station",
}

SZLAB_RESOURCES = {
    "szlab_beaker_500ml",
    "szlab_liquid_reagent_bottle_100ml",
    "szlab_pipette_tip",
    "szlab_poly_powder_container_placeholder_warehouse",
    "szlab_poly_s10_liquid_reagent_placeholder_warehouse",
    "szlab_poly_s11_used_beaker_warehouse",
    "szlab_poly_s1_loading_buffer_warehouse",
    "szlab_poly_s2_tip_placeholder_warehouse",
    "szlab_poly_s3_unused_beaker_warehouse",
    "szlab_poly_studio_deck",
    "szlab_powder_container",
    "szlab_sample_vial_250ml",
    "szlab_sample_vial_500ml",
    "szlab_tip_box",
}


def _scan(root: Path) -> tuple[set[str], set[str], Registry]:
    registry = Registry()
    registry._load_config_cache = lambda: {}
    registry._save_config_cache = lambda _cache: None
    registry._run_ast_scan(devices_dirs=[root], external_only=True)
    devices = {
        key
        for key, value in registry.device_type_registry.items()
        if Path(str(value.get("file_path") or "/")).resolve().is_relative_to(root.resolve())
    }
    resources = {
        key
        for key, value in registry.resource_type_registry.items()
        if Path(str(value.get("file_path") or "/")).resolve().is_relative_to(root.resolve())
    }
    return devices, resources, registry


def test_external_registry_contains_expected_devices_and_resources(repo_root: Path) -> None:
    szlab_root = repo_root / "szlab_poly_studio"

    szlab_devices, szlab_resources, _ = _scan(szlab_root)

    assert szlab_devices == SZLAB_DEVICES
    assert szlab_resources == SZLAB_RESOURCES


def test_action_names_are_python_authoring_safe(action_catalog: dict) -> None:
    decorated_refs = [ref for ref in action_catalog if not ref.startswith("szlab_poly_studio.")]
    assert decorated_refs
    assert not [ref for ref in decorated_refs if ".auto-" in ref]
    assert all(ref.rsplit(".", 1)[1].isidentifier() for ref in decorated_refs)
