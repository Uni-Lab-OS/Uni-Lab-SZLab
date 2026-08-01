"""S07 固体投料 local UI preset 的 Python 调试流程。"""

from unilabos.workflow.authoring import device, workflow_definition

szlab_s07_solid_addition = device("szlab_s07_solid_addition")


@workflow_definition(
    workflow_id="szlab_s07_solid_addition_workflow",
    revision="python-v1",
)
def szlab_s07_solid_addition_workflow(
    cartridge_position: int = 1,
    target_weight: float = 10.0,
) -> None:
    szlab_s07_solid_addition.scan_powder_cartridges(timeout=300.0)
    szlab_s07_solid_addition.rotate_powder_cartridge_to_feed(
        position=cartridge_position,
        timeout=300.0,
    )
    szlab_s07_solid_addition.dose_powder(
        coarse_position=cartridge_position,
        fine_position=cartridge_position,
        target_weight=target_weight,
        recipe_name="default",
        params_json="",
        timeout=300.0,
    )
