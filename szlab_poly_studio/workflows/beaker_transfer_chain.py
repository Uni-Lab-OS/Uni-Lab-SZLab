from typing import TypedDict

from unilabos.registry.placeholder_type import ResourceSlot
from unilabos.workflow.authoring import MaterialFlowRole, material_source, resource_ref, workflow

from szlab_poly_studio.resources.materials import beaker_500ml
from szlab_poly_studio.workflows.material_transfer import s_z_lab_标准物料转运


class SZLab烧杯五工位搬运Result(TypedDict):
    beaker: ResourceSlot


@workflow(
    workflow_uuid="0a6b3005-833d-491b-9fd4-fe6545846dab",
    displayname="S03→S07→S06→S09→S04→S05 烧杯搬运",
    description=(
        "从 S3-L1B1 取烧杯，依次经 S0722、S061、BEAKER1、S041 转运，"
        "最后放到 S051；每段均使用标准物料转运并提交 OS 物料位置。"
    ),
)
def s_z_lab_烧杯五工位搬运() -> SZLab烧杯五工位搬运Result:
    """将 S03 的既有烧杯按固定五段路径线性转运到 S05。

    参数：无；物料来源（MaterialSource）在 S03 挂载范围内解析既有烧杯。
    返回：包含最终位于 S051 的烧杯物料占位符（ResourceSlot）。
    安全约束：同一烧杯身份按 S0722、S061、BEAKER1、S041、S051
    顺序传递，每段物理动作完成后才提交下一个库位（Site）位置。
    """

    # unilab:node_uuid=08f74d07-4815-56ff-9694-1283c127388b
    source_beaker = material_source(
        resource_template=beaker_500ml,
        mode="existing",
        mount=resource_ref("s3_unused_beaker"),
        material_uuid=None,
        site=None,
        slot_range=None,
        flow_role=MaterialFlowRole.PRIMARY_SAMPLE,
    )
    # unilab:node_uuid=0f1e66ac-12e9-5a36-b4e3-91b415a2c297
    beaker_at_s0722 = s_z_lab_标准物料转运(
        resource=source_beaker,
        source_site="L1B1",
        source_warehouse=resource_ref("s3_unused_beaker"),
        target_device="szlab_s07_solid_addition",
        target_site="S0722",
        target_warehouse=resource_ref("s07_process_warehouse"),
    )
    # unilab:node_uuid=68d5f0f0-8a26-5d5a-ae20-146e40793c51
    beaker_at_s06 = s_z_lab_标准物料转运(
        resource=beaker_at_s0722.resource,
        source_site="S0722",
        source_warehouse=resource_ref("s07_process_warehouse"),
        target_device="szlab_mixer_pump",
        target_site="S061",
        target_warehouse=resource_ref("s06_process_warehouse"),
    )
    # unilab:node_uuid=4499a4bc-01d8-5de5-ba8b-a289558aecc0
    beaker_at_s09 = s_z_lab_标准物料转运(
        resource=beaker_at_s06.resource,
        source_site="S061",
        source_warehouse=resource_ref("s06_process_warehouse"),
        target_device="szlab_mixer_pipetting_station",
        target_site="BEAKER1",
        target_warehouse=resource_ref("szlab_mixer_pipetting_station"),
    )
    # unilab:node_uuid=e25a0f92-dccc-577c-94fd-129861a44a8a
    beaker_at_s041 = s_z_lab_标准物料转运(
        resource=beaker_at_s09.resource,
        source_site="BEAKER1",
        source_warehouse=resource_ref("szlab_mixer_pipetting_station"),
        target_device="szlab_mixer_stirrer",
        target_site="S041",
        target_warehouse=resource_ref("s04_process_warehouse"),
    )
    # unilab:node_uuid=a2d777e4-4635-553f-85c5-4f67135868af
    beaker_at_s05 = s_z_lab_标准物料转运(
        resource=beaker_at_s041.resource,
        source_site="S041",
        source_warehouse=resource_ref("s04_process_warehouse"),
        target_device="szlab_mixer_photoshotting",
        target_site="S051",
        target_warehouse=resource_ref("s05_process_warehouse"),
    )
    return {"beaker": beaker_at_s05.resource}
