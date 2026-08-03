from __future__ import annotations

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

