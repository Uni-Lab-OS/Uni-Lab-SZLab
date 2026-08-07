from unilabos.workflow.authoring import device, workflow_definition, workflow_output

from szlab_poly_studio.devices.szlab_s07_solid_addition.device import (
    SZLabS07SolidAdditionDevice,
)

szlab_s07_solid_addition: SZLabS07SolidAdditionDevice = device("szlab_s07_solid_addition")


@workflow_definition(
    workflow_uuid="b1370434-7eb7-553a-ac93-b25f3b3ef742",
    displayname="S07 固体投料调试",
)
def szlab_s07_solid_addition_workflow(
    *,
    cartridge_position: int = 1,
    target_weight: float = 10.0,
):
    # unilab:node_uuid=8f12aaee-28d9-5688-90f9-d02827c93a07
    scanned = szlab_s07_solid_addition.scan_powder_cartridges(timeout=300.0)  # noqa: F841
    # unilab:node_uuid=b5c96f65-75c2-504c-86b9-c18bc2bf138c
    rotated = szlab_s07_solid_addition.rotate_powder_cartridge_to_feed(  # noqa: F841
        position=cartridge_position,
        timeout=300.0,
    )
    # unilab:node_uuid=2ee5cc4d-6e1b-57f9-8a7b-6721ec5640b5
    dosed = szlab_s07_solid_addition.dose_powder(  # noqa: F841
        coarse_position=cartridge_position,
        fine_position=cartridge_position,
        target_weight=target_weight,
        recipe_name="default",
        params_json="",
        timeout=300.0,
    )
    return workflow_output()
