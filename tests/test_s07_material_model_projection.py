from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from unilabos.app.scheduler.inventory.material_projection import (
    build_package_material_projection,
)
from unilabos.package_manager import WorkspaceSource


def test_s07_materials_publish_2_5d_shapes_and_loadable_3d_models(
    repo_root,
    package_catalog,
) -> None:
    source = WorkspaceSource(repo_root)
    projection = build_package_material_projection((source,), (package_catalog,))
    records = {
        record.id: record
        for record in package_catalog.definitions.resources
        if record.id in {"szlab_beaker_500ml", "szlab_powder_container"}
    }
    assert set(records) == {"szlab_beaker_500ml", "szlab_powder_container"}

    public_assets = {asset.public_path for asset in projection.model_assets}
    for resource_id, record in records.items():
        definition = projection.definitions[record.fqid]
        assert definition.model is not None, f"{resource_id} lacks a 3D model"
        assert definition.model["format"] == "xacro"
        assert definition.model["path"] in public_assets
        assert any(
            definition.kind in shape.get("categories", ())
            for shape in projection.shapes
        ), f"{resource_id} lacks a matching 2.5D shape"


@pytest.mark.parametrize(
    ("relative_path", "expected_translation"),
    [
        (
            "szlab_poly_studio/resources/szlab_beaker_500ml/models/resource.xacro",
            (0.043, 0.043, 0.0),
        ),
        (
            "szlab_poly_studio/resources/szlab_powder_container/models/resource.xacro",
            (0.035, 0.035, 0.0),
        ),
    ],
)
def test_s07_material_model_axis_is_centered_on_the_plr_footprint(
    repo_root,
    relative_path: str,
    expected_translation: tuple[float, float, float],
) -> None:
    root = ET.parse(repo_root / relative_path).getroot()
    joint = next(
        joint
        for joint in root.iter("joint")
        if joint.attrib["name"].endswith("device_link_joint")
    )
    origin = joint.find("origin")
    assert origin is not None
    translation = tuple(float(value) for value in origin.attrib["xyz"].split())
    assert translation == pytest.approx(expected_translation)
