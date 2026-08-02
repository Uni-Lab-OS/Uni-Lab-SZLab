"""Wayfinder target only：MaterialSource -> 搬运 -> 固体称量。

当前 SZLab 尚未发布本例需要的 dose_powder_with_materials，pinned OS 的 legacy
operation-tree 路径也尚未满足 D-054 的“普通并行不物化 synthetic Fork/Join”合同，因此本文件
不得登记到 package.yaml。先完成 C1、host.transfer_resource authoring、标准 robot.pick/place
和多物料投粉 Action，再通过 Catalog/round-trip/no-synthetic-join conformance gate。

本轮不实现 Cell Controller。S07 转盘/交接位在完成现场验收前由标准
robot adapter fail-closed；该文件先冻结 Workflow 参数和物料链，不声明已可自动运行。
"""

from typing import Annotated, TypedDict

from pydantic import Field
from unilabos.registry.annotations import AllowedResourceTemplates
from unilabos.registry.placeholder_type import ResourceSlot
from unilabos.workflow.authoring import (
    MaterialFlowRole,
    device,
    material_source,
    parallel,
    workflow_definition,
)

from szlab_poly_studio.devices.szlab_s07_solid_addition.device import (
    SZLabS07SolidAdditionDevice,
)
from szlab_poly_studio.resources.materials import (
    beaker_500ml,
    powder_container,
)

from .material_transfer_target import material_transfer


solid_addition: SZLabS07SolidAdditionDevice = device(
    "szlab_s07_solid_addition"
)


class S07ParallelDoseResult(TypedDict):
    beaker: Annotated[
        ResourceSlot,
        AllowedResourceTemplates(beaker_500ml),
    ]
    powder_cartridge: Annotated[
        ResourceSlot,
        AllowedResourceTemplates(powder_container),
    ]
    actual_mass_g: float


@workflow_definition(
    workflow_uuid="5e7ce142-bf5a-5d30-8666-fdf5374941f1",
    displayname="S07 双物料并行就位与投粉",
    description="粉筒和烧杯拓扑并行搬运、共享机械臂互斥、在 S07 多输入节点汇合。",
)
def s07_parallel_material_dosing(
    *,
    powder_source_warehouse: ResourceSlot,
    beaker_source_warehouse: ResourceSlot,
    solid_addition_warehouse: ResourceSlot,
    powder_source_site: str,
    powder_target_site: str,
    beaker_source_site: str,
    beaker_target_site: str,
    powder_transfer_id: str,
    beaker_transfer_id: str,
    target_mass_g: Annotated[float, Field(gt=0, le=100)] = 1.0,
) -> S07ParallelDoseResult:
    # unilab:node_uuid=f7969031-098d-52eb-9193-92e41de3f3da
    source_powder_container = material_source(
        resource_template=powder_container,
        mode="existing",
        mount=powder_source_warehouse,
        material_uuid=None,
        site=powder_source_site,
        slot_range=None,
        flow_role=MaterialFlowRole.REAGENT,
    )
    # unilab:node_uuid=af599d17-1d6c-5f34-a2f1-dc5239d1275d
    source_beaker = material_source(
        resource_template=beaker_500ml,
        mode="existing",
        mount=beaker_source_warehouse,
        material_uuid=None,
        site=beaker_source_site,
        slot_range=None,
        flow_role=MaterialFlowRole.PRIMARY_SAMPLE,
    )

    with parallel():
        # unilab:node_uuid=9f67e05d-020a-5e8d-bf86-ae812aac7c01
        powder_ready = material_transfer(
            resource=source_powder_container,
            source_warehouse=powder_source_warehouse,
            target_device=solid_addition,
            target_warehouse=solid_addition_warehouse,
            source_site=powder_source_site,
            target_site=powder_target_site,
            transfer_id=powder_transfer_id,
        )
        # unilab:node_uuid=45ffc4a3-ab9e-5805-a2f6-673c35989d2f
        beaker_ready = material_transfer(
            resource=source_beaker,
            source_warehouse=beaker_source_warehouse,
            target_device=solid_addition,
            target_warehouse=solid_addition_warehouse,
            source_site=beaker_source_site,
            target_site=beaker_target_site,
            transfer_id=beaker_transfer_id,
        )

    # 两个 required material input 直接构成 AND convergence；不创建 no-op Join。
    # unilab:node_uuid=58198f7a-eec4-5276-9bc5-5dd5b54c4b06
    dosed = solid_addition.dose_powder_with_materials(
        powder_cartridge=powder_ready.resource,
        beaker=beaker_ready.resource,
        target_mass_g=target_mass_g,
    )
    return {
        "beaker": dosed.beaker,
        "powder_cartridge": dosed.powder_cartridge,
        "actual_mass_g": dosed.actual_mass_g,
    }
