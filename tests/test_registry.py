from __future__ import annotations

from unilabos.package_manager import PackageCatalog

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
    "szlab_poly_s11_used_sample_vial_warehouse",
    "szlab_poly_s1_loading_buffer_warehouse",
    "szlab_poly_s2_tip_placeholder_warehouse",
    "szlab_poly_s3_unused_beaker_warehouse",
    "szlab_poly_s3_unused_sample_vial_warehouse",
    "szlab_poly_studio_deck",
    "szlab_powder_container",
    "szlab_s04_process_warehouse",
    "szlab_s05_process_warehouse",
    "szlab_s06_process_warehouse",
    "szlab_s07_process_warehouse",
    "szlab_sample_vial_250ml",
    "szlab_sample_vial_500ml",
    "szlab_tip_box",
}


def test_catalog_contains_expected_devices_and_resources(
    package_catalog: PackageCatalog,
) -> None:
    szlab_devices = {definition.id for definition in package_catalog.definitions.devices}
    szlab_resources = {
        definition.id for definition in package_catalog.definitions.resources
    }

    assert szlab_devices == SZLAB_DEVICES
    assert szlab_resources == SZLAB_RESOURCES


def test_action_names_are_python_authoring_safe(action_catalog: dict) -> None:
    assert action_catalog
    assert not [ref for ref in action_catalog if ".auto-" in ref]
    assert all(ref.rsplit(".", 1)[1].isidentifier() for ref in action_catalog)
